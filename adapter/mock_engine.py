"""Mock engine for CHEEK_MOCK=1 mode.

Returns findings in the **raw engine shape** including every quirk from
Section 4: duplicate confidence/heuristic_score and delta_p/rule_weight for
rule findings, a pre-filter stub, a benign pre-selection, a Disguised Ad,
and an unknown category 'Foo Pattern'.

This lets the full UI be built and tested without torch.
"""

import time
import numpy as np

# Simulated meta.json
_MOCK_META = {
    "classes": [
        "Urgency",
        "Scarcity",
        "Social Proof",
        "Misdirection",
        "Other Dark Pattern",
        "Not Dark Pattern",
    ],
    "temperature": 1.8,
    "dark_threshold": 0.45,
    "test_report": {
        "Urgency": {"precision": 0.82, "recall": 0.78, "f1-score": 0.80, "support": 45},
        "Scarcity": {"precision": 0.76, "recall": 0.71, "f1-score": 0.73, "support": 38},
        "Social Proof": {"precision": 0.79, "recall": 0.74, "f1-score": 0.76, "support": 42},
        "Misdirection": {"precision": 0.68, "recall": 0.63, "f1-score": 0.65, "support": 30},
        "Other Dark Pattern": {"precision": 0.61, "recall": 0.55, "f1-score": 0.58, "support": 25},
        "Not Dark Pattern": {"precision": 0.91, "recall": 0.94, "f1-score": 0.92, "support": 120},
        "macro avg": {"precision": 0.76, "recall": 0.73, "f1-score": 0.74, "support": 300},
        "weighted avg": {"precision": 0.81, "recall": 0.80, "f1-score": 0.80, "support": 300},
    },
    "binary_report": {"precision": 0.84, "recall": 0.77, "f1": 0.80},
    "binary_report_tuned": {"threshold": 0.45, "precision": 0.85, "recall": 0.78, "f1": 0.81},
    "confusion_matrix": [
        [35, 3, 2, 1, 2, 2],
        [2, 27, 3, 2, 1, 3],
        [3, 2, 31, 1, 2, 3],
        [2, 3, 1, 19, 3, 2],
        [1, 2, 2, 3, 14, 3],
        [1, 1, 1, 1, 3, 113],
    ],
    "args": {"model_name": "distilbert-base-uncased", "epochs": 10},
}

_MODEL_CACHE = {}


