"""Conservative, dataset-independent receipt rules over local OCR text and boxes.

No reference labels, source names, countries, or training records are inputs.
Confidence values describe supporting OCR text, not calibrated field accuracy.
"""
from datetime import datetime
from decimal import Decimal, InvalidOperation
import re
import statistics

from .ml.data import FIELDS, receipt_date

RULE_VERSION = 'ocr-rules-v1'
NUMBER = re.compile(r'(?<![\w./-])\d+(?:[.,]\d+)*(?![\w/.,])')
TOTAL = re.compile(r'\b(grand\s*total|net[t]?\s*total|amount\s*(?:due|payable)|total\s*bayar|jumlah\s*bayar|total|due)\b', re.I)
TAX = re.compile(r'\b(tax|gst|sst|vat|ppn|pb1)\b', re.I)


def parse_amount(text):
    """Parse explicit decimal/grouping syntax without dataset-specific hints."""
    if not re.fullmatch(r'\d+(?:[.,]\d+)*', text):
        return None
    separators = [i for i, c in enumerate(text) if c in '.,']
    if not separators:
        normalized = text
    else:
        tail = len(text) - separators[-1] - 1
        if tail in (1, 2):
            integer = text[:separators[-1]]
            groups = re.split(r'[.,]', integer)
            if len(groups) > 1 and (not 1 <= len(groups[0]) <= 3 or any(len(x) != 3 for x in groups[1:])):
                return None
            normalized = ''.join(groups) + '.' + text[separators[-1] + 1:]
        elif tail == 3:
            groups = re.split(r'[.,]', text)
            if not 1 <= len(groups[0]) <= 3 or any(len(x) != 3 for x in groups[1:]):
                return None
            normalized = ''.join(groups)
        else:
            return None
    try:
        return format(Decimal(normalized), 'f')
    except InvalidOperation:
        return None


def group_rows(lines, threshold=.5):
    slopes = []
    for line in lines:
        poly = line.get('polygon')
        if poly and len(poly) == 4 and line.get('confidence', 0) >= threshold:
            dx, dy = poly[1][0] - poly[0][0], poly[1][1] - poly[0][1]
            if dx > 20 and abs(dy / dx) < .25:
                slopes.append(dy / dx)
    slope = statistics.median(slopes) if len(slopes) >= 3 else 0
    pieces = []
    for index, line in enumerate(lines):
        text = ' '.join(line.get('text', '').split())
        box = line.get('box', [])
        if not text or len(box) != 4 or line.get('confidence', 0) < threshold:
            continue
        x1, y1, x2, y2 = map(float, box)
        if x2 <= x1 or y2 <= y1:
            continue
        pieces.append({'text': text, 'box': [x1, y1, x2, y2], 'confidence': float(line['confidence']), 'index': index,
                       'center': (y1 + y2) / 2 - slope * (x1 + x2) / 2})
    rows = []
    for piece in sorted(pieces, key=lambda item: (item['center'], item['box'][0])):
        box = piece['box']; center = piece['center']
        matching = [r for r in rows if abs(r['center'] - center) <= .45 * min(r['height'], box[3] - box[1])]
        if matching:
            row = min(matching, key=lambda r: abs(r['center'] - center)); row['pieces'].append(piece)
        else:
            rows.append({'center': center, 'height': box[3] - box[1], 'pieces': [piece]})
    for row in rows:
        row['pieces'].sort(key=lambda item: item['box'][0])
        row['text'] = ' '.join(piece['text'] for piece in row['pieces'])
        row['confidence'] = min(piece['confidence'] for piece in row['pieces'])
        row['indices'] = [piece['index'] for piece in row['pieces']]
    return sorted(rows, key=lambda row: row['center'])


def numbers(text, after=0):
    text = re.sub(r'\b(?:RM|RP|IDR|MYR|INR|USD)(?=\d)', ' ', text[after:], flags=re.I)
    text = re.sub(r'(?<=\d)([.,])\s+(?=\d)', r'\1', text)
    result = []
    for match in NUMBER.finditer(text):
        if text[match.end():].lstrip().startswith('%'):
            continue
        value = parse_amount(match.group())
        if value is not None:
            result.append(value)
    return result


def candidate(value, row, score, reason):
    return {'value': value, 'text': row['text'], 'line_indices': row['indices'],
            'ocr_confidence': row['confidence'], 'priority': score, 'reason': reason}


