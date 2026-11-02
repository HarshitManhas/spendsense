import pytest
from ai_expense_scanner.config import Settings
from ai_expense_scanner.schemas import Draft, approved_values, minor_units


def test_currency_precision_and_non_finite_values():
    assert minor_units('349.00', 'INR') == 34900
    assert minor_units('100', 'JPY') == 100
    for value, currency in [('1.001', 'INR'), ('1.5', 'JPY'), ('NaN', 'INR'), ('Infinity', 'INR'), ('-1', 'INR'), ('1e9999999999', 'INR')]:
        with pytest.raises(ValueError): minor_units(value, currency)


def test_approval_requires_confirmed_values():
    with pytest.raises(ValueError): approved_values(Draft(merchant='Shop', total='1'))
    value = approved_values(Draft(merchant='Shop', date='2026-11-01', total='1.00', currency='INR'))
    assert value['taxMinor'] is None
    assert value['totalMinor'] == 100


def test_development_auth_cannot_enable_in_production():
    with pytest.raises(ValueError):
        Settings(_env_file=None, app_env='production', allow_dev_login=True)
