"""Tests for adapter/normalize.py — every quirk from Section 4."""

import pytest
from adapter.normalize import (
    is_rule_based,
    is_prefilter,
    is_benign_preselection,
    normalize_risk,
    determine_kind,
    normalize_finding,
    normalize_findings,
    normalize_summary,
)


# -- Helpers: raw engine-shaped finding dicts --

def _model_finding(**overrides):
    """A typical model-based finding."""
    base = {
        "text": "Hurry! Only 2 left.",
        "category": "Urgency",
        "is_dark_pattern": True,
        "confidence": 0.92,
        "p_dark": 0.95,
        "risk_level": "High Risk",
        "xai_words": [{"word": "Hurry!", "delta_p": 0.42}],
        "explanation": "Creates urgency.",
        "how_to_fix": "Remove pressure.",
        "source_type": "NLP Text Classifier (DistilBERT)",
        "gate_note": None,
        "verdict": "Likely concern, needs human review.",
        "bbox": None,
    }
    base.update(overrides)
    return base


def _rule_finding(**overrides):
    """A typical rule-based finding with duplicate confidence/heuristic_score."""
    base = {
        "text": "Add Rs 199 order protection",
        "category": "Preselected Choice",
        "is_dark_pattern": True,
        "confidence": 0.88,       # duplicate of heuristic_score
        "p_dark": 0.88,           # duplicate of rule_weight
        "heuristic_score": 0.88,
        "risk_level": "High Risk",
        "xai_words": [
            {"word": "Add", "delta_p": 0.30, "rule_weight": 0.30},
            {"word": "order protection", "delta_p": 0.45, "rule_weight": 0.45},
        ],
        "explanation": "Pre-checked add-on.",
        "how_to_fix": "Uncheck by default.",
        "source_type": "DOM Pre-selection Check (Rule-Based Heuristic)",
        "gate_note": None,
        "verdict": "Likely concern.",
        "bbox": None,
    }
    base.update(overrides)
    return base


def _prefilter_stub():
    """A pre-filter stub — not a real finding."""
    return {
        "text": "Add to cart",
        "category": "Not Dark Pattern",
        "is_dark_pattern": False,
        "confidence": 0,
        "p_dark": 0.02,
        "risk_level": "None (Benign)",
        "xai_words": [],
        "explanation": "Standard action.",
        "how_to_fix": "",
        "source_type": "Pre-filter: too short / common action",
        "gate_note": None,
        "verdict": "",
        "bbox": None,
    }


def _benign_preselection():
    """A benign pre-selection — routine, not a flag."""
    return {
        "text": "Remember me",
        "category": "Preselected Choice",
        "is_dark_pattern": False,
        "confidence": 0.15,
        "p_dark": 0.08,
        "risk_level": "Low Risk / Benign Pre-selection",
        "xai_words": [],
        "explanation": "Routine convenience.",
        "how_to_fix": "",
        "source_type": "DOM Pre-selection Check (Rule-Based Heuristic)",
        "gate_note": None,
        "verdict": "",
        "bbox": None,
    }


# -- is_rule_based --

class TestIsRuleBased:
    def test_source_type_suffix(self):
        assert is_rule_based(_rule_finding()) is True

    def test_model_finding(self):
        assert is_rule_based(_model_finding()) is False

    def test_heuristic_score_key(self):
        f = _model_finding()
        f["heuristic_score"] = 0.5
        assert is_rule_based(f) is True

    def test_benign_preselection_is_rule(self):
        # Benign pre-selections from DOM checks are rule-based
        assert is_rule_based(_benign_preselection()) is True


# -- is_prefilter --

class TestIsPrefilter:
    def test_prefilter_stub(self):
        assert is_prefilter(_prefilter_stub()) is True

    def test_model_finding(self):
        assert is_prefilter(_model_finding()) is False

    def test_rule_finding(self):
        assert is_prefilter(_rule_finding()) is False


# -- is_benign_preselection --

class TestIsBenignPreselection:
    def test_benign(self):
        assert is_benign_preselection(_benign_preselection()) is True

    def test_dark_pattern_not_benign(self):
        assert is_benign_preselection(_rule_finding()) is False

    def test_model_finding_not_benign(self):
        assert is_benign_preselection(_model_finding()) is False


# -- normalize_risk --

class TestNormalizeRisk:
    def test_high(self):
        assert normalize_risk("High Risk") == (3, "High Risk")

    def test_medium(self):
        assert normalize_risk("Medium Risk") == (2, "Medium Risk")

    def test_low_needs_review(self):
        assert normalize_risk("Low Risk (Needs Review)") == (1, "Low Risk")

    def test_low_plain(self):
        assert normalize_risk("Low Risk") == (1, "Low Risk")

    def test_none_benign(self):
        # "benign" in the string wins, so the label is "Benign"
        assert normalize_risk("None (Benign)") == (0, "Benign")

    def test_benign_preselection(self):
        # "benign" in the string wins over "low"
        assert normalize_risk("Low Risk / Benign Pre-selection") == (0, "Benign")

    def test_empty(self):
        assert normalize_risk("") == (1, "Low Risk")

    def test_none_input(self):
        assert normalize_risk(None) == (1, "Low Risk")

    def test_unknown_string(self):
        assert normalize_risk("Some Unknown Risk Level") == (1, "Low Risk")


