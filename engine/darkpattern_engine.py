"""
Multi-class dark-pattern text & visual auditor (Upgraded from yamanalab/ec-darkpattern).

Included Features:
  1. DistilBERT Multi-class Classifier with Website GroupSplit & Temperature Calibration
  2. Word-Level Explainability (XAI) via Leave-One-Out Masking (Delta p)
  3. Actionable Remediation (Explanation + Ethical UI Fix for every category)
  4. HTML/DOM Parser (Detects text patterns + pre-checked checkboxes + hidden low-contrast text)
  5. Screenshot Visual Auditor (EasyOCR + High-Recall Colored Subtext OCR + Button Asymmetry + Pre-ticked Checkbox + Countdown Timers)

Note on evidence types: findings from the NLP classifier carry a calibrated model probability
("confidence", "delta_p"). Findings from DOM / OpenCV rules carry a rule-based score. Both are exposed under
the same keys for UI compatibility, and rule-based findings are labelled "(Rule-Based Heuristic)" in "source_type".
"""
import argparse, glob, json, os, re, random
import numpy as np
import pandas as pd
import torch
import torch.nn as nn
from sklearn.metrics import classification_report, confusion_matrix, f1_score
from sklearn.metrics import precision_recall_fscore_support, fbeta_score
from sklearn.model_selection import GroupShuffleSplit
from transformers import AutoModelForSequenceClassification, AutoTokenizer

RARE_TO_OTHER = {"Obstruction", "Sneaking", "Forced Action"}  # too few samples each
OTHER = "Other Dark Pattern"
BENIGN = "Not Dark Pattern"

# Directory of this script, so the model is found even if the UI is launched from another directory
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
# Safety limits so large pages / screenshots cannot hang the demo
MAX_XAI_WORDS = 40      # the tokenizer truncates at 64 tokens anyway
MAX_LINES = 300         # max text lines analysed per HTML page
PRED_BATCH = 32         # inference batch size
MAX_IMG_SIDE = 2000     # screenshots larger than this are shrunk before OCR
MIN_OCR_CONF = 0.20     # lowered so faint/small subtext is not dropped
# Wording for the "likely concern vs verified wrongdoing" requirement
VERDICT_DARK = "Likely dark pattern - flagged by model/heuristic, needs human review (not verified wrongdoing)"
VERDICT_OK = "No suspicious pattern detected"
# Verdict for routine pre-ticked checkboxes (e.g. "Remember me", "Same billing address")
VERDICT_BENIGN_PRESELECT = "Routine pre-selected option - low risk, review only if it should not be ticked by default"
# P(dark) decision threshold used by predict()
DARK_THRESHOLD = 0.50
# Suffix for every finding produced by DOM / OpenCV rules rather than by the NLP model
HEURISTIC_TAG = " (Rule-Based Heuristic)"

# Feature 3: Actionable Remediation (Ethical Fixes & Explanations)
REMEDIATION_GUIDE = {
    "Scarcity": {
        "explanation": "Creates artificial fear of missing out (FOMO) by claiming limited stock or high demand.",
        "how_to_fix": "Show actual verified inventory counts calmly without dramatic phrasing like 'Hurry!' or 'Almost Gone!'."
    },
    "Urgency": {
        "explanation": "Pressures the user into immediate decision-making using countdown timers or expiring offers.",
        "how_to_fix": "State clear, honest offer validity dates without ticking pressure timers or fake deadline resets."
    },
    "Social Proof": {
        "explanation": "Manipulates user choice by claiming many other shoppers are viewing or buying the item right now.",
        "how_to_fix": "Display verified customer reviews and ratings instead of unverified real-time viewer popups."
    },
    "Misdirection": {
        "explanation": "Uses confirmshaming, guilt-pping language, or visual asymmetry to steer users away from opting out.",
        "how_to_fix": "Use neutral, respectful wording ('No, thank you') and equal visual weight (size/color) for both accept and decline buttons."
    },
    "Preselected Choice": {
        "explanation": "Automatically opts the user into paid add-ons, donations, or newsletters without explicit consent.",
        "how_to_fix": "Leave all optional checkboxes unticked by default so users consciously choose what to add."
    },
    "Disguised Ad": {
        "explanation": "Advertising dressed up as navigation, content or a system notification so users click it without realising it is an ad.",
        "how_to_fix": "Label paid placements clearly ('Ad' / 'Sponsored') in a visible, distinct style, keep them out of the navigation bar, and never style promos as system notifications."
    },
    "Other Dark Pattern": {
        "explanation": "Contains potentially manipulative framing such as sneaking extra fees, forced action, or obstruction.",
        "how_to_fix": "Make all fees, subscription terms, and one-click cancellation paths transparent upfront."
    }
}


# =====================================================================
# V2 + V3.2: CONTEXT GATING, OCR TYPO FIXES, LINE MERGING, SYNTHETIC HARD NEGATIVES
# =====================================================================
SURFACE_MIN_THRESHOLD = {"text": 0.50, "html": 0.65, "screenshot": 0.80}
MIN_WORDS_SCREENSHOT = 3      # fragments shorter than this are not classified unless they hold pressure wording
STRONG_OVERRIDE = 0.97        # a very confident multi-word sentence skips the keyword gate

_URGENCY_RE = re.compile(
    r"(hurry|ends?\s+(in|soon|today|tonight|at)\b|offer\s+ends|sale\s+ends|deal\s+ends|limited[- ]time|last\s+chance|"
    r"today\s+only|only\s+today|expires?\b|expiring|act\s+(now|fast)|don'?t\s+miss|before\s+(it'?s|they'?re)\s+gone|"
    r"running\s+out\s+of\s+time|order\s+(within|in\b)|\b\d{1,2}:\d{2}(:\d{2})?\b|"
    r"\b\d+\s*(hrs?|hours?|mins?|minutes?|secs?|seconds?)\s*(left|remaining)?|flash\s+sale|now\s+or\s+never|"
    r"closing\s+soon|final\s+(hours|call)|"
    r"\b\d{1,2}\s?h(?:rs?|ours?)?\s*\d{1,2}\s?m(?:ins?)?(?:\s*\d{1,2}\s?s(?:ecs?)?)?\b)", re.I)
_SCARCITY_RE = re.compile(
    r"(only\s+\d+\s*(left|remaining|available|in\s+stock)|\b\d+\s*(left|remaining)\b|left\s+in\s+stock|"
    r"almost\s+(gone|sold\s+out)|selling\s+(out\s+)?fast|low\s+(in\s+)?stock|few\s+(items?\s+|pieces?\s+|units?\s+)?left|"
    r"limited\s+(stock|quantity|quantities|edition|supply)|last\s+\d+|last\s+(one|piece|unit)|going\s+fast|"
    r"in\s+high\s+demand|nearly\s+sold\s+out|while\s+(stocks?|supplies)\s+last|hurry)", re.I)
_SOCIAL_RE = re.compile(
    r"(\d[\d,.]*\s*[kKmM]?\+?\s*(people|persons|customers|shoppers|users|buyers|others|visitors)|"
    r"(people|others|customers|shoppers)\s+(are\s+)?(viewing|looking|watching|buying|bought|purchased)|"
    r"\d[\d,.]*\s*[kKmM]?\+?\s*(bought|sold|purchased)|bought\s+(in|this|recently)|recently\s+(bought|purchased|sold)|"
    r"best[- ]?sell|trending|most\s+popular|top[- ]?selling|popular\s+choice|in\s+(their|\d+)\s+carts?|"
    r"sold\s+in\s+the\s+(last|past)|viewing\s+(this|now)|just\s+(bought|purchased|booked))", re.I)
_SHAMING_RE = re.compile(
    r"(no,?\s*(thanks|thank\s+you)?,?\s*i\s*(don'?t|do\s+not|prefer|hate|like|would\s+rather|'?ll|will)|"
    r"i\s*(don'?t|do\s+not)\s*(want|need|like|care)|i('?ll|\s+will)\s*(pay|miss|stay|skip|lose)|i\s*(prefer|hate)|"
    r"miss\s+out|rather\s+(pay|not|lose)|not\s+interested\s+in\s+(saving|deals|discounts)|full\s+price|"
    r"i'?m\s+(fine|ok)\s+(with|without)|give\s+up)", re.I)
_COST_RE = re.compile(
    r"(\bfees?\b|\bcharg(e|es|ed)\b|auto[- ]?renew|\bsubscri|free\s+trial|\btrial\b|\brecurring\b|\bbilled\b|"
    r"non-?refundable|processing|convenience|handling|\bsurcharge\b|\bcancel)", re.I)

# Plain delivery information is a fact, not pressure ("Delivery in 4 days", "Delivery by 16 Nov, Mon")
_DELIVERY_RE = re.compile(r"\b(deliver\w*|ship\w*|dispatch\w*|arriv\w*)\b", re.I)
# Ratings, review counts, prices, discounts, dates: formatting, not claims
_FORMAT_ONLY_RE = re.compile(
    r"^(?:[\d\s,.%↓↑₹$€£/\-–+★⭐*()]|\boff\b|\bmrp\b|\bemi\b|\bper\b|\bmo\b|\bratings?\b|\breviews?\b|"
    r"\b(?:jan|feb|mar|apr|may|jun|jul|aug|sep|oct|nov|dec)\w*\b|\b(?:mon|tue|wed|thu|fri|sat|sun)\w*\b)+$", re.I)
# Standard storefront chrome
_STD_UI_RE = re.compile(
    r"^(?:add\s+to\s+(?:cart|bag|wishlist)|buy\s+(?:now|at\b.*)|go\s+to\s+cart|view\s+cart|checkout|log\s*in|"
    r"sign\s*(?:in|up)|search\b.*|home|cart|more|apply|select\s+(?:size|colou?r|delivery\s+location|capacity)\b.*|size\s+chart|"
    r"see\s+other\s+sellers|product\s+highlights|all\s+details|delivery\s+details|bank\s+offers|"
    r"credit\s+card\b.*|best\s+value\s+for\s+you|\d+-?\s*day\s+return|cash\s+on\s+delivery|customer\s+support|flipkart\s+assured)$", re.I)


def _fix_ocr_timer_typos(text):
    """Fixes common OCR misreads inside timer expressions (OOh -> 00h, 00n -> 00h, 26rn -> 26m, 435 -> 43s)."""
    t = str(text or "")
    fix_digits = str.maketrans({"O": "0", "o": "0", "I": "1", "l": "1", "|": "1", "S": "5"})
    t = re.sub(r"\b([OoIl|0-9]{1,2})\s?[hHnN]\b", lambda m: m.group(1).translate(fix_digits) + "h", t)
    t = re.sub(r"\b([OoIl|0-9]{1,2})\s?(?:m|rn|nn)\b", lambda m: m.group(1).translate(fix_digits) + "m", t)
    t = re.sub(r"\b([OoIl|0-9]{1,2})\s?[sS]\b", lambda m: m.group(1).translate(fix_digits) + "s", t)
    t = re.sub(r"(\d{1,2}\s?m\s+\d{1,2})[58]\b", r"\1s", t, flags=re.I)
    return t


def should_classify(text):
    """False for fragments the text model cannot judge reliably (formatting, chrome, plain delivery info,
    very short snippets without any pressure wording)."""
    t = _fix_ocr_timer_typos(re.sub(r"\s+", " ", str(text or "")).strip())
    if len(t) < 2:
        return False
    pressure = bool(_URGENCY_RE.search(t) or _SCARCITY_RE.search(t) or re.search(r"\border\s+(?:in|within)\b", t, re.I))
    if pressure:
        return True
    if t.count(" / ") >= 2 or t.count("/") >= 3:        # breadcrumbs
        return False
    if _FORMAT_ONLY_RE.match(t) or _STD_UI_RE.match(t):
        return False
    if _DELIVERY_RE.search(t):
        return False
    if len(t.split()) < MIN_WORDS_SCREENSHOT and not (_SOCIAL_RE.search(t) or _SHAMING_RE.search(t)):
        return False
    return True


