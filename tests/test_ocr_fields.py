from ai_expense_scanner.ocr_fields import extract_fields, parse_amount, numbers


def line(text, y, x=10, width=220, confidence=.99):
    return {'text': text, 'box': [x, y, x + width, y + 20], 'confidence': confidence}


def test_layout_associates_total_and_tax_without_using_subtotal_or_percent():
    lines = [line('TEST TRADERS SDN BHD', 10), line('Date: 25/12/2018', 60),
             line('Subtotal', 200), line('100.00', 200, 350, 80),
             line('GST 6%', 240), line('6.00', 240, 350, 80),
             line('GRAND TOTAL', 280), line('RM106.00', 280, 350, 90),
             line('CASH 200.00', 320), line('CHANGE 94.00', 360)]
    result = extract_fields(lines, 600)
    assert result['fields'] == {'merchant': 'TEST TRADERS SDN BHD', 'date': '2018-12-25',
                                'total': '106.00', 'tax': '6.00', 'currency': 'MYR'}
    assert result['evidence']['total'][0]['line_indices'] == [6, 7]


def test_unknown_and_conflicting_values_are_not_guessed():
    result = extract_fields([line('Date: 12/01/2018', 10), line('TOTAL 12.00', 200), line('TOTAL 15.00', 300)], 600)
    assert result['fields']['date'] is None
    assert result['fields']['total'] is None
    assert result['fields']['tax'] is None
    assert result['fields']['currency'] is None
    assert len(result['warnings']) == 2


def test_amount_formats_and_identifiers_are_not_silently_repaired():
    assert parse_amount('1,591,600') == '1591600'
    assert parse_amount('48.000') == '48000'
    assert parse_amount('1.234,56') == '1234.56'
    assert parse_amount('60.30') == '60.30'
    assert parse_amount('1,23,456') is None
    assert numbers('10 % RM9.00') == ['9.00']
    assert numbers('9.00A -123 25/12/2018') == []


def test_low_confidence_and_unsupported_currency_do_not_create_fields():
    result = extract_fields([line('TOTAL 99.00', 200, confidence=.1), line('$ 15.00', 240)], 600)
    assert result['fields']['total'] is None
    assert result['fields']['currency'] is None


def test_final_rounded_total_wins_and_tax_registration_is_not_tax_amount():
    result = extract_fields([line('GST ID :000123456789', 20), line('TOTAL RM 33.92', 200),
                             line('TOTAL ROUNDED RM 33.90', 260), line('GST SUMMARY', 320),
                             line('Total: 33.92 0.00', 360)], 600)
    assert result['fields']['total'] == '33.90'
    assert result['fields']['tax'] is None
    assert numbers('1, 591, 600') == ['1591600']


def test_sloping_receipt_rows_use_polygon_orientation():
    lines = []
    # Two different rows; receipt slopes upward to the right. Axis-aligned
    # centers alone would pair TAX with the following SERVICE amount.
    for text, x, baseline in [('SUBTOTAL', 10, 200), ('100.00', 400, 200),
                               ('TAX', 10, 240), ('6.00', 400, 240),
                               ('SERVICE', 10, 280), ('5.00', 400, 280),
                               ('TOTAL', 10, 320), ('111.00', 400, 320)]:
        y = baseline - .08 * x
        polygon = [[x, y], [x + 100, y - 8], [x + 100, y + 12], [x, y + 20]]
        lines.append({'text': text, 'confidence': .99, 'polygon': polygon,
                      'box': [x, y - 8, x + 100, y + 20]})
    result = extract_fields(lines, 500)
    assert result['fields']['tax'] == '6.00'
    assert result['fields']['total'] == '111.00'
