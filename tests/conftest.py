"""Pytest shared fixtures and hooks."""

import os
import pytest

# In test suite, default CHEEK_MOCK to "1" unless explicitly set by the caller
if "CHEEK_MOCK" not in os.environ:
    os.environ["CHEEK_MOCK"] = "1"

import config


def has_real_model():
    """Return True if outputs/model contains meta.json and weights."""
    if not os.path.isdir(config.MODEL_DIR):
        return False
    meta_path = os.path.join(config.MODEL_DIR, "meta.json")
    if not os.path.isfile(meta_path):
        return False
    files = os.listdir(config.MODEL_DIR)
    weight_exts = (".safetensors", ".bin", ".pt", ".pth", ".onnx", ".ckpt")
    return any(f.endswith(weight_exts) for f in files)


def pytest_configure(config):
    config.addinivalue_line(
        "markers", "real_model: mark test as requiring the trained real model files"
    )


def pytest_runtest_setup(item):
    """Skip tests requiring the real model when outputs/model/ is empty."""
    is_real_marked = item.get_closest_marker("real_model") is not None
    needs_real_engine = (not config.MOCK_MODE) and ("test_api" in item.nodeid)

    if (is_real_marked or needs_real_engine) and not has_real_model():
        pytest.skip("outputs/model/ is empty or missing model files; real model tests skipped.")

