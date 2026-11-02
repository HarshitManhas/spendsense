# Recovery plan after the first full training run

Update, 2 November 2026: local OCR is now an explicit application provider with experimental item candidates. The failed custom checkpoint remains uninstalled. Item labels and the category-training path are prepared; recognition pretraining, learned item extraction and real category training remain pending. See [current detailed plan](receipt-details-training-plan.md). The entries below describe the earlier experiment and recovery rationale.

Update, 1 November 2026: the local OCR baseline is implemented and evaluated. It matched **359/457 labeled values (78.6%)** on all 225 validation receipts, compared with 0/457 for the custom model. See [results and limitations](ocr-baseline-results.md). The application still uses its existing manual-review fallback; no extraction provider was replaced automatically.

## Diagnosis from saved predictions

The 225 validation receipts produced only four distinct complete outputs, with counts 99, 99, 14, and 13. One common output repeats total `10000`; another repeats the same merchant, date, and total across unrelated receipts. All outputs are valid JSON, but none of the 457 annotated field values match. The eight-receipt overfit success established memorization, not generalization.

This is output collapse into a few common answers. The exact cause is not established. Likely contributors to test are weak text recognition from random initialization, loss of character detail after resizing entire receipts to 512×256, and an objective dominated by predictable JSON and dataset-specific null placeholders. More epochs with the same configuration are not the next experiment: held-out loss already worsened after epoch 6.

## Recommended next experiment: establish an OCR baseline

1. Run a pretrained local text detector/recognizer on validation receipts. PaddleOCR is a candidate; use its official documentation and a separate environment if its dependencies conflict with the existing PyTorch installation. Do not send receipt images to external inference services.
2. Preserve recognized text, boxes, and confidence. Extract merchant, date, total, and tax using nearby labels and layout; retain raw text and uncertain candidates for review. Do not guess ambiguous dates or currency.
3. Score the exact same 225 validation receipts using the existing normalization and labeled-field denominators. Report per-source exact field accuracy, coverage/abstention, latency, and representative failures. Valid JSON alone is insufficient.
4. Keep this explicitly labeled as an OCR baseline. It is not the requested custom CNN + Transformer model. Install no new serving checkpoint until its measured behavior has been reviewed.

Official OCR reference: https://www.paddleocr.ai/latest/en/quick_start.html

## Continue the requested CNN + Transformer research

1. Audit the local annotation schemas and use available text boxes/transcriptions to create readable text-line crops from training data only. Confirm image/box alignment visually before training.
2. Pretrain the CNN + Transformer on text recognition using those crops and synthetic text. Include varied fonts, amounts, dates, blur, and rotation. Preserve held-out groups; never generate training targets from validation/test annotations.
3. Benchmark text recognition on held-out crops before returning to full receipts. Compare resolution or tiling approaches within the RTX 2050 memory budget instead of simply enlarging every image without measurement.
4. Revisit field supervision. Null-abstention solved serialization but may reinforce source-specific blank fields. Evaluate a field-conditioned objective that trains only known fields, with explicit unsupported-field handling. Keep the existing experiment as a reproducible baseline.
5. Evaluate free-running predictions during training, including distinct-output counts, known-field accuracy, and original-versus-blank/shuffled-image comparisons. Select checkpoints using extraction metrics as well as loss. Test visual dependence on multiple receipts within each dataset, not just dataset appearance.
6. Start another full run only after held-out recognition/extraction improves over the collapsed baseline. Do not promise an accuracy level before measurement.

## Product workflow

The existing upload, human review, approval, MongoDB persistence, and analytics workflow remains usable with manual entry. Keep the failed model out of the serving path. The original 461-receipt test split stays untouched until model selection is complete. Fully annotated target-domain receipts, especially currency labels, are still needed for a realistic final assessment.

The OCR baseline portion is now complete in an isolated environment. The custom CNN + Transformer pretraining work remains planned. No serving-model replacement has been performed.