def context_gate(text, cat, p_dark):
    """Second opinion on a model flag. A category is kept only if the wording that defines it is present
    (Urgency needs deadline/countdown wording, Social Proof needs crowd/popularity wording, ...).
    Returns (keep, note). A very confident, full-sentence prediction overrides the gate."""
    t = _fix_ocr_timer_typos(str(text or ""))
    if p_dark >= STRONG_OVERRIDE and len(t.split()) >= 5 and cat not in ("Urgency", "Scarcity", "Social Proof"):
        return True, None
    need = {
        "Urgency": (_URGENCY_RE, "no deadline / countdown wording"),
        "Scarcity": (_SCARCITY_RE, "no stock / quantity wording"),
        "Social Proof": (_SOCIAL_RE, "no crowd / popularity wording (plain ratings are fine)"),
        "Misdirection": (_SHAMING_RE, "no confirmshaming wording"),
    }
    if cat in need:
        rx, why = need[cat]
        if not rx.search(t):
            return False, f"Downgraded by context gate: {why}"
    elif cat == OTHER:
        if not (_COST_RE.search(t) or _URGENCY_RE.search(t)):
            return False, "Downgraded by context gate: no fee / subscription / pressure wording"
    return True, None


def merge_ocr_boxes(items, max_words=40):
    """Merges raw OCR word/phrase boxes into lines and wrapped paragraphs so the classifier sees whole
    sentences instead of fragments. items: [{'bbox': (x1,y1,x2,y2), 'text': str, 'conf': float}].
    Boxes are joined only when close together, and timer/deadline lines are kept separate from delivery headers."""
    if not items:
        return []
    items = sorted(items, key=lambda d: ((d["bbox"][1] + d["bbox"][3]) / 2.0, d["bbox"][0]))
    # 1) group boxes into visual rows
    rows = []
    for it in items:
        x1, y1, x2, y2 = it["bbox"]
        cy, h = (y1 + y2) / 2.0, max(1, y2 - y1)
        for row in rows:
            if abs(cy - row["cy"]) <= 0.5 * max(h, row["h"]):
                row["items"].append(it)
                n = len(row["items"])
                row["cy"] += (cy - row["cy"]) / n
                row["h"] = max(row["h"], h)
                break
        else:
            rows.append({"cy": cy, "h": h, "items": [it]})
    # 2) inside a row, join neighbours with a small horizontal gap
    segs = []
    for row in rows:
        cur = None
        for it in sorted(row["items"], key=lambda d: d["bbox"][0]):
            x1, y1, x2, y2 = it["bbox"]
            h = max(1, y2 - y1)
            if cur is not None and (x1 - cur["bbox"][2]) <= 1.2 * max(h, cur["h"]):
                b = cur["bbox"]
                cur["bbox"] = (min(b[0], x1), min(b[1], y1), max(b[2], x2), max(b[3], y2))
                cur["text"] += " " + it["text"]
                cur["conf"] = min(cur["conf"], it["conf"])
                cur["h"] = max(cur["h"], h)
            else:
                if cur is not None:
                    segs.append(cur)
                cur = {"bbox": (x1, y1, x2, y2), "text": it["text"], "conf": it["conf"], "h": h}
        if cur is not None:
            segs.append(cur)
    # 3) stack left-aligned, similar-height lines with tight spacing into one paragraph
    # Never merge a countdown/deadline line ("Order in 00h 26m 43s") with a normal line ("Delivery by 17 Nov")
    segs.sort(key=lambda d: (d["bbox"][1], d["bbox"][0]))
    blocks = []
    for sg in segs:
        x1, y1, x2, y2 = sg["bbox"]
        h = max(1, y2 - y1)
        sg_norm = _fix_ocr_timer_typos(sg["text"])
        sg_is_timer = bool(_URGENCY_RE.search(sg_norm) or re.search(r"\border\s+(?:in|within)\b", sg_norm, re.I))
        target = None
        if not sg_is_timer:
            for b in reversed(blocks[-6:]):
                b_norm = _fix_ocr_timer_typos(b["text"])
                if _URGENCY_RE.search(b_norm) or re.search(r"\border\s+(?:in|within)\b", b_norm, re.I):
                    continue
                bx1, by1, bx2, by2 = b["bbox"]
                vgap = y1 - by2
                ratio = h / float(max(1, b["h"]))
                if (-2 <= vgap <= 0.45 * max(h, b["h"]) and abs(x1 - b["last_x1"]) <= 0.8 * max(h, b["h"])
                        and 0.75 <= ratio <= 1.35 and len((b["text"] + " " + sg["text"]).split()) <= max_words):
                    target = b
                    break
        if target is None:
            blocks.append({"bbox": sg["bbox"], "text": sg["text"], "conf": sg["conf"], "h": h, "last_x1": x1})
        else:
            bb = target["bbox"]
            target["bbox"] = (min(bb[0], x1), min(bb[1], y1), max(bb[2], x2), max(bb[3], y2))
            target["text"] += " " + sg["text"]
            target["conf"] = min(target["conf"], sg["conf"])
            target["last_x1"] = x1
    return [{"bbox": b["bbox"], "text": re.sub(r"\s+", " ", b["text"]).strip(), "conf": b["conf"]} for b in blocks]


def _skipped_finding(text):
    """Benign stub for fragments filtered out before the classifier (keeps UI keys intact)."""
    return {
        "text": text, "category": BENIGN, "is_dark_pattern": False, "confidence": 0.0, "p_dark": 0.0,
        "risk_level": "None (Benign)", "xai_words": [],
        "explanation": "Formatting, standard storefront text or a short fragment; no manipulative framing detected.",
        "how_to_fix": "No changes needed.",
        "source_type": "Pre-filter (formatting / short UI text)" + HEURISTIC_TAG, "verdict": VERDICT_OK,
    }


# ---- synthetic contrast pairs: teach the model that PRESSURE wording, not topic, makes a dark pattern ----
def synthetic_context_pairs(n_each=200, seed=0):
    rnd = random.Random(seed)
    months = ["Nov", "Dec", "Jan", "Feb", "Mar"]
    wdays = ["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"]
    sellers = ["RetailNet", "Sai Traders", "Fashion Hub", "Metro Store"]
    N = lambda a, b: rnd.randint(a, b)
    benign_tpl = [
        lambda: f"Delivery by {N(1,28)} {rnd.choice(months)}, {rnd.choice(wdays)}",
        lambda: f"Delivery in {N(2,7)} days",
        lambda: f"Get it by {rnd.choice(wdays)}, {N(1,28)} {rnd.choice(months)}",
        lambda: f"Free delivery on orders above Rs {N(2,9)*100}",
        lambda: f"Estimated delivery {N(2,4)}-{N(5,8)} business days",
        lambda: f"{rnd.choice([3.8,4.0,4.1,4.3,4.5])} out of 5 ({N(100,9000):,} ratings)",
        lambda: f"Rated {rnd.choice([3.9,4.2,4.4])} based on {N(50,5000):,} verified reviews",
        lambda: f"Buy at Rs {N(2,99)*10}",
        lambda: f"Save Rs {N(5,50)*10} with bank offers",
        lambda: f"{N(10,80)}% off on selected styles",
        lambda: f"Offer valid till {N(1,28)} {rnd.choice(months)} 2026",
        lambda: "Apply offers for maximum savings",
        lambda: "Additional benefits on this purchase",
        lambda: f"{N(7,30)}-day return policy",
        lambda: "Cash on delivery available",
        lambda: f"Fulfilled by {rnd.choice(sellers)}",
        lambda: "Pure cotton fabric with self design pattern",
        lambda: "Select your size and colour to continue",
        lambda: "Your order has been placed successfully",
        lambda: "Enter your delivery location to check availability",
    ]
    dark_tpl = {
        "Urgency": [
            lambda: f"Hurry! Offer ends in {N(1,12)} hours",
            lambda: "Sale ends tonight - order now",
            lambda: f"Deal expires in 00:{N(10,59)}:{N(10,59)}",
            lambda: "Last chance! Only today",
            lambda: f"Order within {N(1,5)} hrs {N(1,59)} mins to get this price",
            lambda: f"Order in 00h {N(10,59)}m {N(10,59)}s",
            lambda: f"Order in {N(5,55)} minutes",
        ],
        "Scarcity": [
            lambda: f"Only {N(1,5)} left in stock - order soon",
            lambda: "Hurry, almost sold out!",
            lambda: f"Only {N(1,4)} items remaining at this price",
            lambda: "Selling fast! Limited stock available",
            lambda: f"Just {N(1,9)} pieces left - don't miss out",
            lambda: f"Only {N(1,9)} units left, buy before they're gone",
            lambda: f"Low stock: {N(1,9)} left in size {rnd.choice(['S','M','L','XL'])}",
            lambda: f"Almost gone! {N(1,9)} remaining",
            lambda: "Limited quantity available - grab yours now",
        ],
        "Social Proof": [
            lambda: f"{N(12,300)} people are viewing this right now",
            lambda: f"{N(20,900)} bought this in the last 24 hours",
            lambda: f"{N(3,40)} others have this in their carts",
            lambda: f"Trending now - {N(50,999)} sold today",
        ],
        "Misdirection": [
            lambda: "No thanks, I don't want to save money",
            lambda: "No, I'll pay full price",
            lambda: "I prefer to miss out on this deal",
            lambda: "No thanks, I don't like free shipping",
            lambda: "No, I don't want to save " + f"Rs {N(1,9)*100}",
            lambda: "I'll skip the discount and pay more",
            lambda: "No, I'd rather not get exclusive offers",
            lambda: "No thanks, I enjoy paying full price",
        ],
    }
    rows = [{"text": rnd.choice(benign_tpl)(), "Pattern Category": BENIGN, "page_id": f"synthetic_b{i}"}
            for i in range(n_each)]
    cats = list(dark_tpl)
    for i in range(n_each):
        c = cats[i % len(cats)]
        rows.append({"text": rnd.choice(dark_tpl[c])(), "Pattern Category": c, "page_id": f"synthetic_d{i}"})
    df = pd.DataFrame(rows).drop_duplicates("text").reset_index(drop=True)
    df["label_name"] = df["Pattern Category"]
    return df


def build_extra_train_frame(a, c2i):
    """Synthetic contrast pairs + user-supplied TSVs (e.g. OCR text from your screenshots).
    These go into TRAIN ONLY, so validation / test numbers stay comparable with the original dataset."""
    frames = []
    if a.synthetic > 0:
        frames.append(synthetic_context_pairs(a.synthetic, a.seed))
    for p in (a.extra_data or []):
        frames.append(load_data(p))
    if not frames:
        return pd.DataFrame(columns=["text", "label_name", "y"])
    ex = pd.concat(frames, ignore_index=True)
    unknown = sorted(set(ex["label_name"]) - set(c2i))
    if unknown:
        print(f"WARNING: dropping extra rows with labels not in the base dataset: {unknown}")
        ex = ex[ex["label_name"].isin(c2i)]
    ex = ex.copy()
    ex["y"] = ex["label_name"].map(c2i)
    ex = pd.concat([ex] * max(1, a.extra_repeat), ignore_index=True)
    print(f"extra training rows: {len(ex)} -> {ex['label_name'].value_counts().to_dict()}")
    return ex[["text", "label_name", "y"]]


# ---- turn screenshots into training data ----
_IMG_EXT = (".png", ".jpg", ".jpeg", ".webp", ".bmp")


def _get_ocr_reader():
    import easyocr
    if "_OCR_READER" not in _MODEL_CACHE:
        _MODEL_CACHE["_OCR_READER"] = easyocr.Reader(["en"], gpu=torch.cuda.is_available(), verbose=False)
    return _MODEL_CACHE["_OCR_READER"]


def _load_rgb(path):
    import cv2
    bgr = cv2.imread(path)
    if bgr is None:
        raise ValueError(f"Cannot read image: {path}")
    img = cv2.cvtColor(bgr, cv2.COLOR_BGR2RGB)
    if max(img.shape[:2]) > MAX_IMG_SIDE:
        s = MAX_IMG_SIDE / float(max(img.shape[:2]))
        img = cv2.resize(img, (int(img.shape[1] * s), int(img.shape[0] * s)), interpolation=cv2.INTER_AREA)
    return img


