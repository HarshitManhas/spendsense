import hashlib
import json
import sys

import pytest

from ai_expense_scanner import ocr_evaluate


def test_ocr_failure_stays_in_accuracy_denominator_and_reference_changes_fail(tmp_path, monkeypatch):
    inputs, run = tmp_path / 'inputs', tmp_path / 'run'
    inputs.mkdir(); (run / 'raw').mkdir(parents=True)
    references = [{'id': f'receipt-{i}', 'source': 'synthetic', 'targets': {'total': '10.00'},
                   'label_states': {'total': 'labeled'}} for i in range(2)]
    reference = tmp_path / 'manifest.jsonl'
    reference.write_text(''.join(json.dumps(r) + '\n' for r in references), encoding='utf-8')
    requests = [{'id': r['id'], 'sha256': f'image-hash-{i}'} for i, r in enumerate(references)]
    request_file = inputs / 'requests.jsonl'
    request_file.write_text(''.join(json.dumps(r) + '\n' for r in requests), encoding='utf-8')
    (inputs / 'input-metadata.json').write_text(json.dumps({'manifest': str(reference),
        'manifest_sha256': hashlib.sha256(reference.read_bytes()).hexdigest()}))
    (run / 'run.json').write_text(json.dumps({'requests_sha256': hashlib.sha256(request_file.read_bytes()).hexdigest()}))
    (run / 'status.json').write_text(json.dumps({'state': 'completed_with_errors'}))
    for i, request in enumerate(requests):
        raw = {'id': request['id'], 'image_sha256': request['sha256'], 'height': 500, 'seconds': 1,
               'lines': [{'text': 'TOTAL 10.00', 'confidence': .99, 'box': [0, 300, 200, 320]}] if i == 0 else [],
               'error': None if i == 0 else 'OCR failed'}
        (run / 'raw' / f'{i:04d}.json').write_text(json.dumps(raw))
    monkeypatch.setattr(sys, 'argv', ['evaluate', '--inputs', str(inputs), '--run', str(run)])
    ocr_evaluate.main()
    report = json.loads((run / 'evaluation.json').read_text())
    assert report['fields']['synthetic.total']['accuracy'] == .5
    assert report['fields']['synthetic.total']['coverage'] == .5
    assert report['ocr_errors'] == 1
    reference.write_text('{}\n')
    with pytest.raises(ValueError, match='Reference manifest changed'):
        ocr_evaluate.main()