def _deceptive_text_findings():
    """Produce a rich set of findings for deceptive text input."""
    return [
        # 1. Model-based Urgency (high risk)
        {
            "text": "Hurry! Only 2 left in stock.",
            "category": "Urgency",
            "is_dark_pattern": True,
            "confidence": 0.92,
            "p_dark": 0.95,
            "heuristic_score": None,
            "risk_level": "High Risk",
            "xai_words": [
                {"word": "Hurry!", "delta_p": 0.42},
                {"word": "Only", "delta_p": 0.18},
                {"word": "2 left", "delta_p": 0.25},
            ],
            "explanation": "Creates artificial urgency by implying very limited stock.",
            "how_to_fix": "Show real-time stock levels without pressure language, e.g. 'Stock: 2 available'.",
            "source_type": "NLP Text Classifier (DistilBERT)",
            "gate_note": None,
            "verdict": "Likely concern, needs human review, not verified wrongdoing.",
            "bbox": None,
        },
        # 2. Model-based Scarcity (medium risk)
        {
            "text": "8 people are viewing this item right now.",
            "category": "Social Proof",
            "is_dark_pattern": True,
            "confidence": 0.78,
            "p_dark": 0.82,
            "heuristic_score": None,
            "risk_level": "Medium Risk",
            "xai_words": [
                {"word": "8 people", "delta_p": 0.31},
                {"word": "viewing", "delta_p": 0.15},
                {"word": "right now", "delta_p": 0.22},
            ],
            "explanation": "Uses social proof to pressure the user by implying high demand.",
            "how_to_fix": "Remove real-time viewer counts or show verified purchase counts instead.",
            "source_type": "NLP Text Classifier (DistilBERT)",
            "gate_note": None,
            "verdict": "Likely concern, needs human review, not verified wrongdoing.",
            "bbox": None,
        },
        # 3. Model-based Urgency with countdown (high risk)
        {
            "text": "Offer ends in 04:59. Don't miss out!",
            "category": "Urgency",
            "is_dark_pattern": True,
            "confidence": 0.94,
            "p_dark": 0.97,
            "heuristic_score": None,
            "risk_level": "High Risk",
            "xai_words": [
                {"word": "ends in", "delta_p": 0.38},
                {"word": "04:59", "delta_p": 0.29},
                {"word": "Don't miss out!", "delta_p": 0.35},
            ],
            "explanation": "Countdown timer and loss-aversion language create extreme urgency.",
            "how_to_fix": "If the deadline is real, state it plainly: 'Sale ends November 20'. Remove 'Don't miss out'.",
            "source_type": "NLP Text Classifier (DistilBERT)",
            "gate_note": None,
            "verdict": "Likely concern, needs human review, not verified wrongdoing.",
            "bbox": None,
        },
        # 4. Rule-based Preselected Choice (high risk) — has the duplicate quirk
        {
            "text": "Add Rs 199 order protection",
            "category": "Preselected Choice",
            "is_dark_pattern": True,
            "confidence": 0.88,          # duplicate of heuristic_score
            "p_dark": 0.88,              # duplicate of rule_weight (quirk)
            "heuristic_score": 0.88,
            "risk_level": "High Risk",
            "xai_words": [
                {"word": "Add", "delta_p": 0.30, "rule_weight": 0.30},
                {"word": "order protection", "delta_p": 0.45, "rule_weight": 0.45},
            ],
            "explanation": "A pre-checked add-on charges the user unless they opt out.",
            "how_to_fix": "Uncheck the box by default. Let the user actively choose to add protection.",
            "source_type": "DOM Pre-selection Check (Rule-Based Heuristic)",
            "gate_note": None,
            "verdict": "Likely concern, needs human review, not verified wrongdoing.",
            "bbox": None,
        },
        # 5. Rule-based Misdirection (medium risk) — confirm-shaming
        {
            "text": "No thanks, I prefer paying full price.",
            "category": "Misdirection",
            "is_dark_pattern": True,
            "confidence": 0.72,          # duplicate
            "p_dark": 0.72,              # duplicate
            "heuristic_score": 0.72,
            "risk_level": "Medium Risk",
            "xai_words": [
                {"word": "No thanks", "delta_p": 0.20, "rule_weight": 0.20},
                {"word": "prefer paying full price", "delta_p": 0.40, "rule_weight": 0.40},
            ],
            "explanation": "Confirm-shaming: the decline option uses guilt language.",
            "how_to_fix": "Use a neutral decline: 'No, thanks' without implying the user is losing out.",
            "source_type": "Visual Asymmetry Check (Rule-Based Heuristic)",
            "gate_note": None,
            "verdict": "Likely concern, needs human review, not verified wrongdoing.",
            "bbox": None,
        },
        # 6. Pre-filter stub — NOT a real finding
        {
            "text": "Add to cart",
            "category": "Not Dark Pattern",
            "is_dark_pattern": False,
            "confidence": 0,
            "p_dark": 0.02,
            "heuristic_score": None,
            "risk_level": "None (Benign)",
            "xai_words": [],
            "explanation": "Standard action button.",
            "how_to_fix": "",
            "source_type": "Pre-filter: too short / common action",
            "gate_note": None,
            "verdict": "",
            "bbox": None,
        },
        # 7. Benign pre-selection — routine, not a flag
        {
            "text": "Remember me",
            "category": "Preselected Choice",
            "is_dark_pattern": False,
            "confidence": 0.15,
            "p_dark": 0.08,
            "heuristic_score": None,
            "risk_level": "Low Risk / Benign Pre-selection",
            "xai_words": [],
            "explanation": "A routine pre-ticked checkbox for user convenience.",
            "how_to_fix": "",
            "source_type": "DOM Pre-selection Check (Rule-Based Heuristic)",
            "gate_note": None,
            "verdict": "",
            "bbox": None,
        },
        # 8. Rule-based Disguised Ad (low risk, needs review)
        {
            "text": "Recommended for you: Premium Plan",
            "category": "Disguised Ad",
            "is_dark_pattern": True,
            "confidence": 0.55,
            "p_dark": 0.55,
            "heuristic_score": 0.55,
            "risk_level": "Low Risk (Needs Review)",
            "xai_words": [
                {"word": "Recommended", "delta_p": 0.25, "rule_weight": 0.25},
            ],
            "explanation": "Content styled as a recommendation may be a disguised ad or upsell.",
            "how_to_fix": "Label promotions clearly as 'Sponsored' or 'Ad'.",
            "source_type": "Disguised Ad Check (Rule-Based Heuristic)",
            "gate_note": "Kept because heuristic score exceeds threshold.",
            "verdict": "Likely concern, needs human review, not verified wrongdoing.",
            "bbox": None,
        },
        # 9. Unknown category "Foo Pattern" — tests fallback rendering
        {
            "text": "You will lose your progress if you leave.",
            "category": "Foo Pattern",
            "is_dark_pattern": True,
            "confidence": 0.65,
            "p_dark": 0.70,
            "heuristic_score": None,
            "risk_level": "Medium Risk",
            "xai_words": [
                {"word": "lose", "delta_p": 0.33},
                {"word": "progress", "delta_p": 0.18},
            ],
            "explanation": "Loss aversion language pressures users to stay.",
            "how_to_fix": "Let users leave without emotional pressure. Offer to save progress.",
            "source_type": "NLP Text Classifier (DistilBERT)",
            "gate_note": None,
            "verdict": "Likely concern, needs human review, not verified wrongdoing.",
            "bbox": None,
        },
    ]