def ocr_merged_lines(img):
    reader = _get_ocr_reader()
    raw = []
    for (bbox, text, conf) in reader.readtext(img):
        t = text.strip()
        if len(t) < 2 or conf < MIN_OCR_CONF:
            continue
        pts = np.array(bbox, dtype=np.int32)
        raw.append({"bbox": (int(pts[:, 0].min()), int(pts[:, 1].min()), int(pts[:, 0].max()), int(pts[:, 1].max())),
                    "text": t, "conf": float(conf)})
    return merge_ocr_boxes(raw)


def _list_images(d):
    return sorted(p for p in glob.glob(os.path.join(d, "*")) if p.lower().endswith(_IMG_EXT))


def build_from_images(img_dir, label, tsv_out, out="outputs/model"):
    """OCR every screenshot in img_dir and write a TSV usable with --extra_data."""
    rows = []
    for path in _list_images(img_dir):
        stem = os.path.splitext(os.path.basename(path))[0]
        lines = [m["text"] for m in ocr_merged_lines(_load_rgb(path)) if len(m["text"]) >= 3]
        if label == "predict":
            preds = predict(lines, out=out, explain=False, surface="screenshot") if lines else []
            cats = [p["category"] for p in preds]
        else:
            cats = [BENIGN] * len(lines)
        rows += [{"text": t, "Pattern Category": c, "page_id": "img_" + stem} for t, c in zip(lines, cats)]
        print(f"{os.path.basename(path)}: {len(lines)} text lines")
    pd.DataFrame(rows).to_csv(tsv_out, sep="\t", index=False)
    print(f"wrote {len(rows)} rows to {tsv_out}")


DEFAULT_YOLO_MAP = [  # keyword in the YOLO class name -> category used by this project
    ("scarc", "Scarcity"), ("urgen", "Urgency"), ("countdown", "Urgency"), ("timer", "Urgency"),
    ("social", "Social Proof"), ("proof", "Social Proof"), ("misdir", "Misdirection"), ("shaming", "Misdirection"),
    ("preselect", "Preselected Choice"), ("pre-select", "Preselected Choice"), ("checkbox", "Preselected Choice"),
]


def yolo_name_to_category(name):
    n = name.lower()
    for kw, cat in DEFAULT_YOLO_MAP:
        if kw in n:
            return cat
    return OTHER


def build_from_yolo(img_dir, label_dir, names_file, tsv_out):
    """Uses a YOLO-formatted dark-pattern dataset (images + .txt boxes) as TEXT training data."""
    if names_file.lower().endswith((".yaml", ".yml")):
        import yaml
        nm = yaml.safe_load(open(names_file))["names"]
        names = [nm[k] for k in sorted(nm)] if isinstance(nm, dict) else list(nm)
    else:
        names = [l.strip() for l in open(names_file) if l.strip()]
    cmap = {i: yolo_name_to_category(n) for i, n in enumerate(names)}
    print("class mapping:", {names[i]: c for i, c in cmap.items()})
    rows = []
    for path in _list_images(img_dir):
        stem = os.path.splitext(os.path.basename(path))[0]
        lab = os.path.join(label_dir, stem + ".txt")
        img = _load_rgb(path)
        H, W = img.shape[:2]
        boxes = []
        if os.path.exists(lab):
            for ln in open(lab):
                p = ln.split()
                if len(p) >= 5:
                    c, cx, cy, w, h = int(p[0]), *map(float, p[1:5])
                    boxes.append(((cx - w / 2) * W, (cy - h / 2) * H, (cx + w / 2) * W, (cy + h / 2) * H, cmap.get(c, OTHER)))
        for m in ocr_merged_lines(img):
            if len(m["text"]) < 3:
                continue
            best, cat = 0.5, BENIGN
            for b in boxes:
                f = _overlap_frac(m["bbox"], b[:4])
                if f >= best:
                    best, cat = f, b[4]
            rows.append({"text": m["text"], "Pattern Category": cat, "page_id": "yolo_" + stem})
    df = pd.DataFrame(rows)
    df.to_csv(tsv_out, sep="\t", index=False)
    print(f"wrote {len(df)} rows to {tsv_out}:", df["Pattern Category"].value_counts().to_dict())


def seed_all(s):
    random.seed(s); np.random.seed(s); torch.manual_seed(s)


def norm(t):  # used only to detect near-duplicates
    return re.sub(r"\d+", "0", re.sub(r"\s+", " ", str(t).lower())).strip()


def load_data(path):
    df = pd.read_csv(path, sep="\t")
    need = {"text", "Pattern Category", "page_id"}
    missing = need - set(df.columns)
    if missing:
        raise ValueError(f"Dataset is missing columns {sorted(missing)}; found {list(df.columns)}")
    df = df.dropna(subset=["text"])
    df["text"] = df["text"].astype(str)

    cat = df["Pattern Category"].fillna(BENIGN).astype(str).str.strip()
    cat = cat.replace({"": BENIGN, "None": BENIGN, "none": BENIGN, "N/A": BENIGN, "nan": BENIGN})
    if "label" in df.columns:  # label 0 means "not a dark pattern" in ec-darkpattern
        cat = cat.where(pd.to_numeric(df["label"], errors="coerce").fillna(1) != 0, BENIGN)
    df["Pattern Category"] = cat

    df["page_id"] = df["page_id"].astype(object)
    nan_mask = df["page_id"].isna()
    df.loc[nan_mask, "page_id"] = ["missing_%d" % i for i in df.index[nan_mask]]

    df["label_name"] = df["Pattern Category"].replace({c: OTHER for c in RARE_TO_OTHER})
    df["norm"] = df["text"].map(norm)
    df = df.sort_values("label_name", key=lambda s: s == BENIGN, kind="stable")
    before = len(df)
    df = df.drop_duplicates("norm").reset_index(drop=True)
    print(f"dedup: {before} -> {len(df)} rows")
    return df


def group_split(df, seed):
    """70/15/15 split where all rows of one website stay in one split."""
    g = df["page_id"].values
    gss = GroupShuffleSplit(n_splits=1, test_size=0.30, random_state=seed)
    tr, rest = next(gss.split(df, groups=g))
    rest_df = df.iloc[rest]
    gss2 = GroupShuffleSplit(n_splits=1, test_size=0.50, random_state=seed)
    va, te = next(gss2.split(rest_df, groups=rest_df["page_id"].values))
    return df.iloc[tr], rest_df.iloc[va], rest_df.iloc[te]


class DS(torch.utils.data.Dataset):
    def __init__(self, texts, labels, tok, max_len):
        self.enc = tok(list(texts), truncation=True, max_length=max_len)
        self.labels = list(labels)

    def __len__(self):
        return len(self.labels)

    def __getitem__(self, i):
        d = {k: v[i] for k, v in self.enc.items()}
        d["labels"] = self.labels[i]
        return d


def collate(tok):
    def f(batch):
        labels = torch.tensor([b.pop("labels") for b in batch])
        out = tok.pad(batch, return_tensors="pt")
        out["labels"] = labels
        return out
    return f


@torch.no_grad()
def get_logits(model, dl, dev):
    model.eval(); outs, ys = [], []
    for b in dl:
        y = b.pop("labels")
        b = {k: v.to(dev) for k, v in b.items()}
        outs.append(model(**b).logits.float().cpu()); ys.append(y)
    return torch.cat(outs), torch.cat(ys)


def fit_temperature(logits, y):
    """Temperature scaling on the validation set (calibrated confidence)."""
    t = nn.Parameter(torch.ones(1))
    opt = torch.optim.LBFGS([t], lr=0.1, max_iter=100)
    ce = nn.CrossEntropyLoss()

    def closure():
        opt.zero_grad(); loss = ce(logits / t, y); loss.backward(); return loss
    opt.step(closure)
    return float(t.clamp(0.05, 10.0).item())


def train(a):
    """Fine-tunes DistilBERT on the labelled dataset, calibrates it, evaluates it and saves everything."""
    seed_all(a.seed)
    dev = "cuda" if torch.cuda.is_available() else "cpu"
    df = load_data(a.data)

    classes = sorted(df["label_name"].unique())
    c2i = {c: i for i, c in enumerate(classes)}
    df["y"] = df["label_name"].map(c2i)
    if BENIGN not in classes:
        print(f"WARNING: class '{BENIGN}' not found in dataset, check the 'Pattern Category' values: {classes}")

    tr, va, te = group_split(df, a.seed)
    xtra = build_extra_train_frame(a, c2i)
    if len(xtra):
        tr = pd.concat([tr, xtra], ignore_index=True)

    print("classes:", classes)
    for n, d in [("train", tr), ("val", va), ("test", te)]:
        print(n, len(d), d["label_name"].value_counts().to_dict())

    tok = AutoTokenizer.from_pretrained(a.model)
    model = AutoModelForSequenceClassification.from_pretrained(
        a.model, num_labels=len(classes)).to(dev)
    mk = lambda d, sh: torch.utils.data.DataLoader(
        DS(d["text"], d["y"], tok, a.max_len), batch_size=a.bs, shuffle=sh,
        collate_fn=collate(tok))
    dl_tr, dl_va, dl_te = mk(tr, True), mk(va, False), mk(te, False)

    cnt = np.bincount(tr["y"], minlength=len(classes)).astype(float)
    w = torch.tensor(cnt.sum() / (len(classes) * np.maximum(cnt, 1)), dtype=torch.float).to(dev)
    loss_fn = nn.CrossEntropyLoss(weight=w, label_smoothing=0.05)

    opt = torch.optim.AdamW(model.parameters(), lr=a.lr, weight_decay=0.01)
    steps = a.epochs * len(dl_tr)
    sched = torch.optim.lr_scheduler.LambdaLR(
        opt, lambda s: min((s + 1) / (0.1 * steps), max(0.0, (steps - s) / (0.9 * steps))))
    try:
        scaler = torch.amp.GradScaler(dev, enabled=(dev == "cuda"))
    except Exception:
        scaler = torch.cuda.amp.GradScaler(enabled=(dev == "cuda"))

    best, bad = -1, 0
    os.makedirs(a.out, exist_ok=True)
    for ep in range(a.epochs):
        model.train()
        for b in dl_tr:
            y = b.pop("labels").to(dev)
            b = {k: v.to(dev) for k, v in b.items()}
            with torch.autocast(device_type=dev, dtype=torch.float16, enabled=(dev == "cuda")):
                logits = model(**b).logits

            loss = loss_fn(logits.float(), y)
            opt.zero_grad(); scaler.scale(loss).backward()
            scaler.unscale_(opt); nn.utils.clip_grad_norm_(model.parameters(), 1.0)
            scaler.step(opt); scaler.update(); sched.step()

        lv, yv = get_logits(model, dl_va, dev)
        f1 = f1_score(yv, lv.argmax(1), average="macro", zero_division=0)
        print(f"epoch {ep+1}: val macro-F1 = {f1:.4f}")
        if f1 > best:
            best, bad = f1, 0
            model.save_pretrained(a.out); tok.save_pretrained(a.out)
        else:
            bad += 1
            if bad >= a.patience:
                print("early stop"); break

    model = AutoModelForSequenceClassification.from_pretrained(a.out).to(dev)
    lv, yv = get_logits(model, dl_va, dev)
    T = fit_temperature(lv, yv)
    lt, yt = get_logits(model, dl_te, dev)
    pred = lt.argmax(1).numpy()
    yt = yt.numpy()
    all_labels = list(range(len(classes)))
    rep = classification_report(yt, pred, labels=all_labels, target_names=classes, output_dict=True, zero_division=0)
    print(classification_report(yt, pred, labels=all_labels, target_names=classes, zero_division=0))
    cm = confusion_matrix(yt, pred, labels=all_labels)
    print(pd.DataFrame(cm, index=classes, columns=classes))

    binary = None
    if BENIGN in classes:
        b_idx = classes.index(BENIGN)
        yb, pb = (yt != b_idx).astype(int), (pred != b_idx).astype(int)
        p_, r_, f_, _ = precision_recall_fscore_support(yb, pb, average="binary", zero_division=0)
        binary = {"precision": float(p_), "recall": float(r_), "f1": float(f_)}
        print(f"binary (dark vs benign) -> precision={p_:.3f} recall={r_:.3f} f1={f_:.3f}")

    dark_thr, binary_tuned = DARK_THRESHOLD, None
    if BENIGN in classes:
        b_idx = classes.index(BENIGN)
        pv = (1.0 - torch.softmax(lv / T, dim=-1)[:, b_idx]).numpy()
        yvb = (yv.numpy() != b_idx).astype(int)
        best_fb = -1.0
        for thr in np.arange(0.50, 0.951, 0.025):
            fb = fbeta_score(yvb, (pv > thr).astype(int), beta=0.5, zero_division=0)
            if fb >= best_fb - 1e-9:
                best_fb, dark_thr = fb, float(thr)
        ptt = (1.0 - torch.softmax(lt / T, dim=-1)[:, b_idx]).numpy()
        ybt = (yt != b_idx).astype(int)
        p2, r2, f2, _ = precision_recall_fscore_support(ybt, (ptt > dark_thr).astype(int), average="binary", zero_division=0)
        binary_tuned = {"threshold": dark_thr, "precision": float(p2), "recall": float(r2), "f1": float(f2)}
        print(f"tuned P(dark) threshold = {dark_thr:.3f} -> precision={p2:.3f} recall={r2:.3f} f1={f2:.3f}")

    with open(os.path.join(a.out, "meta.json"), "w") as fh:
        json.dump({"classes": classes, "temperature": T, "dark_threshold": dark_thr, "test_report": rep,
                   "binary_report": binary, "binary_report_tuned": binary_tuned,
                   "confusion_matrix": cm.tolist(), "args": vars(a)}, fh, indent=2)
    te = te.copy(); te["pred"] = [classes[i] for i in pred]
    te[te["pred"] != te["label_name"]][["text", "label_name", "pred"]].to_csv(
        os.path.join(a.out, "test_errors.csv"), index=False)
    print(f"saved to {a.out}/  (temperature={T:.3f}); errors in test_errors.csv")


