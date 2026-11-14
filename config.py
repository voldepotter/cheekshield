"""Environment-driven settings for CheekShield AI."""

import os

# -- Paths --
BASE_DIR = os.path.abspath(os.path.dirname(__file__))
_env_model_dir = os.environ.get("MODEL_DIR")
if _env_model_dir:
    MODEL_DIR = os.path.abspath(_env_model_dir)
else:
    MODEL_DIR = os.path.abspath(os.path.join(BASE_DIR, "outputs", "model"))
ENGINE_MODULE = os.environ.get("ENGINE_MODULE", "engine.darkpattern_engine")

# -- Mock mode (CHEEK_MOCK=1 uses adapter/mock_engine.py instead of real engine; defaults to OFF) --
def __getattr__(name):
    if name == "MOCK_MODE":
        return os.environ.get("CHEEK_MOCK", "0") == "1"
    raise AttributeError(f"module '{__name__}' has no attribute '{name}'")

# -- Input limits --
MAX_TEXT_CHARS = 20_000
MAX_HTML_BYTES = 400 * 1024          # 400 KB
MAX_IMAGE_BYTES = 8 * 1024 * 1024    # 8 MB
MAX_CONTENT_LENGTH = MAX_IMAGE_BYTES + 4096  # Flask overall limit with overhead
ALLOWED_IMAGE_TYPES = {"image/png", "image/jpeg", "image/webp"}
MAX_TEXT_LINES = 300

# -- Rate limit --
RATE_LIMIT_PER_MINUTE = 30

# -- Timeouts --
REQUEST_TIMEOUT_SECONDS = 90

# -- Exposure formula (Section 9) --
EXPOSURE_K = float(os.environ.get("EXPOSURE_K", "1.6"))
TIER_WEIGHTS = {3: 1.0, 2: 0.6, 1: 0.3, 0: 0.0}

# -- Exposure bands --
EXPOSURE_BANDS = [
    (0, 0, "fresh", "Fresh"),
    (1, 24, "bruised", "Slight bruise"),
    (25, 49, "soft", "Soft spots"),
    (50, 74, "squishy", "Squishy"),
    (75, 100, "rotten", "Rotten"),
]

# -- Admin --
ADMIN_TOKEN = os.environ.get("ADMIN_TOKEN", None)

# -- Demo --
DEMO_REPLAY = os.environ.get("DEMO_REPLAY", "0") == "1"

# -- Known limitations (served by /api/model, shown in the UI) --
LIMITATIONS = [
    "Genuine low-stock and fake scarcity can use identical wording.",
    "A ticked checkbox in a screenshot cannot be told apart from a user-ticked one.",
    "Rule-based checks are heuristics, not verified findings.",
    "Hidden checkout steps are not visible from this input.",
    "English only.",
]
