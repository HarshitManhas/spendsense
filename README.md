# SpendSense AI

A receipt-to-expense web app using **React, FastAPI, MongoDB, and GridFS**, with a from-scratch PyTorch CNN + Transformer training pipeline.

Upload an image/PDF → review the fields → approve → see the expense and charts update. Each account has its own data. Firebase was replaced with MongoDB at the user's request.

**Current state:** local OCR can suggest merchant, date, tax, total and experimental item rows for human review. Item quantities/prices and categories are editable and persist in MongoDB. A category-training pipeline is ready but needs verified labels; no category model is trained yet. The failed custom CNN checkpoint is not installed. Google sign-in has been verified in the development workspace; new installations need their own Google web client ID. Two labeled local test accounts are also available. See the [receipt details and training plan](docs/receipt-details-training-plan.md), [build status](docs/build-status.md) and [project plan](SpendSense_AI_Project_Plan.md).

Selectable PDFs now preserve currency signs and table columns before falling back to OCR. See the [currency/spacing fix and symbol-training results](docs/currency-and-layout-fix.md). The trained glyph classifier remains experimental; it is not enabled automatically.

This workspace is connected to **MongoDB Atlas**, starting with an empty cloud expense database at the user's request. Earlier local receipts/files remain on this computer. See [Atlas connection and verification](docs/mongodb-atlas-setup.md). Refresh and sign in again after the database switch.

## Run locally on Windows

