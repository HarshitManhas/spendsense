import json
import re
from datetime import date
from decimal import Decimal, InvalidOperation

FIELDS = ("merchant", "date", "total", "currency", "tax")


def amount(value, source):
    if not isinstance(value, str) or not value.strip():
        return None
    value = value.strip()
    if source == "cord" and re.fullmatch(r"\d{1,3}(?:,\d{3})+|\d{1,3}(?:\.\d{3})+", value):
        value = value.replace(",", "").replace(".", "")
    if not re.fullmatch(r"\d+(?:\.\d{1,2})?", value):
        return None
    try:
        return format(Decimal(value), "f")
    except InvalidOperation:
        return None


def receipt_date(value):
    """Conservative: reject unresolved day/month and century ambiguity."""
    if not isinstance(value, str):
        return None
    match = re.fullmatch(r"\s*(\d{1,4})[-/](\d{1,2})[-/](\d{2,4})\s*", value)
    if not match:
        return None
    a, b, c = match.groups()
    try:
        if len(a) == 4:
            return date(int(a), int(b), int(c)).isoformat()
        # Dataset contains mixed DD/MM and MM/DD, so never blanket day-first.
        year = int(c) if len(c) == 4 else 2000 + int(c) if c in {"17", "18", "19"} else 0
        if int(a) > 12 or int(a) == int(b):
            return date(year, int(b), int(a)).isoformat()
        if int(b) > 12:
            return date(year, int(a), int(b)).isoformat()
    except ValueError:
        pass
    return None


def adapt(row, source):
    targets = dict.fromkeys(FIELDS)
    states = dict.fromkeys(FIELDS, "unlabeled")
    raw = {}
    if source == "sroie":
        entities = row["entities"]
        raw = {"merchant": entities.get("company"), "date": entities.get("date"), "total": entities.get("total")}
        targets["merchant"] = " ".join((raw["merchant"] or "").split()) or None
        targets["date"] = receipt_date(raw["date"])
        targets["total"] = amount(raw["total"], source)
    elif source == "cord":
        gt = json.loads(row["ground_truth"])["gt_parse"]
        for key, section, field in [("total", "total", "total_price"), ("tax", "sub_total", "tax_price")]:
            value = gt.get(section, {})
            if isinstance(value, dict):
                raw[key] = value.get(field)
                targets[key] = amount(raw[key], source)
            elif isinstance(value, list):
                # Multiple subtotal sections do not establish whole-receipt tax.
                raw[key] = [v.get(field) for v in value if isinstance(v, dict) and field in v]
                states[key] = "ambiguous" if raw[key] else "unlabeled"
    else:
        raise ValueError(f"Unsupported dataset: {source}")
    for key in FIELDS:
        if targets[key] is not None:
            states[key] = "labeled"
        elif raw.get(key):
            states[key] = "ambiguous"
    return {"targets": targets, "label_states": states, "raw": raw}


def serialize_target(targets, states):
    """Return canonical JSON and per-character supervision, including value spans."""
    text, mask = "{", [True]
    for index, key in enumerate(FIELDS):
        prefix = ("," if index else "") + json.dumps(key) + ":"
        value = json.dumps(targets.get(key), ensure_ascii=False)
        text += prefix + value
        mask += [True] * len(prefix) + [states.get(key) in {"labeled", "verified_absent"}] * len(value)
    return text + "}", mask + [True]
