"""Cheekometer exposure score.

Pure function, config-driven. No engine imports.

Formula (Section 9):
  For each finding with kind == 'flag':
    strength = max(score, p_dark) for model | score for rule
    tier_weight = {3: 1.0, 2: 0.6, 1: 0.3}[risk_rank]
  pressure = sum(tier_weight * strength)
  percent = round(100 * (1 - exp(-pressure / K)))
  K defaults to 1.6 (tunable).

Bands: 0=Fresh, 1-24=Slight bruise, 25-49=Soft spots,
       50-74=Squishy, 75-100=Rotten.

Sanity targets with K=1.6:
  - 1 strong High  → ~45%
  - 2 strong Highs → ~70%
  - 3+ strong Highs → 80%+
  - 1 Medium → ~25%
  - 1 Low → <15%
"""

import logging
import math

logger = logging.getLogger("cheekshield.exposure")


def compute_exposure(normalized_findings, k=None, tier_weights=None, bands=None, summary_status=None):
    """Compute the Cheekometer exposure score from normalized findings.

    Args:
        normalized_findings: list of API v1 finding dicts.
        k: the K constant for the logarithmic curve (default from config).
        tier_weights: dict mapping risk_rank to weight (default from config).
        bands: list of (lo, hi, band_key, label) tuples.
        summary_status: optional summary status string (e.g. 'clean', 'flagged').

    Returns:
        dict with percent, band, label, pressure.
    """
    # Import config defaults lazily so the module stays testable
    # without config.py in the path
    if k is None:
        from config import EXPOSURE_K
        k = EXPOSURE_K
    if tier_weights is None:
        from config import TIER_WEIGHTS
        tier_weights = TIER_WEIGHTS
    if bands is None:
        from config import EXPOSURE_BANDS
        bands = EXPOSURE_BANDS

    pressure = 0.0
    flag_count = 0

    for f in normalized_findings:
        if f.get("kind") != "flag":
            continue

        flag_count += 1
        rank = f.get("risk_rank", 0)
        tw = tier_weights.get(rank, 0.0)

        # Strength: model uses max(score, p_dark); rule uses score
        score = f.get("score", 0) or 0
        p_dark = f.get("p_dark") or 0
        if f.get("evidence_kind") == "model":
            strength = max(score, p_dark)
        else:
            strength = score

        pressure += tw * strength

    # Logarithmic saturation curve
    if pressure <= 0:
        percent = 0
    else:
        percent = round(100.0 * (1.0 - math.exp(-pressure / k)))

    # Clamp to integer 0-100
    percent = int(max(0, min(100, percent)))

    # Guard 1: If summary.status == "clean" or no flags, force percent=0, band="fresh"
    if summary_status == "clean" or flag_count == 0:
        if percent != 0:
            logger.warning(
                "Guard violation: status is '%s' with %d flags, but exposure percent calculated as %d. Forcing 0.",
                summary_status, flag_count, percent
            )
        percent = 0
    elif flag_count > 0 and percent < 1:
        # Guard 2: If findings include any kind == "flag", percent >= 1
        logger.warning(
            "Guard violation: %d flag findings present, but exposure percent was %d. Forcing 1.",
            flag_count, percent
        )
        percent = 1

    # Determine band
    band_key = "fresh"
    band_label = "Fresh"
    for lo, hi, bk, bl in bands:
        if lo <= percent <= hi:
            band_key = bk
            band_label = bl
            break

    return {
        "percent": percent,
        "band": band_key,
        "label": band_label,
        "pressure": round(pressure, 4),
    }
