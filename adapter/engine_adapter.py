"""Engine adapter — the ONLY file that imports the engine.

Responsibilities:
- Global lock around engine calls (shared torch model and OCR reader).
- Warm-up thread at startup.
- Mode dispatch (text, html, screenshot).
- mtime-based hot reload of the model.
- Fail-fast engine check at startup.
- Text mode: split into lines, dedup, cap at 300, call predict,
  then detect_countdown_timers on unflagged Urgency lines.
"""

import importlib
import json
import logging
import os
import re
import threading
import time
from datetime import datetime, timezone

import config
from adapter.normalize import normalize_findings, normalize_summary
from adapter.exposure import compute_exposure

logger = logging.getLogger("cheekshield.adapter")

# -- Global state --
_lock = threading.Lock()
_engine = None
_model_meta = None
_model_loaded_at = None
_model_mtime = 0.0      # mtime of meta.json for hot-reload detection
_warming_up = True
_engine_error = None
_ocr_ready = False

# Required engine functions (fail fast if missing)
_REQUIRED_FUNCTIONS = [
    "predict",
    "audit_html_dom",
    "analyze_screenshot",
    "summarize_findings",
    "detect_countdown_timers",
    "load_trained_bundle",
]


def _get_meta_path():
    """Absolute path to meta.json in the model directory."""
    return os.path.join(config.MODEL_DIR, "meta.json")


def _load_engine_module():
    """Import the engine module (real or mock)."""
    global _engine
    if config.MOCK_MODE:
        from adapter import mock_engine
        _engine = mock_engine
        logger.info("Loaded mock engine (CHEEK_MOCK=1)")
    else:
        _engine = importlib.import_module(config.ENGINE_MODULE)
        logger.info("Loaded engine module: %s", config.ENGINE_MODULE)


def _check_required_functions():
    """Fail fast if the engine lacks any required function."""
    missing = [fn for fn in _REQUIRED_FUNCTIONS if not hasattr(_engine, fn)]
    if missing:
        msg = (
            f"Engine module is missing required function(s): {', '.join(missing)}. "
            f"Check that {config.ENGINE_MODULE} exposes: {', '.join(_REQUIRED_FUNCTIONS)}"
        )
        raise RuntimeError(msg)


def _read_meta():
    """Read meta.json and return (dict, mtime). Returns (None, 0) on failure."""
    path = _get_meta_path()
    try:
        mtime = os.path.getmtime(path)
        with open(path, "r", encoding="utf-8-sig") as f:
            return json.load(f), mtime
    except FileNotFoundError:
        if config.MOCK_MODE:
            from adapter.mock_engine import get_mock_meta
            return get_mock_meta(), 0.0
        return None, 0.0
    except Exception as exc:
        logger.warning("Failed to read meta.json: %s", exc)
        return None, 0.0


def _do_warmup():
    """Warm up the model on a background thread."""
    global _warming_up, _model_meta, _model_loaded_at, _model_mtime
    global _engine_error, _ocr_ready

    try:
        _load_engine_module()
        _check_required_functions()

        with _lock:
            model_dir = os.path.abspath(config.MODEL_DIR)
            _engine.load_trained_bundle(model_dir)

            # Read meta
            meta, mtime = _read_meta()
            _model_meta = meta
            _model_mtime = mtime
            _model_loaded_at = datetime.now(timezone.utc).isoformat()

            # Warm predict with a tiny input
            _engine.predict(["test"], model_dir, explain=False, surface="text")

            # Check OCR availability
            if config.MOCK_MODE:
                _ocr_ready = True
            else:
                try:
                    import easyocr
                    _ocr_ready = True
                except ImportError:
                    _ocr_ready = False

        logger.info("Model warm-up complete (ocr_ready=%s)", _ocr_ready)
        _warming_up = False

    except Exception as exc:
        _engine_error = str(exc)
        _warming_up = False
        logger.error("Warm-up failed: %s", exc)


def start_warmup():
    """Start the background warm-up thread. Called once at app startup."""
    t = threading.Thread(target=_do_warmup, daemon=True, name="cheek-warmup")
    t.start()


