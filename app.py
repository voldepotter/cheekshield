"""CheekShield AI — Flask entry point.

Serves static files and API routes only. All engine access goes through
adapter/engine_adapter.py.
"""

import io
import logging
import os
import time
from collections import defaultdict

from flask import (
    Flask,
    jsonify,
    request,
    send_from_directory,
)

import config
from adapter import engine_adapter

# -- Logging --
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(name)s %(levelname)s %(message)s",
)
logger = logging.getLogger("cheekshield")

# -- App --
app = Flask(
    __name__,
    static_folder="static",
    static_url_path="/static",
)
app.config["MAX_CONTENT_LENGTH"] = config.MAX_CONTENT_LENGTH

# -- In-memory rate limiter --
_rate_store = defaultdict(list)   # ip → list of timestamps
_RATE_WINDOW = 60                 # seconds


def _rate_limit_check():
    """Return True if the request should be rate-limited."""
    ip = request.remote_addr or "unknown"
    now = time.time()
    window_start = now - _RATE_WINDOW
    # Prune old entries
    _rate_store[ip] = [t for t in _rate_store[ip] if t > window_start]
    if len(_rate_store[ip]) >= config.RATE_LIMIT_PER_MINUTE:
        return True
    _rate_store[ip].append(now)
    return False


# -- Security headers (after every response) --

@app.after_request
def add_security_headers(response):
    """Add CSP and other security headers."""
    response.headers["Content-Security-Policy"] = (
        "default-src 'self'; "
        "img-src 'self' data:; "
        "style-src 'self'; "
        "script-src 'self'"
    )
    response.headers["X-Content-Type-Options"] = "nosniff"
    response.headers["Referrer-Policy"] = "no-referrer"
    response.headers["X-Frame-Options"] = "DENY"
    if request.path.startswith("/api/analyze"):
        response.headers["Cache-Control"] = "no-store"
    return response


# -- Error helper --

def api_error(code, message, http_status=400):
    """Return a standardized API error response."""
    return jsonify({"error": {"code": code, "message": message}}), http_status


# -- Serve index.html at root --

@app.route("/")
def index():
    return send_from_directory(app.static_folder, "index.html")


@app.route("/<path:path>")
def static_proxy(path):
    """Serve static files from the root path as well (e.g. /css/..., /js/...)."""
    file_path = os.path.join(app.static_folder, path)
    if os.path.exists(file_path) and os.path.isfile(file_path):
        return send_from_directory(app.static_folder, path)
    return api_error("not_found", "Not found", 404)


# -- API routes --

@app.route("/api/health")
def api_health():
    return jsonify(engine_adapter.get_health())


@app.route("/api/model")
def api_model():
    info = engine_adapter.get_model_info()
    if info is None:
        return api_error(
            "model_missing",
            "The model is not loaded. Put the trained model in "
            "`outputs/model/` (it must contain `meta.json`) and restart "
            "the server.",
            503,
        )
    return jsonify(info)


@app.route("/api/samples")
def api_samples():
    """List available sample inputs."""
    samples_dir = os.path.join(config.BASE_DIR, "samples")
    samples = []

    # Text samples
    for fname, label, expected in [
        ("text_deceptive.txt", "Deceptive text", "deceptive"),
        ("text_clean.txt", "Clean text", "clean"),
    ]:
        path = os.path.join(samples_dir, fname)
        if os.path.isfile(path):
            with open(path, "r", encoding="utf-8") as f:
                content = f.read()
            samples.append({
                "id": fname.replace(".txt", ""),
                "label": label,
                "mode": "text",
                "expected": expected,
                "content": content,
            })

    # HTML samples
    for fname, label, expected in [
        ("html_deceptive.html", "Deceptive HTML", "deceptive"),
        ("html_clean.html", "Clean HTML", "clean"),
    ]:
        path = os.path.join(samples_dir, fname)
        if os.path.isfile(path):
            with open(path, "r", encoding="utf-8") as f:
                content = f.read()
            samples.append({
                "id": fname.replace(".html", ""),
                "label": label,
                "mode": "html",
                "expected": expected,
                "content": content,
            })

    # Screenshot samples (served as static files; just metadata here)
    for fname, label, expected in [
        ("screenshot_deceptive.png", "Deceptive screenshot", "deceptive"),
        ("screenshot_clean.png", "Clean screenshot", "clean"),
    ]:
        path = os.path.join(samples_dir, fname)
        if os.path.isfile(path):
            samples.append({
                "id": fname.rsplit(".", 1)[0],
                "label": label,
                "mode": "screenshot",
                "expected": expected,
                "file": f"/static/samples/{fname}",
            })

    return jsonify(samples)

from bs4 import BeautifulSoup, Comment

