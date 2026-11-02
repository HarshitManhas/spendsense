"""Small supervised text baseline. Scores are uncalibrated; suggestions need review."""
from collections import Counter
import math
import re

from .schemas import CATEGORIES

CATEGORY_LABELS = tuple(c for c in CATEGORIES if c != 'uncategorized')
VERSION = 'merchant-items-naive-bayes-v1'


def features(record):
    # Deliberately exclude date, price, user IDs, dataset name and category.
    texts = [record.get('merchant') or '']
    texts.extend(item.get('name') or '' for item in record.get('items', []))
    result = Counter()
    for text in texts:
        words = re.findall(r'[^\W\d_]+', text.casefold(), flags=re.UNICODE)
        result.update(words)
        result.update(a + ' ' + b for a, b in zip(words, words[1:]))
    return result


def fit(records):
    documents, counts = Counter(), {}
    vocabulary = set()
    for record in records:
        label = record['category']
        if label not in CATEGORY_LABELS or record.get('verified') is not True:
            raise ValueError('Training requires verified spending-category labels')
        tokens = features(record)
        if not tokens:
            raise ValueError('Each training receipt needs merchant or item text')
        documents[label] += 1
        counts.setdefault(label, Counter()).update(tokens)
        vocabulary.update(tokens)
    if len(documents) < 2:
        raise ValueError('At least two labeled categories are required')
    return {'version': VERSION, 'documents': dict(documents),
            'counts': {k: dict(v) for k, v in counts.items()}, 'vocabulary': sorted(vocabulary)}


def predict(model, record, threshold=.8):
    if model.get('version') != VERSION:
        raise ValueError('Unsupported category model')
    if not 0 <= threshold <= 1:
        raise ValueError('Threshold must be between zero and one')
    vocabulary = set(model['vocabulary'])
    tokens = {k: v for k, v in features(record).items() if k in vocabulary}
    if not tokens:
        return {'category': 'uncategorized', 'score': None, 'reason': 'No known merchant/item words'}
    scores = {}
    n = sum(model['documents'].values())
    for label, docs in model['documents'].items():
        counts = model['counts'][label]
        denominator = sum(counts.values()) + len(vocabulary)
        scores[label] = math.log(docs / n) + sum(count * math.log((counts.get(word, 0) + 1) / denominator)
                                               for word, count in tokens.items())
    best = max(scores, key=scores.get)
    weights = {key: math.exp(value - scores[best]) for key, value in scores.items()}
    score = 1 / sum(weights.values())
    return {'category': best if score >= threshold else 'uncategorized', 'score': score,
            'reason': 'Uncalibrated model score; review required'}
