# SpendSense AI — Complete Project Build Guide

## Project goal

Build a full-stack AI expense scanner that accepts receipt images/PDFs, predicts structured expense fields, lets users review/correct them, and saves approved expenses to an expense tracker.

**Model constraint:** Receipt extraction uses a CNN encoder + Transformer decoder trained from random initialization in PyTorch. Do not use Gemini or another hosted LLM for extraction, and do not use pretrained vision encoders, OCR models, or pretrained language models in the extraction path.

**Reality check:** Direct image-to-JSON receipt reading from scratch is a difficult research problem. The pipeline can be implemented and tested, but a small dataset does not guarantee production-quality accuracy. Keep human review mandatory and report measured test results honestly.

## 1. MVP features

- Upload one or multiple receipt images and PDFs.
- Predict merchant, date, total, currency, and optionally tax.
- Display predictions beside the receipt for manual correction.
- Validate fields and flag missing/invalid values.
- Approve or reject a draft expense.
- Store approved expenses in PostgreSQL.
- Search, filter, sort, and export expenses as CSV.
- Dashboard with spending totals, recent expenses, and category charts.
- Docker-based local development and deployment.

Start with `merchant`, `date`, `total`, and `currency`. Add line items only after the basic model works. Represent missing fields as `null`; never invent values to fill gaps.

## 2. Architecture

```text
React + TypeScript UI
  ├── Upload receipts
  ├── Review/correct predictions
  └── Expenses, dashboard, analytics
             │ REST/JSON
             ▼
FastAPI backend ───────── PostgreSQL
  ├── Authentication           ├── receipts
  ├── File validation           ├── expenses
  ├── Extraction service        └── users
  └── Business validation
             │
             ▼
PyTorch CNN encoder (random init)
  └── visual feature grid → visual tokens
             │
             ▼
Transformer decoder (random init)
  └── autoregressive JSON/token sequence
             │
             ▼
Strict parser + Pydantic validation → pending human review
```

### Stack

| Layer | Technology |
|---|---|
| Frontend | React, TypeScript, Vite |
| Styling | Tailwind CSS |
| Charts/icons | Recharts, Lucide |
| API | FastAPI, Pydantic |
| ML | PyTorch |
| Image handling | Pillow |
| PDF rendering | PyMuPDF |
| Database | PostgreSQL |
| ORM/migrations | SQLAlchemy, Alembic |
| Tests | pytest, HTTPX, Vitest |
| Packaging | Docker, Docker Compose |

## 3. Repository layout

```text
spendsense-ai/
├── README.md
├── .env.example
├── .gitignore
├── docker-compose.yml
├── backend/
│   ├── Dockerfile
│   ├── pyproject.toml
│   ├── app/
│   │   ├── main.py
│   │   ├── core/config.py
│   │   ├── api/routes/{health,receipts,expenses}.py
│   │   ├── db/{session,models}.py
│   │   ├── schemas/{receipt,expense}.py
│   │   ├── services/{file_service,image_service,extraction_service,validation_service}.py
│   │   └── ml/
│   │       ├── config.py
│   │       ├── vocabulary.py
│   │       ├── dataset.py
│   │       ├── cnn_encoder.py
│   │       ├── transformer_decoder.py
│   │       ├── expense_model.py
│   │       ├── train.py
│   │       ├── evaluate.py
│   │       └── infer.py
│   ├── tests/
│   └── artifacts/             # checkpoints; do not commit large files
├── frontend/
│   └── src/
│       ├── api/
│       ├── components/
│       ├── pages/{Dashboard,Upload,Review,Expenses,ExpenseDetails,Analytics,Settings}.tsx
│       ├── hooks/
│       ├── types/
│       └── utils/
├── data/
│   ├── raw/                   # ignored by Git
│   ├── processed/             # ignored by Git
│   └── manifests/
└── scripts/{prepare_dataset,check_dataset}.py
```

## 4. Setup

