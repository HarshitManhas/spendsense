"""Experimental item candidates; separate from the frozen five-field baseline."""
import re

from .ocr_fields import group_rows, parse_amount
from .currency import money, PREFIX

VERSION = 'ocr-items-v2'
STOP = re.compile(r'\b(sub[ -]?total|total|amount due|tax|gst|sst|vat|cash|change|balance|payment|discount|rounding|service charge)\b', re.I)
EXCLUDE = re.compile(r'\b(tel|phone|fax|jalan|jln|address|invoice|receipt|cashier|table|date|time|registration|member|points|qty|quantity|price|description|thank)\b|@|https?://', re.I)
MONEY = r'\d+(?:[.,]\d+)*'


def extract_items(lines, image_height):
    items, evidence = [], []
    for row in group_rows(lines, threshold=.65):
        text = row['text']
        if row['center'] < image_height * .15:
            continue
        if STOP.search(text):
            # After the subtotal, payment/summary lines cannot be products.
            if re.search(r'\b(sub[ -]?total|grand total|amount due)\b|^total\b', text, re.I):
                break
            continue
        if EXCLUDE.search(text) or re.search(r'\d[-/]\d', text):
            continue
        # A distinct right-hand money box provides weak layout evidence.
        pieces = row['pieces']
        if len(pieces) >= 2 and money(pieces[-1]['text']) is not None:
            name = ' '.join(p['text'] for p in pieces[:-1])
            total = money(pieces[-1]['text'])
        else:
            # Some recognizers return an entire printed row as one text box.
            trailing = re.fullmatch(r'(.+?)\s+((?:' + PREFIX + r'\s*)?' + MONEY + ')', text, re.I)
            if not trailing:
                continue
            name, raw_total = trailing.groups()
            total = money(raw_total)
        quantity = unit = None
        # Only explicit x quantities or three numeric columns are parsed.
        columns = re.fullmatch(r'(.+?)\s+(\d+(?:\.\d{1,6})?)\s+((?:' + PREFIX + r'\s*)?' + MONEY + ')', name, re.I)
        multiplier = re.fullmatch(r'(.+?)\s+[xX]\s*(\d+(?:\.\d{1,6})?)', name)
        if columns:
            name, quantity, raw_unit = columns.groups()
            unit = money(raw_unit)
        elif multiplier:
            name, quantity = multiplier.groups()
        if total is None or len(re.findall(r'[^\W\d_]', name)) < 2:
            continue
        if quantity is not None and not 0 < float(quantity) <= 10**6:
            quantity = None
        items.append({'name': name[:300], 'quantity': quantity, 'unit_price': unit, 'line_total': total})
        evidence.append({'text': text, 'line_indices': row['indices'], 'ocr_confidence': row['confidence']})
        if len(items) == 200:
            break
    return {'items': items, 'evidence': evidence, 'method': VERSION,
            'warnings': ['Item rows are experimental OCR candidates. Check names, quantities and prices; add missing items.']}