def extract_fields(lines, image_height):
    rows = group_rows(lines)
    evidence = {key: [] for key in FIELDS}
    warnings = []
    in_tax_summary = False
    for index, row in enumerate(rows):
        text = row['text']
        if re.search(r'\b(?:gst|sst|tax|vat)\s+summary\b|\btax\s+code\b', text, re.I):
            in_tax_summary = True
        for field, pattern in [('total', TOTAL), ('tax', TAX)]:
            match = pattern.search(text)
            if not match:
                continue
            if field == 'total' and (in_tax_summary or re.search(r'\bsub[\s.-]*total\b|\b(items?|qty|quantity|savings?|discount|date)\b', text, re.I)
                                      or re.search(r'\btotal\s+(?:tax|gst|sst|vat|ppn)\b', text, re.I)):
                continue
            if field == 'tax' and ((TOTAL.search(text) and not re.search(r'\btotal\s+(?:tax|gst|sst|vat|ppn|pb1)\b', text, re.I))
                                   or re.search(r'\b(reg|registration|invoice|inclusive|incl|before|after|taxable|id|no|number|summary|code)\b', text, re.I)):
                continue
            values = numbers(text, match.end())
            supporting = row
            if not values and index + 1 < len(rows):
                following = rows[index + 1]
                # Accept a value directly below only when the row is just money.
                if following['center'] - row['center'] <= 2.0 * max(row['height'], following['height']) and re.fullmatch(r'(?:(?:RM|RP|IDR|MYR|INR|USD)\s*)?[\d.,]+', following['text'], re.I):
                    values = numbers(following['text'])
                    supporting = dict(row, text=text + ' / ' + following['text'], indices=row['indices'] + following['indices'],
                                      confidence=min(row['confidence'], following['confidence']))
            if values:
                score = 100 if field == 'total' and re.search(r'grand|amount|net|bayar', match.group(), re.I) else 80
                if field == 'total' and re.search(r'rounded|rounding|inclusiv', text, re.I):
                    score = 110
                elif field == 'total' and re.search(r'exclud|before', text, re.I):
                    score = 60
                evidence[field].append(candidate(values[-1], supporting, score, 'amount following an explicit field label'))

        if not re.search(r'expir|valid until|due date', text, re.I):
            for match in re.finditer(r'(?<!\d)(\d{1,4}[-/.]\d{1,2}[-/.]\d{2,4})(?!\d)', text):
                value = receipt_date(match.group().replace('.', '/'))
                if value:
                    evidence['date'].append(candidate(value, row, 100 if re.search(r'\bdate\b', text, re.I) else 80, 'unambiguous printed date'))
                else:
                    warnings.append(f'Ambiguous or invalid date left unresolved: {match.group()}')
            for match in re.finditer(r'\b(\d{1,2})[\s/-]+([A-Za-z]{3,9})[\s/-]+(\d{4})\b', text):
                for fmt in ('%d %b %Y', '%d %B %Y'):
                    try:
                        value = datetime.strptime(' '.join(match.groups()), fmt).date().isoformat()
                        evidence['date'].append(candidate(value, row, 80, 'printed date with named month'))
                        break
                    except ValueError:
                        pass
        currency_codes = set(re.findall(r'\b(?:IDR|MYR|INR|USD|EUR|GBP)\b', text.upper()))
        for pattern, code in [(r'\bRM\s*\d', 'MYR'), (r'\bRP\.?\s*\d', 'IDR'), ('₹', 'INR'), ('€', 'EUR'), ('£', 'GBP')]:
            if re.search(pattern, text, re.I): currency_codes.add(code)
        for code in currency_codes:
            evidence['currency'].append(candidate(code, row, 80, 'explicit currency code or unambiguous symbol'))

    header = [row for row in rows[:8] if row['center'] < image_height * .35]
    for index, row in enumerate(header):
        text = row['text']
        if (len(re.findall(r'[A-Za-z]', text)) < 3 or re.search(r'\b(receipt|invoice|cashier|tel|fax|www|http|gst|sst|registration|jalan|jln|lot|no\.?|thank|welcome|date|time)\b|@', text, re.I)):
            continue
        if re.search(r'\d[\d., ]*[.,]\d{2,3}\s*$', text):
            continue  # Product lines with prices are not company headers.
        value = re.sub(r'\s*\(\d[\w-]{4,}\)\s*$', '', text).strip()
        legal = bool(re.search(r'\b(?:SDN\.?\s*BHD\.?|BERHAD|ENTERPRISE|LTD\.?|LIMITED|LLC)\b', text, re.I))
        if re.fullmatch(r'SDN\.?\s*BHD\.?', value, re.I) and index:
            previous = header[index - 1]
            if re.fullmatch(r'[A-Za-z &.\-]+', previous['text']):
                value = previous['text'] + ' ' + value
                row = dict(row, text=value, indices=previous['indices'] + row['indices'], confidence=min(previous['confidence'], row['confidence']))
        header_score = (85 if text.isupper() else 70) - index
        evidence['merchant'].append(candidate(value, row, 100 if legal else header_score, 'company header' if legal else 'top-of-receipt text; requires review'))

    fields = dict.fromkeys(FIELDS)
    for field, candidates in evidence.items():
        if not candidates:
            continue
        priority = max(c['priority'] for c in candidates)
        strongest = [c for c in candidates if c['priority'] == priority]
        distinct = {Decimal(c['value']) if field in {'tax', 'total'} else c['value'] for c in strongest}
        if len(distinct) == 1:
            fields[field] = strongest[0]['value']
        else:
            warnings.append(f'Conflicting {field} candidates; human review required')
    return {'fields': fields, 'evidence': evidence, 'warnings': sorted(set(warnings)), 'method': RULE_VERSION}
