"""Contract tests: both mock and real engine outputs normalize into valid
API v1 shapes. Run with CHEEK_MOCK=1 (default) or with the real engine."""

import os
import sys
import pytest

# Ensure project root is in path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

os.environ.setdefault("CHEEK_MOCK", "1")

from adapter.mock_engine import (
    predict,
    audit_html_dom,
    analyze_screenshot,
    summarize_findings,
    detect_countdown_timers,
    load_trained_bundle,
    get_mock_meta,
)
from adapter.normalize import normalize_findings, normalize_summary
from adapter.exposure import compute_exposure

# Test constants
K = 1.6
TIER_WEIGHTS = {3: 1.0, 2: 0.6, 1: 0.3, 0: 0.0}
BANDS = [
    (0, 0, "fresh", "Fresh"),
    (1, 24, "bruised", "Slight bruise"),
    (25, 49, "soft", "Soft spots"),
    (50, 74, "squishy", "Squishy"),
    (75, 100, "rotten", "Rotten"),
]


# -- Required API v1 finding keys --

REQUIRED_FINDING_KEYS = {
    "id", "text", "category", "is_dark_pattern", "kind", "risk_rank",
    "risk_label", "evidence_kind", "score", "score_label", "p_dark",
    "attributions", "explanation", "how_to_fix", "verdict", "gate_note",
    "source_type", "bbox", "order",
}

VALID_KINDS = {"flag", "routine_preselection", "checked"}
VALID_EVIDENCE_KINDS = {"model", "rule"}
VALID_RISK_RANKS = {0, 1, 2, 3}


def _validate_finding(finding):
    """Assert a normalized finding has the correct shape."""
    # All required keys present
    missing = REQUIRED_FINDING_KEYS - set(finding.keys())
    assert not missing, f"Missing keys: {missing}"

    # Type checks
    assert isinstance(finding["id"], str)
    assert finding["id"].startswith("f")
    assert isinstance(finding["text"], str)
    assert isinstance(finding["category"], str)
    assert isinstance(finding["is_dark_pattern"], bool)
    assert finding["kind"] in VALID_KINDS
    assert finding["risk_rank"] in VALID_RISK_RANKS
    assert isinstance(finding["risk_label"], str)
    assert finding["evidence_kind"] in VALID_EVIDENCE_KINDS
    assert isinstance(finding["score"], (int, float))
    assert isinstance(finding["score_label"], str)
    assert isinstance(finding["attributions"], list)
    assert isinstance(finding["order"], int)

    # Evidence-kind-specific checks
    if finding["evidence_kind"] == "model":
        # Model findings may have p_dark
        if finding["p_dark"] is not None:
            assert isinstance(finding["p_dark"], (int, float))
        # Score label is "Confidence"
        assert finding["score_label"] == "Confidence"
        # Attributions use delta_p
        for attr in finding["attributions"]:
            assert attr["unit"] == "delta_p"
    else:
        # Rule findings: p_dark must be None
        assert finding["p_dark"] is None
        # Score label is "Rule score"
        assert finding["score_label"] == "Rule score"
        # Attributions use rule_weight
        for attr in finding["attributions"]:
            assert attr["unit"] == "rule_weight"


def _validate_summary(summary):
    """Assert a normalized summary has the correct shape."""
    assert summary["status"] in ("flagged", "clean", "no_content")
    assert isinstance(summary["overall_risk"], str)
    assert isinstance(summary["total_items"], int)
    assert isinstance(summary["flagged_items"], int)
    assert isinstance(summary["checked_fine"], int)
    assert isinstance(summary["by_category"], dict)


def _validate_exposure(exposure):
    """Assert exposure result has the correct shape."""
    assert isinstance(exposure["percent"], int)
    assert 0 <= exposure["percent"] <= 100
    assert exposure["band"] in ("fresh", "bruised", "soft", "squishy", "rotten")
    assert isinstance(exposure["label"], str)
    assert isinstance(exposure["pressure"], (int, float))


