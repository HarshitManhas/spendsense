"""Local-only PaddleOCR inference. Input JSONL contains images and IDs, no labels."""
import argparse
import hashlib
from importlib.metadata import version
import json
import os
from pathlib import Path
import time
import traceback


def write_json(path, value):
    temporary = path.with_suffix(path.suffix + '.tmp')
    temporary.write_text(json.dumps(value, ensure_ascii=False, indent=2), encoding='utf-8')
    temporary.replace(path)


def main():
    p = argparse.ArgumentParser()
    p.add_argument('--requests', type=Path, required=True)
    p.add_argument('--output', type=Path, required=True)
    p.add_argument('--threads', type=int, default=4)
    p.add_argument('--no-mkldnn', action='store_true')
    p.add_argument('--resume', action='store_true')
    args = p.parse_args()
    args.output.mkdir(parents=True, exist_ok=True)
    raw_dir = args.output / 'raw'; raw_dir.mkdir(exist_ok=True)
    records = [json.loads(line) for line in args.requests.read_text(encoding='utf-8').splitlines() if line]
    config = {'text_detection_model_name': 'PP-OCRv5_mobile_det',
              'text_recognition_model_name': 'en_PP-OCRv5_mobile_rec',
              'use_doc_orientation_classify': False, 'use_doc_unwarping': False,
              'use_textline_orientation': False, 'device': 'cpu', 'cpu_threads': args.threads,
              'enable_mkldnn': not args.no_mkldnn, 'text_det_limit_side_len': 1280,
              'text_det_limit_type': 'max', 'text_rec_score_thresh': 0.0}
    metadata = {'requests_sha256': hashlib.sha256(args.requests.read_bytes()).hexdigest(),
                'config': config, 'paddleocr': version('paddleocr'), 'paddlepaddle': version('paddlepaddle'),
                'runner_sha256': hashlib.sha256(Path(__file__).read_bytes()).hexdigest()}
    if (args.output / 'run.json').exists():
        if not args.resume:
            raise ValueError('Output already exists; use --resume or a new output directory')
        if json.loads((args.output / 'run.json').read_text(encoding='utf-8')) != metadata:
            raise ValueError('Cannot resume with changed inputs, models, versions, or inference settings')
    write_json(args.output / 'run.json', metadata)
    started = time.time()
    status = {'pid': os.getpid(), 'state': 'loading_models', 'completed': 0, 'total': len(records), 'errors': 0}

    def update(**values):
        status.update(values, updated_at=time.time(), elapsed_seconds=time.time() - started)
        write_json(args.output / 'status.json', status)

    update()
    try:
        from paddleocr import PaddleOCR
        model = PaddleOCR(**config)
        from paddlex.utils.cache import CACHE_DIR
        model_files = {}
        for name in (config['text_detection_model_name'], config['text_recognition_model_name']):
            directory = Path(CACHE_DIR) / 'official_models' / name
            for filename in ('inference.json', 'inference.pdiparams', 'inference.yml'):
                path = directory / filename
                if path.is_file():
                    model_files[f'{name}/{filename}'] = hashlib.sha256(path.read_bytes()).hexdigest()
        if not model_files:
            raise ValueError('Could not record loaded model artifact hashes')
        hashes_path = args.output / 'model-files.json'
        if args.resume and hashes_path.exists() and json.loads(hashes_path.read_text(encoding='utf-8')) != model_files:
            raise ValueError('Model artifacts changed; use a new run instead of mixing cached predictions')
        write_json(hashes_path, model_files)
        for index, record in enumerate(records):
            destination = raw_dir / f'{index:04d}.json'
            if args.resume and destination.exists():
                saved = json.loads(destination.read_text(encoding='utf-8'))
                if saved.get('id') == record['id'] and saved.get('image_sha256') == record['sha256'] and not saved.get('error'):
                    update(state='recognizing', completed=index + 1)
                    continue
            update(state='recognizing', current_id=record['id'])
            image_started = time.perf_counter()
            result = {'id': record['id'], 'image_sha256': record['sha256'],
                      'width': record['width'], 'height': record['height']}
            try:
                if hashlib.sha256(Path(record['image']).read_bytes()).hexdigest() != record['sha256']:
                    raise ValueError('Exported image changed after request preparation')
                outputs = list(model.predict(record['image']))
                if len(outputs) != 1:
                    raise ValueError(f'Expected one image result, received {len(outputs)}')
                prediction = outputs[0]
                texts, scores, boxes = prediction['rec_texts'], prediction['rec_scores'], prediction['rec_boxes']
                if not (len(texts) == len(scores) == len(boxes)):
                    raise ValueError('OCR text/score/box lengths disagree')
                result['lines'] = [{'text': str(text), 'confidence': float(score), 'box': [float(v) for v in box]}
                                   for text, score, box in zip(texts, scores, boxes)]
                if 'rec_polys' in prediction and len(prediction['rec_polys']) == len(result['lines']):
                    for line, polygon in zip(result['lines'], prediction['rec_polys']):
                        line['polygon'] = [[float(v) for v in point] for point in polygon]
            except Exception as exc:
                result.update(lines=[], error=str(exc), traceback=traceback.format_exc())
                status['errors'] += 1
            result['seconds'] = time.perf_counter() - image_started
            write_json(destination, result)
            update(completed=index + 1)
            print(json.dumps({'completed': index + 1, 'total': len(records), 'seconds': result['seconds'],
                              'lines': len(result['lines']), 'error': result.get('error')}), flush=True)
        update(state='completed' if not status['errors'] else 'completed_with_errors')
    except BaseException as exc:
        update(state='failed', error=str(exc), traceback=traceback.format_exc())
        raise


if __name__ == '__main__': main()