# =====================================================================
# AUDITOR ENGINE: XAI (Delta p) + REMEDIATION + DOM / VISUAL CHECKS
# =====================================================================

_MODEL_CACHE = {}


def resolve_model_dir(out):
    """Finds the model folder whether the app is started from the project root or another directory."""
    if os.path.isabs(out) or os.path.exists(os.path.join(out, "meta.json")):
        return out
    alt = os.path.join(BASE_DIR, out)
    return alt if os.path.exists(os.path.join(alt, "meta.json")) else out


def load_trained_bundle(out="outputs/model"):
    """Loads and caches model, tokenizer and meta.json so the UI stays fast after the first call."""
    out = resolve_model_dir(out)
    if out not in _MODEL_CACHE:
        meta_path = os.path.join(out, "meta.json")
        if not os.path.exists(meta_path):
            raise FileNotFoundError(
                f"Trained model not found in '{out}'. Run training first:\n"
                f"python train_darkpattern_fixed.py --data ec-darkpattern/dataset/dataset.tsv"
            )
        meta = json.load(open(meta_path))
        tok = AutoTokenizer.from_pretrained(out)
        model = AutoModelForSequenceClassification.from_pretrained(out).eval()
        _MODEL_CACHE[out] = (model, tok, meta)
    return _MODEL_CACHE[out]


@torch.no_grad()
def explain_words_xai(text, pred_idx, base_prob, model, tok, temp):
    """
    Feature 1: Word-Level Explainability (Leave-One-Out Masking).
    Masks one word at a time and measures the probability drop: Delta_p = p_base - p_masked.
    """
    words = text.split()
    if len(words) <= 1:
        return [{"word": text, "delta_p": round(base_prob, 4)}]
    n_explain = min(len(words), MAX_XAI_WORDS)

    masked_texts = []
    for i in range(n_explain):
        rem = words[:i] + words[i+1:]
        masked_texts.append(" ".join(rem))

    enc = tok(masked_texts, truncation=True, max_length=64, padding=True, return_tensors="pt")
    probs = torch.softmax(model(**enc).logits / temp, dim=-1)[:, pred_idx].tolist()

    word_impacts = []
    for w, p_masked in zip(words[:n_explain], probs):
        delta_p = max(0.0, base_prob - float(p_masked))
        word_impacts.append({"word": w, "delta_p": round(delta_p, 4)})
    return word_impacts


@torch.no_grad()
def predict(texts, out="outputs/model", explain=True, surface="text", gate=True):
    """
    Classifies one or more texts.
    Returns category, calibrated confidence, risk level, XAI word attributions,
    explanation and ethical remediation ('how_to_fix') for each text.
    """
    if isinstance(texts, str):
        texts = [texts]
    texts = [str(t).strip() for t in texts if t is not None and str(t).strip()]
    if not texts:
        return []

    model, tok, meta = load_trained_bundle(out)
    temp = meta["temperature"]
    classes = meta["classes"]
    thr = max(float(meta.get("dark_threshold", DARK_THRESHOLD)), SURFACE_MIN_THRESHOLD.get(surface, DARK_THRESHOLD))

    prob_chunks = []
    for s in range(0, len(texts), PRED_BATCH):
        enc = tok(texts[s:s + PRED_BATCH], truncation=True, max_length=64, padding=True, return_tensors="pt")
        prob_chunks.append(torch.softmax(model(**enc).logits / temp, dim=-1))
    p = torch.cat(prob_chunks)

    res = []
    b_idx = classes.index(BENIGN) if BENIGN in classes else None
    for t, row in zip(texts, p):
        if b_idx is None:
            p_dark = 1.0
            i = int(row.argmax())
        else:
            p_dark = float(row.sum() - row[b_idx])
            if p_dark > thr:
                dark_only = row.clone()
                dark_only[b_idx] = -1.0
                i = int(dark_only.argmax())
            else:
                i = b_idx
        cat = classes[i]
        conf = float(row[i])
        gate_note = None
        if gate and b_idx is not None and cat != BENIGN:
            keep, gate_note = context_gate(t, cat, p_dark)
            if not keep:
                cat, i = BENIGN, b_idx
                conf = float(row[b_idx])
        is_dark = (cat != BENIGN)

        if not is_dark:
            risk = "None (Benign)"
            rem = {
                "explanation": "Normal informational or transactional e-commerce text with no manipulative framing.",
                "how_to_fix": "No changes needed. This UI element follows ethical design standards."
            }
            xai_words = []
        else:
            conf_for_risk = max(conf, p_dark)
            risk = ("High Risk" if conf_for_risk >= 0.80
                    else ("Medium Risk" if conf_for_risk >= 0.55 else "Low Risk (Needs Review)"))
            rem = REMEDIATION_GUIDE.get(cat, REMEDIATION_GUIDE[OTHER])
            xai_words = explain_words_xai(t, i, conf, model, tok, temp) if explain else []

        res.append({
            "text": t,
            "category": cat,
            "is_dark_pattern": is_dark,
            "confidence": round(conf, 4),
            "p_dark": round(p_dark, 4),
            "risk_level": risk,
            "xai_words": xai_words,
            "explanation": rem["explanation"],
            "how_to_fix": rem["how_to_fix"],
            "source_type": "NLP Text Classifier (DistilBERT)",
            "gate_note": gate_note,
            "verdict": VERDICT_DARK if is_dark else VERDICT_OK
        })
    return res


def summarize_findings(findings):
    """Audit overview for the UI: counts, overall risk, and a clear message for the empty / clean states."""
    findings = findings or []
    dark = [f for f in findings if f.get("is_dark_pattern")]
    by_cat = {}
    for f in dark:
        by_cat[f["category"]] = by_cat.get(f["category"], 0) + 1
    if not findings:
        status, overall = "no_content", "N/A"
        message = "No analysable text was found in the input. Paste text/HTML or upload a clearer screenshot."
    elif not dark:
        status, overall = "clean", "None"
        message = "No suspicious dark pattern detected in the analysed content. (This is not a guarantee: hidden checkout steps cannot be seen from this input.)"
    else:
        status = "flagged"
        levels = [f.get("risk_level", "") for f in dark]
        overall = "High Risk" if "High Risk" in levels else ("Medium Risk" if "Medium Risk" in levels else "Low Risk")
        message = f"{len(dark)} likely dark-pattern instance(s) flagged. These are likely concerns that need human review, not verified wrongdoing."
    return {"status": status, "overall_risk": overall, "total_items": len(findings),
            "flagged_items": len(dark), "by_category": by_cat, "message": message}


# ---- HTML auditor helpers ----
_BLOCK_TAGS = ["p", "div", "li", "ul", "ol", "h1", "h2", "h3", "h4", "h5", "h6", "button", "label",
               "tr", "td", "th", "section", "article", "form", "header", "footer", "option", "legend", "table",
               "a", "nav", "main", "aside", "summary"]
_MONEY_RE = re.compile(r"(\$|₹|€|£|\bfee|\bcharge|\brenew|\bsubscri|\btrial|\bauto[- ]?(renew|pay|bill)|\bcancel|\bnon-?refundable)", re.I)

_PAID_CHECKBOX_RE = re.compile(
    r"(?:\b(?:subscri(?:be|bes|bed|bing|ption|ptions)|donat(?:e|es|ed|ing|ion|ions)|fees?|"
    r"charg(?:e|es|ed|ing)|protect(?:ion|ions)?|add(?:s|ed|ing)?|add-?ons?|"
    r"insur(?:ance|ed)?|warrant(?:y|ies)|newsletters?|marketing|promo(?:tion|tional|s)?|vip|trials?|"
    r"auto[- ]?(?:renew|pay|bill)|upgrades?|priorit(?:y|ies)|memberships?)\b|[\$₹€£])", re.I)


def _is_paid_checkbox(label):
    return bool(_PAID_CHECKBOX_RE.search(label or ""))


def _style_dict(el):
    try:
        raw = el.get("style", "") or ""
    except Exception:
        return {}
    out = {}
    for part in raw.split(";"):
        if ":" in part:
            k, v = part.split(":", 1)
            out[k.strip().lower()] = v.strip().lower()
    return out


def _parse_css_color(v):
    if not v:
        return None
    v = v.strip().lower()
    names = {"white": (255, 255, 255), "black": (0, 0, 0), "gray": (128, 128, 128), "grey": (128, 128, 128),
             "silver": (192, 192, 192), "lightgray": (211, 211, 211), "lightgrey": (211, 211, 211)}
    if v in names:
        return names[v]
    m = re.fullmatch(r"#([0-9a-f]{3}|[0-9a-f]{6})", v)
    if m:
        h = m.group(1)
        if len(h) == 3:
            h = "".join(c * 2 for c in h)
        return tuple(int(h[i:i + 2], 16) for i in (0, 2, 4))
    m = re.fullmatch(r"rgba?\(\s*(\d+)\s*,\s*(\d+)\s*,\s*(\d+)[^)]*\)", v)
    if m:
        return tuple(min(255, int(x)) for x in m.groups())
    return None


def _contrast_ratio(a, b):
    def lum(rgb):
        ch = []
        for c in rgb:
            c = c / 255.0
            ch.append(c / 12.92 if c <= 0.03928 else ((c + 0.055) / 1.055) ** 2.4)
        return 0.2126 * ch[0] + 0.7152 * ch[1] + 0.0722 * ch[2]
    la, lb = lum(a), lum(b)
    return (max(la, lb) + 0.05) / (min(la, lb) + 0.05)


def _is_hidden(el):
    if el.has_attr("hidden"):
        return True
    st = _style_dict(el)
    return st.get("display", "") == "none" or st.get("visibility", "") == "hidden"


def _checkbox_label(cb, soup):
    cid = cb.get("id")
    if cid:
        lab = soup.find("label", attrs={"for": cid})
        if lab:
            return lab.get_text(" ", strip=True)[:150]
    lab = cb.find_parent("label")
    if lab:
        return lab.get_text(" ", strip=True)[:150]
    parts = []
    for sib in cb.next_siblings:
        if getattr(sib, "name", None) in ("input", "br", "p", "div", "ul", "ol", "table", "form", "label", "button"):
            break
        t = sib.get_text(" ", strip=True) if hasattr(sib, "get_text") else str(sib).strip()
        if t:
            parts.append(t)
        if len(" ".join(parts)) >= 150:
            break
    nxt = " ".join(parts)[:150].strip()
    if nxt:
        return nxt
    txt = cb.parent.get_text(" ", strip=True)[:150] if cb.parent else ""
    return txt or "Pre-checked option"