def _slim_html(html: str) -> str:
    soup = BeautifulSoup(html, "html.parser")
    for tag in soup(["script", "style", "svg", "noscript", "iframe", "canvas", "template"]):
        tag.decompose()
    for c in soup.find_all(string=lambda s: isinstance(s, Comment)):
        c.extract()
    for el in soup.find_all(["img", "source"]):
        for attr in ("src", "srcset"):
            if str(el.get(attr, "")).startswith("data:"):
                del el[attr]
    return str(soup)


@app.route("/api/analyze", methods=["POST"])
def api_analyze():
    """Run the engine on user input and return normalized results."""
    # Rate limit
    if _rate_limit_check():
        return api_error(
            "rate_limit",
            f"Too many requests. Limit is {config.RATE_LIMIT_PER_MINUTE} "
            f"per minute. Wait a moment and try again.",
            429,
        )

    content_type = request.content_type or ""

    # -- Screenshot mode (multipart) --
    if "multipart" in content_type:
        return _handle_screenshot()

    # -- Text / HTML mode (JSON) --
    try:
        body = request.get_json(force=True)
    except Exception:
        return api_error("bad_input", "Request body must be valid JSON.")

    if not body or not isinstance(body, dict):
        return api_error("bad_input", "Request body must be a JSON object.")

    mode = body.get("mode")
    content = body.get("content", "")

    if mode not in ("text", "html"):
        return api_error(
            "bad_input",
            "Field 'mode' must be 'text', 'html', or use multipart for screenshots.",
        )

    if not content or not content.strip():
        return api_error("bad_input", "Field 'content' is empty.")

    # Size limits
    if mode == "text" and len(content) > config.MAX_TEXT_CHARS:
        return api_error(
            "too_large",
            f"Text is {len(content):,} characters. "
            f"Maximum is {config.MAX_TEXT_CHARS:,}. Shorten the input.",
        )

    if mode == "html" and len(content.encode("utf-8")) > config.MAX_HTML_BYTES:
        size_kb = len(content.encode("utf-8")) // 1024
        limit_kb = config.MAX_HTML_BYTES // 1024
        return api_error(
            "too_large",
            f"HTML is {size_kb} KB. Maximum is {limit_kb} KB. "
            f"Remove scripts, images and stylesheets.",
        )

    # Run analysis
    try:
        if mode == "html":
            content = _slim_html(content)
        result = engine_adapter.analyze(mode, content)
        return jsonify(result)
    except RuntimeError as exc:
        if config.DEMO_REPLAY:
            try:
                from adapter import mock_engine
                from adapter.normalize import normalize_findings, normalize_summary
                from adapter.exposure import compute_exposure
                raw_findings = mock_engine.predict([content], "", explain=True, surface=mode)
                findings, _ = normalize_findings(raw_findings)
                summary = normalize_summary(mock_engine.summarize_findings(raw_findings), findings)
                exp = compute_exposure(findings)
                return jsonify({
                    "api_version": "1",
                    "mode": mode,
                    "findings": findings,
                    "summary": summary,
                    "exposure": exp,
                    "elapsed_ms": 120,
                    "_isSavedResult": True,
                })
            except Exception as e:
                logger.error("DEMO REPLAY FAILED: %s", e)
                pass
        return api_error("model_missing", str(exc), 503)
    except Exception as exc:
        if config.DEMO_REPLAY:
            try:
                from adapter import mock_engine
                from adapter.normalize import normalize_findings, normalize_summary
                from adapter.exposure import compute_exposure
                raw_findings = mock_engine.predict([content], "", explain=True, surface=mode)
                findings, _ = normalize_findings(raw_findings)
                summary = normalize_summary(mock_engine.summarize_findings(raw_findings), findings)
                exp = compute_exposure(findings)
                return jsonify({
                    "api_version": "1",
                    "mode": mode,
                    "findings": findings,
                    "summary": summary,
                    "exposure": exp,
                    "elapsed_ms": 120,
                    "_isSavedResult": True,
                })
            except Exception as e:
                logger.error("DEMO REPLAY FAILED: %s", e)
                pass
        logger.exception("Analysis failed")
        return api_error("internal", "Analysis failed unexpectedly. Try again.", 500)


