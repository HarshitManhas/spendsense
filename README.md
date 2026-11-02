# SpendSense AI

An AI-assisted receipt-to-expense application combining fine-tuned OCR, document parsing and human-in-the-loop approval.

**[Live application](https://spendsense-ivory.vercel.app)** · React / TypeScript · FastAPI · PaddleOCR · MongoDB Atlas · Vercel

## Application features

- Upload JPG, PNG and PDF receipts; extract merchant, date, currency, tax, total and line items.
- Correct predictions and item prices before approving an expense.
- Google sign-in with separate receipts and expenses for each user.
- Spending summaries, monthly/category charts, filters and CSV export.
- Manual expense categories and separate summaries for each currency.

## AI pipeline and human-in-the-loop review

```text
Receipt → OCR / PDF text extraction → Field and item parsing
        → Human correction → Approval → Stored expense → Analytics
```

Images and scanned PDFs use PaddleOCR detection and recognition. Selectable PDFs use direct text/table extraction. Layout-aware rules preserve multiword descriptions, distinguish column gaps and interpret monetary values.

Predictions remain drafts until the user reviews and approves them. Only approved expenses contribute to analytics. Corrections are stored; they do not automatically retrain the model.

## Fine-tuning and evaluation

- **Model:** fine-tuned `en_PP-OCRv5_mobile_rec`; the `PP-OCRv5_mobile_det` detector remains unchanged.
- **Data:** CORD/SROIE annotations supplied **40,268 training text crops**, supplemented by **4,000 synthetic currency/amount lines** covering ₹, $, €, £ and ¥.
- **Training:** 3 epochs, batch size 8, Adam with cosine learning-rate decay, initial learning rate `2e-5`; best checkpoint selected on validation data.
- **Evaluation:** identical detector, inputs and frozen field parser for baseline versus fine-tuned comparisons. Exact image duplicates were excluded across train/validation/test splits.

| Labeled-field accuracy | Pretrained | Fine-tuned |
|---|---:|---:|
| Validation: 225 receipts, 457 fields | 78.56% | 81.18% |
| Test: 461 records, 962 fields | 70.06% | **74.32%** |
| Deduplicated test: 458 images, 953 fields | 70.20% | **74.50%** |

The full test gained **41 correct fields**: 54 improvements and 13 regressions. These results do not measure item, real-receipt currency or category accuracy. Public pretraining overlap is unknown, so human review remains necessary.

## Architecture and deployment

| Component | Implementation |
|---|---|
| Frontend | React + TypeScript + Vite, deployed on Vercel |
| API | FastAPI on Vercel Python Functions |
| OCR worker | Docker-based Vercel Daemon with an isolated PaddleOCR environment |
| Storage | MongoDB Atlas for users, sessions and expenses; GridFS for receipts and private model exports |
| Authentication | Google ID-token verification, nonce/CSRF checks, HttpOnly sessions and owner-scoped queries |

The API queues extraction work in MongoDB. The worker uses job leases and heartbeat-based discovery, verifies model hashes at startup, and saves predictions for review. Frontend and API share one domain. Deployed uploads support **4 MB files and up to 5 PDF pages**.

Validation includes **70 Python tests, 6 frontend tests**, a production frontend build and an end-to-end Linux OCR check under a **2 GB memory limit**. Vercel Services/Daemons are beta features.

The custom CNN + Transformer remains a research experiment and is not deployed. Expense categorization is currently manual. Datasets, weights, credentials and private receipts are excluded from Git.
