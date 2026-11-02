"""Export annotated receipt text crops using the existing receipt-level split.

No OCR predictions become labels. The untouched test split is never decoded.
Run with the main project Python; training uses its own isolated environment.
"""
import argparse
from collections import Counter
import hashlib
import json
import math
from pathlib import Path

from datasets import load_from_disk


def annotations(row, source):
    if source == 'sroie':
        assert len(row['words']) == len(row['bboxes'])
        yield from zip(row['words'], row['bboxes'])
        return
    for line in json.loads(row['ground_truth'])['valid_line']:
        # Split wide column gaps rather than teaching the model to merge columns.
        words = []
        for word in line['words']:
            q = word['quad']
            xs, ys = [q[f'x{i}'] for i in range(1, 5)], [q[f'y{i}'] for i in range(1, 5)]
            words.append((word['text'], [min(xs), min(ys), max(xs), max(ys)]))
        words.sort(key=lambda w: w[1][0])
        groups = []
        for word in words:
            if groups:
                previous = groups[-1][-1][1]
                height = max(1, min(previous[3]-previous[1], word[1][3]-word[1][1]))
                if word[1][0] - previous[2] <= 1.5 * height:
                    groups[-1].append(word)
                    continue
            groups.append([word])
        for group in groups:
            yield ' '.join(w[0] for w in group), [min(w[1][0] for w in group), min(w[1][1] for w in group),
                max(w[1][2] for w in group), max(w[1][3] for w in group)]


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--output', type=Path, default=Path('data/paddle-finetune'))
    parser.add_argument('--dictionary', type=Path, default=Path('.tools/PaddleOCR/ppocr/utils/dict/ppocrv5_en_dict.txt'))
    parser.add_argument('--max-length', type=int, default=64)
    args = parser.parse_args()
    if (args.output / 'audit.json').exists():
        raise SystemExit('Export exists; use a new output directory to preserve provenance.')
    args.output.mkdir(parents=True, exist_ok=True)
    alphabet = set(args.dictionary.read_text(encoding='utf-8').splitlines()) | {' '}
    sources = {s: load_from_disk('data/' + s) for s in ('cord', 'sroie')}
    manifests = {s: [json.loads(line) for line in Path(f'data/manifests/{s}.jsonl').read_text(encoding='utf-8').splitlines()]
                 for s in ('train', 'validation')}
    assert not ({r['sha256'] for r in manifests['train']} & {r['sha256'] for r in manifests['validation']})
    audit = {'max_length': args.max_length, 'dictionary_sha256': hashlib.sha256(args.dictionary.read_bytes()).hexdigest(),
             'test_used': False, 'label_source': 'human dataset annotations, not OCR pseudo-labels', 'splits': {}}
    heldout_hashes = set()
    for split in ('validation', 'train'):
        counts, skipped, unsupported = Counter(), Counter(), Counter()
        seen = set()
        records = []
        image_dir = args.output / split
        image_dir.mkdir(exist_ok=True)
        for receipt in manifests[split]:
            row = sources[receipt['source']][receipt['split']][receipt['index']]
            image = row['image'].convert('RGB')
            for index, (text, box) in enumerate(annotations(row, receipt['source'])):
                text = text.strip()
                if not text or text == '###' or any(c in text for c in '\t\n\r'):
                    skipped['invalid_label'] += 1; continue
                if len(text) > args.max_length:
                    skipped['long_label'] += 1; continue
                unknown = set(text) - alphabet
                if unknown:
                    unsupported.update(unknown); skipped['unsupported_characters'] += 1; continue
                left, top, right, bottom = box
                box = (max(0, math.floor(left)-1), max(0, math.floor(top)-1),
                       min(image.width, math.ceil(right)+1), min(image.height, math.ceil(bottom)+1))
                if box[2]-box[0] < 3 or box[3]-box[1] < 3:
                    skipped['invalid_box'] += 1; continue
                crop = image.crop(box)
                digest = hashlib.sha256(str(crop.size).encode() + crop.tobytes()).hexdigest()
                if digest in heldout_hashes or digest in seen:
                    skipped['duplicate_crop'] += 1; continue
                seen.add(digest)
                path = image_dir / f'{len(records):06d}.png'
                crop.save(path)
                records.append({'image': path.resolve().as_posix(), 'text': text, 'receipt_id': receipt['id'],
                                'source': receipt['source'], 'box': box, 'crop_sha256': digest})
                counts[receipt['source']] += 1
        if split == 'validation': heldout_hashes.update(seen)
        (args.output / f'{split}.txt').write_text(''.join(f"{r['image']}\t{r['text']}\n" for r in records), encoding='utf-8')
        (args.output / f'{split}.jsonl').write_text(''.join(json.dumps(r, ensure_ascii=False)+'\n' for r in records), encoding='utf-8')
        audit['splits'][split] = {'receipts': len(manifests[split]), 'crops': len(records), 'sources': dict(counts),
            'skipped': dict(skipped), 'unsupported_characters': dict(unsupported),
            'manifest_sha256': hashlib.sha256(Path(f'data/manifests/{split}.jsonl').read_bytes()).hexdigest(),
            'labels_sha256': hashlib.sha256((args.output / f'{split}.txt').read_bytes()).hexdigest()}
        print(json.dumps({split: audit['splits'][split]}, ensure_ascii=True), flush=True)
    (args.output / 'audit.json').write_text(json.dumps(audit, ensure_ascii=True, indent=2), encoding='utf-8')


if __name__ == '__main__':
    main()
