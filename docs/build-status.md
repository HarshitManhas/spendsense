# Initial build status

Updated 2 November 2026. The active architecture is MongoDB/GridFS plus direct Google sign-in, replacing Firebase at the user's request.

Atlas is connected: the API and worker use the empty `spendsense` database on `HarshitData`, as requested. Authenticated database and GridFS checks passed; local receipts/files were preserved without migration. See [Atlas setup and verification](mongodb-atlas-setup.md).

Currency/layout update: native PDF text preserves rupee signs and table columns; new parsing separates seller/buyer, item quantities/prices and tax, and prioritizes invoice dates. The latest two unedited invoice drafts were corrected without approval. Symbol training is complete as an experiment but not enabled. 56 Python tests, three frontend tests and the production build pass. See [evidence and remaining image-OCR limitation](currency-and-layout-fix.md).

Latest extension: local OCR is connected to the app worker; merchant/date/items/quantities/prices can be reviewed and stored. Approved category examples can be exported per user. Enriched dataset labels and a guarded supervised category trainer are implemented, but no real category model is trained. See [details, commands and remaining training work](receipt-details-training-plan.md). Verification: 38 Python tests (including four MongoDB integrations), three frontend tests, production build and a real OCR-to-approval workflow check passed.

## Implemented

- Python package, uv dependency groups/lockfile, environment example, private-data ignores.
- MongoDB persistence, indexes, GridFS files, server-side sessions, Google token verification, explicit local test identities.
- Validated image/PDF upload, subprocess decoding timeout, page previews, review/edit/approve/reject/delete endpoints.
- Atomic/idempotent approval with revision conflicts and per-user queries.
- MongoDB aggregate summaries, separate currency totals, exact merchant/date/category filters, cursor paging, CSV export.
- Responsive React application with genuine data, manual-review fallback, and honest empty/error/loading states.
- Local dataset preparation, ambiguity handling, label masking, deterministic manifests and byte-level deduplication.
- Random-init CNN/Transformer, character vocabulary, training/checkpointing, free-generation evaluation command, extraction worker.
- Unit/model and real-MongoDB integration tests; fictional receipt generator.

## Validation evidence

- Frontend TypeScript check and Vite production build passed.
- Unit/data/model checks passed, including a two-image synthetic overfit test that distinguishes visual input.
- MongoDB integration tests passed for cross-user access, concurrent repeat approval, editing, exact totals, deletion, CSRF/logout, malformed uploads, and shared multi-page PDF storage.
- A two-real-receipt, one-epoch, 64×64 smoke run produced a checkpoint. Teacher-forced loss was 4.5050 for training and 3.3676 for the same tiny-set validation pass. These are pipeline checks, not reported extraction accuracy.
- Free-generation evaluation of one training example from that smoke checkpoint produced invalid output without EOS and no correct labeled fields. This confirms the evaluator works and the smoke checkpoint is unsuitable for extraction; it is not installed in the serving path.
- Browser verification completed upload, manual field entry, save/reopen draft, approval, and dashboard refresh with an explicitly fictional Sample Cafe receipt (INR 349.00). Its MongoDB draft also survived an API/database restart.
- Browser account switching verified that Sam's separate workspace had no Alex receipts, expenses, totals, or chart data.
- CUDA setup and a real eight-receipt overfit check are complete. The corrected objective generated valid JSON for all eight and matched all 18 labeled fields; this measures memorization only. Full-data training completed after early stopping at epoch 16. Its best checkpoint produced valid JSON for 225/225 validation receipts but matched 0/457 labeled field values. It is not suitable for serving. See `training-status.md` and `training-recovery-plan.md`. The separate local OCR baseline matched 359/457 labeled fields (78.6%) on the same validation manifest, with no OCR failures; see `ocr-baseline-results.md`. It is now available as a separate local OCR provider; the custom model remains uninstalled. Untouched-test evaluation has not been performed. No serving checkpoint is installed at `artifacts/best.pt`.
- Google login cannot be live-tested until a real client ID is configured. Local identities do not simulate verified Google authentication.

## Current limitations and next work

1. Finish dataset corruption/near-duplicate/layout audit, provenance/license record, and fully labeled examples for currency.
2. Improve merchant/tax extraction and evaluate real target-domain receipts for the OCR baseline; integrate it as an explicitly separate review-first provider if selected. Pretrain text recognition before another custom CNN + Transformer full-receipt experiment.
3. Add free-generation model selection and target-domain coverage. Checkpoint resume and mixed precision/accumulation are implemented; CPU resume equivalence is tested. Active runs use explicit null-abstention supervision because fully masking unknown JSON values failed free generation.
4. Exercise worker restart/lease-expiry cases with a real full checkpoint; add heartbeat and per-job operational deadlines.
5. Configure Google client ID and production MongoDB access; verify real Google sessions and deployment cookies.
6. Add production rate limits and request streaming limits, abandoned upload/orphan reconciliation, account deletion, backups, and configurable retention.
7. Extend history from the last 100 event summaries to the required full before/after audit policy.
8. Add automated frontend interaction coverage and further responsive/accessibility checks.

The API/worker source is in `src/ai_expense_scanner`; the web app is in `frontend`; current implementation decisions are in `SpendSense_AI_Project_Plan.md`.
