import csv
import io
import json
import base64

from fastapi import Depends, FastAPI, HTTPException, Query, Request, Response, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse, StreamingResponse
from pymongo.errors import PyMongoError
from starlette.concurrency import run_in_threadpool

from . import auth, service
from .config import settings
from .database import database, files, public_receipt
from .schemas import CURRENCIES, ReviewRequest, RevisionRequest, approved_values
from .extraction import ready

app = FastAPI(title="SpendSense API", version="0.1.0")
app.add_middleware(CORSMiddleware, allow_origins=[settings().frontend_origin],
                   allow_credentials=True, allow_methods=["GET", "POST", "PATCH", "DELETE"],
                   allow_headers=["Content-Type", "X-CSRF-Token"])
app.include_router(auth.router)


@app.middleware("http")
async def private_responses(request: Request, call_next):
    if request.url.path == "/api/receipts" and request.method == "POST":
        try:
            length = int(request.headers.get("content-length", "0"))
        except ValueError:
            return JSONResponse({"detail": "Invalid content length"}, status_code=400)
        if length > settings().max_upload_mb * 1024**2 + 65536:
            return JSONResponse({"detail": "Receipt exceeds the upload limit"}, status_code=413)
    response = await call_next(request)
    response.headers["Cache-Control"] = "no-store"
    response.headers["X-Content-Type-Options"] = "nosniff"
    return response


@app.exception_handler(PyMongoError)
async def database_error(request, exc):
    return JSONResponse({"detail": "Database unavailable. Start MongoDB and retry."}, status_code=503)


@app.get("/api/health")
def health():
    database().command("ping")
    return {"status": "ok", "database": "mongodb", "extraction": settings().extraction_provider + "_available" if ready() else "manual_only", "currencies": CURRENCIES,
            "maxUploadMb": settings().max_upload_mb, "maxPdfPages": settings().max_pdf_pages}


@app.post("/api/receipts", status_code=202, dependencies=[Depends(auth.csrf_guard)])
async def upload(file: UploadFile, user=Depends(auth.current_user)):
    try:
        content = await file.read(settings().max_upload_mb * 1024**2 + 1)
        if len(content) > settings().max_upload_mb * 1024**2:
            raise HTTPException(413, "Receipt exceeds the upload limit")
        if not content:
            raise HTTPException(422, "The uploaded file is empty")
        return await run_in_threadpool(service.upload, user["id"], file.filename or "Receipt", content)
    finally:
        await file.close()


@app.get("/api/receipts")
def receipts(user=Depends(auth.current_user), status: str | None = None, before: str | None = None, limit: int = Query(50, ge=1, le=100)):
    query = {"ownerId": user["id"], "status": status if status else {"$nin": ["deleted", "approved", "rejected"]}}
    if status == "deleted":
        raise HTTPException(422, "Deleted receipts cannot be listed")
    if before:
        anchor = service.owned(user["id"], before)
        query["$or"] = [{"createdAt": {"$lt": anchor["createdAt"]}}, {"createdAt": anchor["createdAt"], "_id": {"$gt": anchor["_id"]}}]
    rows = list(database().receipts.find(query).sort([("createdAt", -1), ("_id", 1)]).limit(limit + 1))
    return {"items": [public_receipt(r) for r in rows[:limit]], "nextCursor": rows[limit - 1]["_id"] if len(rows) > limit else None}


@app.get("/api/receipts/{receipt_id}")
def receipt(receipt_id: str, user=Depends(auth.current_user)):
    return public_receipt(service.owned(user["id"], receipt_id))


@app.get("/api/receipts/{receipt_id}/preview")
def preview(receipt_id: str, user=Depends(auth.current_user)):
    row = service.owned(user["id"], receipt_id)
    content = files().get(row["previewId"])
    if content.metadata["ownerId"] != user["id"]:
        raise HTTPException(404)
    preview = content.read()
    return Response(preview, media_type="image/jpeg" if preview.startswith(b'\xff\xd8') else "image/png")


@app.patch("/api/receipts/{receipt_id}/review", dependencies=[Depends(auth.csrf_guard)])
def review(receipt_id: str, body: ReviewRequest, user=Depends(auth.current_user)):
    return service.mutate(user["id"], receipt_id, body.revision, ["pending_review", "failed"],
                          {"fields": body.fields.model_dump(), "status": "pending_review"}, "review_saved")


@app.post("/api/receipts/{receipt_id}/approve", dependencies=[Depends(auth.csrf_guard)])
def approve(receipt_id: str, body: ReviewRequest, user=Depends(auth.current_user)):
    return service.approve(user["id"], receipt_id, body)


@app.post("/api/receipts/{receipt_id}/reject", dependencies=[Depends(auth.csrf_guard)])
def reject(receipt_id: str, body: RevisionRequest, user=Depends(auth.current_user)):
    return service.mutate(user["id"], receipt_id, body.revision, ["pending_review", "failed", "queued"], {"status": "rejected"}, "rejected")


