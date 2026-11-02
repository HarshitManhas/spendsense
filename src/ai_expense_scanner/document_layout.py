"""Receipt layout parsing: keep multiword text, separate columns and labeled fields."""
import re

from .currency import detect_currency, money
from .ml.data import receipt_date
from .ocr_fields import extract_fields, group_rows
from .ocr_items import extract_items

VERSION = 'document-layout-v2'


def preserve_gaps(lines):
    result = []
    for line in lines:
        text = line['text']
        parts = list(re.finditer(r'\S+(?:[^\S\r\n]\S+)*', text)) if re.search(r'\s{2,}', text) else []
        if len(parts) < 2:
            result.append(line); continue
        x1, y1, x2, y2 = line['box']
        for part in parts:
            result.append({**line, 'text': part.group(),
                           'box': [x1 + (x2-x1)*part.start()/len(text), y1,
                                   x1 + (x2-x1)*part.end()/len(text), y2]})
    return result


def text_blocks(lines):
    """Split spatially distant cells without treating every word space as a field."""
    result = []
    for row in group_rows(lines):
        cells = []
        for piece in row['pieces']:
            if cells and piece['box'][0] - cells[-1][-1]['box'][2] <= max(12, row['height'] * 1.4):
                cells[-1].append(piece)
            else:
                cells.append([piece])
        for cell in cells:
            result.append({'text': ' '.join(p['text'] for p in cell),
                'box': [min(p['box'][0] for p in cell), min(p['box'][1] for p in cell),
                        max(p['box'][2] for p in cell), max(p['box'][3] for p in cell)],
                'confidence': min(p['confidence'] for p in cell)})
    return result


def heading(text):
    text = re.sub(r'[^a-z ]', '', ' '.join(text.casefold().split())).strip()
    return {'description': 'name', 'item': 'name', 'item name': 'name', 'product': 'name',
            'qty': 'quantity', 'quantity': 'quantity', 'unit price': 'unit_price', 'rate': 'unit_price',
            'price': 'unit_price', 'net amount': 'net', 'tax amount': 'tax',
            'total amount': 'gross', 'line total': 'gross', 'amount': 'gross', 'total': 'gross'}.get(text)


def table_items(lines, tables):
    items, totals, taxes, evidence = [], [], [], []
    for table in tables:
        columns = {heading(cell['text']): cell['box'] for cell in table['headers'] if heading(cell['text'])}
        if 'name' not in columns or not ({'gross', 'net'} & columns.keys()):
            continue
        all_headers = sorted(table['headers'], key=lambda h: h['box'][0])
        # PDF cells supply exact column boundaries. OCR headers use midpoint boundaries.
        def in_column(piece, box):
            center = (piece['box'][0] + piece['box'][2]) / 2
            return box[0] <= center < box[2]
        bottom = max(h['box'][3] for h in all_headers)
        body = [line for line in lines if (line['box'][1] + line['box'][3]) / 2 > bottom
                and (line['box'][1] + line['box'][3]) / 2 < table['box'][3]
                and table['box'][0] <= (line['box'][0] + line['box'][2]) / 2 < table['box'][2]]
        rows = group_rows(body)
        anchors = []
        summary_top = table['box'][3]
        for row in rows:
            cells = {key: ' '.join(p['text'] for p in row['pieces'] if in_column(p, box)) for key, box in columns.items()}
            if re.match(r'^(?:grand\s+)?(?:sub\s*total|total)\s*[:.]?', row['text'], re.I):
                summary_top = min(summary_top, min(p['box'][1] for p in row['pieces']))
                if not re.match(r'^sub', row['text'], re.I):
                    if money(cells.get('gross')) is not None: totals.append(money(cells['gross']))
                    if money(cells.get('tax')) is not None: taxes.append(money(cells['tax']))
                break
            amount = money(cells.get('net') or cells.get('gross'))
            if amount is not None:
                anchors.append((row, cells, amount))
        start = bottom
        for index, (row, cells, amount) in enumerate(anchors):
            stop = min(p['box'][1] for p in anchors[index + 1][0]['pieces']) if index + 1 < len(anchors) else summary_top
            description = [p for p in body if start <= (p['box'][1] + p['box'][3]) / 2 < stop and in_column(p, columns['name'])]
            name = ' '.join(r['text'] for r in group_rows(description))
            # Codes are retained in the source PDF, but are not the product name.
            name = re.split(r'\bHSN\s*:', name, flags=re.I)[0].strip()
            start = stop
            if not name or not re.search(r'[^\W\d_]', name):
                continue
            qty = cells.get('quantity', '').strip()
            qty = qty if re.fullmatch(r'\d+(?:\.\d{1,6})?', qty) and 0 < float(qty) <= 1e6 else None
            items.append({'name': name[:300], 'quantity': qty, 'unit_price': money(cells.get('unit_price')),
                          'line_total': amount})
            evidence.append({'name': name, 'cells': cells})
    return {'items': items[:200], 'total': totals[0] if totals and len(set(totals)) == 1 else None,
            'tax': taxes[0] if taxes and len(set(taxes)) == 1 else None, 'evidence': evidence}


