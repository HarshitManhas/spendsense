"""Field equivalence shared by custom-model and OCR-baseline evaluation."""
from decimal import Decimal, InvalidOperation


def equivalent(key, expected, actual):
    if expected is None or actual is None:
        return expected is actual
    if key in {'total', 'tax'}:
        try:
            return Decimal(str(expected)) == Decimal(str(actual))
        except InvalidOperation:
            return False
    if key == 'merchant':
        return ' '.join(str(expected).split()).casefold() == ' '.join(str(actual).split()).casefold()
    return expected == actual
