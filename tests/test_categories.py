import pytest

from ai_expense_scanner.category_model import features, fit, predict
from ai_expense_scanner.ml.train_categories import merchant_group, partition, evaluate


def examples():
    # Fictional fixtures test mechanics only; they are never real training data.
    return [{'id': f'{label}-{merchant}-{item}', 'merchant': f'{label} merchant {chr(97 + merchant)}',
             'items': [{'name': f'{word} option {chr(97 + item)}'}], 'category': label,
             'verified': True, 'label_source': 'test_fixture'}
            for label, word in [('food', 'sandwich'), ('travel', 'hotel')]
            for merchant in range(8) for item in range(5)]


def test_category_training_holdout_and_abstention():
    train, validation, excluded = partition(examples())
    assert not {merchant_group(r) for r in train} & {merchant_group(r) for r in validation}
    assert len(train) + len(validation) + excluded == 80
    model = fit(train)
    assert predict(model, {'merchant': 'Unknown', 'items': [{'name': 'hotel'}]})['category'] == 'travel'
    assert predict(model, {'merchant': 'xyzzy'})['category'] == 'uncategorized'
    report = evaluate(model, validation, .8)
    assert report['samples'] == len(validation)
    assert 0 <= report['macro_f1'] <= 1
    assert features({'merchant': 'Cafe', 'date': '2026-11-02', 'total': '123', 'category': 'food'}) == features({'merchant': 'Cafe'})


def test_category_training_rejects_missing_labels_leakage_and_conflicts():
    with pytest.raises(ValueError, match='verified'):
        partition([{'merchant': 'Cafe', 'verified': False, 'category': None}])
    records = examples()
    with pytest.raises(ValueError, match='Test receipts'):
        partition([{**records[0], 'split': 'test'}])
    with pytest.raises(ValueError, match='conflicting'):
        partition(records + [{**records[0], 'id': 'duplicate', 'category': 'travel'}])
    with pytest.raises(ValueError, match='verified'):
        fit([{**records[0], 'verified': False}])
