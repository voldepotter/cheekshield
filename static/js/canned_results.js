export const CANNED_DECEPTIVE = {
  "api_version": "1",
  "request_id": "c81a3ca9-947c-4af7-8609-ad8319a499e2",
  "mode": "text",
  "elapsed_ms": 1,
  "model": {
    "name": "DistilBERT",
    "loaded_at": "2026-11-14T03:41:22.330467+00:00"
  },
  "summary": {
    "status": "flagged",
    "overall_risk": "High Risk",
    "total_items": 9,
    "flagged_items": 7,
    "checked_fine": 1,
    "routine_preselections": 1,
    "by_category": {
      "Urgency": 2,
      "Social Proof": 1,
      "Preselected Choice": 1,
      "Misdirection": 1,
      "Disguised Ad": 1,
      "Foo Pattern": 1
    },
    "message": "Found 7 potential dark pattern(s)."
  },
  "exposure": {
    "percent": 93,
    "band": "rotten",
    "label": "Rotten",
    "pressure": 4.309
  },
  "findings": [
    {
      "id": "f1",
      "text": "Hurry! Only 2 left in stock.",
      "category": "Urgency",
      "is_dark_pattern": true,
      "kind": "flag",
      "risk_rank": 3,
      "risk_label": "High Risk",
      "evidence_kind": "model",
      "score": 0.92,
      "score_label": "Confidence",
      "p_dark": 0.95,
      "attributions": [
        {
          "token": "Hurry!",
          "weight": 0.42,
          "unit": "delta_p"
        },
        {
          "token": "Only",
          "weight": 0.18,
          "unit": "delta_p"
        },
        {
          "token": "2 left",
          "weight": 0.25,
          "unit": "delta_p"
        }
      ],
      "explanation": "Creates artificial urgency by implying very limited stock.",
      "how_to_fix": "Show real-time stock levels without pressure language, e.g. 'Stock: 2 available'.",
      "verdict": "Likely concern, needs human review, not verified wrongdoing.",
      "gate_note": null,
      "source_type": "NLP Text Classifier (DistilBERT)",
      "bbox": null,
      "order": 0
    },
    {
      "id": "f2",
      "text": "8 people are viewing this item right now.",
      "category": "Social Proof",
      "is_dark_pattern": true,
      "kind": "flag",
      "risk_rank": 2,
      "risk_label": "Medium Risk",
      "evidence_kind": "model",
      "score": 0.78,
      "score_label": "Confidence",
      "p_dark": 0.82,
      "attributions": [
        {
          "token": "8 people",
          "weight": 0.31,
          "unit": "delta_p"
        },
        {
          "token": "viewing",
          "weight": 0.15,
          "unit": "delta_p"
        },
        {
          "token": "right now",
          "weight": 0.22,
          "unit": "delta_p"
        }
      ],
      "explanation": "Uses social proof to pressure the user by implying high demand.",
      "how_to_fix": "Remove real-time viewer counts or show verified purchase counts instead.",
      "verdict": "Likely concern, needs human review, not verified wrongdoing.",
      "gate_note": null,
      "source_type": "NLP Text Classifier (DistilBERT)",
      "bbox": null,
      "order": 1
    },
    {
      "id": "f3",
      "text": "Offer ends in 04:59. Don't miss out!",
      "category": "Urgency",
      "is_dark_pattern": true,
      "kind": "flag",
      "risk_rank": 3,
      "risk_label": "High Risk",
      "evidence_kind": "model",
      "score": 0.94,
      "score_label": "Confidence",
      "p_dark": 0.97,
      "attributions": [
        {
          "token": "ends in",
          "weight": 0.38,
          "unit": "delta_p"
        },
        {
          "token": "04:59",
          "weight": 0.29,
          "unit": "delta_p"
        },
        {
          "token": "Don't miss out!",
          "weight": 0.35,
          "unit": "delta_p"
        }
      ],
      "explanation": "Countdown timer and loss-aversion language create extreme urgency.",
      "how_to_fix": "If the deadline is real, state it plainly: 'Sale ends November 20'. Remove 'Don't miss out'.",
      "verdict": "Likely concern, needs human review, not verified wrongdoing.",
      "gate_note": null,
      "source_type": "NLP Text Classifier (DistilBERT)",
      "bbox": null,
      "order": 2
    },
    {
      "id": "f4",
      "text": "Add Rs 199 order protection",
      "category": "Preselected Choice",
      "is_dark_pattern": true,
      "kind": "flag",
      "risk_rank": 3,
      "risk_label": "High Risk",
      "evidence_kind": "rule",
      "score": 0.88,
      "score_label": "Rule score",
      "p_dark": null,
      "attributions": [
        {
          "token": "Add",
          "weight": 0.3,
          "unit": "rule_weight"
        },
        {
          "token": "order protection",
          "weight": 0.45,
          "unit": "rule_weight"
        }
      ],
      "explanation": "A pre-checked add-on charges the user unless they opt out.",
      "how_to_fix": "Uncheck the box by default. Let the user actively choose to add protection.",
      "verdict": "Likely concern, needs human review, not verified wrongdoing.",
      "gate_note": null,
      "source_type": "DOM Pre-selection Check (Rule-Based Heuristic)",
      "bbox": null,
      "order": 3
    },
    {
      "id": "f5",
      "text": "No thanks, I prefer paying full price.",
      "category": "Misdirection",
      "is_dark_pattern": true,
      "kind": "flag",
      "risk_rank": 2,
      "risk_label": "Medium Risk",
      "evidence_kind": "rule",
      "score": 0.72,
      "score_label": "Rule score",
      "p_dark": null,
      "attributions": [
        {
          "token": "No thanks",
          "weight": 0.2,
          "unit": "rule_weight"
        },
        {
          "token": "prefer paying full price",
          "weight": 0.4,
          "unit": "rule_weight"
        }
      ],
      "explanation": "Confirm-shaming: the decline option uses guilt language.",
      "how_to_fix": "Use a neutral decline: 'No, thanks' without implying the user is losing out.",
      "verdict": "Likely concern, needs human review, not verified wrongdoing.",
      "gate_note": null,
      "source_type": "Visual Asymmetry Check (Rule-Based Heuristic)",
      "bbox": null,
      "order": 4
    },
    {
      "id": "f6",
      "text": "Add to cart",
      "category": "Not Dark Pattern",
      "is_dark_pattern": false,
      "kind": "checked",
      "risk_rank": 0,
      "risk_label": "Benign",
      "evidence_kind": "model",
      "score": 0,
      "score_label": "Confidence",
      "p_dark": 0.02,
      "attributions": [],
      "explanation": "Standard action button.",
      "how_to_fix": "",
      "verdict": "",
      "gate_note": null,
      "source_type": "Pre-filter: too short / common action",
      "bbox": null,
      "order": 5
    },
    {
      "id": "f7",
      "text": "Remember me",
      "category": "Preselected Choice",
      "is_dark_pattern": false,
      "kind": "routine_preselection",
      "risk_rank": 0,
      "risk_label": "Benign",
      "evidence_kind": "rule",
      "score": 0,
      "score_label": "Rule score",
      "p_dark": null,
      "attributions": [],
      "explanation": "A routine pre-ticked checkbox for user convenience.",
      "how_to_fix": "",
      "verdict": "",
      "gate_note": null,
      "source_type": "DOM Pre-selection Check (Rule-Based Heuristic)",
      "bbox": null,
      "order": 6
    },
    {
      "id": "f8",
      "text": "Recommended for you: Premium Plan",
      "category": "Disguised Ad",
      "is_dark_pattern": true,
      "kind": "flag",
      "risk_rank": 1,
      "risk_label": "Low Risk",
      "evidence_kind": "rule",
      "score": 0.55,
      "score_label": "Rule score",
      "p_dark": null,
      "attributions": [
        {
          "token": "Recommended",
          "weight": 0.25,
          "unit": "rule_weight"
        }
      ],
      "explanation": "Content styled as a recommendation may be a disguised ad or upsell.",
      "how_to_fix": "Label promotions clearly as 'Sponsored' or 'Ad'.",
      "verdict": "Likely concern, needs human review, not verified wrongdoing.",
      "gate_note": "Kept because heuristic score exceeds threshold.",
      "source_type": "Disguised Ad Check (Rule-Based Heuristic)",
      "bbox": null,
      "order": 7
    },
    {
      "id": "f9",
      "text": "You will lose your progress if you leave.",
      "category": "Foo Pattern",
      "is_dark_pattern": true,
      "kind": "flag",
      "risk_rank": 2,
      "risk_label": "Medium Risk",
      "evidence_kind": "model",
      "score": 0.65,
      "score_label": "Confidence",
      "p_dark": 0.7,
      "attributions": [
        {
          "token": "lose",
          "weight": 0.33,
          "unit": "delta_p"
        },
        {
          "token": "progress",
          "weight": 0.18,
          "unit": "delta_p"
        }
      ],
      "explanation": "Loss aversion language pressures users to stay.",
      "how_to_fix": "Let users leave without emotional pressure. Offer to save progress.",
      "verdict": "Likely concern, needs human review, not verified wrongdoing.",
      "gate_note": null,
      "source_type": "NLP Text Classifier (DistilBERT)",
      "bbox": null,
      "order": 8
    }
  ],
  "warnings": []
};

