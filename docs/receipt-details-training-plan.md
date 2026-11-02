# Merchant, dates, items, prices and expense categories

Updated 2 November 2026 (Asia/Calcutta).

## Product target and current implementation

Upload image/PDF → local OCR → suggested merchant, receipt date, tax, total and item rows → human correction and category selection → approval → MongoDB/GridFS → per-user analytics.

The application now supports local PaddleOCR as a separate provider from the custom CNN + Transformer. Its original five-field rules remain frozen. New item-row rules are experimental and have not received a held-out accuracy score. Missing/ambiguous values remain blank. A user can add, remove and correct items before approval or when editing an approved expense.

An item stores name, optional quantity, optional unit price and optional line total. Approved prices use integer currency minor units; quantities use decimal strings. Quantity × unit-price differences require explicit confirmation, allowing discounts/adjustments. The receipt total remains authoritative: tax, service charges and discounts mean it need not equal the sum of item totals. Dates must be valid `YYYY-MM-DD` values before approval; ambiguous printed day/month order requires review.

Categories: food (prepared meals/drinks), groceries (food ingredients/household groceries), travel (flights, hotels and intercity trips), transport (local taxi/transit/fuel), shopping, health, utilities, other, and uncategorized. These are labeling guidelines, not keyword rules. Mixed receipts receive one user-selected primary category for now; splitting expenses across categories is future work. Treat genuinely ambiguous receipts as uncategorized instead of assigning a convenient training label.

**Category prediction is not trained or enabled yet.** The supervised text baseline and validation pipeline are implemented; real verified labels are the missing input. No category is inferred from dataset identity, price, date or merchant keywords alone. The classifier learns merchant/item word frequencies from reviewed examples. Its scores are uncalibrated and support abstention.

## What the local datasets actually label

| Target | CORD v1 | SROIE |
|---|---|---|
| Merchant | Not annotated | Company entity |
| Receipt date | Not annotated | Date entity; ambiguous values excluded |
| Receipt total | Total price | Total entity |
| Tax | Some subtotal tax annotations | Not annotated |
| Item name / quantity / line total | Main menu annotations | Not annotated |
| Unit price | Explicit `menu.unitprice` on some entries | Not annotated |
| Currency | Not annotated | Not annotated |
| Food/travel/etc. category | Not annotated | Not annotated |

CORD's `valid_line.category` describes receipt fields such as `menu.nm`; it is not an expense category. Do not teach missing unit price as zero or derive a training label by dividing total by quantity. Modifiers, discounts and nested CORD fields are retained in raw annotations for a later adapter; they are not silently flattened into main items.

Prepared data preserves the original deduplicated 1,286 train / 225 validation / 461 test split and source record IDs. Original five-field manifests and baseline parser were not changed. The test split was mechanically adapted only; no test inference, scoring or model selection was performed.

Current training coverage in `data/details/audit.json`:

- 798 CORD receipts with item annotations, containing 2,106 main item entries.
- 2,093 labeled item names, 1,881 quantities, 483 explicit usable unit prices and 1,984 usable line totals.
- Unavailable/ambiguous fields have separate states. Category labels: **0**.

Rebuild the additional artifacts with:

```powershell
uv run python -m ai_expense_scanner.ml.prepare_details
```

This writes `data/details/{train,validation,test}.jsonl`, separate category-label templates and an audit with hashes of the source manifests. Keep human-edited label files in a separate directory before rebuilding templates. These enriched manifests are preparation artifacts; the existing five-field CNN training command does not yet consume item targets.

## Training and evaluation sequence

