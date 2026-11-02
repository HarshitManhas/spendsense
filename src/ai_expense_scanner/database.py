from datetime import datetime, timezone
from functools import lru_cache

from gridfs import GridFS
from pymongo import MongoClient

from .config import settings


def now():
    return datetime.now(timezone.utc)


@lru_cache
def database():
    config = settings()
    client = MongoClient(config.mongodb_uri, serverSelectionTimeoutMS=3000, tz_aware=True)
    db = client[config.mongodb_database]
    db.receipts.create_index([("ownerId", 1), ("status", 1), ("createdAt", -1)])
    db.receipts.create_index([("ownerId", 1), ("expense.expenseDate", -1), ("_id", 1)])
    db.receipts.create_index([("status", 1), ("leaseUntil", 1)])
    db.receipts.create_index([("uploadId", 1), ("status", 1)])
    db.sessions.create_index("expiresAt", expireAfterSeconds=0)
    return db


def files():
    return GridFS(database(), collection="receipt_files")


def public_receipt(record):
    return {"id": record["_id"], **{key: record.get(key) for key in (
        "filename", "page", "status", "revision", "fields", "prediction", "warnings",
        "createdAt", "updatedAt", "expense", "source", "modelVersion"
    )}}