def _check_hot_reload():
    """Check if meta.json or weights have changed; if so, reload.
    Must be called with _lock held."""
    global _model_meta, _model_mtime, _model_loaded_at

    meta_path = _get_meta_path()
    try:
        current_mtime = os.path.getmtime(meta_path)
    except FileNotFoundError:
        return  # no meta.json, nothing to reload

    if current_mtime <= _model_mtime:
        return  # unchanged

    if _engine is None:
        _load_engine_module()
    if _engine is None:
        return

    logger.info("meta.json changed (mtime %s → %s), attempting hot reload",
                _model_mtime, current_mtime)

    model_dir = os.path.abspath(config.MODEL_DIR)

    # Validate the new bundle in a temporary load
    try:
        new_meta, _ = _read_meta()
        if not new_meta or "classes" not in new_meta:
            logger.warning("New meta.json invalid (missing 'classes'), keeping old model")
            return

        # Test predict with the new bundle
        _engine.predict(["validation test"], model_dir, explain=False, surface="text")

        # Clear only model entries in the cache, never _OCR_READER
        if hasattr(_engine, "_MODEL_CACHE"):
            keys_to_clear = [k for k in _engine._MODEL_CACHE if k != "_OCR_READER"]
            for k in keys_to_clear:
                del _engine._MODEL_CACHE[k]

        # Reload the bundle
        _engine.load_trained_bundle(model_dir)

        _model_meta = new_meta
        _model_mtime = current_mtime
        _model_loaded_at = datetime.now(timezone.utc).isoformat()
        logger.info("Hot reload successful")

    except Exception as exc:
        logger.warning("Hot reload failed, keeping old model: %s", exc)


def reload_engine():
    """Reload the engine module (for /api/admin/reload-model)."""
    global _engine, _model_meta, _model_loaded_at, _model_mtime, _engine_error

    with _lock:
        try:
            if not config.MOCK_MODE:
                importlib.reload(_engine)
            _check_required_functions()

            model_dir = os.path.abspath(config.MODEL_DIR)
            _engine.load_trained_bundle(model_dir)

            meta, mtime = _read_meta()
            _model_meta = meta
            _model_mtime = mtime
            _model_loaded_at = datetime.now(timezone.utc).isoformat()
            _engine_error = None

            logger.info("Engine reloaded successfully")
            return {"status": "ok", "message": "Model reloaded."}

        except Exception as exc:
            _engine_error = str(exc)
            logger.error("Engine reload failed: %s", exc)
            return {"status": "error", "message": str(exc)}


# -- Text splitting for plain-text mode (Section 4 point 7) --

def _split_text_to_lines(text):
    """Split text into lines, split long lines into sentences, dedup, cap at 300."""
    raw_lines = text.strip().splitlines()

    lines = []
    for line in raw_lines:
        line = line.strip()
        if not line:
            continue
        # Split long lines (>200 chars) into sentences
        if len(line) > 200:
            sentences = re.split(r'(?<=[.!?])\s+', line)
            lines.extend(s.strip() for s in sentences if s.strip())
        else:
            lines.append(line)

    # Deduplicate while preserving order
    seen = set()
    unique = []
    for line in lines:
        key = line.lower().strip()
        if key not in seen:
            seen.add(key)
            unique.append(line)

    # Cap at MAX_TEXT_LINES
    return unique[:config.MAX_TEXT_LINES]


# -- Main analysis function --

def analyze(mode, content, image_np=None):
    """Run the engine on the given input and return the full API v1 response.

    Args:
        mode: 'text', 'html', or 'screenshot'
        content: str for text/html, ignored for screenshot
        image_np: RGB uint8 numpy array (H,W,3) for screenshot mode

    Returns:
        dict matching the POST /api/analyze response shape from Section 5.2
    """
    if _engine is None:
        raise RuntimeError("Engine not loaded. Is the server still warming up?")

    start = time.monotonic()
    model_dir = os.path.abspath(config.MODEL_DIR)
    annotated_data = None
    screenshot_info = None
    warnings_list = []

    with _lock:
        _check_hot_reload()

        try:
            if mode == "text":
                raw_findings = _analyze_text(content, model_dir)
            elif mode == "html":
                raw_findings = _analyze_html(content, model_dir)
            elif mode == "screenshot":
                raw_findings, annotated_data, screenshot_info = _analyze_screenshot(
                    image_np, model_dir
                )
            else:
                raise ValueError(f"Unknown mode: {mode}")

            # Get engine summary
            raw_summary = _engine.summarize_findings(raw_findings)

        except Exception as exc:
            logger.error("Engine analysis failed: %s", exc)
            raise

    # Normalize (outside lock — pure functions)
    elapsed_ms = round((time.monotonic() - start) * 1000)

    normalized, norm_warnings = normalize_findings(raw_findings)
    warnings_list.extend(norm_warnings)

    summary = normalize_summary(raw_summary, normalized)
    exposure = compute_exposure(normalized, summary_status=summary.get("status"))

    import uuid
    response = {
        "api_version": "1",
        "request_id": str(uuid.uuid4()),
        "mode": mode,
        "elapsed_ms": elapsed_ms,
        "model": {
            "name": "DistilBERT",
            "loaded_at": _model_loaded_at,
        },
        "summary": summary,
        "exposure": exposure,
        "findings": normalized,
        "warnings": warnings_list,
    }

    if screenshot_info:
        response["screenshot"] = screenshot_info
    if annotated_data:
        response["screenshot"]["annotated"] = annotated_data

    return response