Prerequisites: Python 3.11 (or a version supported by the selected PyTorch build), Node.js LTS, Git, and Docker. An NVIDIA GPU helps but is not required for basic tests.

### Python environment

**Windows PowerShell**
```powershell
py -3.11 -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install --upgrade pip
```

**Windows CMD**
```bat
py -3.11 -m venv .venv
.venv\Scripts\activate.bat
python -m pip install --upgrade pip
```

**Linux/macOS/WSL**
```bash
python3.11 -m venv .venv
source .venv/bin/activate
python -m pip install --upgrade pip
```

Install PyTorch using the current official selector for your operating system and CUDA configuration. Install backend dependencies:

```bash
pip install fastapi "uvicorn[standard]" pydantic-settings python-multipart pillow pymupdf sqlalchemy alembic "psycopg[binary]" pytest httpx numpy tqdm
```

Install authentication libraries only if implementing password-based authentication; prefer a well-maintained, reviewed authentication solution rather than inventing security primitives.

### Frontend

```bash
mkdir frontend
cd frontend
npm create vite@latest . -- --template react-ts
npm install
npm install react-router-dom recharts lucide-react
npm install -D tailwindcss @tailwindcss/vite
```

Follow the Tailwind instructions for the installed major version because configuration differs by version.

## 5. Dataset

Start with legally usable receipt datasets and inspect the current licenses/terms before use:

- CORD: https://github.com/clovaai/cord
- CORD on Hugging Face: https://huggingface.co/datasets/naver-clova-ix/cord-v2
- SROIE: https://github.com/jsdnrs/ICDAR2019-SROIE

CORD is commonly distributed with roughly 800 train, 100 validation, and 100 test receipts. Verify the current release and split before relying on these counts. SROIE has field-level annotations such as company, date, address, and total. Keep a record of each dataset's source and license; do not redistribute data unless permitted.

A few hundred receipts are not enough to expect robust OCR-free extraction from scratch. Use public licensed data, add more diverse data where permitted, and consider synthetic receipts rendered with known labels, varied fonts/layouts, blur, lighting, and compression. Split by receipt/source/merchant where possible to avoid layout leakage. Keep a final test set untouched.

### Canonical target schema

Normalize annotations to a fixed schema and key order:

```json
{
  "merchant": "EXAMPLE STORE",
  "date": "2025-03-18",
  "total": "349.00",
  "currency": "INR",
  "tax": null
}
```

Use strings for monetary values during token generation, then parse them as decimal values in the backend. Preserve unknowns as `null`. Do not assume every dataset uses INR.

Create fixed train/validation/test manifests and inspect random image-label pairs manually. Never fit the vocabulary using validation or test target strings.

## 6. From-scratch model design

### Initial configuration

| Parameter | Starting value |
|---|---:|
| Input | RGB `224×224` |
| CNN output channels | 128 |
| Total downsampling | 16× |
| Visual grid | `14×14` = 196 tokens |
| `d_model` | 256 |
| Attention heads | 4 |
| Transformer decoder layers | 3 |
| Feed-forward dimension | 1024 |
| Dropout | 0.1 |
| Batch size | 4 (reduce to 1–2 if memory is tight) |
| Optimizer | AdamW |
| Learning rate | `3e-4` |
| Weight decay | `1e-4` |
| Gradient clipping | 1.0 |

Treat these as starting points, not optimal settings. On a modest laptop GPU, reduce batch size or model dimensions if memory runs out.

### CNN encoder (`cnn_encoder.py`)

Input tensor: `(B, 3, 224, 224)`. Use four stride-2 convolution blocks to reduce `224 → 112 → 56 → 28 → 14`. Each block can use a 3×3 convolution, stride 2, padding 1, GroupNorm, and GELU. The final map should be `(B, 128, 14, 14)`.

Flatten the spatial grid into `(B, 196, 128)`, project each visual token to 256 dimensions, and add learned 2D positional embeddings. The encoder memory becomes `(B, 196, 256)`.

