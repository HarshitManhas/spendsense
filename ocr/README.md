# Local OCR baseline

This directory has its own Python 3.11 environment and lockfile. It uses pretrained PaddleOCR text detection/recognition on the CPU, independently of the custom CNN + Transformer and its CUDA PyTorch environment. It does not call a hosted OCR service. Initial setup downloads public model weights; receipt inference is local.

From the repository root:

```powershell
uv sync --project ocr --python 3.11
.venv\Scripts\python.exe scripts/prepare_ocr_inputs.py --output artifacts/ocr/validation
.venv\Scripts\python.exe scripts/run_ocr_baseline.py
```

The fixed model pair is `PP-OCRv5_mobile_det` plus `en_PP-OCRv5_mobile_rec`, with document orientation/unwarping disabled for the upright dataset baseline. Images are exported at their original resolution; detection is bounded to a longest side of 1280 pixels, while text recognition operates on detected crops. OCR uses four CPU threads. These choices need separate testing for arbitrary rotated user uploads.

The exported requests contain image paths, identifiers, dimensions, and hashes, without labels. Raw OCR JSON retains text, boxes, scores, and latency. The field parser uses explicit labels and spatial rows; it never receives dataset names or expected values. Ambiguous dates, conflicting amounts, and unsupported currency symbols remain unresolved.

Outputs live under ignored `artifacts/ocr/validation-baseline/`:

- `status.json`: image progress and failures.
- `pipeline.json`: OCR/evaluation wrapper state.
- `run.json`: pinned runtime versions, model selection, settings, runner-code hash, and input hash.
- `model-files.json`: SHA-256 hashes of the actual detector/recognizer weights and configurations.
- `raw/`: reusable text/box/score results, one file per receipt.
- `evaluation.json`: exact field accuracy, coverage, errors, and OCR latency.
- `predictions.jsonl`: extracted values, expected values for scoring, supporting text, and warnings.

Resume interrupted inference using the same settings:

```powershell
.venv\Scripts\python.exe scripts/run_ocr_baseline.py --resume
```

Successful cached OCR results are reused only when their IDs and image hashes match. Failed receipts remain in the scoring denominator. The evaluator rejects mismatched manifests/requests and incomplete coverage unless a diagnostic subset is explicitly requested.

For a small training-only diagnostic:

```powershell
.venv\Scripts\python.exe scripts/prepare_ocr_inputs.py --manifest data/manifests/train.jsonl --limit 8 --output artifacts/ocr/training-debug
ocr\.venv\Scripts\python.exe ocr/run.py --requests artifacts/ocr/training-debug/requests.jsonl --output artifacts/ocr/training-debug-run
.venv\Scripts\python.exe -m ai_expense_scanner.ocr_evaluate --inputs artifacts/ocr/training-debug --run artifacts/ocr/training-debug-run --allow-subset
```

The 225-receipt validation manifest and normalization are the same as for the failed custom-model experiment. Some validation IDs begin with `sroie:train`: these refer to the original snapshot and were held out by merchant group in the project's prepared validation split. They are not part of the prepared training manifest. External OCR pretraining overlap with these public datasets is unknown, so this comparison is not a guarantee of accuracy on unseen customer receipts. Currency has no labeled examples here. The 461-receipt test set remains unused. This baseline is not automatically installed into the application.

Official model/API documentation: [PaddleOCR pipeline](https://www.paddleocr.ai/latest/en/version3.x/pipeline_usage/OCR.html).
