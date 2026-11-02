"""Currency evidence and monetary syntax; shared symbols never imply a country."""
import re
import unicodedata

from .ocr_fields import parse_amount
from .schemas import CURRENCIES

VERSION = 'currency-v2'
PREFIX = r'(?:US\s*\$|JP\s*[¥￥]|INR|IDR|MYR|USD|EUR|GBP|JPY|RM|Rp\.?|Rs\.?|[₹€£$¥￥])'


def money(text):
    if not isinstance(text, str):
        return None
    text = unicodedata.normalize('NFKC', text).strip()
    text = re.sub(r'^' + PREFIX + r'\s*|\s*' + PREFIX + r'$', '', text, flags=re.I).strip()
    # Grouping spaces differ from gaps between separate numeric columns.
    if re.fullmatch(r'\d{1,3}(?:\s\d{3})+(?:[.,]\d{1,2})?', text):
        text = re.sub(r'\s', '', text)
    if re.fullmatch(r'\d{1,2}(?:,\d{2})+,\d{3}(?:\.\d{1,2})?', text):
        text = text.replace(',', '')
    return parse_amount(text)


def detect_currency(lines):
    evidence = []
    ambiguous = set()
    for line in lines:
        if line.get('confidence', 0) < .65:
            continue
        text = unicodedata.normalize('NFKC', line['text'])
        for code in CURRENCIES:
            if re.search(r'(?<![A-Za-z])' + code + r'(?![A-Za-z])', text, re.I):
                evidence.append({'currency': code, 'text': text, 'kind': 'code'})
        for pattern, code in [(r'₹', 'INR'), (r'€', 'EUR'), (r'£', 'GBP'),
                              (r'(?<!\w)US\s*\$', 'USD'), (r'(?<!\w)JP\s*¥', 'JPY'),
                              (r'(?<!\w)RM(?=\s|\d|$)', 'MYR'), (r'(?<!\w)Rp\.?(?=\s|\d|$)', 'IDR'),
                              (r'\bIndian\s+Rupees?\b', 'INR')]:
            if re.search(pattern, text, re.I):
                evidence.append({'currency': code, 'text': text, 'kind': 'symbol_or_name'})
        if '$' in text and not re.search(r'\bUS\s*\$', text, re.I):
            ambiguous.add('$')
        if '¥' in text and not re.search(r'\bJP\s*¥', text, re.I):
            ambiguous.add('¥')
        if re.search(r'(?<!\w)Rs\.?(?=\s|\d|$)', text, re.I):
            ambiguous.add('Rs')
    distinct = {item['currency'] for item in evidence}
    warnings = []
    currency = next(iter(distinct)) if len(distinct) == 1 else None
    if len(distinct) > 1:
        warnings.append('Conflicting currency evidence; select the currency shown on the receipt.')
    if ambiguous and currency is None:
        warnings.append('Shared currency sign (' + ', '.join(sorted(ambiguous)) + ') needs an explicit currency code or human selection.')
    # An incompatible shared symbol must not be explained away by another code.
    if currency and (('$' in ambiguous and currency != 'USD') or ('¥' in ambiguous and currency != 'JPY')
                     or ('Rs' in ambiguous and currency != 'INR')):
        currency = None
        warnings.append('Currency code and shared symbol disagree; review required.')
    return {'currency': currency, 'evidence': evidence, 'warnings': warnings}