def _handle_screenshot():
    """Handle multipart screenshot upload."""
    mode = request.form.get("mode")
    if mode != "screenshot":
        return api_error("bad_input", "Multipart requests must have mode=screenshot.")

    if "file" not in request.files:
        return api_error("bad_input", "No file uploaded. Attach an image.")

    file = request.files["file"]
    if not file.filename:
        return api_error("bad_input", "No file selected.")

    # Read into memory (never write to disk — privacy rule G)
    file_bytes = file.read()

    if len(file_bytes) > config.MAX_IMAGE_BYTES:
        size_mb = len(file_bytes) / (1024 * 1024)
        limit_mb = config.MAX_IMAGE_BYTES / (1024 * 1024)
        return api_error(
            "too_large",
            f"Image is {size_mb:.1f} MB. Maximum is {limit_mb:.0f} MB.",
        )

    # Validate image type with Pillow (not file extension)
    try:
        from PIL import Image
        # Guard against decompression bombs
        Image.MAX_IMAGE_PIXELS = 100_000_000
        img = Image.open(io.BytesIO(file_bytes))
        img.verify()  # check integrity

        # Re-open after verify (verify closes the file)
        img = Image.open(io.BytesIO(file_bytes))
        mime = Image.MIME.get(img.format, "")
        if mime not in config.ALLOWED_IMAGE_TYPES:
            return api_error(
                "unsupported_type",
                "That file is not a PNG, JPEG or WEBP image.",
            )

        # Convert to RGB numpy array
        import numpy as np
        img_rgb = img.convert("RGB")
        image_np = np.array(img_rgb, dtype=np.uint8)

    except Exception:
        return api_error(
            "unsupported_type",
            "That file is not a PNG, JPEG or WEBP image.",
        )

    # Check OCR availability
    if not engine_adapter.get_health().get("ocr_ready", False):
        return api_error(
            "ocr_unavailable",
            "OCR engine is not available on this server. Text and HTML analysis remain operational.",
            503,
        )

    # Run analysis
    try:
        result = engine_adapter.analyze("screenshot", None, image_np=image_np)
        return jsonify(result)
    except RuntimeError as exc:
        if config.DEMO_REPLAY:
            try:
                from adapter import mock_engine
                from adapter.normalize import normalize_findings, normalize_summary
                from adapter.exposure import compute_exposure
                raw_findings = mock_engine.analyze_screenshot(image_np, "")
                findings, _ = normalize_findings(raw_findings)
                summary = normalize_summary(mock_engine.summarize_findings(raw_findings), findings)
                exp = compute_exposure(findings)
                return jsonify({
                    "api_version": "1",
                    "mode": "screenshot",
                    "findings": findings,
                    "summary": summary,
                    "exposure": exp,
                    "elapsed_ms": 150,
                    "_isSavedResult": True,
                })
            except Exception as e:
                logger.error("DEMO REPLAY FAILED: %s", e)
                pass
        return api_error("model_missing", str(exc), 503)
    except Exception as exc:
        if config.DEMO_REPLAY:
            try:
                from adapter import mock_engine
                from adapter.normalize import normalize_findings, normalize_summary
                from adapter.exposure import compute_exposure
                raw_findings = mock_engine.analyze_screenshot(image_np, "")
                findings, _ = normalize_findings(raw_findings)
                summary = normalize_summary(mock_engine.summarize_findings(raw_findings), findings)
                exp = compute_exposure(findings)
                return jsonify({
                    "api_version": "1",
                    "mode": "screenshot",
                    "findings": findings,
                    "summary": summary,
                    "exposure": exp,
                    "elapsed_ms": 150,
                    "_isSavedResult": True,
                })
            except Exception as e:
                logger.error("DEMO REPLAY FAILED: %s", e)
                pass
        logger.exception("Screenshot analysis failed")
        return api_error("internal", "Analysis failed unexpectedly. Try again.", 500)


@app.route("/api/admin/reload-model", methods=["POST"])
def api_reload_model():
    """Reload the engine module and model. Local-only or requires ADMIN_TOKEN."""
    # Check authorization
    remote = request.remote_addr or ""
    is_local = remote in ("127.0.0.1", "::1", "localhost")

    if not is_local:
        token = request.headers.get("Authorization", "").replace("Bearer ", "")
        if not config.ADMIN_TOKEN or token != config.ADMIN_TOKEN:
            return api_error("unauthorized", "Admin access required.", 403)

    result = engine_adapter.reload_engine()
    status_code = 200 if result["status"] == "ok" else 500
    return jsonify(result), status_code


# -- Serve sample screenshots as static files --

@app.route("/static/samples/<path:filename>")
def serve_sample(filename):
    samples_dir = os.path.join(config.BASE_DIR, "samples")
    return send_from_directory(samples_dir, filename)


# -- Startup --

def log_startup_banner():
    """Log startup configuration: engine mode, absolute model dir, and whether meta.json was found."""
    meta_path = os.path.join(config.MODEL_DIR, "meta.json")
    meta_found = os.path.isfile(meta_path)
    engine_mode = "mock" if config.MOCK_MODE else "real"
    logger.info(
        "CheekShield startup: engine=%s, model_dir=%s, meta.json=%s",
        engine_mode,
        config.MODEL_DIR,
        "found" if meta_found else "not found",
    )


def create_app():
    """Factory for testing and WSGI servers."""
    log_startup_banner()
    engine_adapter.start_warmup()
    return app


if __name__ == "__main__":
    log_startup_banner()
    engine_adapter.start_warmup()
    app.run(
        host="0.0.0.0",  
        port=int(os.environ.get("PORT", 5000)),
        debug=os.environ.get("FLASK_DEBUG", "0") == "1",
        threaded=True,
    )


