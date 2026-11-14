"""Normalize raw engine findings into API v1 shape.

Pure functions only. No imports of the engine. Tolerant of missing or
unexpected keys (.get with defaults everywhere).
"""


def is_rule_based(raw):
    """A finding is rule-based when source_type ends with
    '(Rule-Based Heuristic)' or it has a non-None heuristic_score."""
    st = raw.get("source_type", "")
    if st.endswith("(Rule-Based Heuristic)"):
        return True
    # Check that heuristic_score exists AND is not None
    return raw.get("heuristic_score") is not None


def is_prefilter(raw):
    """Pre-filter stubs have source_type starting with 'Pre-filter'.
    They are skipped fragments (confidence 0, benign). Not real findings —
    counted as 'checked' only."""
    return raw.get("source_type", "").startswith("Pre-filter")


def is_benign_preselection(raw):
    """Benign pre-selection: is_dark_pattern is false AND risk_level contains
    'benign pre-selection' (case-insensitive)."""
    return (
        not raw.get("is_dark_pattern", False)
        and "benign pre-selection" in raw.get("risk_level", "").lower()
    )


def normalize_risk(raw_risk):
    """Normalize a risk string to (rank: int, label: str).

    Match by substring; 'benign' wins over 'low'.
    Returns:
        rank  3=High, 2=Medium, 1=Low/needs-review, 0=Benign/none
        label Human-readable label
    """
    r = (raw_risk or "").lower()
    if "benign" in r:
        return 0, "Benign"
    if "high" in r:
        return 3, "High Risk"
    if "medium" in r:
        return 2, "Medium Risk"
    if "low" in r:
        return 1, "Low Risk"
    if "none" in r:
        return 0, "None"
    # Safe fallback — don't hide things
    return 1, "Low Risk"


def determine_kind(raw):
    """Determine finding kind: 'flag', 'routine_preselection', or 'checked'."""
    if is_prefilter(raw):
        return "checked"
    if is_benign_preselection(raw):
        return "routine_preselection"
    if raw.get("is_dark_pattern", False):
        return "flag"
    return "checked"


def normalize_finding(raw, order_index):
    """Convert one raw engine finding dict into an API v1 finding dict.

    Handles every quirk from Section 4:
    - Rule findings carry duplicate confidence/heuristic_score and
      delta_p/rule_weight — we pick the correct one.
    - Pre-filter stubs become kind='checked'.
    - Benign pre-selections become kind='routine_preselection'.
    - Risk strings are normalized by substring.
    """
    rule = is_rule_based(raw)
    kind = determine_kind(raw)
    risk_rank, risk_label = normalize_risk(raw.get("risk_level"))

    # Score: model → confidence, rule → heuristic_score
    if rule:
        score = raw.get("heuristic_score", raw.get("confidence", 0))
    else:
        score = raw.get("confidence", 0)

    # p_dark: only meaningful for model findings
    p_dark = raw.get("p_dark", 0) if not rule else None

    # Attributions: model → delta_p, rule → rule_weight
    attributions = []
    for w in raw.get("xai_words", []):
        if rule:
            weight = w.get("rule_weight", w.get("delta_p", 0))
            unit = "rule_weight"
        else:
            weight = w.get("delta_p", w.get("rule_weight", 0))
            unit = "delta_p"
        attributions.append({
            "token": w.get("word", ""),
            "weight": round(float(weight), 4) if weight else 0,
            "unit": unit,
        })

    return {
        "id": f"f{order_index + 1}",
        "text": raw.get("text", ""),
        "category": raw.get("category", "Unknown"),
        "is_dark_pattern": bool(raw.get("is_dark_pattern", False)),
        "kind": kind,
        "risk_rank": risk_rank,
        "risk_label": risk_label,
        "evidence_kind": "rule" if rule else "model",
        "score": round(float(score), 4) if score else 0,
        "score_label": "Rule score" if rule else "Confidence",
        "p_dark": round(float(p_dark), 4) if p_dark else None,
        "attributions": attributions,
        "explanation": raw.get("explanation", ""),
        "how_to_fix": raw.get("how_to_fix", ""),
        "verdict": raw.get("verdict", ""),
        "gate_note": raw.get("gate_note"),
        "source_type": raw.get("source_type", ""),
        "bbox": raw.get("bbox"),
        "order": order_index,
    }


def normalize_findings(raw_findings):
    """Normalize a list of raw engine findings. Malformed entries are dropped
    and reported via the returned warnings list."""
    results = []
    warnings = []
    for i, raw in enumerate(raw_findings or []):
        try:
            results.append(normalize_finding(raw, i))
        except Exception as exc:
            warnings.append(
                f"Dropped malformed finding at index {i}: {exc}"
            )
    return results, warnings


def normalize_summary(raw_summary, normalized_findings):
    """Build the API v1 summary from the engine's summarize_findings output
    and the normalized findings list.

    Recomputes flagged/checked/routine counts from normalized findings
    rather than trusting engine totals (which may count stubs differently).
    """
    if not raw_summary:
        return {
            "status": "no_content",
            "overall_risk": "None",
            "total_items": 0,
            "flagged_items": 0,
            "checked_fine": 0,
            "routine_preselections": 0,
            "by_category": {},
            "message": "Nothing to analyze.",
        }

    flagged = sum(1 for f in normalized_findings if f["kind"] == "flag")
    routine = sum(
        1 for f in normalized_findings if f["kind"] == "routine_preselection"
    )
    checked = sum(1 for f in normalized_findings if f["kind"] == "checked")

    # Recompute by_category from normalized findings (only flags)
    by_category = {}
    for f in normalized_findings:
        if f["kind"] == "flag":
            cat = f["category"]
            by_category[cat] = by_category.get(cat, 0) + 1

    return {
        "status": raw_summary.get("status", "no_content"),
        "overall_risk": raw_summary.get("overall_risk", "None"),
        "total_items": flagged + routine + checked,
        "flagged_items": flagged,
        "checked_fine": checked,
        "routine_preselections": routine,
        "by_category": by_category,
        "message": raw_summary.get("message", ""),
    }