### Transformer decoder (`transformer_decoder.py`)

Use `torch.nn.TransformerDecoder` with `d_model=256`, `nhead=4`, `num_layers=3`, `dim_feedforward=1024`, `batch_first=True`, and dropout near 0.1.

Embed target tokens and add learned 1D positional embeddings. Apply a causal mask so each target position cannot attend to future positions. Use cross-attention to the CNN visual memory. Project decoder output from `(B,T,256)` to `(B,T,vocab_size)`.

### Expense model (`expense_model.py`)

Combine the encoder and decoder. `forward(images, input_ids)` should return logits of shape `(B,T,V)`. Keep vocabulary and model configuration saved alongside the checkpoint.

### Vocabulary and teacher forcing

For the first experiment, use a character-level vocabulary built only from training target JSON strings, with reserved IDs `<PAD>`, `<BOS>`, `<EOS>`, and `<UNK>`. Character-level generation is simple and avoids a pretrained tokenizer, but it creates long sequences and may be harder to train.

For each target:
- Decoder input: `<BOS>` + target tokens
- Labels: target tokens + `<EOS>`
- Pad sequences in each batch.
- Ignore `<PAD>` labels in cross-entropy loss.

During inference, begin with `<BOS>` and generate tokens autoregressively until `<EOS>` or a maximum length.

### Required shape tests

Before training, pass random tensors through the model and verify:

```text
images:       (2, 3, 224, 224)
input_ids:    (2, T)
logits:       (2, T, vocabulary_size)
```

Also verify finite logits/loss, nonzero finite gradients, correct causal masking, vocabulary round-trip, and generation termination. Do not start dataset-scale training until these tests pass.

## 7. Training

### Preprocessing

1. Decode image safely and convert to RGB.
2. Resize while preserving aspect ratio where possible; pad to the model canvas instead of severely squeezing text.
3. Normalize pixels consistently.
4. Apply mild training-only augmentation: small rotation, brightness/contrast variation, light blur, and compression artifacts.
5. Avoid augmentations that make text unreadable or alter labels.
6. Use deterministic preprocessing for validation, test, and production inference.

### Training loop

```python
for epoch in range(num_epochs):
    model.train()
    for images, decoder_input_ids, target_ids in train_loader:
        images = images.to(device)
        decoder_input_ids = decoder_input_ids.to(device)
        target_ids = target_ids.to(device)

        optimizer.zero_grad(set_to_none=True)
        logits = model(images, decoder_input_ids)
        loss = criterion(
            logits.reshape(-1, vocab_size),
            target_ids.reshape(-1),
        )
        loss.backward()
        torch.nn.utils.clip_grad_norm_(model.parameters(), 1.0)
        optimizer.step()

    val_loss = evaluate_loss(model, val_loader)
    # Save the best checkpoint using validation loss.
```

This is a training-loop skeleton; implement the dataset, collate function, masks, `evaluate_loss`, checkpoint saving, and scheduler. Configure cross-entropy with `ignore_index=PAD_ID`.

Start with up to 30 epochs and early stopping, not a fixed promise of convergence. First overfit 8–16 examples. If it cannot, check image/label pairing, target shifting, padding IDs, causal mask, and gradients before scaling up.

Save the model state, optimizer state, epoch, validation metric, vocabulary, model config, preprocessing config, and dataset split/version. Keep large checkpoints out of Git.

## 8. Evaluation

Do not report only loss. Evaluate the untouched test set using:

- JSON parse/validity rate
- Merchant exact match
- Date exact match
- Total exact match
- Per-field accuracy
- Receipt-level exact match
- Missing-field rate
- Invalid-output rate
- Human correction rate

Include sample counts with percentages. Normalize merchant whitespace and compare monetary amounts numerically, but never count a wrong amount as correct because punctuation differs. Break down results by merchant/layout when possible.

