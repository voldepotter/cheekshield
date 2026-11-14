"""CheekShield AI — Preflight verification script.

Prints a PASS/FAIL checklist for:
1. Engine file presence and required function exports.
2. Model bundle files (meta.json, weights, tokenizer) in outputs/model/.
3. Required Python dependencies import.
4. EasyOCR weights presence (with download fix command).
5. Port availability.

Each FAIL line states the exact fix.
Does NOT load the full model unless files are present.
"""

import ast
import os
import socket
import sys

# Ensure project root is in sys.path
PROJECT_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)

try:
    import config
    MODEL_DIR = config.MODEL_DIR
except Exception:
    MODEL_DIR = os.path.join(PROJECT_ROOT, "outputs", "model")

REQUIRED_ENGINE_FUNCS = [
    "predict",
    "audit_html_dom",
    "analyze_screenshot",
    "summarize_findings",
    "detect_countdown_timers",
    "load_trained_bundle",
]

REQUIRED_PACKAGES = [
    ("flask", "Flask web framework"),
    ("torch", "PyTorch deep learning"),
    ("transformers", "Hugging Face Transformers"),
    ("easyocr", "EasyOCR text detection & recognition"),
    ("cv2", "OpenCV image processing (opencv-python-headless)"),
    ("bs4", "BeautifulSoup4 HTML parser"),
    ("PIL", "Pillow image library"),
    ("sklearn", "scikit-learn metrics & classification"),
    ("pandas", "Pandas data analysis"),
]


def check_engine():
    """Check engine/darkpattern_engine.py presence and exported functions via AST."""
    engine_path = os.path.join(PROJECT_ROOT, "engine", "darkpattern_engine.py")
    if not os.path.isfile(engine_path):
        return False, (
            "[FAIL] Engine file: engine/darkpattern_engine.py not found.\n"
            "       Fix: Place darkpattern_engine.py into the engine/ folder."
        )

    try:
        with open(engine_path, "r", encoding="utf-8") as f:
            tree = ast.parse(f.read(), filename=engine_path)

        defined_funcs = {
            node.name
            for node in ast.walk(tree)
            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef))
        }

        missing = [fn for fn in REQUIRED_ENGINE_FUNCS if fn not in defined_funcs]
        if missing:
            return False, (
                f"[FAIL] Engine functions: engine/darkpattern_engine.py is missing required function(s): {', '.join(missing)}.\n"
                f"       Fix: Implement {', '.join(missing)} in engine/darkpattern_engine.py."
            )

        return True, "[PASS] Engine file: engine/darkpattern_engine.py present and exports all required functions"

    except Exception as exc:
        return False, (
            f"[FAIL] Engine file parse error: {exc}\n"
            "       Fix: Check engine/darkpattern_engine.py for syntax errors."
        )


def check_model_bundle():
    """Check outputs/model/ for meta.json, model weights, and tokenizer files."""
    if not os.path.isdir(MODEL_DIR):
        return False, (
            f"[FAIL] Model directory: {MODEL_DIR} does not exist.\n"
            f"       Fix: Create {MODEL_DIR} and place your model files inside."
        )

    files = os.listdir(MODEL_DIR)

    # 1. meta.json
    has_meta = "meta.json" in files

    # 2. Model weights (*.safetensors, *.bin, *.pt)
    weight_exts = (".safetensors", ".bin", ".pt", ".pth", ".onnx", ".ckpt")
    has_weights = any(f.endswith(weight_exts) for f in files)

    # 3. Tokenizer files (tokenizer.json, vocab.txt, tokenizer_config.json)
    tok_files = {"tokenizer.json", "vocab.txt", "tokenizer_config.json", "special_tokens_map.json"}
    has_tokenizer = any(f in tok_files for f in files)

    missing_items = []
    if not has_meta:
        missing_items.append("meta.json")
    if not has_weights:
        missing_items.append("model weights (*.safetensors or *.bin)")
    if not has_tokenizer:
        missing_items.append("tokenizer files (tokenizer.json or vocab.txt)")

    if missing_items:
        return False, (
            f"[FAIL] Model bundle in {MODEL_DIR}: missing {', '.join(missing_items)}.\n"
            f"       Fix: Copy {', '.join(missing_items)} into {MODEL_DIR}."
        )

    return True, f"[PASS] Model bundle: meta.json, weights, and tokenizer found in {MODEL_DIR}"


def check_packages():
    """Verify required Python packages import successfully."""
    failed = []
    for mod_name, desc in REQUIRED_PACKAGES:
        try:
            __import__(mod_name)
        except ImportError as exc:
            failed.append(f"{mod_name} ({desc})")

    if failed:
        return False, (
            f"[FAIL] Python packages missing: {', '.join(failed)}.\n"
            "       Fix: Run 'pip install -r requirements.txt' in your virtual environment."
        )

    return True, "[PASS] Python packages: All required packages (torch, transformers, easyocr, cv2, bs4, PIL, sklearn, pandas, flask) import successfully"


def check_easyocr_weights():
    """Check if EasyOCR weights are present in ~/.EasyOCR/model/."""
    easyocr_dir = os.path.expanduser(os.path.join("~", ".EasyOCR", "model"))
    has_weights = False
    if os.path.isdir(easyocr_dir):
        files = os.listdir(easyocr_dir)
        has_weights = any(f.endswith(".pth") for f in files)

    if not has_weights:
        return False, (
            f"[FAIL] EasyOCR weights: Not found in {easyocr_dir}.\n"
            '       Fix: Run python -c "import easyocr; easyocr.Reader([\'en\'])" to download OCR model weights.'
        )

    return True, f"[PASS] EasyOCR weights: Found detector/recognizer models in {easyocr_dir}"


def check_port():
    """Verify default or configured port is free."""
    port_str = os.environ.get("PORT", "5000")
    try:
        port = int(port_str)
    except ValueError:
        port = 5000

    sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    try:
        sock.bind(("127.0.0.1", port))
        sock.close()
        return True, f"[PASS] Port: Port {port} is free and ready"
    except OSError:
        return False, (
            f"[FAIL] Port: Port {port} is already in use by another process.\n"
            f"       Fix: Stop the process using port {port} or set $env:PORT=<free_port> (e.g. $env:PORT=\"5005\")."
        )


def run_preflight():
    """Run all preflight checks and return total failed count."""
    print("=" * 70)
    print(" CheekShield AI — Preflight Checklist")
    print("=" * 70)

    checks = [
        ("Python dependencies", check_packages),
        ("Engine module", check_engine),
        ("Model bundle", check_model_bundle),
        ("EasyOCR weights", check_easyocr_weights),
        ("Server port", check_port),
    ]

    passed_count = 0
    failed_count = 0

    for name, fn in checks:
        ok, msg = fn()
        print(msg)
        if ok:
            passed_count += 1
        else:
            failed_count += 1

    print("-" * 70)
    if failed_count == 0:
        print(f"Preflight SUCCESS: All {passed_count} checks passed! App is ready for real model.")
        return 0
    else:
        print(f"Preflight NOTICE: {passed_count} passed, {failed_count} item(s) need attention.")
        print("Note: To run in mock engine mode for testing/UI review, set $env:CHEEK_MOCK=\"1\".")
        return 1


if __name__ == "__main__":
    sys.exit(run_preflight())
