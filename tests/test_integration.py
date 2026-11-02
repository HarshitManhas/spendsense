import io
import os
import uuid
from concurrent.futures import ThreadPoolExecutor

import pytest
from fastapi.testclient import TestClient
from PIL import Image
from pymongo import MongoClient

from ai_expense_scanner.config import settings
from ai_expense_scanner.database import database, files

pytestmark = pytest.mark.integration


@pytest.fixture
def clients(monkeypatch):
    uri = os.environ.get('TEST_MONGODB_URI', 'mongodb://127.0.0.1:27017')
    mongo = MongoClient(uri, serverSelectionTimeoutMS=1000)
    try: mongo.admin.command('ping')
    except Exception: pytest.skip('Start local MongoDB with npm run db')
    name = 'spendsense_test_' + uuid.uuid4().hex
    monkeypatch.setenv('MONGODB_URI', uri)
    monkeypatch.setenv('MONGODB_DATABASE', name)
    monkeypatch.setenv('ALLOW_DEV_LOGIN', 'true')
    monkeypatch.setenv('MODEL_PATH', 'artifacts/not-installed-test.pt')
    monkeypatch.setenv('EXTRACTION_PROVIDER', 'checkpoint')
    monkeypatch.setenv('REMOTE_WORKER', 'false')
    settings.cache_clear(); database.cache_clear()
    from ai_expense_scanner.api import app
    a, b = TestClient(app), TestClient(app)
    for client, account in [(a, 'alex'), (b, 'sam')]:
        config = client.get('/api/auth/config').json()
        client.headers.update({'Origin': 'http://localhost:5173', 'X-CSRF-Token': config['csrfToken']})
        assert client.post('/api/auth/development', json={'account': account}).status_code == 200
    yield a, b
    a.close(); b.close()
    database().client.close()
    mongo.drop_database(name); mongo.close()
    database.cache_clear(); settings.cache_clear()


def sample_image():
    content = io.BytesIO(); Image.new('RGB', (140, 250), 'white').save(content, 'PNG')
    return content.getvalue()


def upload(client):
    result = client.post('/api/receipts', files={'file': ('test.png', sample_image(), 'image/png')})
    assert result.status_code == 202, result.text
    return result.json()['receipts'][0]


def reviewed(row):
    return {'revision': row['revision'], 'fields': {'merchant': '=Example store', 'date': '2026-11-01', 'total': '349.00', 'currency': 'INR', 'tax': None, 'category': 'food', 'notes': ''}}


def test_review_approval_isolation_money_and_deletion(clients):
    a, b = clients; row = upload(a); receipt_id = row['id']; body = reviewed(row)
    assert a.get('/api/analytics/summary').json()['currencies'] == []
    assert a.get(f'/api/receipts/{receipt_id}/preview').status_code == 200
    for path in [f'/api/receipts/{receipt_id}', f'/api/receipts/{receipt_id}/preview']:
        assert b.get(path).status_code == 404
    assert b.post(f'/api/receipts/{receipt_id}/approve', json=body).status_code == 404
    assert b.patch(f'/api/receipts/{receipt_id}/review', json=body).status_code == 404
    assert b.get('/api/expenses').json()['items'] == []
    assert b.get('/api/expenses/export.csv').text.count('\n') == 1
    # Concurrent repeat approval must return the same single expense.
    with ThreadPoolExecutor(max_workers=2) as pool:
        results = list(pool.map(lambda _: a.post(f'/api/receipts/{receipt_id}/approve', json=body), range(2)))
    assert all(r.status_code == 200 for r in results), [r.text for r in results]
    assert len(a.get('/api/expenses').json()['items']) == 1
    assert a.get('/api/analytics/summary').json()['currencies'][0]['totalMinor'] == 34900
    assert "'=Example store" in a.get('/api/expenses/export.csv').text
    approved = results[0].json()
    body['revision'] = approved['revision']; body['fields']['total'] = '100.50'
    updated = a.patch(f'/api/expenses/{receipt_id}', json=body)
    assert updated.status_code == 200
    assert a.get('/api/analytics/summary').json()['currencies'][0]['totalMinor'] == 10050
    assert a.patch(f'/api/expenses/{receipt_id}', json=body).status_code == 409
    assert b.request('DELETE', f'/api/receipts/{receipt_id}', json={'revision': updated.json()['revision']}).status_code == 404
    assert a.request('DELETE', f'/api/receipts/{receipt_id}', json={'revision': updated.json()['revision']}).status_code == 200
    assert a.get('/api/analytics/summary').json()['currencies'] == []
    assert database().receipt_files.files.count_documents({}) == 0


