# Local OCR baseline results — 1 November 2026

The pretrained PaddleOCR + receipt-rule baseline matched **359 of 457 labeled field values (78.6%)** across the same **225 validation receipts** on which the custom CNN + Transformer matched 0/457. This is an offline baseline; it has not been enabled in the application.

| Dataset / field | Correct / labeled | Exact accuracy | Values provided |
|---|---:|---:|---:|
| CORD total | 86 / 95 | 90.5% | 86 / 95 |
| CORD tax | 26 / 43 | 60.5% | 28 / 43 |
| SROIE merchant | 84 / 125 | 67.2% | 121 / 125 |
| SROIE total | 90 / 118 | 76.3% | 97 / 118 |
| SROIE date | 73 / 76 | 96.1% | 74 / 76 |
| **All labeled fields** | **359 / 457** | **78.6%** | **406 / 457** |

Blank predictions count as incorrect in the accuracy denominator. Of the 98 unmatched fields, 51 were left blank and 47 had an incorrect value. All known fields matched on 138 receipts; that is not five-field receipt accuracy because these datasets have incomplete annotations. Currency has no labeled examples and was not scored.

## Method and verification

- Local CPU inference: PaddleOCR 3.7.0, PaddlePaddle 3.2.0, `PP-OCRv5_mobile_det` + `en_PP-OCRv5_mobile_rec`, four CPU threads. Separate `ocr/.venv`; the main CUDA PyTorch environment remains unchanged.
- Original images exported without reference labels. Detection longest side capped at 1280 pixels; recognition uses detected text crops. Document orientation/unwarping disabled for this upright-dataset baseline.
- Fields derived from recognized text and geometry. The parser handles page tilt, explicit total/tax labels, grouping separators, rounded final totals, unambiguous dates, and company headers. Supporting text, boxes, OCR scores, candidate values, and warnings are retained. OCR scores are not calibrated field-confidence estimates.
- Rules developed with synthetic fixtures and eight prepared training receipts, then frozen before the full OCR validation run. The training-only diagnostic matched 16/18 labeled values; it is not included in the validation score above.
- Verified the previous custom-model evaluation and this run have identical reference-manifest hashes, sample counts, and every field denominator. Prepared training and validation IDs have no overlap. The 461-receipt test split remains untouched.
- **225/225 OCR calls completed, zero inference failures.** Median per-image OCR time was **2.23 seconds**, 95th percentile **3.70 seconds**, and cumulative image processing **489 seconds**. Model initialization, field evaluation, and earlier setup are outside those per-image times. The complete benchmark wrapper ran for about 8 minutes 18 seconds.
- **22 non-integration tests passed**, including layout/tilt, totals vs subtotals, rounding, tax IDs, ambiguity, failed-OCR denominators, reference-hash validation, and existing model/data tests. Three MongoDB integration tests were deselected; this work did not change persistence or authentication.

Manifest SHA-256: `d1c760bc32c1a7b32193c73d49585090cd0746b2a993f8303825b942a5d88e93`.

Frozen parser SHA-256: `dd2ef158aecb5bee03e7f845c00380fb6d734eef7762e999ae348c3cf0251751`.

## Remaining errors and next work

Merchant selection is the largest source of wrong values: some company names span several OCR rows, while another header is selected or only the legal suffix is retained. Tax and total abstentions often lack a matching candidate under the current label/layout rules. One date had a recognized year of 2016 instead of the annotated 2018. The training diagnostic also exposed a rounded amount whose final label was misread. These require stronger recognition/field selection, not more training of the collapsed custom decoder.

Human review remains necessary. External OCR pretraining overlap with CORD/SROIE is unknown, so the comparison does not certify accuracy on unseen customer receipts. Further rule/model changes should be developed on training examples and checked on a newly annotated target-domain holdout; preserve this baseline and the untouched test split. The custom CNN + Transformer remains a separate research path requiring text-recognition pretraining.

## Reproduction and evidence

See [OCR setup and commands](../ocr/README.md). Generated artifacts are ignored by Git:

- `artifacts/ocr/validation-baseline/evaluation.json`: full metrics and runtime/artifact hashes.
- `artifacts/ocr/validation-baseline/predictions.jsonl`: per-receipt fields, references, matches, and evidence.
- `artifacts/ocr/validation-baseline/raw/`: recognized text, polygons, scores, and timings.
- `artifacts/ocr/validation-baseline/model-files.json`: actual model-weight/configuration hashes.
- `artifacts/ocr/validation-baseline/pipeline.json`: completed run state and frozen rule hash.

Official API/model reference: [PaddleOCR pipeline documentation](https://www.paddleocr.ai/latest/en/version3.x/pipeline_usage/OCR.html).