def _clean_text_findings():
    """Findings for clean text — nothing flagged."""
    texts = [
        "Ships in 2 business days.",
        "Free returns within 30 days of delivery.",
        "Order summary",
        "Price includes all taxes.",
        "Add to cart",
    ]
    findings = []
    for text in texts:
        findings.append({
            "text": text,
            "category": "Not Dark Pattern",
            "is_dark_pattern": False,
            "confidence": 0.05,
            "p_dark": 0.03,
            "heuristic_score": None,
            "risk_level": "None (Benign)",
            "xai_words": [],
            "explanation": "Standard e-commerce copy.",
            "how_to_fix": "",
            "source_type": "NLP Text Classifier (DistilBERT)",
            "gate_note": None,
            "verdict": "",
            "bbox": None,
        })
    return findings


def _is_deceptive(texts):
    """Heuristic: if any text contains known deceptive keywords, treat as deceptive."""
    deceptive_words = [
        "hurry", "only", "left in stock", "miss out", "order protection",
        "prefer paying full price", "don't like saving", "auto-renews",
        "people are viewing",
    ]
    joined = " ".join(t.lower() for t in texts)
    return any(w in joined for w in deceptive_words)


def predict(texts, out, explain=True, surface="text", gate=True):
    """Mock predict: returns deceptive or clean findings based on content."""
    if _is_deceptive(texts):
        return _deceptive_text_findings()
    return _clean_text_findings()


def audit_html_dom(html, out):
    """Mock HTML audit: returns findings based on content."""
    # Treat the HTML as text lines for the deceptive check
    if _is_deceptive([html if isinstance(html, str) else html.decode("utf-8", errors="ignore")]):
        return _deceptive_text_findings()
    return _clean_text_findings()