@app.post("/api/receipts/{receipt_id}/extract", dependencies=[Depends(auth.csrf_guard)])
def extract(receipt_id: str, body: RevisionRequest, user=Depends(auth.current_user)):
    if not ready():
        raise HTTPException(503, "Extraction provider unavailable; manual review is available")
    return service.mutate(user["id"], receipt_id, body.revision, ["pending_review", "failed"],
                          {"status": "queued", "attempts": 0, "source": settings().extraction_provider}, "extraction_requested")


@app.get('/api/expenses/category-labels.jsonl')
def category_labels(user=Depends(auth.current_user)):
    query = service.expense_query(user['id'])
    query['expense.category'] = {'$ne': 'uncategorized'}

    def generate():
        for row in database().receipts.find(query).sort('_id', 1):
            expense = row['expense']
            yield json.dumps({'id': row['_id'], 'image_sha256': row.get('sha256'),
                'merchant': expense['merchant'], 'date': expense['expenseDate'],
                'items': [{'name': item['name']} for item in expense.get('items', [])],
                'category': expense['category'], 'verified': True,
                'label_source': 'user_approved_expense', 'revision': row['revision']}, ensure_ascii=False) + '\n'
    return StreamingResponse(generate(), media_type='application/x-ndjson',
        headers={'Content-Disposition': 'attachment; filename="spendsense-category-labels.jsonl"'})


@app.delete("/api/receipts/{receipt_id}", dependencies=[Depends(auth.csrf_guard)])
def delete(receipt_id: str, body: RevisionRequest, user=Depends(auth.current_user)):
    row = service.owned(user["id"], receipt_id)
    result = service.mutate(user["id"], receipt_id, body.revision,
        ["pending_review", "failed", "approved", "queued", "rejected", "processing"], {"status": "deleted"}, "deleted")
    # Tombstone first; a retryable cleanup command handles crashes between DB and GridFS.
    files().delete(row["previewId"])
    if not database().receipts.count_documents({"uploadId": row["uploadId"], "ownerId": user["id"], "status": {"$ne": "deleted"}}):
        files().delete(row["originalId"])
    return result


@app.get("/api/expenses/export.csv")
def export(start: str | None = None, end: str | None = None, currency: str | None = None,
           category: str | None = None, merchant: str | None = None, user=Depends(auth.current_user)):
    query = service.expense_query(user["id"], start, end, currency, category, merchant)
    def generate():
        buf = io.StringIO(); writer = csv.writer(buf)
        writer.writerow(["Merchant", "Date", "Total", "Currency", "Tax", "Category", "Notes"])
        yield buf.getvalue(); buf.seek(0); buf.truncate(0)
        for row in database().receipts.find(query).sort("expense.expenseDate", -1):
            e = row['expense']; exp = e['currencyExponent']
            def money(value):
                from decimal import Decimal
                return '' if value is None else f"{Decimal(value) / 10**exp:.{exp}f}"
            values = [e['merchant'], e['expenseDate'], money(e['totalMinor']), e['currency'], money(e['taxMinor']), e['category'], e['notes']]
            writer.writerow(["'" + v if v.lstrip().startswith(('=', '+', '-', '@', '\t', '\r')) else v for v in values])
            yield buf.getvalue(); buf.seek(0); buf.truncate(0)
    return StreamingResponse(generate(), media_type="text/csv", headers={"Content-Disposition": 'attachment; filename="spendsense-expenses.csv"'})


@app.get("/api/expenses")
def expenses(start: str | None = None, end: str | None = None, currency: str | None = None,
             category: str | None = None, merchant: str | None = None, cursor: str | None = None,
             limit: int = Query(50, ge=1, le=100), user=Depends(auth.current_user)):
    query = service.expense_query(user["id"], start, end, currency, category, merchant)
    if cursor:
        try:
            boundary = json.loads(base64.urlsafe_b64decode(cursor))
            if not isinstance(boundary, list) or len(boundary) != 2 or not all(isinstance(x, str) for x in boundary):
                raise ValueError()
            query['$or'] = [{"expense.expenseDate": {"$lt": boundary[0]}}, {"expense.expenseDate": boundary[0], "_id": {"$gt": boundary[1]}}]
        except Exception as exc:
            raise HTTPException(422, "Invalid cursor") from exc
    rows = list(database().receipts.find(query).sort([("expense.expenseDate", -1), ("_id", 1)]).limit(limit + 1))
    next_cursor = None
    if len(rows) > limit:
        last = rows[limit - 1]
        next_cursor = base64.urlsafe_b64encode(json.dumps([last['expense']['expenseDate'], last['_id']]).encode()).decode()
    return {"items": [public_receipt(r) for r in rows[:limit]], "nextCursor": next_cursor}


@app.patch("/api/expenses/{receipt_id}", dependencies=[Depends(auth.csrf_guard)])
def edit_expense(receipt_id: str, body: ReviewRequest, user=Depends(auth.current_user)):
    try:
        values = approved_values(body.fields, body.confirm_warnings)
    except ValueError as exc:
        raise HTTPException(422, str(exc)) from exc
    return service.mutate(user["id"], receipt_id, body.revision, ["approved"],
                          {"fields": body.fields.model_dump(), "expense": values}, "expense_edited")


@app.get("/api/analytics/summary")
def analytics(start: str | None = None, end: str | None = None, user=Depends(auth.current_user)):
    return service.summary(user["id"], start, end)
