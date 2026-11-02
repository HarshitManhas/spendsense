"""Train on explicitly verified labels, with merchant-disjoint validation."""
import argparse
from collections import Counter
import hashlib
import json
from pathlib import Path
import re

from ..category_model import CATEGORY_LABELS, features, fit, predict


def merchant_group(record):
    # Missing merchant names cannot establish an independent validation group.
    return ' '.join(re.findall(r'[^\W_]+', (record.get('merchant') or '').casefold()))


def partition(records):
    seen_ids, seen_images, seen_text = set(), set(), {}
    clean = []
    for record in records:
        if record.get('split') == 'test':
            raise ValueError('Test receipts must remain untouched; use development labels only')
        if record.get('verified') is not True:
            continue
        if record.get('category') not in CATEGORY_LABELS:
            raise ValueError('Verified records must have a supported category')
        if not record.get('label_source'):
            raise ValueError('Verified records need label_source (review provenance)')
        if not merchant_group(record) or not features(record):
            raise ValueError('Verified records require a merchant name and usable text')
        signature = json.dumps(sorted(features(record).items()))
        if signature in seen_text and seen_text[signature] != record['category']:
            raise ValueError('Identical merchant/item text has conflicting category labels; resolve them first')
        duplicate = signature in seen_text or record.get('id') in seen_ids or (
            record.get('image_sha256') and record['image_sha256'] in seen_images)
        seen_text[signature] = record['category']
        if duplicate:
            continue
        if record.get('id'):
            seen_ids.add(record['id'])
        if record.get('image_sha256'):
            seen_images.add(record['image_sha256'])
        clean.append(record)
    counts = Counter(r['category'] for r in clean)
    if len(counts) < 2 or min(counts.values(), default=0) < 20:
        raise ValueError('Need at least 20 distinct verified receipts per category, covering at least two categories')
    groups = {label: {merchant_group(r) for r in clean if r['category'] == label} for label in counts}
    if any(len(group) < 5 for group in groups.values()):
        raise ValueError('Need at least five distinct merchants per category for merchant-disjoint evaluation')
    # Choose holdout merchants deterministically, shared across every category.
    holdout = set()
    for label in sorted(groups):
        ordered = sorted(groups[label], key=lambda g: hashlib.sha256(g.encode()).hexdigest())
        holdout.update(ordered[:max(1, len(ordered) // 5)])
    train = [r for r in clean if merchant_group(r) not in holdout]
    validation = [r for r in clean if merchant_group(r) in holdout]
    train_counts, validation_counts = Counter(r['category'] for r in train), Counter(r['category'] for r in validation)
    if any(train_counts[c] < 5 or validation_counts[c] < 2 for c in counts):
        raise ValueError('Merchant holdout lacks coverage; add more verified receipts/merchants for each category')
    return train, validation, len(records) - len(clean)


def evaluate(model, records, threshold):
    labels = sorted(model['documents'])
    confusion = {label: dict.fromkeys(labels + ['uncategorized'], 0) for label in labels}
    predictions = [predict(model, row, threshold) for row in records]
    for row, prediction in zip(records, predictions):
        confusion[row['category']][prediction['category']] += 1
    f1 = {}
    for label in labels:
        tp = confusion[label][label]
        fp = sum(confusion[other][label] for other in labels if other != label)
        fn = sum(confusion[label].values()) - tp
        f1[label] = 2 * tp / (2 * tp + fp + fn) if 2 * tp + fp + fn else 0
    covered = sum(p['category'] != 'uncategorized' for p in predictions)
    correct = sum(confusion[label][label] for label in labels)
    return {'samples': len(records), 'accuracy_including_abstentions': correct / len(records),
            'coverage': covered / len(records), 'precision_when_suggested': correct / covered if covered else None,
            'macro_f1': sum(f1.values()) / len(f1), 'f1_by_category': f1, 'confusion': confusion}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--labels', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--threshold', type=float, default=.8)
    args = parser.parse_args()
    if not 0 <= args.threshold <= 1:
        parser.error('--threshold must be between zero and one')
    if args.output.exists():
        parser.error('Choose a new output directory to preserve earlier experiments')
    records = [json.loads(line) for line in args.labels.read_text(encoding='utf-8').splitlines() if line.strip()]
    try:
        train, validation, excluded = partition(records)
        model = fit(train)
    except ValueError as exc:
        parser.error(str(exc))
    report = {'model_version': model['version'], 'threshold': args.threshold, 'scores_calibrated': False,
              'labels_sha256': hashlib.sha256(args.labels.read_bytes()).hexdigest(),
              'train_samples': len(train), 'excluded_unverified_or_duplicate': excluded,
              'train_ids': [r.get('id') for r in train], 'validation_ids': [r.get('id') for r in validation],
              'validation': evaluate(model, validation, args.threshold),
              'limitations': ['Development baseline only; no test score or production readiness claim.',
                              'Scores are not calibrated probabilities. Classes with no labels cannot be learned.',
                              'Merchant aliases/near duplicates still require a manual leakage audit.']}
    args.output.mkdir(parents=True)
    (args.output / 'model.json').write_text(json.dumps(model, ensure_ascii=False), encoding='utf-8')
    (args.output / 'report.json').write_text(json.dumps(report, indent=2), encoding='utf-8')
    print(json.dumps(report['validation'], indent=2))


if __name__ == '__main__':
    main()
