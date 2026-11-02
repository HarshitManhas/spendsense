# GPU training — 1 November 2026

## Final result

Training and validation evaluation completed at approximately 22:00 IST on 1 November 2026, about 43 minutes after launch. Early stopping ended training after epoch 16; the best checkpoint was epoch 6 (validation loss 0.581344). The best checkpoint generated valid JSON and EOS for all 225 validation receipts, but matched **0 of 457 labeled field values**: CORD total 0/95, CORD tax 0/43, SROIE merchant 0/125, total 0/118, and date 0/76. This is a failed extraction-quality experiment despite valid output formatting. The model is not ready for application use and was not installed for serving. The test set remains untouched. Detailed predictions and artifact hashes are in `artifacts/runs/2026-11-01-full/evaluation.json`.

The launch record and reproduction instructions follow.

Full-data training was launched at 21:17 IST on the local NVIDIA RTX 2050 (4 GiB). Live progress is in `artifacts/runs/2026-11-01-full/status.json`; the training/evaluation wrapper state is in `pipeline.json` beside it. This document records the launch and completed checks, not a claim that the full run has finished.

## Completed checks

- Installed pinned PyTorch 2.11.0+cu128. Verified CUDA availability and an actual GPU matrix multiplication.
- All 15 non-integration tests passed on this build, including model causality, gradient flow, generation termination, exact resumed-vs-uninterrupted CPU optimization, and the explicit abstention policy. The three MongoDB integration tests were deselected for this ML-only change.
- First real eight-receipt experiment: four CORD + four SROIE, 100 epochs, 512×256 images. Masking every unannotated value achieved teacher-forced loss 0.000407 but **0/8 valid generated JSON objects**. The untrained `null` spans broke autoregressive decoding. This failed checkpoint is retained separately for reproducibility.
- Repeated from random initialization with explicit null-abstention supervision. After 100 epochs, teacher-forced loss was 0.000386; free generation produced **8/8 valid JSON objects, 8/8 EOS terminations, and 18/18 correct labeled fields**: CORD total 4/4, CORD tax 3/3, SROIE merchant 4/4, SROIE date 3/3, SROIE total 4/4.
- These eight receipts are training examples. This is a memorization/correctness gate, **not unseen-receipt accuracy**. There are no fully labeled five-field receipts in this check. Null placeholders are excluded from field-accuracy denominators.

Evidence: `artifacts/runs/2026-11-01-overfit/evaluation.json` (failed original objective) and `artifacts/runs/2026-11-01-overfit-abstention/evaluation.json` (passed corrected objective). Both checkpoints remain marked tiny-overfit-only and cannot serve the app.

## Full experiment

| Setting | Value |
|---|---|
| Initialization | Fresh random weights; no transfer from the eight-receipt check |
| Training / validation | 1,286 / 225 receipts |
| Test data | 461 receipts, not evaluated or used for tuning |
| Input | Aspect-preserving, white-padded 512 height × 256 width |
| Model | Four CNN blocks + 256-dimensional, three-layer, four-head Transformer decoder |
| Batch / gradient accumulation | 2 / 2 (effective batch of 4, except the final partial group) |
| Optimizer | AdamW, learning rate 0.0003, weight decay 0.0001, gradient clipping 1.0 |
| Precision | CUDA FP16 autocast with gradient scaling |
| Duration | Up to 30 epochs; early stopping after 10 epochs without lower validation loss |
| Dropout / seed | 0.1 / 42 |
| Checkpoints | `latest.pt` each completed epoch; `best.pt` by validation loss |
| Evaluation | Automatic free generation on all 225 validation receipts after training |

The explicit `--supervise-unknowns` policy learns JSON `null` as abstention for missing/ambiguous annotations. It never invents zero tax, resolves an ambiguous date by guessing, or infers currency from a dataset's country. This policy can teach dataset-specific blank fields; fully annotated target-domain evaluation is still needed. Currency has no labeled examples and requires human entry. Raw datasets and prepared labels were not modified.

## Inspect and resume

From the project directory:

```powershell
powershell -File scripts/training_status.ps1
Get-Content artifacts/runs/2026-11-01-full/metrics.jsonl -Tail 3
Get-Content artifacts/runs/2026-11-01-full/pipeline.json
```

The process runs in the background. Keep the laptop powered and awake. If it stops, first confirm no training process for this run remains, then resume from its last completed epoch:

```powershell
uv run --extra ml python scripts/train_full.py --output artifacts/runs/2026-11-01-full --epochs 30 --resume
```

`stdout.log` and `stderr.log` contain the original background launch's output. The resume command above runs in the terminal. A resume repeats any interrupted epoch; it does not discard completed epochs. `run.json` records configuration and selected-data hash; `metrics.jsonl` records epoch losses and timings. `evaluation.json` appears when validation generation completes.

No checkpoint is automatically installed in the application's serving path. Validation results must be reviewed before enabling AI extraction. The app continues to support manual review meanwhile.
