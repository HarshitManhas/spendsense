"""Score OCR rules using the same reference labels/normalization as the CNN model."""
import argparse
from collections import Counter
import hashlib
import json
import math
from pathlib import Path
import statistics

from .ml.metrics import equivalent
from .ocr_fields import extract_fields, RULE_VERSION
from . import ocr_fields


def main():
    p = argparse.ArgumentParser()
    p.add_argument('--inputs', type=Path, required=True)
    p.add_argument('--run', type=Path, required=True)
    p.add_argument('--allow-subset', action='store_true', help='Explicitly label a limited diagnostic run')
    args = p.parse_args()
    metadata = json.loads((args.inputs / 'input-metadata.json').read_text(encoding='utf-8'))
    reference_path = Path(metadata['manifest'])
    reference_bytes = reference_path.read_bytes()
    if hashlib.sha256(reference_bytes).hexdigest() != metadata['manifest_sha256']:
        raise ValueError('Reference manifest changed after image export')
    references = {r['id']: r for r in (json.loads(line) for line in reference_bytes.decode('utf-8').splitlines() if line)}
    request_bytes = (args.inputs / 'requests.jsonl').read_bytes()
    requests = [json.loads(line) for line in request_bytes.decode('utf-8').splitlines() if line]
    runtime = json.loads((args.run / 'run.json').read_text(encoding='utf-8'))
    if runtime['requests_sha256'] != hashlib.sha256(request_bytes).hexdigest():
        raise ValueError('OCR run does not match these exported images')
    if len({r['id'] for r in requests}) != len(requests):
        raise ValueError('Duplicate evaluation requests')
    if any(r['id'] not in references for r in requests):
        raise ValueError('Evaluation request not in reference manifest')
    limited = len(requests) != len(references)
    if limited and not args.allow_subset:
        raise ValueError('Incomplete manifest coverage; use --allow-subset for an explicitly limited diagnostic')
    state = json.loads((args.run / 'status.json').read_text(encoding='utf-8'))
    if state['state'] not in {'completed', 'completed_with_errors'}:
        raise ValueError('OCR inference must finish before evaluation')
    counts, correct, covered = Counter(), Counter(), Counter()
    times, predictions, errors, all_known_correct = [], [], 0, 0
    for index, request in enumerate(requests):
        raw = json.loads((args.run / 'raw' / f'{index:04d}.json').read_text(encoding='utf-8'))
        if raw['id'] != request['id'] or raw['image_sha256'] != request['sha256']:
            raise ValueError('Saved OCR result does not match request')
        reference = references[request['id']]
        # Extraction sees no labels or dataset/source name.
        extraction = extract_fields(raw['lines'], raw['height'])
        error = raw.get('error'); errors += bool(error)
        field_matches = {}
        for field, label_state in reference['label_states'].items():
            if label_state not in {'labeled', 'verified_absent'}:
                continue
            metric = f"{reference['source']}.{field}"
            actual = extraction['fields'][field]
            counts[metric] += 1
            covered[metric] += actual is not None and not error
            matched = bool(not error and equivalent(field, reference['targets'][field], actual))
            correct[metric] += matched
            field_matches[field] = matched
        all_known_correct += bool(field_matches) and all(field_matches.values())
        times.append(raw['seconds'])
        predictions.append({'id': request['id'], **extraction, 'expected': reference['targets'],
                            'label_states': reference['label_states'], 'matches': field_matches, 'ocr_error': error,
                            'ocr_seconds': raw['seconds']})
    report = {
        'method': RULE_VERSION, 'samples': len(requests), 'limited_run': limited,
        'ocr_errors': errors, 'receipts_with_all_known_fields_correct': all_known_correct,
        'fields': {key: {'correct': correct[key], 'labeled': count, 'accuracy': correct[key] / count,
                         'predicted': covered[key], 'coverage': covered[key] / count,
                         'precision_when_predicted': correct[key] / covered[key] if covered[key] else None}
                   for key, count in counts.items()},
        'overall_labeled_fields': {'correct': sum(correct.values()), 'labeled': sum(counts.values()),
                                   'accuracy': sum(correct.values()) / sum(counts.values()) if counts else None},
        'ocr_latency_seconds': {'median': statistics.median(times),
                               'p95': sorted(times)[max(0, math.ceil(.95 * len(times)) - 1)],
                               'p99': sorted(times)[max(0, math.ceil(.99 * len(times)) - 1)], 'total': sum(times)},
        'manifest_sha256': metadata['manifest_sha256'], 'requests_sha256': runtime['requests_sha256'],
        'rule_sha256': hashlib.sha256(Path(ocr_fields.__file__).read_bytes()).hexdigest(),
        'runtime': runtime, 'reference_labels_used_for_inference': False,
        'model_file_hashes': json.loads((args.run / 'model-files.json').read_text(encoding='utf-8')) if (args.run / 'model-files.json').exists() else None,
        'external_ocr_pretraining_overlap_with_datasets': 'unknown; this is a baseline comparison, not certified unseen-data accuracy',
        'currency_label_coverage': 'No labeled currency examples in these local datasets; currency accuracy is not measured',
    }
    (args.run / 'predictions.jsonl').write_text(''.join(json.dumps(r, ensure_ascii=False) + '\n' for r in predictions), encoding='utf-8')
    (args.run / 'evaluation.json').write_text(json.dumps(report, indent=2), encoding='utf-8')
    print(json.dumps(report, indent=2))


if __name__ == '__main__': main()