A token softmax score is not automatically a reliable field confidence score. Initially flag drafts for review when fields are missing, JSON is invalid, date/amount parsing fails, totals are suspicious, or generation hits its length limit. Calibrate confidence on validation data before using thresholds.

## 9. Backend and APIs

Suggested endpoints:

| Method | Endpoint | Purpose |
|---|---|---|
| GET | `/api/health` | Health check |
| POST | `/api/receipts` | Upload receipt |
| GET | `/api/receipts/{id}` | Receipt status/draft |
| POST | `/api/receipts/{id}/extract` | Run/re-run inference |
| POST | `/api/receipts/{id}/approve` | Approve reviewed fields |
| POST | `/api/receipts/{id}/reject` | Reject draft |
| GET | `/api/expenses` | List/search/filter |
| GET | `/api/expenses/{id}` | Expense detail |
| PATCH | `/api/expenses/{id}` | Edit expense |
| DELETE | `/api/expenses/{id}` | Delete under retention policy |
| GET | `/api/analytics/summary` | Dashboard summary |
| GET | `/api/expenses/export.csv` | CSV export |

### Upload flow

1. Authenticate user.
2. Validate file size, actual content type, dimensions/page count, and supported format.
3. Generate a random server-side filename; never trust client paths.
4. Store the file privately outside the public web root.
5. Create a receipt row.
6. Convert PDF pages to images with PyMuPDF, with strict page and resolution limits.
7. Run model inference; load weights once at application startup.
8. Parse generated text strictly and validate the schema.
9. Save the extraction as `pending_review`.
10. Return the receipt ID, fields, and warnings.

Use a background job if inference is too slow for a request/response cycle. Never use `eval()` to parse generated output. Treat model output as untrusted input and never automatically approve invalid or incomplete predictions.

### Example schema

```python
from datetime import date
from decimal import Decimal
from typing import Optional
from pydantic import BaseModel, Field, field_validator

class ExtractedExpense(BaseModel):
    merchant: Optional[str] = Field(default=None, max_length=200)
    date: Optional[date] = None
    total: Optional[Decimal] = Field(default=None, ge=0)
    currency: Optional[str] = Field(default=None, min_length=3, max_length=3)
    tax: Optional[Decimal] = Field(default=None, ge=0)

    @field_validator("merchant")
    @classmethod
    def clean_merchant(cls, value):
        if value is None:
            return None
        value = " ".join(value.split())
        return value or None
```

Use a Pydantic version compatible with this syntax. Only set currency when known; do not assume INR for an unknown receipt. Apply business checks, preserve nulls, and keep predictions pending until user confirmation.

## 10. Database

Suggested tables:

**users**
- `id`, `email`, `password_hash` or identity provider ID, `created_at`

**receipts**
- `id`, `user_id`, `original_filename`, `storage_key`, `mime_type`, `sha256`, `status`, `created_at`, `processed_at`, `model_version`

**expenses**
- `id`, `user_id`, nullable `receipt_id`, `merchant`, `expense_date`, `total`, `currency`, `tax`, `category`, `payment_method`, `notes`, `review_status`, `created_at`, `updated_at`

**expense_items** (later)
- `id`, `expense_id`, `description`, `quantity`, `unit_price`, `line_total`

Use SQLAlchemy and Alembic migrations. Use `NUMERIC`/decimal types for money, not binary floating point. Add foreign keys and indexes on `user_id`, date, and frequently searched fields. Every query must enforce user ownership; user A must never be able to read or edit user B's receipts.

## 11. Frontend design

Product name: **SpendSense AI**.

Suggested visual system:
- Primary indigo `#4F46E5`
- Background `#F8FAFC`
- Cards `#FFFFFF`
- Main text `#0F172A`
- Secondary text `#64748B`

