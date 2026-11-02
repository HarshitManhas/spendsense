"""Persistent OCR worker; MongoDB leases survive daemon restarts."""
from datetime import timedelta
import io
import signal
import threading
import time
import uuid

from PIL import Image, ImageDraw
from pymongo import ReturnDocument

from .config import settings
from .database import database, files, now
from .extraction import load_predictor
from .model_store import restore_model


def process_next(predictor, db):
    token = uuid.uuid4().hex
    row = db.receipts.find_one_and_update(
        {"$or": [{"status": "queued"}, {"status": "processing", "leaseUntil": {"$lt": now()}}], "attempts": {"$lt": 3}},
        {"$set": {"status": "processing", "leaseUntil": now() + timedelta(minutes=10), "leaseToken": token}, "$inc": {"attempts": 1}},
        return_document=ReturnDocument.AFTER)
    if not row:
        db.receipts.update_many({"status": "processing", "leaseUntil": {"$lt": now()}, "attempts": {"$gte": 3}},
                               {"$set": {"status": "failed", "warnings": ["Extraction attempts exhausted. Enter details manually."]}, "$inc": {"revision": 1}})
        return False
    try:
        fields, warnings, version = predictor(files().get(row['previewId']).read(),
            original=files().get(row['originalId']).read(), page_number=row['page'])
        updates = {"status": "pending_review", "prediction": fields.model_dump(), "fields": fields.model_dump(),
                   "warnings": warnings, "modelVersion": version,
                   "source": 'pdf_text' if version.startswith('pdf-text:') else settings().extraction_provider, "updatedAt": now()}
    except Exception as exc:
        print(f"Extraction failed: {type(exc).__name__}", flush=True)
        updates = {"status": "failed", "warnings": ["Extraction failed. Retry or enter details manually."], "updatedAt": now()}
    db.receipts.update_one({"_id": row['_id'], "ownerId": row['ownerId'], "status": "processing", "leaseToken": token, "revision": row['revision']},
                           {"$set": updates, "$inc": {"revision": 1}, "$unset": {"leaseToken": "", "leaseUntil": ""}})
    return True


def main():
    config = settings()
    if config.ocr_model_id:
        config.ocr_recognition_model_dir = restore_model(config.ocr_model_id)
    predictor = load_predictor()
    # Advertise readiness only after the actual OCR runtime has read an image.
    if config.extraction_provider == 'paddleocr':
        image = Image.new('RGB', (640, 240), 'white')
        ImageDraw.Draw(image).text((30, 50), 'SpendSense startup check 123.45', fill='black')
        content = io.BytesIO()
        image.save(content, 'PNG')
        predictor(content.getvalue())
    db = database()
    worker_id = uuid.uuid4().hex
    stopped = threading.Event()
    for name in (signal.SIGTERM, signal.SIGINT):
        signal.signal(name, lambda *_: stopped.set())
    print(f'Worker ready, provider {config.extraction_provider}', flush=True)
    last_heartbeat = 0.0
    try:
        while not stopped.is_set():
            if time.monotonic() - last_heartbeat >= 30:
                db.workers.update_one({'_id': worker_id}, {'$set': {
                    'provider': config.extraction_provider, 'modelId': config.ocr_model_id,
                    'lastSeen': now(),
                }}, upsert=True)
                last_heartbeat = time.monotonic()
            if not process_next(predictor, db):
                stopped.wait(2)
    finally:
        db.workers.delete_one({'_id': worker_id})


if __name__ == '__main__':
    main()
