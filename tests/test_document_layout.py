import pytest

from ai_expense_scanner.currency import detect_currency, money
from ai_expense_scanner.document_layout import extract_document, preserve_gaps
from ai_expense_scanner.pdf_text import read_pdf_page


def line(text, x=10, y=250, w=150, h=16):
    return {'text': text, 'box': [x, y, x+w, y+h], 'confidence': .99}


@pytest.mark.parametrize('text, expected', [('₹150', 'INR'), ('EUR 20.00', 'EUR'), ('€20', 'EUR'),
    ('£30', 'GBP'), ('US$40', 'USD'), ('JPY ¥500', 'JPY'), ('RM10', 'MYR'), ('Rp. 1000', 'IDR'),
    ('$40', None), ('¥500', None), ('Rs.100', None), ('INR ₹100', 'INR')])
def test_currency_symbols_and_shared_signs(text, expected):
    assert detect_currency([line(text)])['currency'] == expected


def test_currency_conflicts_and_amount_grouping():
    assert detect_currency([line('INR 100'), line('£20')])['currency'] is None
    assert detect_currency([line('INR 100'), line('$20')])['currency'] is None
    assert money('₹1,23,456.78') == '123456.78'
    assert money('€1 234,56') == '1234.56'
    assert money('100 200.00') == '100200.00'  # Valid thousands grouping in one money cell.
    assert money('2 50.00') is None
    assert money('18%') is None


def test_spaces_preserve_multiword_names_and_separate_money():
    pieces = preserve_gaps([line('Green Tea    2    ₹50.00    ₹100.00', w=500)])
    assert [p['text'] for p in pieces] == ['Green Tea', '2', '₹50.00', '₹100.00']
    result = extract_document([line('Green Tea    2    ₹50.00    ₹100.00', w=500)], 600, 600)
    assert result['items'] == [{'name': 'Green Tea', 'quantity': '2', 'unit_price': '50.00', 'line_total': '100.00'}]
    single = extract_document([line('Green Tea 2 ₹50.00 ₹100.00', w=500)], 600, 600)
    assert single['items'] == result['items']


def test_seller_buyer_columns_and_invoice_date_priority():
    result = extract_document([line('Sold By:', y=80), line('Billing Address:', x=400, y=80),
        line('Example Seller Limited', y=100, w=220), line('Buyer Name', x=400, y=100),
        line('Order Date: 05.06.2026', y=320), line('Invoice Date: 06.06.2026', x=300, y=350),
        line('TOTAL ₹500.00', y=450)], 650, 700)
    assert result['fields']['merchant'] == 'Example Seller Limited'
    assert result['fields']['date'] == '2026-06-06'
    assert result['fields']['currency'] == 'INR'
    assert result['fields']['total'] == '500.00'


def test_table_columns_keep_tax_and_shipping_out_of_description():
    headers = [{'text': name, 'box': [x, 200, x+width, 220]} for name, x, width in
               [('Description', 10, 240), ('Unit Price', 250, 80), ('Qty', 330, 40),
                ('Net Amount', 370, 80), ('Tax Amount', 450, 80), ('Total Amount', 530, 100)]]
    rows = [line('Long Product', y=230), line('with several words', y=250),
            line('₹100.00', 255, 250, 65), line('2', 335, 250, 10), line('₹200.00', 375, 250, 65),
            line('₹36.00', 455, 250, 65), line('₹236.00', 535, 250, 65),
            line('more description', y=275), line('Shipping Charges', y=300),
            line('₹30.00', 255, 300, 65), line('₹0.00', 375, 300, 65), line('₹0.00', 535, 300, 65),
            line('TOTAL:', y=330), line('₹36.00', 455, 330, 65), line('₹236.00', 535, 330, 65)]
    result = extract_document(rows, 650, 700, [{'headers': headers, 'box': [10, 200, 630, 400]}])
    assert result['items'][0] == {'name': 'Long Product with several words more description', 'quantity': '2',
                                  'unit_price': '100.00', 'line_total': '200.00'}
    assert result['items'][1]['name'] == 'Shipping Charges'
    assert result['items'][1]['line_total'] == '0.00'
    assert result['fields']['tax'] == '36.00'
    assert result['fields']['total'] == '236.00'


def test_native_pdf_page_selection_and_scanned_fallback():
    import pymupdf
    with pymupdf.open() as document:
        document.new_page().insert_text((40, 50), 'First page has enough individual words to select native text INR 20')
        document.new_page().insert_text((40, 50), 'Second page has enough individual words to select native text EUR 30')
        content = document.tobytes()
    assert any(word['text'] == 'EUR' for word in read_pdf_page(content, 2)['lines'])
    assert read_pdf_page(content, 3) is None
    with pymupdf.open() as document:
        document.new_page()
        assert read_pdf_page(document.tobytes(), 1) is None
    assert read_pdf_page(b'not pdf', 1) is None


def test_pdf_footer_does_not_suppress_image_recognition(monkeypatch):
    from ai_expense_scanner import extraction
    monkeypatch.setattr(extraction, 'read_pdf_page', lambda *args: {'width': 600, 'height': 800,
        'lines': [line('Thank you for shopping with our store', y=700)], 'tables': []})
    assert extraction.native_prediction(b'%PDF-test') is None
