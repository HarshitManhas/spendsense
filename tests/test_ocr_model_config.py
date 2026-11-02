import io
import json
from pathlib import Path

from PIL import Image
import pytest

from ai_expense_scanner import extraction
from ai_expense_scanner.config import Settings


def test_ready_rejects_incomplete_custom_recognizer(tmp_path, monkeypatch):
    runtime = tmp_path / 'runtime'
    runtime.touch()
    config = Settings(_env_file=None, extraction_provider='paddleocr', ocr_python=runtime, ocr_runner=runtime)
    monkeypatch.setattr(extraction, 'settings', lambda: config)
    assert extraction.ready()
    config.ocr_recognition_model_dir = tmp_path / 'recognizer'
    assert not extraction.ready()
    config.ocr_recognition_model_dir.mkdir()
    for filename in ('inference.json', 'inference.pdiparams', 'inference.yml'):
        (config.ocr_recognition_model_dir / filename).touch()
    assert extraction.ready()
    (config.ocr_recognition_model_dir / 'inference.pdiparams').unlink()
    assert not extraction.ready()


@pytest.mark.parametrize('custom', [False, True])
def test_extraction_forwards_model_directory_and_preserves_review(tmp_path, monkeypatch, custom):
    model = tmp_path / 'recognizer' if custom else None
    config = Settings(_env_file=None, ocr_recognition_model_dir=model)
    monkeypatch.setattr(extraction, 'settings', lambda: config)
    original_resolve = Path.resolve
    # Model the venv executable symlink that exists on Linux, including on Windows CI.
    monkeypatch.setattr(Path, 'resolve', lambda path, *a, **kw:
                        tmp_path / 'system-python' if path == config.ocr_python else original_resolve(path, *a, **kw))

    def run(command, **kwargs):
        assert command[0] == str(config.ocr_python.absolute())
        if custom:
            assert command[command.index('--recognition-model-dir') + 1] == str(model.resolve())
        else:
            assert '--recognition-model-dir' not in command
        output = Path(command[command.index('--output') + 1])
        (output / 'raw').mkdir(parents=True)
        (output / 'raw/0000.json').write_text(json.dumps({'lines': [
            {'text': 'TOTAL INR 349.00', 'box': [0, 200, 190, 220], 'confidence': .99}]}))
        (output / 'model-files.json').write_text(json.dumps({'recognizer': 'trained' if custom else 'original'}))

    monkeypatch.setattr(extraction.subprocess, 'run', run)
    image = io.BytesIO()
    Image.new('RGB', (300, 400), 'white').save(image, format='PNG')
    fields, warnings, version = extraction.paddle_extract(image.getvalue())
    assert fields.total == '349.00' and fields.currency == 'INR'
    assert any('Check every value before approval' in warning for warning in warnings)
    assert version and not version.startswith('pdf-text:')