def test_validation_csrf_and_logout(clients):
    a, _ = clients
    old_csrf = a.headers['X-CSRF-Token']
    assert a.get('/api/auth/config').json()['csrfToken'] == old_csrf
    row = upload(a); body = reviewed(row)
    body['fields']['total'] = 'NaN'
    assert a.post(f"/api/receipts/{row['id']}/approve", json=body).status_code == 422
    assert a.get('/api/expenses?start=20261101').status_code == 422
    assert a.get('/api/expenses?start=2026-11-01&end=2026-01-01').status_code == 422
    assert a.post('/api/receipts', files={'file': ('bad.png', b'not an image', 'image/png')}).status_code == 422
    response = a.post('/api/auth/logout', headers={'Origin': 'https://attacker.invalid'})
    assert response.status_code == 403
    assert a.post('/api/auth/logout').status_code == 200
    assert a.get('/api/receipts').status_code == 401


def test_pdf_pages_and_shared_original_retention(clients):
    import pymupdf
    a, _ = clients
    with pymupdf.open() as document:
        document.new_page(); document.new_page()
        pdf = document.tobytes()
    response = a.post('/api/receipts', files={'file': ('two.pdf', pdf, 'application/pdf')})
    assert response.status_code == 202, response.text
    rows = response.json()['receipts']; assert len(rows) == 2
    assert database().receipt_files.files.count_documents({}) == 3
    for i, row in enumerate(rows):
        assert a.request('DELETE', f"/api/receipts/{row['id']}", json={'revision': 1}).status_code == 200
        assert database().receipt_files.files.count_documents({}) == (2 if i == 0 else 0)


def test_item_review_and_private_category_export(clients):
    import json
    a, b = clients
    row = upload(a); body = reviewed(row)
    body['fields']['category'] = 'travel'
    body['fields']['items'] = [{'name': 'Breakfast', 'quantity': '2', 'unit_price': '50.00', 'line_total': '100.00'}]
    saved = a.patch(f"/api/receipts/{row['id']}/review", json=body)
    assert saved.status_code == 200
    assert a.get('/api/expenses/category-labels.jsonl').text == ''

    body['revision'] = saved.json()['revision']
    approved = a.post(f"/api/receipts/{row['id']}/approve", json=body)
    assert approved.status_code == 200, approved.text
    assert approved.json()['expense']['items'][0]['unitPriceMinor'] == 5000
    assert a.get(f"/api/receipts/{row['id']}").json()['fields']['items'][0]['quantity'] == '2'
    record = json.loads(a.get('/api/expenses/category-labels.jsonl').text)
    assert record['category'] == 'travel' and record['verified'] is True
    assert record['date'] == '2026-11-01'
    assert record['items'] == [{'name': 'Breakfast'}]
    assert b.get('/api/expenses/category-labels.jsonl').text == ''
    # Edits must replace the labels; removing items must clear approved storage.
    body['revision'] = approved.json()['revision']
    body['fields']['category'] = 'uncategorized'; body['fields']['items'] = []
    changed = a.patch(f"/api/expenses/{row['id']}", json=body)
    assert changed.status_code == 200
    assert 'items' not in changed.json()['expense']
    assert a.get('/api/expenses/category-labels.jsonl').text == ''


def test_google_identity_nonce_audience_and_owner_isolation(clients, monkeypatch):
    from ai_expense_scanner import auth
    a, b = clients
    dev_receipt = upload(a)
    monkeypatch.setenv('GOOGLE_CLIENT_ID', 'spendsense-test.apps.googleusercontent.com')
    settings.cache_clear()
    calls = []

    def verify(token, request, audience):
        calls.append(audience)
        if token == 'invalid-signature':
            raise ValueError('Invalid signature fixture')
        return {'sub': 'google-user-a' if token != 'user-b' else 'google-user-b',
                'email': 'fixture@example.test', 'name': 'Google fixture',
                'email_verified': token != 'unverified-email',
                'nonce': 'incorrect' if token == 'wrong-nonce' else
                         b.cookies.get('spendsense_csrf') if token == 'user-b' else a.cookies.get('spendsense_csrf')}

    monkeypatch.setattr(auth.id_token, 'verify_oauth2_token', verify)
    for token in ('invalid-signature', 'wrong-nonce', 'unverified-email'):
        assert a.post('/api/auth/google', json={'credential': token}).status_code == 401
        assert a.get('/api/auth/me').json()['id'] == 'dev:alex'
    signed_in = a.post('/api/auth/google', json={'credential': 'user-a'})
    assert signed_in.status_code == 200
    assert signed_in.json()['id'] == 'google:google-user-a'
    assert a.get(f"/api/receipts/{dev_receipt['id']}").status_code == 404
    google_receipt = upload(a)
    assert b.post('/api/auth/google', json={'credential': 'user-b'}).status_code == 200
    assert b.get(f"/api/receipts/{google_receipt['id']}").status_code == 404
    assert all(audience == 'spendsense-test.apps.googleusercontent.com' for audience in calls)


