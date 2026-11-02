import hashlib
import io
import zipfile

import pytest
from pydantic import ValidationError

from ai_expense_scanner.config import Settings
from ai_expense_scanner.model_store import FILES, pack_model, unpack_model


def test_vercel_caps_uploads_and_requires_production_auth():
    values = dict(_env_file=None, vercel=True, allow_dev_login=False,
                  google_client_id='test.apps.googleusercontent.com', frontend_origin='https://example.test')
    config = Settings(**values)
    assert config.app_env == 'production'
    assert config.remote_worker
    assert config.max_upload_mb == 4
    assert Settings(**values, max_upload_mb=2).max_upload_mb == 2
    with pytest.raises(ValidationError):
        Settings(**{**values, 'allow_dev_login': True})
    with pytest.raises(ValidationError):
        Settings(**{**values, 'frontend_origin': 'http://localhost:5173'})


def test_model_bundle_round_trip_and_tampering(tmp_path):
    source = tmp_path / 'source'
    source.mkdir()
    for name in FILES:
        (source / name).write_bytes(('fixture-' + name).encode())
    model_id, content = pack_model(source)
    assert pack_model(source) == (model_id, content)
    restored = unpack_model(content, model_id, tmp_path / 'restored')
    assert all((restored / name).read_bytes() == (source / name).read_bytes() for name in FILES)
    with pytest.raises(ValueError, match='integrity'):
        unpack_model(content + b'corrupt', model_id, tmp_path / 'bad')
    assert not (tmp_path / 'bad').exists()


def test_model_bundle_rejects_unexpected_paths_before_writing(tmp_path):
    content = io.BytesIO()
    with zipfile.ZipFile(content, 'w') as archive:
        for name in FILES:
            archive.writestr(name, b'fixture')
        archive.writestr('../escape', b'unsafe')
    value = content.getvalue()
    with pytest.raises(ValueError, match='Unexpected files'):
        unpack_model(value, hashlib.sha256(value).hexdigest(), tmp_path / 'model')
    assert not (tmp_path / 'model').exists()


def test_large_preview_stays_below_function_response_limit(tmp_path):
    import random
    from PIL import Image
    from ai_expense_scanner.render import render
    image = Image.frombytes('RGB', (1800, 2000), random.Random(42).randbytes(1800 * 2000 * 3))
    image.save(tmp_path / 'input', format='JPEG', quality=80)
    assert (tmp_path / 'input').stat().st_size < 4 * 1024**2
    render(tmp_path, 5)
    previews = list(tmp_path.glob('page-*'))
    assert len(previews) == 1 and previews[0].suffix == '.jpg'
    assert previews[0].stat().st_size <= 4 * 1024**2
    with Image.open(previews[0]) as preview:
        preview.verify()