# -- determine_kind --

class TestDetermineKind:
    def test_flag(self):
        assert determine_kind(_model_finding()) == "flag"
        assert determine_kind(_rule_finding()) == "flag"

    def test_checked_prefilter(self):
        assert determine_kind(_prefilter_stub()) == "checked"

    def test_routine_preselection(self):
        assert determine_kind(_benign_preselection()) == "routine_preselection"

    def test_benign_model(self):
        f = _model_finding(is_dark_pattern=False, risk_level="None (Benign)")
        assert determine_kind(f) == "checked"


# -- normalize_finding --

class TestNormalizeFinding:
    def test_model_finding_shape(self):
        nf = normalize_finding(_model_finding(), 0)
        assert nf["id"] == "f1"
        assert nf["evidence_kind"] == "model"
        assert nf["kind"] == "flag"
        assert nf["risk_rank"] == 3
        assert nf["risk_label"] == "High Risk"
        assert nf["score"] == 0.92
        assert nf["score_label"] == "Confidence"
        assert nf["p_dark"] == 0.95
        assert nf["order"] == 0
        assert len(nf["attributions"]) == 1
        assert nf["attributions"][0]["unit"] == "delta_p"

    def test_rule_finding_uses_heuristic_score(self):
        """Rule findings must use heuristic_score, not confidence."""
        nf = normalize_finding(_rule_finding(), 1)
        assert nf["evidence_kind"] == "rule"
        assert nf["score"] == 0.88
        assert nf["score_label"] == "Rule score"
        assert nf["p_dark"] is None  # rule findings have no p_dark

    def test_rule_attributions_use_rule_weight(self):
        """Rule attributions must use rule_weight, not delta_p."""
        nf = normalize_finding(_rule_finding(), 0)
        for attr in nf["attributions"]:
            assert attr["unit"] == "rule_weight"

    def test_prefilter_is_checked(self):
        nf = normalize_finding(_prefilter_stub(), 5)
        assert nf["kind"] == "checked"
        assert nf["is_dark_pattern"] is False

    def test_benign_preselection(self):
        nf = normalize_finding(_benign_preselection(), 3)
        assert nf["kind"] == "routine_preselection"
        assert nf["risk_rank"] == 0
        assert nf["risk_label"] == "Benign"

    def test_bbox_preserved(self):
        f = _model_finding(bbox=[10, 20, 100, 200])
        nf = normalize_finding(f, 0)
        assert nf["bbox"] == [10, 20, 100, 200]

    def test_unknown_category(self):
        f = _model_finding(category="Foo Pattern")
        nf = normalize_finding(f, 0)
        assert nf["category"] == "Foo Pattern"

    def test_gate_note_preserved(self):
        f = _rule_finding(gate_note="Kept because score exceeds threshold.")
        nf = normalize_finding(f, 0)
        assert nf["gate_note"] == "Kept because score exceeds threshold."


# -- normalize_findings --

class TestNormalizeFindings:
    def test_all_quirks(self):
        raw = [
            _model_finding(),
            _rule_finding(),
            _prefilter_stub(),
            _benign_preselection(),
        ]
        results, warnings = normalize_findings(raw)
        assert len(results) == 4
        assert len(warnings) == 0

        kinds = [r["kind"] for r in results]
        assert kinds == ["flag", "flag", "checked", "routine_preselection"]

    def test_malformed_dropped(self):
        """A finding that causes an exception is dropped with a warning."""
        raw = [_model_finding(), "not a dict"]
        results, warnings = normalize_findings(raw)
        assert len(results) == 1
        assert len(warnings) == 1
        assert "index 1" in warnings[0]

    def test_empty(self):
        results, warnings = normalize_findings([])
        assert results == []
        assert warnings == []

    def test_none(self):
        results, warnings = normalize_findings(None)
        assert results == []


# -- normalize_summary --

class TestNormalizeSummary:
    def test_flagged_summary(self):
        raw = [_model_finding(), _rule_finding(), _prefilter_stub(), _benign_preselection()]
        findings, _ = normalize_findings(raw)
        engine_summary = {
            "status": "flagged",
            "overall_risk": "High Risk",
            "total_items": 4,
            "flagged_items": 2,
            "by_category": {"Urgency": 1, "Preselected Choice": 1},
            "message": "Found 2 dark patterns.",
        }
        summary = normalize_summary(engine_summary, findings)
        assert summary["status"] == "flagged"
        assert summary["flagged_items"] == 2
        assert summary["checked_fine"] == 1
        assert summary["routine_preselections"] == 1
        assert summary["total_items"] == 4
        assert summary["by_category"]["Urgency"] == 1

    def test_clean_summary(self):
        raw = [_prefilter_stub()]
        findings, _ = normalize_findings(raw)
        engine_summary = {
            "status": "clean",
            "overall_risk": "None",
            "total_items": 1,
            "flagged_items": 0,
            "by_category": {},
            "message": "No dark patterns detected.",
        }
        summary = normalize_summary(engine_summary, findings)
        assert summary["status"] == "clean"
        assert summary["flagged_items"] == 0

    def test_none_summary(self):
        summary = normalize_summary(None, [])
        assert summary["status"] == "no_content"