def ocr_tables(lines, image_width, image_height):
    tables = []
    for row in group_rows(lines):
        headers = [p for p in row['pieces'] if heading(p['text'])]
        if not any(heading(p['text']) == 'name' for p in headers) or len(headers) < 3:
            continue
        pieces = row['pieces']
        cells = []
        for i, p in enumerate(pieces):
            left = (pieces[i-1]['box'][2] + p['box'][0]) / 2 if i else 0
            right = (p['box'][2] + pieces[i+1]['box'][0]) / 2 if i + 1 < len(pieces) else image_width
            cells.append({'text': p['text'], 'box': [left, p['box'][1], right, p['box'][3]]})
        tables.append({'headers': cells, 'box': [0, row['center'], image_width, image_height]})
        break
    return tables


def extract_document(lines, width, height, tables=None):
    lines = preserve_gaps(lines)
    base = extract_fields(lines, height)
    blocks = text_blocks(lines)
    fields, warnings = base['fields'], list(base['warnings'])
    currencies = detect_currency(lines)
    fields['currency'] = currencies['currency']
    warnings.extend(currencies['warnings'])
    exact_totals = []
    for row in group_rows(lines):
        match = re.fullmatch(r'(?:grand\s+total|total|amount\s+due)\s*:?\s+(.+)', row['text'], re.I)
        if match and money(match.group(1)) is not None:
            exact_totals.append(money(match.group(1)))
    if exact_totals:
        fields['total'] = exact_totals[0] if len(set(exact_totals)) == 1 else None
    # A labeled seller is stronger evidence than a generic top-of-page header.
    sellers = []
    for block in blocks:
        match = re.match(r'^(?:sold\s+by|seller|supplier)\s*:\s*(.*)$', block['text'], re.I)
        if not match:
            continue
        if match.group(1):
            sellers.append(match.group(1)); continue
        box = block['box']; h = box[3] - box[1]
        following = [b for b in blocks if box[1] + h * .5 < b['box'][1] < box[3] + 2 * h
                     and abs(b['box'][0] - box[0]) < h * 2 and re.search('[A-Za-z]', b['text'])]
        if following:
            sellers.append(min(following, key=lambda b: b['box'][1])['text'])
    if sellers:
        fields['merchant'] = sellers[0][:200] if len(set(sellers)) == 1 else None
        warnings = [w for w in warnings if 'merchant' not in w]
    dates = []
    for row in group_rows(lines):
        match = re.search(r'\b(?:invoice|receipt)\s+date\s*:\s*(\d{1,4}[-/.]\d{1,2}[-/.]\d{2,4})', row['text'], re.I)
        if match:
            dates.append(receipt_date(match.group(1).replace('.', '/')))
    if dates:
        fields['date'] = dates[0] if None not in dates and len(set(dates)) == 1 else None
        warnings = [w for w in warnings if 'date' not in w.casefold()]
        if fields['date'] is None:
            warnings.append('Invoice/receipt date is ambiguous; confirm its day/month order.')
    detail = table_items(lines, tables if tables is not None else ocr_tables(lines, width, height))
    if detail['items']:
        items = detail['items']
        for key in ('tax', 'total'):
            if detail[key] is not None:
                fields[key] = detail[key]
        warnings.append('Items follow table columns; line totals use net amounts when present. Review discounts and tax separately.')
    else:
        fallback = extract_items(lines, height)
        items = fallback['items']; warnings.extend(fallback['warnings'])
    return {'fields': fields, 'items': items, 'warnings': warnings, 'method': VERSION}