def test_remote_worker_discovery_queue_and_review(clients, monkeypatch):
    from datetime import timedelta
    from ai_expense_scanner.database import now
    from ai_expense_scanner.schemas import Draft
    from ai_expense_scanner.worker import process_next
    a, b = clients
    monkeypatch.setenv('REMOTE_WORKER', 'true')
    monkeypatch.setenv('MAX_UPLOAD_MB', '4')
    settings.cache_clear()
    assert a.get('/api/health').json()['maxUploadMb'] == 4
    assert a.get('/api/health').json()['extraction'] == 'manual_only'
    db = database()
    db.workers.insert_one({'_id': 'test-worker', 'provider': 'checkpoint', 'modelId': '', 'lastSeen': now()})
    assert a.get('/api/health').json()['extraction'] == 'checkpoint_available'
    row = upload(a)
    assert row['status'] == 'queued'
    assert b.get(f"/api/receipts/{row['id']}").status_code == 404
    assert process_next(lambda *args, **kwargs: (Draft(merchant='Worker fixture'), [], 'fixture-v1'), db)
    result = a.get(f"/api/receipts/{row['id']}").json()
    assert result['status'] == 'pending_review' and result['fields']['merchant'] == 'Worker fixture'
    assert a.get('/api/analytics/summary').json()['currencies'] == []
    assert not process_next(lambda *args, **kwargs: pytest.fail('No work should be claimed'), db)
    db.workers.update_one({'_id': 'test-worker'}, {'$set': {'lastSeen': now() - timedelta(seconds=241)}})
    assert a.get('/api/health').json()['extraction'] == 'manual_only'
    assert a.post(f"/api/receipts/{row['id']}/extract", json={'revision': result['revision']}).status_code == 503
    db.workers.update_one({'_id': 'test-worker'}, {'$set': {'lastSeen': now(), 'modelId': 'a' * 64}})
    assert a.get('/api/health').json()['extraction'] == 'manual_only'


def test_server_rejects_oversize_upload_before_rendering(clients, monkeypatch):
    from ai_expense_scanner import service
    a, _ = clients
    monkeypatch.setenv('MAX_UPLOAD_MB', '4')
    settings.cache_clear()
    monkeypatch.setattr(service, 'render_upload', lambda *args: pytest.fail('Oversize input reached renderer'))
    response = a.post('/api/receipts', files={'file': ('big.png', b'x' * (4 * 1024**2 + 1), 'image/png')})
    assert response.status_code == 413
    assert database().receipt_files.files.count_documents({}) == 0


def test_private_model_publication_is_repeatable(clients, tmp_path):
    from ai_expense_scanner.model_store import FILES, publish_model, restore_model
    for name in FILES:
        (tmp_path / name).write_bytes(b'fixture-' + name.encode())
    model_id = publish_model(tmp_path)
    assert publish_model(tmp_path) == model_id
    assert database().ocr_models.files.count_documents({}) == 1
    restored = restore_model(model_id)
    assert all((restored / name).read_bytes() == (tmp_path / name).read_bytes() for name in FILES)


def test_worker_does_not_overwrite_review_during_extraction(clients):
    from ai_expense_scanner.schemas import Draft
    from ai_expense_scanner.worker import process_next
    a, _ = clients
    row = upload(a)
    db = database()
    db.receipts.update_one({'_id': row['id']}, {'$set': {'status': 'queued'}})

    def predict(*args, **kwargs):
        db.receipts.update_one({'_id': row['id']}, {'$set': {'status': 'rejected'}, '$inc': {'revision': 1}})
        return Draft(merchant='Must not be saved'), [], 'fixture-v1'

    assert process_next(predict, db)
    result = a.get('/api/receipts/' + row['id']).json()
    assert result['status'] == 'rejected' and result['fields']['merchant'] is None