def _inspect_hidden_text(soup, matched_texts=None):
    out = []
    for el in soup.find_all(True):
        st = _style_dict(el)
        if not st:
            continue
        own = " ".join(s.strip() for s in el.find_all(string=True, recursive=False)).strip()
        if len(own) < 4 or not _MONEY_RE.search(own):
            continue
        reasons = []
        m = re.match(r"(\d+(?:\.\d+)?)px", st.get("font-size", ""))
        if m and float(m.group(1)) <= 10:
            reasons.append(f"tiny font ({m.group(1)}px)")
        try:
            op = float(st.get("opacity", "1"))
        except ValueError:
            op = 1.0
        if op <= 0.35:
            reasons.append(f"faded (opacity {op})")
        fg = _parse_css_color(st.get("color"))
        bg = _parse_css_color(st.get("background-color") or st.get("background"))
        if fg and bg:
            cr = _contrast_ratio(fg, bg)
            if cr < 2.0:
                reasons.append(f"low contrast ({cr:.1f}:1)")
        if reasons:
            rem = REMEDIATION_GUIDE[OTHER]
            if matched_texts is not None:
                matched_texts.append(own)
            out.append({
                "text": f"[DOM hidden/low-visibility text] {own[:150]}",
                "category": OTHER,
                "is_dark_pattern": True,
                "confidence": 0.80,
                "heuristic_score": 0.80,
                "risk_level": "Medium Risk",
                "xai_words": [{"word": r, "delta_p": 0.40, "rule_weight": 0.40} for r in reasons],
                "explanation": "Important fee/commitment wording is made hard to notice: " + ", ".join(reasons) + ".",
                "how_to_fix": rem["how_to_fix"],
                "source_type": "DOM Style Inspector (hidden / low-contrast text)" + HEURISTIC_TAG,
                "verdict": VERDICT_DARK
            })
    return out


def audit_html_dom(html_content, out="outputs/model"):
    from bs4 import BeautifulSoup
    if isinstance(html_content, bytes):
        html_content = html_content.decode("utf-8", "ignore")
    if not html_content or not str(html_content).strip():
        return []
    soup = BeautifulSoup(str(html_content), "html.parser")
    findings = []

    for tag in soup(["script", "style", "noscript", "head"]):
        tag.decompose()
    for el in list(soup.find_all(True)):
        try:
            if _is_hidden(el):
                el.decompose()
        except Exception:
            continue

    for cb in soup.find_all("input", {"type": "checkbox"}):
        if cb.has_attr("checked"):
            parent_text = _checkbox_label(cb, soup)
            if _is_paid_checkbox(parent_text):
                rem = REMEDIATION_GUIDE["Preselected Choice"]
                findings.append({
                    "text": f"[DOM <input checked>] {parent_text}",
                    "category": "Preselected Choice",
                    "is_dark_pattern": True,
                    "confidence": 0.96,
                    "heuristic_score": 0.96,
                    "risk_level": "High Risk",
                    "xai_words": [{"word": "checked", "delta_p": 0.65, "rule_weight": 0.65}],
                    "explanation": rem["explanation"],
                    "how_to_fix": rem["how_to_fix"],
                    "source_type": "DOM Attribute Inspector" + HEURISTIC_TAG,
                    "verdict": VERDICT_DARK
                })
            else:
                findings.append({
                    "text": f"[DOM <input checked>] {parent_text}",
                    "category": BENIGN,
                    "is_dark_pattern": False,
                    "confidence": 0.20,
                    "heuristic_score": 0.20,
                    "risk_level": "Low Risk / Benign Pre-selection",
                    "xai_words": [{"word": "checked", "delta_p": 0.10, "rule_weight": 0.10}],
                    "explanation": "This option is pre-ticked, but its label does not suggest a paid add-on, fee, donation or subscription, so it is treated as a routine (benign) pre-selection.",
                    "how_to_fix": "No change needed for routine options. Keep optional paid extras unticked by default.",
                    "source_type": "DOM Attribute Inspector" + HEURISTIC_TAG,
                    "verdict": VERDICT_BENIGN_PRESELECT
                })

    hidden_own = []
    findings += _inspect_hidden_text(soup, hidden_own)

    for br in soup.find_all("br"):
        br.replace_with("\n")
    for tag in soup.find_all(_BLOCK_TAGS):
        tag.insert_before("\n")
        tag.insert_after("\n")
    lines = [re.sub(r"\s+", " ", line).strip() for line in soup.get_text(" ").splitlines()]

    for inp in soup.find_all("input", attrs={"type": re.compile(r"^(submit|button)$", re.I)}):
        val = re.sub(r"\s+", " ", str(inp.get("value", "") or "")).strip()
        if val:
            lines.append(val)

    pieces = []
    for line in lines:
        if len(line) < 4:
            continue
        if len(line) > 200:
            pieces += [s.strip() for s in re.split(r"(?<=[.!?])\s+", line) if len(s.strip()) >= 4]
        else:
            pieces.append(line)

    if hidden_own:
        hidden_norm = [re.sub(r"\s+", " ", h).strip() for h in hidden_own]
        pieces = [x for x in pieces
                  if not any(h and h in x and len(h) >= 0.8 * len(x) for h in hidden_norm)]

    seen = set()
    unique_lines = [x for x in pieces if not (x in seen or seen.add(x))]
    unique_lines = unique_lines[:MAX_LINES]

    nlp_results = predict(unique_lines, out=out, explain=True, surface="html")
    flagged_urgency = {r["text"] for r in nlp_results if r.get("is_dark_pattern") and r.get("category") == "Urgency"}
    timer_findings = detect_countdown_timers([{"text": x} for x in unique_lines if x not in flagged_urgency])
    return findings + nlp_results + timer_findings


# =====================================================================
# V3: STRICT CHECKBOX DETECTION + DISGUISED-AD DETECTION
# =====================================================================
CHECKBOX_MIN_PX, CHECKBOX_MAX_PX = 12, 42
CHECKBOX_MIN_RECTANGULARITY = 0.86
CHECKBOX_MAX_LABEL_GAP = 48

_AD_LABEL_RE = re.compile(
    r"(\(\s*ads?\s*\)|\[\s*ads?\s*\]|\bsponsored\b|\bpromoted\b|\badvert(?:isement|ising|orial)?\b|"
    r"\bpaid\s+(?:partnership|promotion|content)\b|\bpartner\s+content\b|\bad\b)", re.I)
_PROMO_BAIT_RE = re.compile(
    r"\b(free|samples?|gifts?|prize|winner|won|win|claim|redeem|reward|rewards|bonus|giveaway|"
    r"cashback|voucher|coupon|exclusive|limited|offer|deal|deals|\d+\s?%\s?off|save\s+\d+)\b", re.I)
_NAV_BAIT_RE = re.compile(r"\b(free\s+(?:samples?|gifts?|trial)|giveaway|prize|prizes|winner|win\s+(?:a|an|free|big|prizes?)\b|"
                          r"claim\s+(?:your|now|free)|you(?:'ve|\s+have)?\s+won)\b", re.I)
_PROMO_URGENCY_RE = re.compile(r"\b(limited|today|now|hurry|ends?|last chance|expires?|only|don'?t miss)\b", re.I)
_PROMO_CTA_RE = re.compile(
    r"\b(redeem|claim|grab|get\s+(?:it|yours|offer|now)|shop\s+now|buy\s+now|order\s+now|install|"
    r"download\s+now|unlock|activate|apply\s+now|try\s+(?:it\s+)?free|learn\s+more)\b", re.I)
AD_NAV_TOP_FRAC = 0.16
AD_FLOAT_MIN_SCORE = 6


def _is_ad_label(text):
    t = (text or "").strip()
    if not t:
        return False
    if re.fullmatch(r"(?i)ad", t):
        return True
    m = _AD_LABEL_RE.search(t)
    if not m:
        return False
    if m.group(0).strip().lower() == "ad" and len(t.split()) > 5:
        return bool(re.match(r"(?i)\s*ad\b\s*[:\-·|•]?\s", t) or re.search(r"(?i)\s[·|•\-]?\s*ad\s*$", t))
    return True


def _has_tick_mark(rgb, x, y, w, h):
    import cv2
    pad = max(2, int(round(w * 0.18)))
    inner = rgb[y + pad: y + h - pad, x + pad: x + w - pad]
    if inner.ndim != 3 or inner.shape[0] < 5 or inner.shape[1] < 5:
        return False
    S = 24
    inner = cv2.resize(inner, (S, S), interpolation=cv2.INTER_AREA)
    lab = cv2.cvtColor(inner, cv2.COLOR_RGB2LAB).astype(np.float32)
    ring = np.ones((S, S), bool)
    ring[2:-2, 2:-2] = False
    bg = np.median(lab[ring], axis=0)
    ink = np.linalg.norm(lab - bg, axis=2) > 40.0
    frac = float(ink.mean())
    if not (0.05 <= frac <= 0.50):
        return False
    ys, xs = np.nonzero(ink)
    nx, ny = xs / float(S - 1), ys / float(S - 1)
    if (nx.max() - nx.min()) < 0.45 or (ny.max() - ny.min()) < 0.35:
        return False
    total = float(len(xs))

    def share(mask):
        return float(mask.sum()) / total

    tl_empty = share((nx < 0.30) & (ny < 0.30)) < 0.10
    br_empty = share((nx > 0.70) & (ny > 0.70)) < 0.10
    left_mid = share((nx < 0.48) & (ny >= 0.30) & (ny <= 0.85)) > 0.10
    top_right = share((nx > 0.55) & (ny < 0.55)) > 0.10
    low_rows = ny >= ny.max() - 0.08
    low_x = float(nx[low_rows].mean())
    solid = cv2.erode(ink.astype(np.uint8), np.ones((7, 7), np.uint8)).sum() / float(max(1, ink.sum()))
    is_tick = (tl_empty and br_empty and left_mid and top_right and 0.12 <= low_x <= 0.70
               and frac <= 0.50 and solid < 0.15)
    if is_tick:
        return True
    corners = [ink[0:8, 0:8], ink[0:8, 16:24], ink[16:24, 0:8], ink[16:24, 16:24]]
    mid_edges = [ink[0:6, 9:15], ink[18:24, 9:15], ink[9:15, 0:6], ink[9:15, 18:24]]
    d1 = np.abs(ny - nx) < 0.20
    d2 = np.abs(ny - (1.0 - nx)) < 0.20
    is_cross = (all(float(c.mean()) > 0.12 for c in corners)
                and all(float(m.mean()) < 0.25 for m in mid_edges)
                and frac <= 0.55 and share(d1 | d2) > 0.85 and share(d1) > 0.30 and share(d2) > 0.30)
    return bool(is_cross)


def find_ticked_checkboxes(image_rgb, ocr_items):
    import cv2
    gray = cv2.cvtColor(image_rgb, cv2.COLOR_RGB2GRAY)
    edges = cv2.Canny(gray, 50, 150)
    edges = cv2.dilate(edges, np.ones((2, 2), np.uint8), iterations=1)
    contours, _ = cv2.findContours(edges, cv2.RETR_LIST, cv2.CHAIN_APPROX_SIMPLE)

    cands = []
    for cnt in contours:
        x, y, w, h = cv2.boundingRect(cnt)
        if not (CHECKBOX_MIN_PX <= w <= CHECKBOX_MAX_PX and CHECKBOX_MIN_PX <= h <= CHECKBOX_MAX_PX):
            continue
        if not (0.80 <= w / float(h) <= 1.25):
            continue
        if cv2.contourArea(cnt) / float(w * h) < CHECKBOX_MIN_RECTANGULARITY:
            continue
        cands.append((w * h, x, y, w, h))
    cands.sort(reverse=True)

    kept = []
    for _, x, y, w, h in cands:
        if any(abs((x + w / 2) - (kx + kw / 2)) < 8 and abs((y + h / 2) - (ky + kh / 2)) < 8
               for kx, ky, kw, kh, _l in kept):
            continue
        cand = (x, y, x + w, y + h)
        if any(_overlap_frac(cand, it["bbox"]) > 0.30 for it in ocr_items):
            continue
        if not _has_tick_mark(image_rgb, x, y, w, h):
            continue
        label, best_gap = None, 1e9
        for it in ocr_items:
            ix1, iy1, ix2, iy2 = it["bbox"]
            gap = ix1 - (x + w)
            if (-6 <= gap <= CHECKBOX_MAX_LABEL_GAP and gap < best_gap
                    and abs((iy1 + iy2) / 2.0 - (y + h / 2.0)) <= h * 0.9):
                label, best_gap = it["text"], gap
        if label:
            kept.append((x, y, w, h, label))
    return kept


