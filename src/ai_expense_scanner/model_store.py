"""Keep exported OCR weights in private GridFS, addressed by their SHA-256."""
import hashlib
import io
from pathlib import Path
import tempfile
import zipfile

from gridfs import GridFS

from .database import database

FILES = ('inference.json', 'inference.pdiparams', 'inference.yml')
MAX_BYTES = 64 * 1024**2


def pack_model(directory: Path):
    output = io.BytesIO()
    with zipfile.ZipFile(output, 'w', compression=zipfile.ZIP_STORED) as archive:
        for name in FILES:
            content = (directory / name).read_bytes()
            if not content or len(content) > MAX_BYTES:
                raise ValueError('Invalid exported model size')
            archive.writestr(zipfile.ZipInfo(name), content)
    content = output.getvalue()
    if len(content) > MAX_BYTES:
        raise ValueError('Exported model exceeds 64 MB')
    return hashlib.sha256(content).hexdigest(), content


def publish_model(directory: Path):
    model_id, content = pack_model(directory)
    store = GridFS(database(), collection='ocr_models')
    if not store.exists(model_id):
        store.put(content, _id=model_id, filename='recognizer.zip')
    if hashlib.sha256(store.get(model_id).read()).hexdigest() != model_id:
        raise ValueError('Stored model failed integrity verification')
    return model_id


def unpack_model(content: bytes, model_id: str, directory: Path):
    if len(content) > MAX_BYTES or hashlib.sha256(content).hexdigest() != model_id:
        raise ValueError('Downloaded model failed integrity verification')
    with zipfile.ZipFile(io.BytesIO(content)) as archive:
        if sorted(archive.namelist()) != sorted(FILES):
            raise ValueError('Unexpected files in model export')
        if sum(item.file_size for item in archive.infolist()) > MAX_BYTES:
            raise ValueError('Expanded model exceeds 64 MB')
        contents = {name: archive.read(name) for name in FILES}
    if not all(contents.values()):
        raise ValueError('Empty model export file')
    directory.mkdir(parents=True, exist_ok=True)
    for name, value in contents.items():
        (directory / name).write_bytes(value)
    return directory


def restore_model(model_id: str):
    store = GridFS(database(), collection='ocr_models')
    content = store.get(model_id).read(MAX_BYTES + 1)
    directory = Path(tempfile.gettempdir()) / 'spendsense-models' / model_id
    return unpack_model(content, model_id, directory)


if __name__ == '__main__':
    import argparse
    parser = argparse.ArgumentParser(description='Publish an exported recognizer to the configured private MongoDB database.')
    parser.add_argument('directory', type=Path)
    args = parser.parse_args()
    print('OCR_MODEL_ID=' + publish_model(args.directory))
