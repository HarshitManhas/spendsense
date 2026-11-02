"""Export local dataset images without exposing reference labels to inference."""
import argparse
import hashlib
import json
from pathlib import Path

from datasets import load_from_disk
from PIL import ImageOps


def main():
    p = argparse.ArgumentParser()
    p.add_argument('--manifest', type=Path, default=Path('data/manifests/validation.jsonl'))
    p.add_argument('--data', type=Path, default=Path('data'))
    p.add_argument('--output', type=Path, required=True)
    p.add_argument('--limit', type=int)
    args = p.parse_args()
    if args.limit is not None and args.limit < 1:
        p.error('--limit must be positive')
    records = [json.loads(line) for line in args.manifest.read_text(encoding='utf-8').splitlines() if line]
    if not records:
        p.error('The input manifest is empty')
    if args.limit:
        groups = {}
        for record in records:
            groups.setdefault(record['source'], []).append(record)
        records = [group[i] for i in range(max(map(len, groups.values())))
                   for group in groups.values() if i < len(group)][:args.limit]
    sources = {name: load_from_disk(str(args.data / name)) for name in {r['source'] for r in records}}
    images = args.output / 'images'; images.mkdir(parents=True, exist_ok=True)
    requests = []
    for index, record in enumerate(records):
        image = sources[record['source']][record['split']][record['index']]['image']
        image = ImageOps.exif_transpose(image).convert('RGB')
        path = images / f'{index:04d}.png'
        image.save(path, compress_level=1)
        requests.append({'id': record['id'], 'image': str(path.resolve()), 'width': image.width,
                         'height': image.height, 'sha256': hashlib.sha256(path.read_bytes()).hexdigest()})
    (args.output / 'requests.jsonl').write_text(''.join(json.dumps(r) + '\n' for r in requests), encoding='utf-8')
    (args.output / 'input-metadata.json').write_text(json.dumps({
        'manifest': str(args.manifest.resolve()), 'manifest_sha256': hashlib.sha256(args.manifest.read_bytes()).hexdigest(),
        'samples': len(requests), 'limited': bool(args.limit), 'reference_labels_passed_to_ocr': False,
    }, indent=2), encoding='utf-8')
    print(f'Exported {len(requests)} images to {args.output}', flush=True)


if __name__ == '__main__': main()
