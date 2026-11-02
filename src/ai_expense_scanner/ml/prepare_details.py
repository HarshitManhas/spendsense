"""Enrich existing splits; never infer missing item or spending-category labels."""
import argparse
from collections import Counter
from decimal import Decimal
import hashlib
import json
from pathlib import Path
import re

from datasets import load_from_disk

from .data import amount


def quantity(value):
    if not isinstance(value, str):
        return None
    value = value.strip()
    value = re.sub(r'^[xX]\s*|\s*[xX]$', '', value).strip()
    if re.fullmatch(r'\d+(?:\.\d{1,6})?', value) and 0 < Decimal(value) <= 10**6:
        return format(Decimal(value), 'f')
    return None


def cord_items(ground_truth):
    menus = ground_truth['gt_parse'].get('menu')
    if menus is None:
        return None
    if isinstance(menus, dict):
        menus = [menus]
    if not isinstance(menus, list):
        raise ValueError('Unexpected CORD menu structure')
    items = []
    for menu in menus:
        raw = {key: menu.get(source) for key, source in
               [('name', 'nm'), ('quantity', 'cnt'), ('unit_price', 'unitprice'), ('line_total', 'price')]}
        name = ' '.join(raw['name'].split()) if isinstance(raw['name'], str) else None
        values = {'name': name or None, 'quantity': quantity(raw['quantity']),
                  'unit_price': amount(raw['unit_price'], 'cord'), 'line_total': amount(raw['line_total'], 'cord')}
        states = {key: 'labeled' if value is not None else 'ambiguous' if raw[key] is not None else 'unlabeled'
                  for key, value in values.items()}
        items.append({'values': values, 'label_states': states, 'raw': menu})
    return items


def prepare(data, manifests, output):
    if output.resolve() == manifests.resolve():
        raise ValueError('Use a separate output directory; original manifests are frozen')
    for existing in output.glob('*-category-labels.jsonl'):
        for line in existing.read_text(encoding='utf-8').splitlines():
            record = json.loads(line)
            if record.get('category') is not None or record.get('verified') is True:
                raise ValueError(f'Preserving edited labels in {existing}; choose a new output directory')
    output.mkdir(parents=True, exist_ok=True)
    cord = load_from_disk(str(data / 'cord'))
    cord = {split: ds.select_columns(['ground_truth']) for split, ds in cord.items()}
    audit = {'version': 1, 'splits': {}, 'manifest_hashes': {}, 'categories_labeled': 0,
             'limitations': ['Only main CORD menu entries are normalized; modifiers and discounts remain in raw.',
                            'SROIE has no item labels. CORD has no merchant/date labels.',
                            'Neither source has spending-category labels. Never infer absent labels as negatives.']}
    for split in ('train', 'validation', 'test'):
        path = manifests / f'{split}.jsonl'
        audit['manifest_hashes'][split] = hashlib.sha256(path.read_bytes()).hexdigest()
        counts = Counter()
        with (output / f'{split}.jsonl').open('w', encoding='utf-8') as handle, \
             (output / f'{split}-category-labels.jsonl').open('w', encoding='utf-8') as labels:
            for line in path.read_text(encoding='utf-8').splitlines():
                record = json.loads(line)
                items = None
                if record['source'] == 'cord':
                    gt = json.loads(cord[record['split']][record['index']]['ground_truth'])
                    items = cord_items(gt)
                record['item_labels'] = items
                record['items_label_state'] = 'labeled' if items is not None else 'unlabeled'
                record['category_label'] = None
                record['category_label_state'] = 'unlabeled'
                handle.write(json.dumps(record, ensure_ascii=False) + '\n')
                counts['receipts'] += 1
                counts['receipts_with_item_labels'] += items is not None
                for item in items or []:
                    counts['items'] += 1
                    counts.update(f'{key}.{state}' for key, state in item['label_states'].items())
                # Keep development labels separate from untouched test records.
                labels.write(json.dumps({'id': record['id'], 'split': split, 'image_sha256': record['sha256'],
                    'merchant': record['targets']['merchant'],
                    'items': [item['values'] for item in items or []],
                    'date': record['targets']['date'], 'category': None, 'verified': False,
                    'label_source': None}, ensure_ascii=False) + '\n')
        audit['splits'][split] = dict(counts)
    (output / 'audit.json').write_text(json.dumps(audit, indent=2), encoding='utf-8')
    return audit


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--data', type=Path, default=Path('data'))
    parser.add_argument('--manifests', type=Path, default=Path('data/manifests'))
    parser.add_argument('--output', type=Path, default=Path('data/details'))
    args = parser.parse_args()
    print(json.dumps(prepare(args.data, args.manifests, args.output), indent=2))


if __name__ == '__main__':
    main()
