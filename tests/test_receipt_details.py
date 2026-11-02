import pytest

from ai_expense_scanner.ml.prepare_details import cord_items
from ai_expense_scanner.ocr_items import extract_items
from ai_expense_scanner.schemas import Draft, approved_values


def draft(**values):
    return Draft(merchant='Cafe', date='2026-11-02', total='236.00', currency='INR', **values)


def test_item_money_and_adjustment_confirmation():
    fields = draft(category='travel', items=[{'name': ' Breakfast ', 'quantity': '2', 'unit_price': '100', 'line_total': '180'}])
    with pytest.raises(ValueError, match='adjustment'):
        approved_values(fields)
    expense = approved_values(fields, confirm_warnings=True)
    assert expense['expenseDate'] == '2026-11-02'
    assert expense['items'] == [{'name': 'Breakfast', 'quantity': '2', 'unitPriceMinor': 10000, 'lineTotalMinor': 18000}]
    assert expense['category'] == 'travel'
    assert expense['totalMinor'] == 23600  # Item totals never replace the receipt total.


@pytest.mark.parametrize('item', [
    {'name': ''}, {'name': 'Tea', 'quantity': '0'}, {'name': 'Tea', 'quantity': '-2'},
    {'name': 'Tea', 'quantity': 'NaN'}, {'name': 'Tea', 'unit_price': '1.001'},
    {'name': 'Tea', 'line_total': '-1'},
])
def test_invalid_items_cannot_be_approved(item):
    with pytest.raises(ValueError):
        approved_values(draft(items=[item]), confirm_warnings=True)


def test_unknown_item_values_and_invalid_dates():
    assert approved_values(draft(items=[{'name': 'Coffee'}]))['items'][0]['unitPriceMinor'] is None
    assert 'items' not in approved_values(draft())
    for value in ['2026-02-30', '02/11/2026', '20261102']:
        with pytest.raises(ValueError):
            approved_values(draft().model_copy(update={'date': value}))


def test_cord_item_labels_preserve_unknowns_and_modifiers():
    items = cord_items({'gt_parse': {'menu': [
        {'nm': 'Nasi', 'cnt': 'x 2', 'price': '36,000', 'sub_nm': 'Extra hot'},
        {'nm': 'Drink', 'unitprice': '4.500', 'cnt': 'many', 'price': '???'},
    ]}})
    assert items[0]['values'] == {'name': 'Nasi', 'quantity': '2', 'unit_price': None, 'line_total': '36000'}
    assert items[0]['label_states']['unit_price'] == 'unlabeled'
    assert items[0]['raw']['sub_nm'] == 'Extra hot'
    assert items[1]['values']['unit_price'] == '4500'
    assert items[1]['label_states']['quantity'] == 'ambiguous'
    assert cord_items({'gt_parse': {}}) is None


def test_ocr_items_stop_at_summary_and_leave_unknown_prices():
    def line(text, x, y, width):
        return {'text': text, 'confidence': .99, 'box': [x, y, x + width, y + 20]}
    lines = [line('CAFE', 10, 20, 100), line('GST ID 123', 10, 100, 180),
             line('Coffee 2 50.00', 10, 250, 180), line('100.00', 300, 250, 80),
             line('Toast', 10, 300, 90), line('25.00', 300, 300, 80),
             line('Subtotal', 10, 400, 90), line('125.00', 300, 400, 80),
             line('Cash', 10, 450, 90), line('200.00', 300, 450, 80)]
    result = extract_items(lines, 800)
    assert result['items'] == [
        {'name': 'Coffee', 'quantity': '2', 'unit_price': '50.00', 'line_total': '100.00'},
        {'name': 'Toast', 'quantity': None, 'unit_price': None, 'line_total': '25.00'}]