class TestMockTextDeceptive:
    """Deceptive text through mock engine → valid API v1."""

    def test_predict_returns_findings(self):
        raw = predict(
            ["Hurry! Only 2 left.", "Add Rs 199 order protection"],
            "outputs/model",
            explain=True,
            surface="text",
            gate=True,
        )
        assert isinstance(raw, list)
        assert len(raw) > 0

    def test_normalize_deceptive(self):
        raw = predict(
            ["Hurry! Only 2 left.", "Add Rs 199 order protection"],
            "outputs/model",
        )
        findings, warnings = normalize_findings(raw)
        assert len(findings) > 0

        for f in findings:
            _validate_finding(f)

        # Should have flags, checked, and routine_preselection
        kinds = {f["kind"] for f in findings}
        assert "flag" in kinds
        assert "checked" in kinds
        assert "routine_preselection" in kinds

    def test_summarize_and_normalize(self):
        raw = predict(["Hurry! Only 2 left."], "outputs/model")
        findings, _ = normalize_findings(raw)
        raw_summary = summarize_findings(raw)
        summary = normalize_summary(raw_summary, findings)
        _validate_summary(summary)
        assert summary["status"] == "flagged"

    def test_exposure_deceptive(self):
        raw = predict(["Hurry! Only 2 left."], "outputs/model")
        findings, _ = normalize_findings(raw)
        exposure = compute_exposure(
            findings, k=K, tier_weights=TIER_WEIGHTS, bands=BANDS
        )
        _validate_exposure(exposure)
        assert exposure["percent"] > 0


class TestMockTextClean:
    """Clean text through mock engine → valid API v1 with clean status."""

    def test_clean_summary(self):
        raw = predict(
            ["Ships in 2 business days.", "Free returns."],
            "outputs/model",
        )
        findings, _ = normalize_findings(raw)
        raw_summary = summarize_findings(raw)
        summary = normalize_summary(raw_summary, findings)
        _validate_summary(summary)
        assert summary["status"] == "clean"
        assert summary["flagged_items"] == 0

    def test_clean_exposure(self):
        raw = predict(
            ["Ships in 2 business days."],
            "outputs/model",
        )
        findings, _ = normalize_findings(raw)
        exposure = compute_exposure(
            findings, k=K, tier_weights=TIER_WEIGHTS, bands=BANDS
        )
        assert exposure["percent"] == 0
        assert exposure["band"] == "fresh"


class TestMockHtml:
    """HTML mode through mock engine → valid API v1."""

    def test_html_deceptive(self):
        html = '<input type="checkbox" checked> Add Rs 199 order protection'
        raw = audit_html_dom(html, "outputs/model")
        findings, _ = normalize_findings(raw)
        assert len(findings) > 0
        for f in findings:
            _validate_finding(f)


class TestMockScreenshot:
    """Screenshot mode through mock engine → valid API v1."""

    def test_screenshot(self):
        import numpy as np
        img = np.zeros((480, 640, 3), dtype=np.uint8)
        annotated, raw = analyze_screenshot(img, "outputs/model")
        assert annotated.shape[:2] == (480, 640)

        findings, _ = normalize_findings(raw)
        for f in findings:
            _validate_finding(f)
            # Screenshot findings should have bbox
            assert f["bbox"] is not None


class TestMockTimers:
    """Countdown timer detection → valid findings."""

    def test_timer_detection(self):
        items = [{"text": "Offer ends in 04:59"}]
        raw = detect_countdown_timers(items)
        assert len(raw) > 0
        findings, _ = normalize_findings(raw)
        for f in findings:
            _validate_finding(f)
            assert f["category"] == "Urgency"


class TestMockMeta:
    """meta.json has the required fields."""

    def test_meta_shape(self):
        _, _, meta = load_trained_bundle("outputs/model")
        assert "classes" in meta
        assert isinstance(meta["classes"], list)
        assert len(meta["classes"]) > 0
        assert "temperature" in meta
        assert "dark_threshold" in meta
        assert "test_report" in meta
        assert "confusion_matrix" in meta

    def test_meta_has_macro_avg(self):
        meta = get_mock_meta()
        assert "macro avg" in meta["test_report"]
        assert "f1-score" in meta["test_report"]["macro avg"]


class TestUnknownCategory:
    """The mock includes a 'Foo Pattern' category — it must normalize safely."""

    def test_unknown_category_passes(self):
        raw = predict(["Hurry! Only 2 left."], "outputs/model")
        findings, _ = normalize_findings(raw)
        foo = [f for f in findings if f["category"] == "Foo Pattern"]
        assert len(foo) == 1
        _validate_finding(foo[0])


class TestRuleVsModelDistinction:
    """Rule and model findings are always distinguishable."""

    def test_distinct_evidence_kind(self):
        raw = predict(["Hurry! Only 2 left."], "outputs/model")
        findings, _ = normalize_findings(raw)
        model_findings = [f for f in findings if f["evidence_kind"] == "model"]
        rule_findings = [f for f in findings if f["evidence_kind"] == "rule"]
        assert len(model_findings) > 0
        assert len(rule_findings) > 0

    def test_rule_score_never_called_confidence(self):
        raw = predict(["Add Rs 199 order protection"], "outputs/model")
        findings, _ = normalize_findings(raw)
        for f in findings:
            if f["evidence_kind"] == "rule":
                assert f["score_label"] == "Rule score"
                assert f["p_dark"] is None
