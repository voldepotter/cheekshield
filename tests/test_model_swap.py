"""Tests for the Model-Swap Drill (Section 5.4 & Section 7 Phase 5).

Verifies that modifying meta.json dynamically updates the model panel metrics,
classes, and confusion matrix with zero code changes.
"""

import os
import json
import time
import pytest
from adapter.engine_adapter import get_model_info, _do_warmup
import config

@pytest.fixture(autouse=True)
def ensure_mock():
    old_mock = config.MOCK_MODE
    config.MOCK_MODE = True
    _do_warmup()
    yield
    config.MOCK_MODE = old_mock


def test_model_swap_drill():
    # 1. Baseline check
    baseline_info = get_model_info()
    assert baseline_info is not None
    assert "Urgency" in baseline_info["classes"]
    original_classes_count = len(baseline_info["classes"])

    # 2. Prepare temporary meta.json in MODEL_DIR
    model_dir = os.path.abspath(config.MODEL_DIR)
    os.makedirs(model_dir, exist_ok=True)
    meta_path = os.path.join(model_dir, "meta.json")

    # Create modified meta with new class and higher macro-f1
    swapped_classes = list(baseline_info["classes"]) + ["Confirm Shaming"]
    n_classes = len(swapped_classes)

    swapped_meta = {
        "model_name": "distilbert-base-uncased-v2",
        "classes": swapped_classes,
        "temperature": 2.1,
        "dark_threshold": 0.40,
        "test_report": {
            "macro avg": {"precision": 0.94, "recall": 0.93, "f1-score": 0.942, "support": 350},
            "Confirm Shaming": {"precision": 0.95, "recall": 0.92, "f1-score": 0.935, "support": 45},
            "Urgency": {"precision": 0.96, "recall": 0.94, "f1-score": 0.95, "support": 50},
        },
        "binary_report_tuned": {
            "precision": 0.95,
            "recall": 0.94,
            "f1-score": 0.945,
            "threshold": 0.40,
        },
        "confusion_matrix": [[10] * n_classes for _ in range(n_classes)],
    }

    try:
        # Write modified meta.json and ensure mtime is newer
        with open(meta_path, "w", encoding="utf-8") as f:
            json.dump(swapped_meta, f)
        # Update mtime to future
        now = time.time() + 2.0
        os.utime(meta_path, (now, now))

        # 3. Retrieve model info — hot reload should detect the new file
        swapped_info = get_model_info()
        assert swapped_info is not None
        assert swapped_info["macro_f1"] == 0.942
        assert swapped_info["temperature"] == 2.1
        assert "Confirm Shaming" in swapped_info["classes"]
        assert "Confirm Shaming" in swapped_info["per_class"]
        assert len(swapped_info["classes"]) == original_classes_count + 1
        assert len(swapped_info["confusion_matrix"]) == n_classes

    finally:
        # 4. Cleanup and revert
        if os.path.exists(meta_path):
            os.remove(meta_path)

        # Force re-warmup to baseline
        _do_warmup()
        reverted_info = get_model_info()
        assert reverted_info is not None
        assert "Confirm Shaming" not in reverted_info["classes"]
        assert len(reverted_info["classes"]) == original_classes_count