Screens:
1. **Dashboard:** spending totals, month-to-date spend, recent expenses, category chart, pending review count.
2. **Upload:** drag/drop, multi-file selection, accepted formats, progress, retry/error states.
3. **AI Review:** receipt preview, editable fields, missing/invalid warnings, approve/reject actions.
4. **All Expenses:** search, date/category/status filters, sorting, pagination, CSV export.
5. **Expense Details:** fields, receipt preview, change history.
6. **Analytics:** monthly trends, category and merchant breakdown.
7. **Settings:** profile, currency preference, export/delete data options.

Keep API calls in `src/api/`, share TypeScript interfaces, show loading/error/empty states, confirm destructive actions, and make controls accessible by keyboard. Frontend validation complements but never replaces backend validation. Do not store authentication secrets or private receipt data in `localStorage`. Mock data is fine for a clearly labelled prototype, but not as a substitute for live model predictions in the final demo.

## 12. Security and privacy

Receipts are private financial documents. At minimum:
- Require authentication and enforce ownership checks on every private record.
- Use HTTPS in deployment.
- Store uploads outside public directories with random storage keys.
- Validate file contents and limit file size, image dimensions, PDF pages, and processing time.
- Prevent path traversal and reject malformed files.
- Hash passwords with a vetted password-hashing implementation; never store plaintext.
- Keep secrets in environment variables or a secrets manager, never source control.
- Restrict CORS to known frontend origins.
- Rate-limit upload and extraction endpoints.
- Avoid logging raw receipt images, full receipt text, or sensitive values.
- Define retention/deletion for files, extracted text, and logs.
- Ask for consent before using user corrections for training.
- Never put real private receipts in public demos or repositories.

This project is not automatically compliant with any particular regulation; review requirements for the intended deployment.

## 13. Environment and Docker

Create `.env.example`:

```dotenv
APP_ENV=development
SECRET_KEY=replace-with-a-long-random-secret
DATABASE_URL=postgresql+psycopg://app:change-me@db:5432/spendsense
MODEL_PATH=/app/artifacts/best_model.pt
VOCAB_PATH=/app/artifacts/vocab.json
UPLOAD_DIR=/app/private_uploads
MAX_UPLOAD_MB=10
FRONTEND_ORIGIN=http://localhost:5173
```

Copy to `.env` and change secrets. Never commit `.env`.

Use Docker Compose services for:
- `db`: PostgreSQL with health check and persistent named volume
- `backend`: FastAPI app
- `frontend`: dev server or built static app
- optional `trainer` profile: isolated training environment

Do not put a large model checkpoint in the frontend image. Keep model and vocabulary versions paired. If model artifacts are absent, report inference as unavailable rather than returning fake data.

Once Dockerfiles and Compose are implemented:

```bash
docker compose up --build
```

Document the configured ports. Test API health, UI loading, uploads, review/approval, and persistence after a container restart.

## 14. Tests

### Model
- CNN output `(B,128,14,14)`
- Visual memory `(B,196,256)`
- Logits `(B,T,V)`
- Finite loss and gradients
- Tiny-subset overfit test
- EOS/max-length generation stop
- Vocabulary encode/decode round-trip

### Data
- Image/label alignment
- Corrupt files handled safely
- Missing values remain null
- No train/test leakage
- Same preprocessing for evaluation and inference

### API/security
- Health endpoint works
- Unsupported/oversized files rejected
- Unauthenticated access denied
- Cross-user receipt access denied
- Invalid output stays in review
- Approval persists
- Deletion follows retention policy

### Frontend/end-to-end
- Upload success/failure
- Review fields editable
- Warnings visible
- Approval sends edited values
- Search/filter/export work
- Responsive and accessible loading/empty states
- Upload a test receipt → review → correct → approve → find in expenses → export CSV

## 15. Milestone plan

### Milestone 1: Contracts and UI skeleton
Define fields, statuses, JSON schema, and typed API payloads. Build static screens with clearly labelled mock data.

### Milestone 2: Dataset pipeline
Download licensed data, normalize annotations, create split manifests, and inspect samples.