Prerequisites: Python 3.11, [uv](https://docs.astral.sh/uv/), and Node.js 22.12+ (tested with Node 24). Run the following from the repository root:

```powershell
uv sync --extra ml
npm.cmd ci
npm.cmd --prefix frontend ci
Copy-Item .env.example .env  # Only if .env does not already exist
```

Start MongoDB in one terminal:

```powershell
npm.cmd run db
```

The development helper downloads an official MongoDB 8.0.17 binary on first use (about 756 MB on Windows), binds to `127.0.0.1:27017`, and persists data under ignored `.local-db/`. It is a real MongoDB process, not a mock database. Stop with Ctrl+C; data remains for the next run. Do not run both this helper and Docker on the same port.

Alternatively, with Docker Desktop running:

```powershell
docker compose up -d mongo
```

Start the API in a second terminal:

```powershell
uv run --extra ml uvicorn ai_expense_scanner.api:app --reload --reload-dir src --host 127.0.0.1 --port 8000
```

Start the web app in a third terminal:

```powershell
npm.cmd --prefix frontend run dev
```

Open [SpendSense](http://localhost:5173). Open Alex's local workspace to try the application; Sam's workspace has independent data. API documentation is at [localhost:8000/docs](http://127.0.0.1:8000/docs). State-changing requests require an Origin and CSRF header, so the web UI is the easiest way to exercise them.

Optional fictional receipt for testing:

```powershell
uv run python scripts/create_sample_receipt.py
```

Upload `data/demo/sample-receipt.png`. The file is explicitly labeled fictional; it contains Sample Cafe, 2026-11-01, INR 349.00, and unspecified tax. Its values are not automatically predicted when no model is installed.

## Google sign-in

1. Create an OAuth **web application client** in Google Cloud and configure the consent screen/test users as required.
2. Add `http://localhost:5173` as an authorized JavaScript origin for local development.
3. Set `GOOGLE_CLIENT_ID=...apps.googleusercontent.com` in `.env` and restart the API.
4. Reload the web app. The Google button uses Google Identity Services; the API verifies the signed ID token, client ID, issuer, and login nonce before creating a session.
5. Set `ALLOW_DEV_LOGIN=false` when testing only real Google identities. Production must use `APP_ENV=production`, HTTPS `FRONTEND_ORIGIN`, and a real client ID; development account access is rejected outside development.

This flow needs a client ID, not a Google client secret. No Firebase project is used. Never paste MongoDB passwords or authentication tokens into tracked files. See [Google's server verification documentation](https://developers.google.com/identity/gsi/web/guides/verify-google-id-token).

## MongoDB and file storage

Set `MONGODB_URI` and `MONGODB_DATABASE` in `.env` to use a different server or Atlas. Give the database user access only to the application database and configure the network allowlist. Local defaults intentionally bind only to loopback.

Collections: `users`, `sessions`, `receipts`, `receipt_files.files`, `receipt_files.chunks`. An approved expense is embedded in its receipt document, making approval atomic even on standalone MongoDB. GridFS stores original uploads and page previews; browser previews always go through the authenticated API. See [MongoDB's GridFS guide](https://www.mongodb.com/docs/languages/python/pymongo-driver/current/crud/gridfs/).

The app never sums different currencies. Amounts use Decimal validation and integer minor units. Only approved receipts appear in spending totals; rejected/draft/deleted receipts do not.

## Prepare existing CORD and SROIE data

The snapshots already in `data/cord` and `data/sroie` are loaded directly without downloading:

```powershell
uv run --extra ml spendsense-data
```

This writes ignored JSONL manifests, a training-only character vocabulary, and `data/manifests/audit.json`. Current split: **1,286 train / 225 validation / 461 test**, after excluding 15 duplicate images from training/validation. Original test rows are retained. SROIE train is grouped by normalized merchant before its validation holdout.

The local CORD copy is **v1**. CORD does not label merchant/date/currency; SROIE does not label tax/currency. Partial-label masks prevent missing annotations from being taught as absent fields. Ambiguous dates/amounts remain unsupervised. Near-duplicate/corruption audits and fully labeled currency examples remain necessary.

## Train and evaluate

On Windows, `uv sync --extra ml` installs the pinned PyTorch 2.11 CUDA 12.8 build from the official PyTorch index. CUDA execution has been verified on this machine's 4 GiB RTX 2050. Other platforms use PyPI; select a compatible build for their hardware. Training automatically uses CUDA when available.

Smoke test (not an accuracy experiment):

```powershell
uv run --extra ml spendsense-train --limit 2 --epochs 1 --batch-size 2 --height 64 --width 64 --max-length 256 --output artifacts/smoke
```

Real-receipt overfit experiment, followed by free-running inspection:

```powershell
uv run --extra ml spendsense-train --limit 8 --epochs 100 --batch-size 2 --height 512 --width 256 --dropout 0 --learning-rate 0.001 --patience 100 --supervise-unknowns --output artifacts/overfit
uv run --extra ml python -m ai_expense_scanner.ml.evaluate --checkpoint artifacts/overfit/best.pt --manifest artifacts/overfit/training-selection.jsonl --output artifacts/overfit/evaluation.json
```

Initial full-data experiment, after completing the dataset/overfit gates:

```powershell
uv run --extra ml spendsense-train --height 512 --width 256 --batch-size 2 --accumulate 2 --epochs 30 --supervise-unknowns --output artifacts/full
uv run --extra ml python -m ai_expense_scanner.ml.evaluate --checkpoint artifacts/full/best.pt --manifest data/manifests/validation.jsonl --output artifacts/full/evaluation.json
```

The overfit subset alternates sources, is saved as `training-selection.jsonl`, and uses itself for validation. It measures memorization only. Full training uses the separate 225-receipt validation set. CUDA runs use FP16 mixed precision with gradient scaling by default (`--no-amp` disables it). Each run writes `status.json`, `metrics.jsonl`, `run.json`, `best.pt`, and an epoch-boundary `latest.pt` checkpoint. To resume, repeat the same command with the desired total epoch count and `--resume <output>/latest.pt`; keep model dimensions, batch size, accumulation, seed, learning rate, and the supervision policy unchanged.

The original fully masked unknown-value objective failed free generation: it never learned the literal `null` placeholders required by the JSON format. The current experiment explicitly enables `--supervise-unknowns`, teaching `null` as **abstention because an answer is unannotated or ambiguous**, not proof that a receipt field is absent. It does not replace unknown tax with zero or guess dates/currencies. This can bias the model to leave fields blank according to dataset annotation patterns; a fully annotated target-domain validation set remains necessary. Accuracy counts only genuinely labeled values; unknown placeholders never count as correct extracted fields. Currency has no labeled training examples and requires human entry.

To train and automatically evaluate validation after completion, use `uv run --extra ml python scripts/train_full.py --output artifacts/full --epochs 30`. Add `--resume` to restart this wrapper from its latest completed epoch. It never evaluates the test split or installs a serving model automatically.

For runs under `artifacts/runs`, inspect progress with `powershell -File scripts/training_status.ps1`. `ProcessAlive: False` with a running state means the process stopped unexpectedly; resume from the latest completed epoch. Keep the computer awake while a local run is active.

Use the test manifest only after selecting the model and preprocessing. These commands do not promise useful accuracy. A randomly initialized model trained on this small dataset may require substantially more data and experimentation. `--limit` checkpoints are flagged as tiny-overfit-only and cannot serve the app.

To serve an evaluated full checkpoint, set `EXTRACTION_PROVIDER=checkpoint` and `MODEL_PATH`, then start the worker separately:

```powershell
uv run --extra ml python -m ai_expense_scanner.worker
```

In checkpoint mode, uploads use manual review if no checkpoint exists and otherwise queue for the worker. The custom-model worker loads the model once, uses revision/lease guards, and leaves predictions awaiting approval. Copying a file to `MODEL_PATH` is not evidence of model quality; keep its evaluation report alongside it. For local OCR instead, install `ocr/.venv`, set `EXTRACTION_PROVIDER=paddleocr` and start the same worker. See [setup, item targets and category labeling](docs/receipt-details-training-plan.md).

## Verification

The separate pretrained OCR baseline lives in [`ocr/README.md`](ocr/README.md). It runs local PaddleOCR in its own CPU environment, then applies receipt-field rules and the same labeled-field evaluation used for the custom model. It matched **359/457 labeled fields (78.6%)** on 225 validation receipts; see [results and limitations](docs/ocr-baseline-results.md). The benchmark preserves OCR text, geometry, scores and evidence. It is now available as an explicit app provider, independent of the custom CNN + Transformer. New experimental item rules do not change the frozen five-field benchmark and have no held-out accuracy score yet.

```powershell
uv run --extra ml pytest -q
npm.cmd --prefix frontend test
npm.cmd --prefix frontend run build
```

MongoDB integration tests use a unique `spendsense_test_*` database and remove only that database afterward. Start `npm run db` before running them; otherwise they are reported as skipped. Unit/data/model tests do not require MongoDB.

Deletion recovery:

```powershell
uv run python -m ai_expense_scanner.cleanup
```

This removes GridFS data for already-tombstoned receipts, preserving shared originals still used by other pages. It does not delete active receipts.

## Before production

Complete rate limiting, a streaming request-body cap at the proxy/server boundary, abandoned-upload reconciliation, account/data deletion, retention/backup policy, worker operational limits, Google login verification, and a measured full-model evaluation. The current build has basic validation, ownership checks, CSRF/session protection, decoding limits, and private previews, but is not a production release.

Data, checkpoints, `.env`, database files, and build outputs are ignored. Do not add them to Git. The original dataset snapshots have not been modified.