1. **Collect verified category examples.** In the app, correct merchant/date/items, choose a category and approve. Settings → Download category examples exports only the signed-in user's currently approved, categorized receipts. Nothing is automatically added to training. Export omits receipt images, notes, email and monetary amounts; it includes receipt IDs, content hashes, revision, merchant, item names, date and category. Store each user's export separately and do not pool users' data by default.
2. **Prepare a category pilot.** Minimum mechanical gate: 20 distinct verified receipts per included category, at least two categories and five merchants per category. This is a pipeline gate, not a claim of statistical adequacy. Aim for 100–200 diverse reviewed receipts per category and representative local receipts before making product-quality claims. Label food vs groceries and travel vs transport consistently. Unlabeled categories cannot be learned.
3. **Run the category baseline.** The trainer ignores unverified examples; refuses test receipts, invalid labels and conflicting identical-text labels; deduplicates image/feature signatures; and holds out entire normalized merchants. Dates and prices are excluded from model features. Review merchant aliases and near duplicates separately. It reports confusion counts, per-category F1, macro F1, coverage and accuracy including abstentions. Training and validation records are recorded; the saved model is fit only on the training portion.

```powershell
uv run python -m ai_expense_scanner.ml.train_categories --labels data/private/alex-category-labels.jsonl --output artifacts/categories/alex-v1
```

For manually labeled template rows, set `category`, `verified: true` and a meaningful `label_source`, and verify merchant/item text. Keep held-out test receipts out of this input. Preserve `report.json` alongside `model.json`. The model is not installed automatically. Future serving must preserve owner scope for models trained on private receipts, show suggestions as editable and retain manual uncategorized fallback.

4. **Improve item extraction on training data.** Score main-item detection/alignment, name match, quantity/unit-price/line-total exact matches using only labeled fields; include missing/spurious rows. Develop against training receipts first, then evaluate the frozen extractor on validation. Record discounts/modifier coverage separately. Do not reuse the five-field 78.6% score as item accuracy.
5. **Resume the custom model research with text recognition.** Build CORD/SROIE word/line crops using annotated geometry; preserve parent receipt splits. Pretrain CNN + Transformer recognition; measure character/word errors and image dependence. Only then extend the decoder schema/vocabulary to item sequences with a length budget, explicit unknown states, held-out free-generation checks and numeric/date validation. The earlier full-receipt model scored 0/457 validation fields and stays out of serving.
6. **Target-domain evaluation and release.** Assemble fully annotated receipts with merchant/date/currency/items/category and a separate untouched holdout. Freeze preprocessing, rules/models and category thresholds before evaluation. Measure date ambiguity/abstentions, merchant accuracy, item metrics, category macro F1/coverage, latency and review corrections. Select release criteria against real data; do not promise a target accuracy before measuring it.

## Run extraction in the application

Install the isolated environment as described in `ocr/README.md`, then set these values in `.env`:

```dotenv
EXTRACTION_PROVIDER=paddleocr
OCR_PYTHON=ocr/.venv/Scripts/python.exe
OCR_RUNNER=ocr/run.py
```

Restart the API and run `uv run python -m ai_expense_scanner.worker` alongside MongoDB and the frontend. New uploads queue for local OCR. The process has a 180-second per-receipt subprocess deadline, private temporary working files, revision/lease guards and manual correction on failure. The current implementation reloads OCR models per receipt, so startup adds latency; a persistent isolated inference service is future optimization. No hosted receipt inference is used.

Use `EXTRACTION_PROVIDER=checkpoint` to return to the original custom-model path. With no installed checkpoint, that mode uses manual review. Provider readiness currently checks executable/runner files, not a worker heartbeat or model-load probe; operational readiness monitoring remains future work.

## Verification on this change

- 38 Python tests passed, including four real-MongoDB integration tests.
- Three frontend tests and TypeScript/Vite production build passed; the existing bundle-size advisory remains.
- Real local OCR extracted merchant `DEMO CAFE`, date `2026-11-02`, tax `36.00`, total `236.00` INR, and Coffee quantity 2 × unit price 100.00 = line total 200.00 from an explicitly fictional receipt.
- A separate temporary database verified upload → queued worker → actual OCR → correction/category selection → approval → item persistence → dashboard totals, plus second-user isolation and private category export. That database was removed after verification.
- An actual category-training invocation with the unlabeled dataset template refused to train, as intended. Classifier unit tests use fictional fixtures only; their scores are not reported as real-world accuracy.
- Existing OCR five-field validation remains 359/457 (78.6%); no new item/category accuracy is claimed. Custom recognition pretraining and learned item extraction remain pending.
