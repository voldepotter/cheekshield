"""Tests for adapter/exposure.py — exposure score formula and sanity targets."""

import pytest
from adapter.exposure import compute_exposure

# Use explicit test constants matching config defaults
K = 1.6
TIER_WEIGHTS = {3: 1.0, 2: 0.6, 1: 0.3, 0: 0.0}
BANDS = [
    (0, 0, "fresh", "Fresh"),
    (1, 24, "bruised", "Slight bruise"),
    (25, 49, "soft", "Soft spots"),
    (50, 74, "squishy", "Squishy"),
    (75, 100, "rotten", "Rotten"),
]


def _flag(risk_rank, score, p_dark=None, evidence_kind="model"):
    """Create a minimal normalized flag finding for exposure tests."""
    return {
        "kind": "flag",
        "risk_rank": risk_rank,
        "score": score,
        "p_dark": p_dark,
        "evidence_kind": evidence_kind,
    }


class TestExposureBasics:
    def test_no_findings(self):
        result = compute_exposure([], k=K, tier_weights=TIER_WEIGHTS, bands=BANDS)
        assert result["percent"] == 0
        assert result["band"] == "fresh"
        assert result["label"] == "Fresh"
        assert result["pressure"] == 0

    def test_only_checked(self):
        """Non-flag findings contribute nothing."""
        findings = [{"kind": "checked", "risk_rank": 3, "score": 0.9}]
        result = compute_exposure(findings, k=K, tier_weights=TIER_WEIGHTS, bands=BANDS)
        assert result["percent"] == 0

    def test_only_routine(self):
        """Routine pre-selections contribute nothing."""
        findings = [{"kind": "routine_preselection", "risk_rank": 0, "score": 0.1}]
        result = compute_exposure(findings, k=K, tier_weights=TIER_WEIGHTS, bands=BANDS)
        assert result["percent"] == 0


class TestExposureSanityTargets:
    """Sanity targets from Section 9 with K=1.6."""

    def test_one_strong_high(self):
        """One strong High finding → ~45%."""
        findings = [_flag(risk_rank=3, score=0.92, p_dark=0.95)]
        result = compute_exposure(findings, k=K, tier_weights=TIER_WEIGHTS, bands=BANDS)
        assert 35 <= result["percent"] <= 55, f"Got {result['percent']}%"

    def test_two_strong_highs(self):
        """Two strong High findings → ~70%."""
        findings = [
            _flag(risk_rank=3, score=0.92, p_dark=0.95),
            _flag(risk_rank=3, score=0.94, p_dark=0.97),
        ]
        result = compute_exposure(findings, k=K, tier_weights=TIER_WEIGHTS, bands=BANDS)
        assert 60 <= result["percent"] <= 80, f"Got {result['percent']}%"

    def test_three_strong_highs(self):
        """Three or more strong High findings → 80%+."""
        findings = [
            _flag(risk_rank=3, score=0.92, p_dark=0.95),
            _flag(risk_rank=3, score=0.94, p_dark=0.97),
            _flag(risk_rank=3, score=0.88, p_dark=0.91),
        ]
        result = compute_exposure(findings, k=K, tier_weights=TIER_WEIGHTS, bands=BANDS)
        assert result["percent"] >= 80, f"Got {result['percent']}%"

    def test_one_medium(self):
        """One Medium finding → ~25%."""
        findings = [_flag(risk_rank=2, score=0.78, p_dark=0.82)]
        result = compute_exposure(findings, k=K, tier_weights=TIER_WEIGHTS, bands=BANDS)
        assert 15 <= result["percent"] <= 35, f"Got {result['percent']}%"

    def test_one_low(self):
        """A single Low finding → <15%."""
        findings = [_flag(risk_rank=1, score=0.55, p_dark=0.60)]
        result = compute_exposure(findings, k=K, tier_weights=TIER_WEIGHTS, bands=BANDS)
        assert result["percent"] < 15, f"Got {result['percent']}%"


class TestExposureBands:
    def test_fresh(self):
        result = compute_exposure([], k=K, tier_weights=TIER_WEIGHTS, bands=BANDS)
        assert result["band"] == "fresh"

    def test_bruised(self):
        findings = [_flag(risk_rank=1, score=0.55, p_dark=0.60)]
        result = compute_exposure(findings, k=K, tier_weights=TIER_WEIGHTS, bands=BANDS)
        assert result["band"] == "bruised"

    def test_squishy(self):
        findings = [
            _flag(risk_rank=3, score=0.92, p_dark=0.95),
            _flag(risk_rank=3, score=0.94, p_dark=0.97),
        ]
        result = compute_exposure(findings, k=K, tier_weights=TIER_WEIGHTS, bands=BANDS)
        assert result["band"] in ("squishy", "rotten")  # ~70%


