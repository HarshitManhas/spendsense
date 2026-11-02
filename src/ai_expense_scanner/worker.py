"""Run with: uv run --extra ml python -m ai_expense_scanner.worker."""
from datetime import timedelta
import time
import uuid

from pymongo import ReturnDocument

from .config import settings
from .database import database, files, now
from .extraction import load_predictor


def main():
    predictor = load_predictor()
    db = database()
    print(f"Worker ready, provider {settings().extraction_provider}", flush=True)
    while True:
        token = uuid.uuid4().hex
        row = db.receipts.find_one_and_update(
            {"$or": [{"status": "queued"}, {"status": "processing", "leaseUntil": {"$lt": now()}}], "attempts": {"$lt": 3}},
            {"$set": {"status": "processing", "leaseUntil": now() + timedelta(minutes=10), "leaseToken": token}, "$inc": {"attempts": 1}},
            return_document=ReturnDocument.AFTER)
        if not row:
            db.receipts.update_many({"status": "processing", "leaseUntil": {"$lt": now()}, "attempts": {"$gte": 3}},
                                   {"$set": {"status": "failed", "warnings": ["Extraction attempts exhausted. Enter details manually."]}, "$inc": {"revision": 1}})
            time.sleep(2); continue
        try:
            fields, warnings, version = predictor(files().get(row['previewId']).read(),
                original=files().get(row['originalId']).read(), page_number=row['page'])
            updates = {"status": "pending_review", "prediction": fields.model_dump(), "fields": fields.model_dump(),
                       "warnings": warnings, "modelVersion": version,
                       "source": 'pdf_text' if version.startswith('pdf-text:') else settings().extraction_provider, "updatedAt": now()}
        except Exception:
            updates = {"status": "failed", "warnings": ["Extraction failed. Retry or enter details manually."], "updatedAt": now()}
        db.receipts.update_one({"_id": row['_id'], "ownerId": row['ownerId'], "status": "processing", "leaseToken": token, "revision": row['revision']},
                               {"$set": updates, "$inc": {"revision": 1}, "$unset": {"leaseToken": "", "leaseUntil": ""}})


if __name__ == '__main__':
    main()
