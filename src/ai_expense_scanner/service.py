from datetime import date
import hashlib
import uuid

from fastapi import HTTPException
from pymongo import ReturnDocument

from .config import settings
from .database import database, files, now, public_receipt
from .render import render_upload
from .schemas import Draft, ReviewRequest, approved_values
from .extraction import ready


def owned(uid, receipt_id):
    item = database().receipts.find_one({"_id": receipt_id, "ownerId": uid, "status": {"$ne": "deleted"}})
    if not item:
        raise HTTPException(404, "Receipt not found")
    return item


def upload(uid, filename, content):
    try:
        pages = render_upload(content, settings().max_pdf_pages)
    except Exception as exc:
        raise HTTPException(422, "Could not read this receipt. Use JPG, PNG, or an unencrypted PDF (maximum 5 pages).") from exc
    upload_id = uuid.uuid4().hex
    created_files, records = [], []
    fs = files()
    try:
        original_id = fs.put(content, filename=upload_id, metadata={"ownerId": uid, "uploadId": upload_id, "kind": "original"})
        created_files.append(original_id)
        for page, (_, preview) in enumerate(pages):
            preview_id = fs.put(preview, filename=f"{upload_id}-{page}.png", metadata={"ownerId": uid, "uploadId": upload_id, "kind": "preview"})
            created_files.append(preview_id)
            available = ready()
            records.append({"_id": uuid.uuid4().hex, "ownerId": uid, "uploadId": upload_id,
                "originalId": original_id, "previewId": preview_id, "filename": filename[:200],
                "sha256": hashlib.sha256(content).hexdigest(), "page": page + 1,
                "status": "queued" if available else "pending_review", "revision": 1,
                "fields": Draft().model_dump(), "prediction": None, "source": settings().extraction_provider if available else "manual",
                "warnings": [] if available else ["Extraction provider unavailable. Enter receipt details manually."],
                "createdAt": now(), "updatedAt": now(), "history": [], "attempts": 0})
        database().receipts.insert_many(records)
        return {"receipts": [public_receipt(item) for item in records]}
    except Exception:
        database().receipts.delete_many({"ownerId": uid, "uploadId": upload_id})
        for file_id in created_files:
            fs.delete(file_id)
        raise


def mutate(uid, receipt_id, revision, allowed, updates, event):
    result = database().receipts.find_one_and_update(
        {"_id": receipt_id, "ownerId": uid, "revision": revision, "status": {"$in": allowed}},
        {"$set": {**updates, "updatedAt": now()}, "$inc": {"revision": 1},
         "$push": {"history": {"$each": [{"event": event, "at": now(), "actor": uid, "revision": revision + 1}], "$slice": -100}}},
        return_document=ReturnDocument.AFTER)
    if not result:
        owned(uid, receipt_id)
        raise HTTPException(409, "Receipt changed or action is unavailable; reload before retrying")
    return public_receipt(result)


def approve(uid, receipt_id, body: ReviewRequest):
    try:
        values = approved_values(body.fields, body.confirm_warnings)
    except ValueError as exc:
        raise HTTPException(422, str(exc)) from exc
    existing = owned(uid, receipt_id)
    if existing["status"] == "approved":
        if existing["expense"] == values:
            return public_receipt(existing)
        raise HTTPException(409, "Already approved with different values")
    # Approval and the expense are one atomic document mutation. No dual writes.
    try:
        return mutate(uid, receipt_id, body.revision, ["pending_review"],
                      {"status": "approved", "fields": body.fields.model_dump(), "expense": values, "approvedAt": now()}, "approved")
    except HTTPException as exc:
        if exc.status_code == 409:
            existing = owned(uid, receipt_id)
            if existing["status"] == "approved" and existing.get("expense") == values:
                return public_receipt(existing)
        raise


def expense_query(uid, start=None, end=None, currency=None, category=None, merchant=None):
    query = {"ownerId": uid, "status": "approved"}
    if start or end:
        for value in [start, end]:
            if value:
                try:
                    if date.fromisoformat(value).isoformat() != value:
                        raise ValueError("Noncanonical date")
                except ValueError as exc:
                    raise HTTPException(422, "Dates must use YYYY-MM-DD") from exc
        if start and end and start > end:
            raise HTTPException(422, "Start date must not be after end date")
        query["expense.expenseDate"] = {**({"$gte": start} if start else {}), **({"$lte": end} if end else {})}
    for name, value in [("currency", currency), ("category", category), ("merchantSearch", merchant.casefold().strip() if merchant else None)]:
        if value:
            query[f"expense.{name}"] = value
    return query


def summary(uid, start=None, end=None):
    match = expense_query(uid, start, end)
    pipeline = [{"$match": match}, {"$facet": {
        "currencies": [{"$group": {"_id": "$expense.currency", "totalMinor": {"$sum": "$expense.totalMinor"}, "count": {"$sum": 1}}}],
        "categories": [{"$group": {"_id": {"currency": "$expense.currency", "category": "$expense.category"}, "totalMinor": {"$sum": "$expense.totalMinor"}}}],
        "months": [{"$group": {"_id": {"currency": "$expense.currency", "month": {"$substrBytes": ["$expense.expenseDate", 0, 7]}}, "totalMinor": {"$sum": "$expense.totalMinor"}}}, {"$sort": {"_id.month": 1}}]
    }}]
    result = next(database().receipts.aggregate(pipeline))
    result["pending"] = database().receipts.count_documents({"ownerId": uid, "status": {"$in": ["pending_review", "queued", "processing", "failed"]}})
    return result