class TestExposureRuleFindings:
    def test_rule_uses_score_only(self):
        """Rule findings use score (heuristic_score), not max(score, p_dark)."""
        findings = [_flag(risk_rank=3, score=0.5, p_dark=None, evidence_kind="rule")]
        result = compute_exposure(findings, k=K, tier_weights=TIER_WEIGHTS, bands=BANDS)
        # pressure = 1.0 * 0.5 = 0.5, percent ≈ 27%
        assert 20 <= result["percent"] <= 35, f"Got {result['percent']}%"

    def test_model_uses_max_score_pdark(self):
        """Model findings use max(score, p_dark)."""
        findings = [_flag(risk_rank=3, score=0.5, p_dark=0.9, evidence_kind="model")]
        result = compute_exposure(findings, k=K, tier_weights=TIER_WEIGHTS, bands=BANDS)
        # pressure = 1.0 * 0.9 = 0.9, percent ≈ 43%
        assert 35 <= result["percent"] <= 50, f"Got {result['percent']}%"


class TestExposureGuardsAndVariability:
    """Tests required by Change 4 for guards and input variability."""

    def test_no_findings_gives_zero(self):
        res = compute_exposure([], k=K, tier_weights=TIER_WEIGHTS, bands=BANDS)
        assert res["percent"] == 0
        assert res["band"] == "fresh"

    def test_clean_status_gives_zero(self):
        findings = [_flag(risk_rank=3, score=0.99, p_dark=0.99)]
        res = compute_exposure(findings, k=K, tier_weights=TIER_WEIGHTS, bands=BANDS, summary_status="clean")
        assert res["percent"] == 0
        assert res["band"] == "fresh"

    def test_one_strong_high_exact(self):
        # 1 strong high with strength 1.0: 100 * (1 - exp(-1.0 / 1.6)) = 46.47 -> 46%
        findings = [_flag(risk_rank=3, score=1.0, p_dark=1.0)]
        res = compute_exposure(findings, k=K, tier_weights=TIER_WEIGHTS, bands=BANDS)
        assert res["percent"] == 46

    def test_two_strong_highs_exact(self):
        # 2 strong highs with strength 1.0: 100 * (1 - exp(-2.0 / 1.6)) = 71.35 -> 71% (~70%)
        findings = [_flag(risk_rank=3, score=1.0, p_dark=1.0), _flag(risk_rank=3, score=1.0, p_dark=1.0)]
        res = compute_exposure(findings, k=K, tier_weights=TIER_WEIGHTS, bands=BANDS)
        assert 68 <= res["percent"] <= 73

    def test_one_medium_exact(self):
        # 1 medium: weight 0.6, strength 0.8 -> pressure 0.48 -> 100 * (1 - exp(-0.48/1.6)) = 25.9 -> 26% (~25%)
        findings = [_flag(risk_rank=2, score=0.8, p_dark=0.8)]
        res = compute_exposure(findings, k=K, tier_weights=TIER_WEIGHTS, bands=BANDS)
        assert 23 <= res["percent"] <= 28

    def test_one_low_under_fifteen(self):
        # 1 low: weight 0.3, strength 0.6 -> pressure 0.18 -> 10.6% -> 11% (<15%)
        findings = [_flag(risk_rank=1, score=0.6, p_dark=0.6)]
        res = compute_exposure(findings, k=K, tier_weights=TIER_WEIGHTS, bands=BANDS)
        assert res["percent"] < 15

    def test_flag_present_gives_at_least_one_percent(self):
        findings = [_flag(risk_rank=1, score=0.0001, p_dark=0.0001)]
        res = compute_exposure(findings, k=K, tier_weights=TIER_WEIGHTS, bands=BANDS)
        assert res["percent"] >= 1

    def test_api_analyze_two_different_inputs_give_different_percents(self, monkeypatch):
        from app import app
        import adapter.engine_adapter as ea

        ea._do_warmup()
        client = app.test_client()

        # Input A: clean text
        res_a = client.post("/api/analyze", json={"mode": "text", "content": "Clean item description with no rush."})
        assert res_a.status_code == 200
        data_a = res_a.get_json()
        assert data_a["exposure"]["percent"] == 0
        assert data_a["exposure"]["band"] == "fresh"

        # Input B: deceptive text
        res_b = client.post("/api/analyze", json={"mode": "text", "content": "Hurry! Only 2 left in stock. Offer ends in 04:59"})
        assert res_b.status_code == 200
        data_b = res_b.get_json()
        assert data_b["exposure"]["percent"] > 0
        assert data_b["exposure"]["percent"] != data_a["exposure"]["percent"]

    def test_api_analyze_cache_control_no_store(self):
        from app import app
        client = app.test_client()
        res = client.post("/api/analyze", json={"mode": "text", "content": "Check headers."})
        assert "no-store" in res.headers.get("Cache-Control", "")
