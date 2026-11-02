import json
import pytest

from ai_expense_scanner.ml.data import adapt, amount, receipt_date, serialize_target
from ai_expense_scanner.ml.vocabulary import Vocabulary
from ai_expense_scanner.ml.parsing import parse_prediction


def test_mixed_date_conventions_do_not_silently_swap_days():
    assert receipt_date('25/12/2018') == '2018-12-25'
    assert receipt_date('12/28/2017') == '2017-12-28'
    assert receipt_date('12-01-19') is None
    assert receipt_date('31/02/2018') is None
    assert receipt_date('18/03/18') == '2018-03-18'


def test_amounts_preserve_decimal_meaning():
    assert amount('1,591,600', 'cord') == '1591600'
    assert amount('48.000', 'cord') == '48000'
    assert amount('60.30', 'sroie') == '60.30'
    assert amount('1,23', 'cord') is None
    assert amount('NaN', 'sroie') is None


def test_unlabeled_tax_is_not_a_zero_or_negative_label():
    record = adapt({'entities': {'company': '  A  Store ', 'date': '25/12/2018', 'total': '3.20'}}, 'sroie')
    assert record['targets']['merchant'] == 'A Store'
    assert record['targets']['tax'] is None
    assert record['label_states']['tax'] == 'unlabeled'
    text, mask = serialize_target(record['targets'], record['label_states'])
    start = text.index('null', text.index('"tax"'))
    assert mask[start:start + 4] == [False] * 4
    assert mask[text.index('3.20')]
    assert len(text) == len(mask)


def test_cord_multi_section_tax_requires_audit():
    row = {'ground_truth': json.dumps({'gt_parse': {'total': {'total_price': '100'}, 'sub_total': [{'subtotal_price': '80'}, {'tax_price': '20'}]}})}
    record = adapt(row, 'cord')
    assert record['targets']['total'] == '100'
    assert record['targets']['tax'] is None
    assert record['label_states']['tax'] == 'ambiguous'


def test_escaped_targets_and_training_only_vocabulary():
    record = adapt({'entities': {'company': 'A "shop"', 'total': '1.00'}}, 'sroie')
    text, mask = serialize_target(record['targets'], record['label_states'])
    assert json.loads(text)['merchant'] == 'A "shop"'
    vocab = Vocabulary.build([text])
    assert vocab.decode(vocab.encode(text)) == text
    assert vocab.encode('漢') == [vocab.UNK]
    assert len(text) == len(mask)


def test_prediction_rejects_duplicate_and_missing_fields():
    for text in ['{}', '{"total":"1", "total":"2"}', '[]', '```json\n{}\n```']:
        with pytest.raises(ValueError): parse_prediction(text)


def test_prediction_preserves_unknowns_without_inventing_values():
    record = parse_prediction('{"merchant":"Shop","date":null,"total":"1.00","currency":null,"tax":null}')
    assert record.total == '1.00'
    assert record.tax is None and record.currency is None