def _is_image_deceptive(image_np):
    """Heuristic: check whether a mock screenshot contains deceptive patterns."""
    try:
        import cv2
        gray = cv2.cvtColor(image_np, cv2.COLOR_RGB2GRAY) if len(image_np.shape) == 3 else image_np
        if gray.std() < 5:
            return False  # blank / solid image is clean
        from PIL import Image, ImageDraw
        keywords = ["Hurry", "Only", "Offer", "left in stock"]
        for kw in keywords:
            im_kw = Image.new("L", (len(kw) * 8, 15), 255)
            d = ImageDraw.Draw(im_kw)
            d.text((0, 0), kw, fill=0)
            templ = np.array(im_kw, dtype=np.uint8)
            if gray.shape[0] >= templ.shape[0] and gray.shape[1] >= templ.shape[1]:
                res = cv2.matchTemplate(gray, templ, cv2.TM_CCOEFF_NORMED)
                if res.max() >= 0.70:
                    return True
    except Exception:
        pass
    return False


def analyze_screenshot(image_np, out):
    """Mock screenshot analysis: returns a dummy annotated image and findings."""
    h, w = image_np.shape[:2]
    annotated = image_np.copy()

    if _is_image_deceptive(image_np):
        findings = _deceptive_text_findings()[:4]
    else:
        findings = _clean_text_findings()

    box_h = h // max(1, len(findings) + 1)
    for i, f in enumerate(findings):
        y1 = i * box_h + 10
        f["bbox"] = [20, y1, max(21, w - 20), y1 + max(1, box_h - 20)]

    return annotated, findings


def summarize_findings(findings):
    """Mock summarize: mirrors the real engine's output shape."""
    flagged = [f for f in findings if f.get("is_dark_pattern")]
    if not findings:
        return {
            "status": "no_content",
            "overall_risk": "None",
            "total_items": 0,
            "flagged_items": 0,
            "by_category": {},
            "message": "No content to analyze.",
        }

    if not flagged:
        return {
            "status": "clean",
            "overall_risk": "None",
            "total_items": len(findings),
            "flagged_items": 0,
            "by_category": {},
            "message": "No dark patterns detected.",
        }

    by_cat = {}
    highest_risk = "Low Risk"
    risk_order = {"High Risk": 3, "Medium Risk": 2, "Low Risk": 1, "None": 0}
    max_rank = 0
    for f in flagged:
        cat = f.get("category", "Unknown")
        by_cat[cat] = by_cat.get(cat, 0) + 1
        rank = risk_order.get(f.get("risk_level", "").split(" (")[0], 0)
        if rank > max_rank:
            max_rank = rank
            highest_risk = f.get("risk_level", "Low Risk")

    return {
        "status": "flagged",
        "overall_risk": highest_risk,
        "total_items": len(findings),
        "flagged_items": len(flagged),
        "by_category": by_cat,
        "message": f"Found {len(flagged)} potential dark pattern(s).",
    }


def detect_countdown_timers(items):
    """Mock timer detection: flags items containing time patterns."""
    import re
    time_pattern = re.compile(r"\d{1,2}:\d{2}")
    findings = []
    for item in items:
        text = item.get("text", "")
        if time_pattern.search(text):
            findings.append({
                "text": text,
                "category": "Urgency",
                "is_dark_pattern": True,
                "confidence": 0.85,
                "p_dark": 0.88,
                "heuristic_score": None,
                "risk_level": "High Risk",
                "xai_words": [{"word": "countdown", "delta_p": 0.35}],
                "explanation": "A countdown timer creates artificial urgency.",
                "how_to_fix": "If the deadline is real, state it as a date. Remove the countdown.",
                "source_type": "NLP Text Classifier (DistilBERT)",
                "gate_note": None,
                "verdict": "Likely concern, needs human review, not verified wrongdoing.",
                "bbox": None,
            })
    return findings


def load_trained_bundle(out):
    """Mock model load: returns fake model, tokenizer, meta."""
    if "model" not in _MODEL_CACHE:
        # Simulate a short load time
        time.sleep(0.1)
        _MODEL_CACHE["model"] = "mock_model"
        _MODEL_CACHE["tokenizer"] = "mock_tokenizer"
        _MODEL_CACHE["meta"] = _MOCK_META.copy()
    return _MODEL_CACHE["model"], _MODEL_CACHE["tokenizer"], _MODEL_CACHE["meta"]


def get_mock_meta():
    """Return the mock meta.json dict (for tests and /api/model)."""
    return _MOCK_META.copy()