export const CANNED_CLEAN = {
  "api_version": "1",
  "request_id": "869f9fa3-dba7-428f-893a-619a169deb8f",
  "mode": "text",
  "elapsed_ms": 0,
  "model": {
    "name": "DistilBERT",
    "loaded_at": "2026-11-14T03:41:22.330467+00:00"
  },
  "summary": {
    "status": "clean",
    "overall_risk": "None",
    "total_items": 5,
    "flagged_items": 0,
    "checked_fine": 5,
    "routine_preselections": 0,
    "by_category": {},
    "message": "No dark patterns detected."
  },
  "exposure": {
    "percent": 0,
    "band": "fresh",
    "label": "Fresh",
    "pressure": 0.0
  },
  "findings": [
    {
      "id": "f1",
      "text": "Ships in 2 business days.",
      "category": "Not Dark Pattern",
      "is_dark_pattern": false,
      "kind": "checked",
      "risk_rank": 0,
      "risk_label": "Benign",
      "evidence_kind": "model",
      "score": 0.05,
      "score_label": "Confidence",
      "p_dark": 0.03,
      "attributions": [],
      "explanation": "Standard e-commerce copy.",
      "how_to_fix": "",
      "verdict": "",
      "gate_note": null,
      "source_type": "NLP Text Classifier (DistilBERT)",
      "bbox": null,
      "order": 0
    },
    {
      "id": "f2",
      "text": "Free returns within 30 days of delivery.",
      "category": "Not Dark Pattern",
      "is_dark_pattern": false,
      "kind": "checked",
      "risk_rank": 0,
      "risk_label": "Benign",
      "evidence_kind": "model",
      "score": 0.05,
      "score_label": "Confidence",
      "p_dark": 0.03,
      "attributions": [],
      "explanation": "Standard e-commerce copy.",
      "how_to_fix": "",
      "verdict": "",
      "gate_note": null,
      "source_type": "NLP Text Classifier (DistilBERT)",
      "bbox": null,
      "order": 1
    },
    {
      "id": "f3",
      "text": "Order summary",
      "category": "Not Dark Pattern",
      "is_dark_pattern": false,
      "kind": "checked",
      "risk_rank": 0,
      "risk_label": "Benign",
      "evidence_kind": "model",
      "score": 0.05,
      "score_label": "Confidence",
      "p_dark": 0.03,
      "attributions": [],
      "explanation": "Standard e-commerce copy.",
      "how_to_fix": "",
      "verdict": "",
      "gate_note": null,
      "source_type": "NLP Text Classifier (DistilBERT)",
      "bbox": null,
      "order": 2
    },
    {
      "id": "f4",
      "text": "Price includes all taxes.",
      "category": "Not Dark Pattern",
      "is_dark_pattern": false,
      "kind": "checked",
      "risk_rank": 0,
      "risk_label": "Benign",
      "evidence_kind": "model",
      "score": 0.05,
      "score_label": "Confidence",
      "p_dark": 0.03,
      "attributions": [],
      "explanation": "Standard e-commerce copy.",
      "how_to_fix": "",
      "verdict": "",
      "gate_note": null,
      "source_type": "NLP Text Classifier (DistilBERT)",
      "bbox": null,
      "order": 3
    },
    {
      "id": "f5",
      "text": "Add to cart",
      "category": "Not Dark Pattern",
      "is_dark_pattern": false,
      "kind": "checked",
      "risk_rank": 0,
      "risk_label": "Benign",
      "evidence_kind": "model",
      "score": 0.05,
      "score_label": "Confidence",
      "p_dark": 0.03,
      "attributions": [],
      "explanation": "Standard e-commerce copy.",
      "how_to_fix": "",
      "verdict": "",
      "gate_note": null,
      "source_type": "NLP Text Classifier (DistilBERT)",
      "bbox": null,
      "order": 4
    }
  ],
  "warnings": []
};
