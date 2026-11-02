"""Local extraction providers; Paddle is isolated from the PyTorch environment."""
import hashlib
import io
import json
import os
from pathlib import Path
import subprocess
import tempfile

from PIL import Image

from .config import settings
from .document_layout import extract_document, VERSION as LAYOUT_VERSION
from .currency import VERSION as CURRENCY_VERSION
from .pdf_text import read_pdf_page
from .schemas import Draft


def ready():
    config = settings()
    if config.extraction_provider == 'paddleocr':
        return config.ocr_python.is_file() and config.ocr_runner.is_file()
    return config.model_path.is_file()


def native_prediction(original, page_number=1):
    native = read_pdf_page(original, page_number) if original is not None else None
    if native is not None:
        parsed = extract_document(native['lines'], native['width'], native['height'], native['tables'])
        fields = Draft(**parsed['fields'], items=parsed['items'])
        if fields.total is None and not fields.items:
            return None  # A text footer alone must not hide a scanned invoice body.
        warnings = ['Read from the PDF text and table positions. Check all values before approval.',
                    'Choose the expense category; no trained category model is installed.', *parsed['warnings']]
        missing = [key for key in ('merchant', 'date', 'total', 'currency') if not getattr(fields, key)]
        if missing:
            warnings.append('Missing fields: ' + ', '.join(missing) + '.')
        return fields, warnings, 'pdf-text:' + LAYOUT_VERSION + '+' + CURRENCY_VERSION
    return None


def paddle_extract(content, original=None, page_number=1):
    config = settings()
    native = native_prediction(original, page_number)
    if native is not None:
        return native
    # Private temporary receipt files are removed on both success and failure.
    with tempfile.TemporaryDirectory(prefix='spendsense-ocr-') as directory:
        root = Path(directory)
        path = root / 'receipt.png'
        with Image.open(io.BytesIO(content)) as image:
            image.convert('RGB').save(path)
            width, height = image.size
        request = {'id': 'receipt', 'image': str(path), 'width': width, 'height': height,
                   'sha256': hashlib.sha256(path.read_bytes()).hexdigest()}
        requests = root / 'requests.jsonl'
        requests.write_text(json.dumps(request) + '\n', encoding='utf-8')
        with (root / 'runner.log').open('w', encoding='utf-8') as log:
            subprocess.run([str(config.ocr_python.resolve()), str(config.ocr_runner.resolve()),
                            '--requests', str(requests), '--output', str(root / 'output')],
                           stdout=log, stderr=subprocess.STDOUT, timeout=180, check=True,
                           creationflags=subprocess.CREATE_NO_WINDOW if os.name == 'nt' else 0)
        result = json.loads((root / 'output/raw/0000.json').read_text(encoding='utf-8'))
        if result.get('error'):
            raise ValueError('OCR could not read this receipt')
        parsed = extract_document(result['lines'], width, height)
        fields = Draft(**parsed['fields'], items=parsed['items'])
        missing = [key for key in ('merchant', 'date', 'total', 'currency') if not getattr(fields, key)]
        warnings = ['Local pretrained OCR with receipt rules. Check every value before approval.',
                    'Choose the expense category; no trained category model is installed.',
                    *parsed['warnings']]
        if missing:
            warnings.append('Missing fields: ' + ', '.join(missing) + '.')
        hashes = json.loads((root / 'output/model-files.json').read_text(encoding='utf-8'))
        version = LAYOUT_VERSION + '+' + CURRENCY_VERSION + ':' + hashlib.sha256(json.dumps(hashes, sort_keys=True).encode()).hexdigest()[:16]
        return fields, warnings, version


def load_predictor():
    if not ready():
        raise ValueError('Selected extraction provider is not installed. Manual review remains available.')
    if settings().extraction_provider == 'paddleocr':
        return paddle_extract
    import torch
    from .ml.model import ExpenseModel, ModelConfig
    from .ml.train import preprocess
    from .ml.vocabulary import Vocabulary
    from .ml.parsing import parse_prediction
    path = settings().model_path
    checkpoint = torch.load(path, map_location='cpu', weights_only=True)
    if checkpoint.get('tiny_overfit_only'):
        raise ValueError('Tiny-overfit checkpoints cannot serve app predictions')
    config = ModelConfig(**checkpoint['config'])
    vocab = Vocabulary(checkpoint['characters'])
    model = ExpenseModel(len(vocab), config)
    model.load_state_dict(checkpoint['state_dict']); model.eval()
    version = hashlib.sha256(path.read_bytes()).hexdigest()[:16]

    def predict(content, original=None, page_number=1):
        with Image.open(io.BytesIO(content)) as image:
            ids = model.generate(preprocess(image, config).unsqueeze(0))[0].tolist()
        warnings = ['Experimental extraction. Check every field against the receipt.']
        if vocab.EOS not in ids:
            warnings.append('Model reached its generation limit.')
        try:
            fields = parse_prediction(vocab.decode(ids))
        except (ValueError, TypeError):
            fields = Draft()
            warnings.append('Model output was invalid. Enter the receipt details manually.')
        missing = [key for key in ('merchant', 'date', 'total', 'currency') if not getattr(fields, key)]
        if missing:
            warnings.append('Missing fields: ' + ', '.join(missing) + '.')
        return fields, warnings, version
    return predict