# ---------------- Disguised ad detection ----------------
def _group_rows(items, tol=0.6):
    rows = []
    for it in sorted(items, key=lambda d: ((d["bbox"][1] + d["bbox"][3]) / 2.0, d["bbox"][0])):
        x1, y1, x2, y2 = it["bbox"]
        cy, h = (y1 + y2) / 2.0, max(1, y2 - y1)
        for r in rows:
            if abs(cy - r["cy"]) <= tol * max(h, r["h"]):
                r["items"].append(it)
                r["cy"] = (r["cy"] * (len(r["items"]) - 1) + cy) / len(r["items"])
                r["h"] = max(r["h"], h)
                break
        else:
            rows.append({"cy": cy, "h": h, "items": [it]})
    for r in rows:
        r["items"].sort(key=lambda d: d["bbox"][0])
    return rows


def _find_container_rect(gray, bbox, W, H):
    import cv2
    x1, y1, x2, y2 = bbox
    edges = cv2.Canny(gray, 12, 40)
    edges = cv2.dilate(edges, np.ones((2, 2), np.uint8), iterations=1)
    contours, _ = cv2.findContours(edges, cv2.RETR_LIST, cv2.CHAIN_APPROX_SIMPLE)
    best = None
    for cnt in contours:
        x, y, w, h = cv2.boundingRect(cnt)
        if w < (x2 - x1) or h < (y2 - y1) or w * h > 0.25 * W * H or h > 0.22 * H or w < 1.6 * h:
            continue
        if not (x - 2 <= x1 and y - 2 <= y1 and x + w + 2 >= x2 and y + h + 2 >= y2):
            continue
        if cv2.contourArea(cnt) / float(w * h) < 0.80:
            continue
        if best is None or w * h < best[2] * best[3]:
            best = (x, y, w, h)
    if best is None:
        return None
    return (best[0], best[1], best[0] + best[2], best[1] + best[3])


def _shadow_bottom_edge(gray, bbox):
    x1, y1, x2, y2 = bbox
    H, W = gray.shape
    xa, xb = max(0, x1), min(W, x2)
    if xb - xa < 12 or y2 + 24 >= H:
        return None
    m = gray[:, xa:xb].astype(np.float32).mean(axis=1)
    top = min(H, y2 + 44)
    base = float(m[y2 + 3])
    for y in range(y2 + 4, top - 18):
        if m[y] <= base - 10.0:
            dark = float(m[y:y + 4].min())
            if float(m[y + 6:y + 18].max()) >= dark + 8.0:
                return int(y)
            break
    return None


def _button_contrast(rgb, bbox):
    import cv2
    H, W = rgb.shape[:2]
    x1, y1, x2, y2 = bbox
    px, py = int((x2 - x1) * 0.25), int((y2 - y1) * 0.45)
    patch = rgb[max(0, y1 - py): min(H, y2 + py), max(0, x1 - px): min(W, x2 + px)]
    if patch.size == 0:
        return 255.0, 0.0
    return (float(cv2.cvtColor(patch, cv2.COLOR_RGB2GRAY).mean()),
            float(cv2.cvtColor(patch, cv2.COLOR_RGB2HSV)[:, :, 1].mean()))


def _ad_finding(text, score, bbox, risk, explanation, evidence, source):
    rem = REMEDIATION_GUIDE["Disguised Ad"]
    conf = round(min(0.95, score), 4)
    return {
        "text": text, "category": "Disguised Ad", "is_dark_pattern": True,
        "confidence": conf, "heuristic_score": conf,
        "risk_level": risk,
        "xai_words": [{"word": w, "delta_p": round(v, 2), "rule_weight": round(v, 2)} for w, v in evidence],
        "explanation": explanation, "how_to_fix": rem["how_to_fix"],
        "source_type": source + HEURISTIC_TAG, "verdict": VERDICT_DARK,
        "bbox": [int(b) for b in bbox],
    }