### Milestone 3: Model shape correctness
Implement `config.py`, `vocabulary.py`, `cnn_encoder.py`, `transformer_decoder.py`, `expense_model.py`, and shape/gradient tests.

### Milestone 4: Training
Implement dataset, collate function, teacher forcing, padding, cross-entropy, optimizer, validation, checkpointing, and early stopping. Overfit 8–16 examples first.

### Milestone 5: Evaluation/inference
Implement greedy decoding, strict JSON parsing, per-field metrics, and error inspection.

### Milestone 6: FastAPI integration
Load model once on startup; implement health, upload, status, extraction, and review endpoints with validation.

### Milestone 7: PostgreSQL
Add migrations, users/receipts/expenses tables, review history, and ownership checks.

### Milestone 8: Frontend integration
Replace mock data with API calls; finish upload, review, expense list, details, and analytics.

### Milestone 9: Docker and hardening
Containerize services, configure secrets/CORS/limits, add tests, and document reproducible setup.

## 16. Troubleshooting

**Invalid JSON:** Check target formatting, BOS/EOS, token shifting, padding IDs, and maximum generation length. Keep invalid output in review; never invent amounts to repair it.

**Repeated tokens/no EOS:** Verify causal mask, EOS training labels, generation loop, and vocabulary.

**Loss does not decrease:** Verify image/label pairing, target shift, padding masks, gradients, and optimizer parameters. Try to overfit a tiny subset.

**Training works but unseen merchants fail:** Dataset diversity is insufficient or the model overfits layouts. Add legally usable diverse receipts, use synthetic data, split by merchant/layout, and report per-group metrics.

**CUDA out of memory:** Reduce batch size, use gradient accumulation, reduce `d_model`/layers/resolution, close other GPU processes, and first validate on CPU if necessary.

**PDF failures:** Limit page count and render resolution, handle encrypted/malformed files, and return a clear error to the user.

## 17. MVP completion checklist

- [ ] Upload receipt image/PDF securely.
- [ ] Run a CNN + Transformer model trained from random initialization.
- [ ] No hosted LLM or pretrained extraction model in the inference path.
- [ ] Strictly parse and validate model output.
- [ ] Show uncertain/missing fields for review.
- [ ] Edit and approve/reject drafts.
- [ ] Persist approved expenses in PostgreSQL.
- [ ] Dashboard/list use real backend data.
- [ ] Search, filters, and CSV export work.
- [ ] Tests cover model, API validation, and user isolation.
- [ ] Docker setup works from a clean environment.
- [ ] README documents dataset licenses, measured metrics, and limitations.

## 18. References

- CORD: https://github.com/clovaai/cord
- CORD dataset on Hugging Face: https://huggingface.co/datasets/naver-clova-ix/cord-v2
- SROIE: https://github.com/jsdnrs/ICDAR2019-SROIE
- PyTorch: https://pytorch.org/docs/stable/index.html
- TransformerDecoder: https://pytorch.org/docs/stable/generated/torch.nn.TransformerDecoder.html
- FastAPI: https://fastapi.tiangolo.com/
- Pydantic: https://docs.pydantic.dev/
- SQLAlchemy: https://docs.sqlalchemy.org/
- Alembic: https://alembic.sqlalchemy.org/
- React: https://react.dev/
- Vite: https://vite.dev/
- Docker Compose: https://docs.docker.com/compose/

Check current documentation and dataset terms during implementation; versions and URLs can change.

## 19. First coding task

Start with the model correctness milestone:
1. Create `backend/app/ml/config.py`.
2. Implement `cnn_encoder.py`.
3. Implement `transformer_decoder.py`.
4. Implement `expense_model.py`.
5. Implement `vocabulary.py`.
6. Add `test_model_shapes.py`.
7. Verify forward/backward passes with random tensors.
8. Implement the dataset adapter and training loop only after the shape tests pass.

**Principle:** a full-stack demo can be useful before the model is highly accurate, provided predictions are labelled honestly, humans review them, and test metrics are transparent.