def _analyze_text(text, model_dir):
    """Text mode: split → predict → timer detection on unflagged Urgency lines."""
    lines = _split_text_to_lines(text)
    if not lines:
        return []

    findings = _engine.predict(
        lines, model_dir, explain=True, surface="text", gate=True
    )

    # Detect countdown timers on lines not already flagged as Urgency
    flagged_urgency_texts = {
        f["text"]
        for f in findings
        if f.get("category") == "Urgency" and f.get("is_dark_pattern")
    }

    timer_candidates = [
        {"text": line}
        for line in lines
        if line not in flagged_urgency_texts
    ]

    if timer_candidates:
        timer_findings = _engine.detect_countdown_timers(timer_candidates)
        findings.extend(timer_findings)

    return findings


def _analyze_html(html, model_dir):
    """HTML mode: pass directly to audit_html_dom."""
    return _engine.audit_html_dom(html, model_dir)


def _analyze_screenshot(image_np, model_dir):
    """Screenshot mode: call analyze_screenshot, encode annotated as data URL."""
    import io
    import base64
    from PIL import Image

    annotated_np, findings = _engine.analyze_screenshot(image_np, model_dir)

    # Encode annotated image as JPEG data URL (quality 88)
    h, w = annotated_np.shape[:2]
    img = Image.fromarray(annotated_np)
    buf = io.BytesIO()
    img.save(buf, format="JPEG", quality=88)
    b64 = base64.b64encode(buf.getvalue()).decode("ascii")
    data_url = f"data:image/jpeg;base64,{b64}"

    screenshot_info = {
        "width": w,
        "height": h,
    }

    return findings, data_url, screenshot_info


# -- Info accessors (for routes, no lock needed for reads) --

def get_health():
    """Return health status dict for /api/health."""
    if _engine_error and not _warming_up:
        is_missing = "model" in _engine_error.lower() or "meta.json" in _engine_error.lower()
        status = "model_missing" if is_missing else "error"
        msg = _engine_error
    elif _warming_up:
        status = "warming"
        msg = "Model is warming up, the first audit can take longer."
    elif _model_meta is None and not config.MOCK_MODE:
        status = "model_missing"
        msg = "The model is not loaded. Put the trained model in `outputs/model/` (it must contain `meta.json`) and restart the server."
    else:
        status = "ready"
        msg = None

    return {
        "status": status,
        "engine": "mock" if config.MOCK_MODE else "real",
        "model_loaded": _model_meta is not None and not _warming_up,
        "ocr_ready": _ocr_ready,
        "api_version": "1",
        "demo_replay": config.DEMO_REPLAY,
        "message": msg,
    }


def get_model_info():
    """Return model info dict for /api/model, derived from meta.json."""
    with _lock:
        _check_hot_reload()

    if _model_meta is None:
        return None

    meta = _model_meta
    classes = meta.get("classes", [])

    # Per-class metrics from test_report
    test_report = meta.get("test_report", {})
    per_class = {}
    for cls in classes:
        if cls in test_report:
            entry = test_report[cls]
            per_class[cls] = {
                "precision": entry.get("precision", 0),
                "recall": entry.get("recall", 0),
                "f1": entry.get("f1-score", 0),
                "support": entry.get("support", 0),
            }

    # Macro F1
    macro = test_report.get("macro avg", {})
    macro_f1 = macro.get("f1-score", 0)

    # Binary report
    binary = meta.get("binary_report_tuned") or meta.get("binary_report")

    return {
        "name": "DistilBERT",
        "dir_label": os.path.basename(config.MODEL_DIR),
        "loaded_at": _model_loaded_at,
        "classes": classes,
        "temperature": meta.get("temperature"),
        "dark_threshold": meta.get("dark_threshold"),
        "macro_f1": macro_f1,
        "per_class": per_class,
        "binary": binary,
        "confusion_matrix": meta.get("confusion_matrix"),
        "limitations": config.LIMITATIONS,
    }