def detect_disguised_ads(image_rgb, items, nav_items=None):
    import cv2
    H, W = image_rgb.shape[:2]
    gray = cv2.cvtColor(image_rgb, cv2.COLOR_RGB2GRAY)
    findings, notes = [], []

    band = [it for it in (nav_items if nav_items else items) if it["bbox"][3] <= AD_NAV_TOP_FRAC * H]
    for row in _group_rows(band):
        links = [it for it in row["items"] if 1 <= len(it["text"].split()) <= 4]
        if len(links) < 4:
            continue
        hs = sorted(max(1, it["bbox"][3] - it["bbox"][1]) for it in links)
        med_h = hs[len(hs) // 2]
        for it in links:
            txt = it["text"]
            has_label = _is_ad_label(txt)
            has_bait = bool(_NAV_BAIT_RE.search(txt))
            if not (has_label or has_bait):
                continue
            h = max(1, it["bbox"][3] - it["bbox"][1])
            if not (0.70 <= h / float(med_h) <= 1.40):
                continue
            siblings = [s for s in links if s is not it
                        and 0.70 <= max(1, s["bbox"][3] - s["bbox"][1]) / float(med_h) <= 1.40]
            if len(siblings) < 3:
                continue
            x1, y1, x2, y2 = it["bbox"]
            pad = 5
            box = (max(0, x1 - pad), max(0, y1 - pad), min(W, x2 + pad), min(H, y2 + pad))
            if has_label:
                score, risk = 0.72, "Medium Risk"
                expl = (f"Ad blended into navigation: '{txt}' is styled exactly like the real menu links "
                        f"(same size, row and weight) and its ad disclosure is only a tiny inline tag. "
                        f"Users read it as site navigation, not as a paid placement.")
                ev = [("Same row/size as nav links", 0.40), ("Ad tag is inline & small", 0.30)]
            else:
                score, risk = 0.85, "High Risk"
                expl = (f"Undisclosed promotion blended into navigation: '{txt}' looks like a menu link but "
                        f"uses giveaway wording and carries no ad / sponsored label.")
                ev = [("Same row/size as nav links", 0.40), ("Giveaway wording, no ad label", 0.45)]
            findings.append(_ad_finding(f"Disguised Ad in navigation: '{txt}'", score, box, risk, expl, ev,
                                        "OpenCV Layout Check (ad styled as nav link)"))
            notes.append((box, "Disguised Ad (nav)"))

    for row in _group_rows(items, tol=0.8):
        cluster = []
        for it in row["items"]:
            if cluster and it["bbox"][0] - cluster[-1]["bbox"][2] > 0.30 * W:
                break
            cluster.append(it)
        text = " ".join(c["text"] for c in cluster)
        if len(text.split()) < 3 or len(text.split()) > 20:
            continue
        bait = set(m.group(0).lower() for m in _PROMO_BAIT_RE.finditer(text))
        if not bait:
            continue
        cta_items = [c for c in cluster if _PROMO_CTA_RE.search(c["text"])]
        if not cta_items:
            continue
        x1 = min(c["bbox"][0] for c in cluster); y1 = min(c["bbox"][1] for c in cluster)
        x2 = max(c["bbox"][2] for c in cluster); y2 = max(c["bbox"][3] for c in cluster)
        rect = _find_container_rect(gray, (x1, y1, x2, y2), W, H)
        edge_y = _shadow_bottom_edge(gray, (x1, y1, x2, y2))
        if rect:
            box = rect
        else:
            bottom = edge_y if edge_y else min(H, y2 + 12)
            box = (max(0, x1 - 20), max(0, y1 - 12), min(W, x2 + 20), min(H, bottom))
        shadow = edge_y is not None
        trusted = bool(rect) or shadow

        label_near = any(_is_ad_label(it["text"]) and _overlap_frac(
            (it["bbox"][0] - 40, it["bbox"][1] - 25, it["bbox"][2] + 40, it["bbox"][3] + 25), box) > 0.2
            for it in items) or _is_ad_label(text)
        member = set(id(c) for c in cluster)
        clips = trusted and any(id(it) not in member and 0.03 < _overlap_frac(it["bbox"], box) < 0.95
                                for it in items)
        floating = clips or shadow
        g, s = _button_contrast(image_rgb, cta_items[0]["bbox"])
        styled_button = g < 110 or s > 90

        score = 0
        score += 1 if bait else 0
        score += 1 if len(bait) >= 2 else 0
        score += 1 if _PROMO_URGENCY_RE.search(text) else 0
        score += 1
        score += 1 if styled_button else 0
        score += 0 if label_near else 2
        score += 1 if clips else 0
        score += 1 if shadow else 0
        if floating and not label_near and score >= AD_FLOAT_MIN_SCORE:
            ev = [("Promo / giveaway wording", 0.30), ("CTA button", 0.20), ("No ad label", 0.30),
                  ("Floats over content", 0.25)]
            findings.append(_ad_finding(
                f"Disguised Ad (fake notification): '{text}'", 0.50 + 0.05 * score, box, "High Risk",
                f"Floating promo card styled like a system notification: '{text}'. It sits on top of the page "
                f"content, offers a giveaway with urgency wording and a button, and has no ad / sponsored label, "
                f"so users may take it for a site message instead of an advertisement.", ev,
                "OpenCV Layout Check (floating promo overlay)"))
            notes.append((box, "Disguised Ad (overlay)"))
    return findings, notes


# =====================================================================
# V3.2: COUNTDOWN-TIMER DETECTION (3-unit, 2-unit, 1-unit & clock timers)
# =====================================================================
_TIMER_UNITS3_RE = re.compile(
    r"(?<![\w.:])(\d{1,2})\s?h(?:rs?|ours?)?\s*[:,]?\s*(\d{1,2})\s?m(?:ins?|inutes?)?\s*[:,]?\s*(\d{1,2})\s?s(?:ecs?|econds?)?(?![a-z])", re.I)
_TIMER_UNITS2_RE = re.compile(
    r"(?<![\w.:])(?:(\d{1,2})\s?h(?:rs?|ours?)?\s*[:,]?\s*(\d{1,2})\s?m(?:ins?|inutes?)?|"
    r"(\d{1,2})\s?m(?:ins?|inutes?)?\s*[:,]?\s*(\d{1,2})\s?s(?:ecs?|econds?)?)(?![a-z])", re.I)
_TIMER_UNITS1_RE = re.compile(
    r"(?<![\w.:])(\d{1,3})\s*(?:h(?:rs?|ours?)|m(?:ins?|inutes?)|s(?:ecs?|econds?))\b", re.I)
_TIMER_CLOCK_RE = re.compile(r"(?<![\d:.])(\d{1,2}):(\d{2})(?::(\d{2}))?(?![\d:])(?!\s?(?:am|pm|a\.m|p\.m)\b)", re.I)
_TIMER_CTX_RE = re.compile(
    r"(order\s+(?:in|within)|ends?\s+(?:in|at|soon)|ending|expires?|expiring|hurry|\bleft\b|remaining|\boffers?\b|\bsale\b|"
    r"\bdeals?\b|limited|\bonly\b|valid|before|within|cut-?off|checkout|reserved|closing|starts?\s+in|get\s+it\s+in)", re.I)
_TIMER_DEAL_RE = re.compile(r"(\boffers?\b|\bsale\b|\bdeals?\b|discount|\d\s?%\s?off|coupon|\bprice\b|\bsave\b|flash|lightning|limited|order\s+(?:in|within))", re.I)
_TIMER_NEG_RE = re.compile(r"(\bago\b|duration|run\s?time|\bwatch\s*(?:time|later)\b|\bvideo\s+(?:length|duration)|\bviews?\b|"
                           r"\bprep\b|\bcook\s*time|\bcooking\b|read\s+time|elapsed|uptime|posted|published|updated|\bplay\b|"
                           r"\btrack\s+(?:length|time)|\bsong\b|\bepisode\b|\bep\b)", re.I)


def _norm_timer_text(t):
    return _fix_ocr_timer_typos(t)


def match_countdown(text):
    """Detects 3-unit (00h 26m 43s), 2-unit (00h 26m), 1-unit with deadline wording (Order in 22 minutes), and clock timers."""
    t = _norm_timer_text(re.sub(r"\s+", " ", str(text or "")).strip())
    if not t or _TIMER_NEG_RE.search(t):
        return None
    ctx = bool(_TIMER_CTX_RE.search(t))
    m = _TIMER_UNITS3_RE.search(t)
    if m:
        return m.group(0), 3, ctx
    m = _TIMER_UNITS2_RE.search(t)
    if m and (ctx or "00h" in m.group(0).lower()):
        return m.group(0), 2, ctx
    m = _TIMER_UNITS1_RE.search(t)
    if m and ctx:
        return m.group(0), 1, ctx
    m = _TIMER_CLOCK_RE.search(t)
    if m and ctx and (m.group(3) is not None or re.search(r"(ends?\s+in|expires?|\bleft\b|remaining|hurry|order\s+in|within)", t, re.I)):
        return m.group(0), (3 if m.group(3) else 2), ctx
    return None


def _warm_emphasis_ratio(rgb, bbox):
    """Share of red/orange saturated pixels in the box (includes light-orange subtext like Flipkart timers)."""
    import cv2
    H, W = rgb.shape[:2]
    x1, y1, x2, y2 = [int(v) for v in bbox]
    patch = rgb[max(0, y1 - 2): min(H, y2 + 2), max(0, x1 - 2): min(W, x2 + 2)]
    if patch.size == 0:
        return 0.0
    hsv = cv2.cvtColor(patch, cv2.COLOR_RGB2HSV)
    warm = ((hsv[:, :, 0] <= 25) | (hsv[:, :, 0] >= 162)) & (hsv[:, :, 1] >= 38) & (hsv[:, :, 2] >= 100)
    return float(warm.mean())


def detect_countdown_timers(items, image_rgb=None):
    """Detects countdown timers in OCR boxes or plain HTML lines."""
    clusters = []
    boxed = [it for it in items if it.get("bbox")]
    if boxed:
        for row in _group_rows(boxed, tol=0.7):
            cur = None
            for it in row["items"]:
                b = it["bbox"]
                h = max(1, b[3] - b[1])
                if cur is not None and b[0] - cur["bbox"][2] <= 2.2 * max(h, cur["h"]):
                    cb = cur["bbox"]
                    cur["bbox"] = (min(cb[0], b[0]), min(cb[1], b[1]), max(cb[2], b[2]), max(cb[3], b[3]))
                    cur["text"] += " " + it["text"]
                    cur["h"] = max(cur["h"], h)
                else:
                    if cur is not None:
                        clusters.append(cur)
                    cur = {"bbox": tuple(b), "text": it["text"], "h": h}
            if cur is not None:
                clusters.append(cur)
    clusters += [{"bbox": None, "text": it["text"]} for it in items if not it.get("bbox")]

    findings, rem = [], REMEDIATION_GUIDE["Urgency"]
    for c in clusters:
        norm_t = _norm_timer_text(c["text"])
        hit = match_countdown(norm_t)
        if not hit:
            continue
        snippet, units, ctx = hit
        deal = bool(_TIMER_DEAL_RE.search(norm_t))
        warm = _warm_emphasis_ratio(image_rgb, c["bbox"]) if (image_rgb is not None and c["bbox"]) else 0.0
        warm_on = warm >= 0.02
        score = 0.78 + (0.07 if ctx else 0) + (0.05 if deal else 0) + (0.05 if warm_on else 0) + (0.03 if units == 3 else 0)
        score = round(min(0.96, score), 4)
        evid = [(f"Countdown timer ({snippet.strip()})", 0.50)]
        if ctx:
            evid.append(("Deadline wording", 0.30))
        if warm_on:
            evid.append(("Red/orange emphasis", 0.15))
        f = {
            "text": f"Countdown timer: '{re.sub(chr(10), ' ', norm_t).strip()}'",
            "category": "Urgency", "is_dark_pattern": True,
            "confidence": score, "heuristic_score": score,
            "risk_level": "High Risk" if (deal or ctx) else "Medium Risk",
            "xai_words": [{"word": w, "delta_p": v, "rule_weight": v} for w, v in evid],
            "explanation": (f"A live countdown ('{snippet.strip()}') pressures the user to decide before the clock runs out. "
                            f"Delivery-cutoff timers can be genuine, so check that this one reflects a real cutoff and does not "
                            f"reset when the page is reloaded."),
            "how_to_fix": rem["how_to_fix"],
            "source_type": ("Countdown Timer Detector (OCR + colour check)" if c["bbox"] else "Countdown Timer Detector (text)") + HEURISTIC_TAG,
            "verdict": VERDICT_DARK,
        }
        if c["bbox"]:
            f["bbox"] = [int(v) for v in c["bbox"]]
        findings.append(f)
    return findings


# ---- Screenshot auditor helpers ----
def _to_rgb_uint8(img):
    if img is None:
        raise ValueError("No image provided")
    arr = np.asarray(img)
    if arr.size == 0:
        raise ValueError("Empty image")
    if arr.dtype != np.uint8:
        arr = np.clip(arr * 255 if arr.max() <= 1.0 else arr, 0, 255).astype(np.uint8)
    if arr.ndim == 2:
        arr = np.stack([arr] * 3, axis=-1)
    elif arr.shape[2] == 1:
        arr = np.repeat(arr, 3, axis=2)
    elif arr.shape[2] == 4:
        alpha = arr[:, :, 3:4].astype(np.float32) / 255.0
        arr = (arr[:, :, :3] * alpha + 255 * (1 - alpha)).astype(np.uint8)
    return np.ascontiguousarray(arr[:, :, :3])


def _overlap_frac(a, b):
    """Fraction of box a (x1,y1,x2,y2) that lies inside box b."""
    ix1, iy1, ix2, iy2 = max(a[0], b[0]), max(a[1], b[1]), min(a[2], b[2]), min(a[3], b[3])
    inter = max(0, ix2 - ix1) * max(0, iy2 - iy1)
    area = max(1, (a[2] - a[0]) * (a[3] - a[1]))
    return inter / float(area)


def _read_small_colored_subtext(reader, image_rgb, existing_raw):
    """Finds small warm/orange/red text strips on light backgrounds (such as 9px 'Order in 00h 26m 43s'
    under delivery details) that standard grayscale OCR can miss, enhances their blue/min-channel contrast,
    upscales 2.5x, and reads them with EasyOCR."""
    import cv2
    H, W = image_rgb.shape[:2]
    hsv = cv2.cvtColor(image_rgb, cv2.COLOR_RGB2HSV)
    warm = (((hsv[:, :, 0] <= 26) | (hsv[:, :, 0] >= 160)) & (hsv[:, :, 1] >= 35) & (hsv[:, :, 2] >= 110)).astype(np.uint8) * 255
    kernel = cv2.getStructuringElement(cv2.MORPH_RECT, (18, 3))
    connected = cv2.dilate(warm, kernel, iterations=1)
    contours, _ = cv2.findContours(connected, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)

    extra = []
    for cnt in contours:
        x, y, w, h = cv2.boundingRect(cnt)
        if not (6 <= h <= 48 and w >= 35 and w >= 1.8 * h):
            continue
        cand_box = (x, y, x + w, y + h)
        # Skip if an existing OCR box already covers this strip and has timer/meaningful text
        if any(_overlap_frac(cand_box, r["bbox"]) > 0.45 and match_countdown(r["text"]) for r in existing_raw):
            continue
        pad_x, pad_y = 10, 6
        x1, y1 = max(0, x - pad_x), max(0, y - pad_y)
        x2, y2 = min(W, x + w + pad_x), min(H, y + h + pad_y)
        patch = image_rgb[y1:y2, x1:x2]
        if patch.size == 0 or float(np.median(patch)) < 160.0:
            continue
        # Orange/red ink has a dark Blue channel -> min(R,G,B) turns faint orange ink into high-contrast dark text
        min_ch = patch.min(axis=2)
        lo, hi = float(np.percentile(min_ch, 5)), float(np.percentile(min_ch, 90))
        if hi - lo < 20:
            continue
        stretched = np.clip((min_ch.astype(np.float32) - lo) * (255.0 / (hi - lo)), 0, 255).astype(np.uint8)
        up = cv2.resize(stretched, None, fx=2.5, fy=2.5, interpolation=cv2.INTER_CUBIC)
        for (bbox, text, conf) in reader.readtext(up):
            t = _fix_ocr_timer_typos(text.strip())
            if len(t) < 2 or conf < 0.15:
                continue
            pts = np.array(bbox, dtype=np.float32) / 2.5
            bx1 = int(x1 + pts[:, 0].min())
            by1 = int(y1 + pts[:, 1].min())
            bx2 = int(x1 + pts[:, 0].max())
            by2 = int(y1 + pts[:, 1].max())
            extra.append({"bbox": (bx1, by1, bx2, by2), "text": t, "conf": float(conf)})
    return extra


def analyze_screenshot(image_np, out="outputs/model", yolo_weights=None):
    """
    Feature 5: Screenshot & Visual Logic (EasyOCR + Colored Subtext Booster + Button Asymmetry + Ticked Checkbox + Timers).
    Accepts an RGB numpy image, runs OCR + DistilBERT XAI + OpenCV visual checks,
    and returns the annotated RGB image plus a unified findings list.
    """
    import cv2
    import easyocr

    image_np = _to_rgb_uint8(image_np)
    if max(image_np.shape[:2]) > MAX_IMG_SIDE:
        s = MAX_IMG_SIDE / float(max(image_np.shape[:2]))
        image_np = cv2.resize(image_np, (int(image_np.shape[1] * s), int(image_np.shape[0] * s)),
                              interpolation=cv2.INTER_AREA)

    if "_OCR_READER" not in _MODEL_CACHE:
        _MODEL_CACHE["_OCR_READER"] = easyocr.Reader(["en"], gpu=torch.cuda.is_available(), verbose=False)
    reader = _MODEL_CACHE["_OCR_READER"]

    annotated = image_np.copy()
    H, W, _ = annotated.shape
    findings = []
    ocr_items = []

    # Step A: High-recall OCR + small colored subtext pass so 9px orange countdown timers are never missed
    raw = []
    ocr_results = reader.readtext(
        image_np, mag_ratio=1.5, text_threshold=0.5, low_text=0.28, contrast_ths=0.05, adjust_contrast=0.7
    )
    for (bbox, text, ocr_conf) in ocr_results:
        t = _fix_ocr_timer_typos(text.strip())
        if len(t) < 2 or ocr_conf < MIN_OCR_CONF:
            continue
        pts = np.array(bbox, dtype=np.int32)
        raw.append({"bbox": (int(pts[:, 0].min()), int(pts[:, 1].min()), int(pts[:, 0].max()), int(pts[:, 1].max())),
                    "text": t, "conf": float(ocr_conf)})

    # Add any small orange/red text strips that default OCR missed or misread
    # Add any small orange/red text strips that default OCR missed or misread
    for ext in _read_small_colored_subtext(reader, image_np, raw):
        replaced = False
        for r in raw:
            if _overlap_frac(ext["bbox"], r["bbox"]) > 0.45 or _overlap_frac(r["bbox"], ext["bbox"]) > 0.45:
                if match_countdown(ext["text"]) and not match_countdown(r["text"]):
                    r["text"] = ext["text"]
                    r["bbox"] = ext["bbox"]
                replaced = True
                break
        if not replaced:
            raw.append(ext)

    merged = merge_ocr_boxes(raw)
    for m in merged:
        m["cls"] = should_classify(m["text"])
    to_cls = [m["text"] for m in merged if m["cls"]]
    nlp_preds = predict(to_cls, out=out, explain=True, surface="screenshot") if to_cls else []
    pred_iter = iter(nlp_preds)

    for m in merged:
        x1, y1, x2, y2 = m["bbox"]
        pred_info = next(pred_iter) if m["cls"] else _skipped_finding(m["text"])
        pred_info["bbox"] = [x1, y1, x2, y2]
        findings.append(pred_info)
        ocr_items.append({"bbox": (x1, y1, x2, y2), "text": m["text"], "pred": pred_info})

    # Step E (run before drawing Step A boxes so timer upgrades draw purely in Red without green underneath)
    for tf in detect_countdown_timers(raw, image_np):
        tb = tf["bbox"]
        if any(f.get("is_dark_pattern") and f.get("category") == "Urgency" and f.get("bbox")
               and (_overlap_frac(tb, f["bbox"]) > 0.40 or _overlap_frac(f["bbox"], tb) > 0.40) for f in findings):
            continue
        # Upgrade overlapping benign finding in-place if present
        upgraded = False
        for idx, f in enumerate(findings):
            if not f.get("is_dark_pattern") and f.get("bbox") and (
                _overlap_frac(tb, f["bbox"]) > 0.40 or _overlap_frac(f["bbox"], tb) > 0.40
            ):
                findings[idx] = tf
                upgraded = True
                break
        if not upgraded:
            findings.append(tf)

    # Draw bounding boxes for ALL detected text & timer items (Green = Benign, Red = Dark Pattern)
    for f in findings:
        if not f.get("bbox"):
            continue
        x1, y1, x2, y2 = f["bbox"]
        if f["is_dark_pattern"]:
            cv2.rectangle(annotated, (x1, y1), (x2, y2), (220, 38, 38), 2)
            label_str = f"{f['category']} ({int(f['confidence'] * 100)}%)"
            cv2.putText(annotated, label_str, (x1, max(18, y1 - 6)),
                        cv2.FONT_HERSHEY_SIMPLEX, 0.52, (220, 38, 38), 2)
        else:
            cv2.rectangle(annotated, (x1, y1), (x2, y2), (34, 197, 94), 2)

    # Step B: visual check 1 -> button size and colour-saturation asymmetry (visual misdirection)
    POS_CTA = re.compile(r"\b(accept|keep|yes|continue|claim|agree|stay|upgrade|buy|subscribe)\b", re.I)
    NEG_CTA = re.compile(r"(?:^\W*no\b|\b(?:cancel|decline|skip|reject|opt out|unsubscribe|dismiss|not now|no thanks|"
                         r"no thank you|maybe later|remind me later|ask me later)\b)", re.I)
    NO_CLAIM = re.compile(r"\bno[\s-]+(?:\w+\s+){0,2}?(?:cost|fees?|charges?|emi|hidden|extra|commitment)\b", re.I)

    pos_buttons, neg_buttons = [], []
    hsv_img = cv2.cvtColor(image_np, cv2.COLOR_RGB2HSV)

    for item in ocr_items:
        if len(item["text"].split()) > 6:
            continue
        x1, y1, x2, y2 = item["bbox"]
        pad_x, pad_y = int((x2 - x1) * 0.25), int((y2 - y1) * 0.35)
        bx1, by1 = max(0, x1 - pad_x), max(0, y1 - pad_y)
        bx2, by2 = min(W, x2 + pad_x), min(H, y2 + pad_y)
        patch_hsv = hsv_img[by1:by2, bx1:bx2]
        mean_sat = float(patch_hsv[:, :, 1].mean()) if patch_hsv.size > 0 else 0.0
        area = float((x2 - x1) * (y2 - y1)) / max(len(item["text"]), 1)

        neg_text = NO_CLAIM.sub("", item["text"])
        if NEG_CTA.search(neg_text):
            neg_buttons.append({"item": item, "area": area, "sat": mean_sat, "box": (bx1, by1, bx2, by2)})
        elif POS_CTA.search(item["text"]):
            pos_buttons.append({"item": item, "area": area, "sat": mean_sat, "box": (bx1, by1, bx2, by2)})

    best_pair = None
    max_dist = max(300, 0.30 * max(H, W))
    for pb in pos_buttons:
        for nb in neg_buttons:
            pcx, pcy = (pb["box"][0] + pb["box"][2]) / 2, (pb["box"][1] + pb["box"][3]) / 2
            ncx, ncy = (nb["box"][0] + nb["box"][2]) / 2, (nb["box"][1] + nb["box"][3]) / 2
            if ((pcx - ncx) ** 2 + (pcy - ncy) ** 2) ** 0.5 > max_dist:
                continue
            ratio = pb["area"] / max(nb["area"], 1e-6)
            sdiff = pb["sat"] - nb["sat"]
            if ratio >= 1.45 or sdiff >= 45.0:
                score = ratio + sdiff / 45.0
                if best_pair is None or score > best_pair[0]:
                    best_pair = (score, pb, nb, ratio, sdiff)

    if best_pair is not None:
        _, best_pos, best_neg, area_ratio, sat_diff = best_pair
        bx1, by1, bx2, by2 = best_neg["box"]
        cv2.rectangle(annotated, (bx1, by1), (bx2, by2), (249, 115, 22), 3)
        cv2.putText(annotated, "Visual Misdirection", (bx1, max(18, by1 - 6)),
                    cv2.FONT_HERSHEY_SIMPLEX, 0.55, (249, 115, 22), 2)
        rem = REMEDIATION_GUIDE["Misdirection"]
        asym_score = round(min(0.98, 0.65 + 0.10 * area_ratio + 0.002 * max(0, sat_diff)), 4)
        findings.append({
            "text": f"Visual Button Asymmetry: '{best_pos['item']['text']}' vs '{best_neg['item']['text']}'",
            "category": "Misdirection",
            "is_dark_pattern": True,
            "confidence": asym_score,
            "heuristic_score": asym_score,
            "risk_level": "High Risk",
            "xai_words": [
                {"word": f"Area Ratio: {area_ratio:.2f}x", "delta_p": 0.45, "rule_weight": 0.45},
                {"word": f"Color Saturation Diff: +{sat_diff:.0f}", "delta_p": 0.35, "rule_weight": 0.35}
            ],
            "explanation": (
                f"Visual Interference detected: The accept option ('{best_pos['item']['text']}') has "
                f"{area_ratio:.1f}x larger visual footprint and +{sat_diff:.0f} higher color saturation "
                f"than the low-contrast opt-out ('{best_neg['item']['text']}')."
            ),
            "how_to_fix": rem["how_to_fix"],
            "source_type": "OpenCV Visual Hierarchy & Contrast Check" + HEURISTIC_TAG,
            "verdict": VERDICT_DARK,
            "bbox": [int(bx1), int(by1), int(bx2), int(by2)]
        })

    # Step C (V3): pre-selected checkbox detector
    for (x, y, w, h, nearby_text) in find_ticked_checkboxes(image_np, ocr_items):
        paid = _is_paid_checkbox(nearby_text)
        cv2.rectangle(annotated, (x, y), (x + w, y + h), (168, 85, 247), 3)
        cv2.putText(annotated, "Pre-Ticked [x]" if paid else "Pre-Ticked [x] (low risk)",
                    (x, max(18, y - 6)), cv2.FONT_HERSHEY_SIMPLEX, 0.5, (168, 85, 247), 2)
        rem = REMEDIATION_GUIDE["Preselected Choice"]
        box = [int(x), int(y), int(x + w), int(y + h)]
        if paid:
            findings.append({
                "text": f"Pre-selected Checkbox [☑]: '{nearby_text}'",
                "category": "Preselected Choice",
                "is_dark_pattern": True,
                "confidence": 0.91,
                "heuristic_score": 0.91,
                "risk_level": "High Risk",
                "xai_words": [{"word": "Checkbox Ticked (☑)", "delta_p": 0.58, "rule_weight": 0.58}],
                "explanation": f"Detected a pre-ticked checkbox next to '{nearby_text}', nudging users into an unintended selection.",
                "how_to_fix": rem["how_to_fix"],
                "source_type": "Visual Checkbox State Detector" + HEURISTIC_TAG,
                "verdict": VERDICT_DARK,
                "bbox": box
            })
        else:
            findings.append({
                "text": f"Pre-selected Checkbox [☑]: '{nearby_text}'",
                "category": BENIGN,
                "is_dark_pattern": False,
                "confidence": 0.20,
                "heuristic_score": 0.20,
                "risk_level": "Low Risk / Benign Pre-selection",
                "xai_words": [{"word": "Checkbox Ticked (☑)", "delta_p": 0.10, "rule_weight": 0.10}],
                "explanation": f"Detected a ticked checkbox next to '{nearby_text}'. Its label does not suggest a paid add-on, fee, donation or subscription, so it is treated as a routine (benign) pre-selection.",
                "how_to_fix": "No change needed for routine options. Keep optional paid extras unticked by default.",
                "source_type": "Visual Checkbox State Detector" + HEURISTIC_TAG,
                "verdict": VERDICT_BENIGN_PRESELECT,
                "bbox": box
            })

    # Step D (V3): disguised ads
    nav_items = []
    try:
        strip_h = int(AD_NAV_TOP_FRAC * H)
        if strip_h >= 12:
            strip = cv2.resize(image_np[:strip_h], None, fx=2.0, fy=2.0, interpolation=cv2.INTER_CUBIC)
            for (bbox, text, ocr_conf) in reader.readtext(strip):
                t = text.strip()
                if len(t) < 2 or ocr_conf < MIN_OCR_CONF:
                    continue
                pts = np.array(bbox, dtype=np.float32) / 2.0
                nav_items.append({"bbox": (int(pts[:, 0].min()), int(pts[:, 1].min()),
                                           int(pts[:, 0].max()), int(pts[:, 1].max())),
                                  "text": t, "conf": float(ocr_conf)})
    except Exception:
        nav_items = []
    ad_findings, ad_marks = detect_disguised_ads(image_np, raw, nav_items)
    for (ax1, ay1, ax2, ay2), lab in ad_marks:
        cv2.rectangle(annotated, (ax1, ay1), (ax2, ay2), (245, 158, 11), 3)
        cv2.putText(annotated, lab, (ax1, max(18, ay1 - 6)), cv2.FONT_HERSHEY_SIMPLEX, 0.5, (245, 158, 11), 2)
    findings.extend(ad_findings)

    return annotated, findings


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--data", default="ec-darkpattern/dataset/dataset.tsv")
    ap.add_argument("--model", default="distilbert-base-uncased")
    ap.add_argument("--out", default="outputs/model")
    ap.add_argument("--epochs", type=int, default=5)
    ap.add_argument("--bs", type=int, default=16)
    ap.add_argument("--lr", type=float, default=3e-5)
    ap.add_argument("--max_len", type=int, default=64)
    ap.add_argument("--patience", type=int, default=2)
    ap.add_argument("--seed", type=int, default=42)
    ap.add_argument("--predict", nargs="*")
    # V2 options
    ap.add_argument("--extra_data", nargs="*", help="TSV files (text, Pattern Category, page_id) added to TRAIN only")
    ap.add_argument("--extra_repeat", type=int, default=3, help="repeat extra rows N times (they are few)")
    ap.add_argument("--synthetic", type=int, default=200, help="synthetic contrast pairs per side (0 = off)")
    ap.add_argument("--no_gate", action="store_true", help="disable the context gate in --predict")
    ap.add_argument("--surface", default="text", choices=list(SURFACE_MIN_THRESHOLD))
    ap.add_argument("--build_from_images", help="folder of screenshots -> OCR -> TSV for --extra_data")
    ap.add_argument("--image_label", default="benign", choices=["benign", "predict"])
    ap.add_argument("--build_from_yolo", help="folder of YOLO-dataset images")
    ap.add_argument("--yolo_labels", help="folder with YOLO .txt label files")
    ap.add_argument("--yolo_names", help="classes.txt or data.yaml with the class names")
    ap.add_argument("--tsv_out", default="extra_from_images.tsv")
    a = ap.parse_args()
    if a.build_from_images:
        build_from_images(a.build_from_images, a.image_label, a.tsv_out, a.out)
        raise SystemExit
    if a.build_from_yolo:
        build_from_yolo(a.build_from_yolo, a.yolo_labels, a.yolo_names, a.tsv_out)
        raise SystemExit
    if a.predict is not None:
        for r in predict(a.predict, a.out, surface=a.surface, gate=not a.no_gate):
            print(json.dumps(r, indent=2))
    else:
        train(a)