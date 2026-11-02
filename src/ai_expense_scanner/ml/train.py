import argparse
from dataclasses import asdict
import hashlib
import json
from pathlib import Path
import random
import os
import time
import traceback

import numpy as np
from PIL import Image, ImageOps
import torch
from torch.utils.data import DataLoader, Dataset
from datasets import load_from_disk

from .data import serialize_target
from .model import ExpenseModel, ModelConfig
from .vocabulary import Vocabulary


def preprocess(image, config):
    image = ImageOps.exif_transpose(image).convert("RGB")
    image = ImageOps.pad(image, (config.width, config.height), method=Image.Resampling.LANCZOS, color="white")
    return torch.from_numpy(np.asarray(image).copy()).permute(2, 0, 1).float().div(127.5).sub(1)


class ReceiptDataset(Dataset):
    def __init__(self, manifest, root, vocab, config, limit=None, supervise_unknowns=False):
        self.records = [json.loads(line) for line in Path(manifest).read_text(encoding="utf-8").splitlines() if line]
        if limit:
            # The manifest is ordered by source. Round-robin sampling covers both
            # datasets in the overfit experiment without touching held-out data.
            groups = {}
            for record in self.records:
                groups.setdefault(record['source'], []).append(record)
            self.records = [group[i] for i in range(max(map(len, groups.values())))
                            for group in groups.values() if i < len(group)][:limit]
        self.cache = {} if limit else None
        self.sources = {name: load_from_disk(str(Path(root) / name)) for name in {r["source"] for r in self.records}}
        self.vocab, self.config = vocab, config
        self.supervise_unknowns = supervise_unknowns
        for record in self.records:
            text, _ = serialize_target(record["targets"], record["label_states"])
            if len(text) + 1 > config.max_length:
                raise ValueError(f"Target exceeds max length: {record['id']}; increase --max-length")

    def __len__(self):
        return len(self.records)

    def __getitem__(self, index):
        if self.cache is not None and index in self.cache:
            return self.cache[index]
        record = self.records[index]
        image = self.sources[record["source"]][record["split"]][record["index"]]["image"]
        text, mask = serialize_target(record["targets"], record["label_states"])
        ids = self.vocab.encode(text)
        # Optional complete-JSON objective: null means "no annotated answer".
        # It is an abstention target, never a zero tax or proof of absence.
        if self.supervise_unknowns:
            mask = [True] * len(mask)
        labels = [value if valid else -100 for value, valid in zip(ids, mask)] + [self.vocab.EOS]
        result = preprocess(image, self.config), torch.tensor([self.vocab.BOS] + ids), torch.tensor(labels)
        if self.cache is not None:
            self.cache[index] = result
        return result


def collate(batch):
    return (torch.stack([x[0] for x in batch]),
            torch.nn.utils.rnn.pad_sequence([x[1] for x in batch], batch_first=True, padding_value=0),
            torch.nn.utils.rnn.pad_sequence([x[2] for x in batch], batch_first=True, padding_value=-100))


def write_json(path, value):
    temporary = path.with_suffix(path.suffix + '.tmp')
    temporary.write_text(json.dumps(value, indent=2), encoding='utf-8')
    temporary.replace(path)


def save_checkpoint(path, value):
    temporary = path.with_suffix('.tmp')
    torch.save(value, temporary)
    temporary.replace(path)


def main():
    p = argparse.ArgumentParser(description="Train from random initialization; no pretrained extraction weights")
    p.add_argument("--data", default="data")
    p.add_argument("--manifests", default="data/manifests")
    p.add_argument("--output", default="artifacts")
    p.add_argument("--epochs", type=int, default=30)
    p.add_argument("--batch-size", type=int, default=2)
    p.add_argument("--limit", type=int, help="Tiny overfit experiment only")
    p.add_argument("--height", type=int, default=224)
    p.add_argument("--width", type=int, default=224)
    p.add_argument("--max-length", type=int, default=512)
    p.add_argument("--seed", type=int, default=42)
    p.add_argument("--learning-rate", type=float, default=3e-4)
    p.add_argument("--dropout", type=float, default=.1)
    p.add_argument("--accumulate", type=int, default=1)
    p.add_argument("--patience", type=int, default=10)
    p.add_argument("--resume", type=Path)
    p.add_argument("--no-amp", action='store_true')
    p.add_argument("--threads", type=int, default=2)
    p.add_argument("--supervise-unknowns", action='store_true',
                   help='Learn JSON null as abstention for unannotated/ambiguous fields; may induce dataset-specific abstention bias')
    p.add_argument("--device", default="cuda" if torch.cuda.is_available() else "cpu")
    args = p.parse_args()
    if min(args.epochs, args.batch_size, args.accumulate, args.patience, args.threads) < 1:
        p.error('Epochs, batch size, accumulation, patience, and threads must be positive')
    if args.limit is not None and args.limit < 1:
        p.error('--limit must be positive')
    torch.set_num_threads(args.threads)
    random.seed(args.seed); np.random.seed(args.seed); torch.manual_seed(args.seed)
    config = ModelConfig(height=args.height, width=args.width, max_length=args.max_length, dropout=args.dropout)
    manifests = Path(args.manifests)
    vocab = Vocabulary(json.loads((manifests / "vocabulary.json").read_text(encoding="utf-8")))
    train = ReceiptDataset(manifests / "train.jsonl", args.data, vocab, config, args.limit, args.supervise_unknowns)
    validation = train if args.limit else ReceiptDataset(manifests / "validation.jsonl", args.data, vocab, config,
                                                        supervise_unknowns=args.supervise_unknowns)
    if not len(train) or not len(validation):
        raise ValueError('Training and validation datasets must both contain receipts')
    model = ExpenseModel(len(vocab), config).to(args.device)
    optimizer = torch.optim.AdamW(model.parameters(), lr=args.learning_rate, weight_decay=1e-4)
    criterion = torch.nn.CrossEntropyLoss(ignore_index=-100)
    output = Path(args.output); output.mkdir(parents=True, exist_ok=True)
    selection = '\n'.join(json.dumps(r, sort_keys=True) for r in train.records) + '\n'
    selection_sha = hashlib.sha256(selection.encode()).hexdigest()
    amp = args.device.startswith('cuda') and not args.no_amp
    scaler = torch.amp.GradScaler('cuda', enabled=amp)
    best, stale, start_epoch = float('inf'), 0, 0
    if args.resume:
        checkpoint = torch.load(args.resume, map_location=args.device, weights_only=True)
        if (checkpoint['config'] != asdict(config) or checkpoint['characters'] != vocab.characters
                or checkpoint.get('selection_sha256') != selection_sha):
            raise ValueError('Resume requires the same model, vocabulary, and training records')
        for key in ('seed', 'batch_size', 'accumulate', 'learning_rate', 'no_amp', 'supervise_unknowns'):
            if checkpoint['arguments'][key] != vars(args)[key]:
                raise ValueError(f'Resume requires the same --{key.replace("_", "-")}')
        model.load_state_dict(checkpoint['state_dict']); optimizer.load_state_dict(checkpoint['optimizer'])
        scaler.load_state_dict(checkpoint['scaler'])
        best, stale, start_epoch = checkpoint['best_validation_loss'], checkpoint['stale'], checkpoint['epoch']
        torch.set_rng_state(checkpoint['rng_state'].cpu())
        if args.device.startswith('cuda') and checkpoint.get('cuda_rng_state') is not None:
            torch.cuda.set_rng_state_all([state.cpu() for state in checkpoint['cuda_rng_state']])
    elif (output / 'latest.pt').exists():
        raise ValueError('This output already contains a run; use --resume or a new --output')
    (output / 'training-selection.jsonl').write_text(selection, encoding='utf-8')
    arguments = {key: str(value) if isinstance(value, Path) else value for key, value in vars(args).items()}
    write_json(output / 'run.json', {'arguments': arguments, 'config': asdict(config), 'torch': str(torch.__version__),
        'device': torch.cuda.get_device_name() if args.device.startswith('cuda') else args.device,
        'train_samples': len(train), 'validation_samples': len(validation), 'amp': amp,
        'validation_is_training_set': bool(args.limit), 'selection_sha256': selection_sha})
    loaders = {stage: DataLoader(dataset, batch_size=args.batch_size, shuffle=stage == 'train',
               collate_fn=collate, pin_memory=args.device.startswith('cuda'))
               for stage, dataset in [('train', train), ('validation', validation)]}
    started = time.time()
    status = {'pid': os.getpid(), 'state': 'running', 'epoch': start_epoch, 'epochs': args.epochs}
    write_json(output / 'status.json', status)
    try:
        for epoch in range(start_epoch, args.epochs):
            epoch_started = time.time()
            losses = {}
            for stage, loader in loaders.items():
                training = stage == 'train'
                model.train(training)
                total, count = 0., 0
                optimizer.zero_grad(set_to_none=True)
                for batch, (images, tokens, labels) in enumerate(loader):
                    images, tokens, labels = [x.to(args.device, non_blocking=True) for x in (images, tokens, labels)]
                    with torch.set_grad_enabled(training), torch.autocast(device_type='cuda' if amp else 'cpu', dtype=torch.float16, enabled=amp):
                        logits = model(images, tokens)
                        loss = criterion(logits.flatten(0, 1), labels.flatten())
                    if not torch.isfinite(loss):
                        raise FloatingPointError(f'Non-finite loss at epoch {epoch + 1}, {stage}, batch {batch + 1}')
                    if training:
                        group_start = (batch // args.accumulate) * args.accumulate
                        group_size = min(args.accumulate, len(loader) - group_start)
                        scaler.scale(loss / group_size).backward()
                        if (batch + 1) % args.accumulate == 0 or batch + 1 == len(loader):
                            scaler.unscale_(optimizer)
                            torch.nn.utils.clip_grad_norm_(model.parameters(), 1.)
                            scaler.step(optimizer); scaler.update(); optimizer.zero_grad(set_to_none=True)
                    valid = int(labels.ne(-100).sum())
                    total += loss.item() * valid; count += valid
                    if batch % 20 == 0 or batch + 1 == len(loader):
                        status.update(epoch=epoch + 1, stage=stage, batch=batch + 1, batches=len(loader),
                            loss=total / max(count, 1), updated_at=time.time(), elapsed_seconds=time.time() - started)
                        write_json(output / 'status.json', status)
                losses[stage] = total / max(count, 1)
            metrics = {'epoch': epoch + 1, **losses, 'seconds': time.time() - epoch_started}
            print(json.dumps(metrics), flush=True)
            with (output / 'metrics.jsonl').open('a', encoding='utf-8') as stream:
                stream.write(json.dumps(metrics) + '\n')
            improved = losses['validation'] < best
            best, stale = (losses['validation'], 0) if improved else (best, stale + 1)
            checkpoint = {'state_dict': model.state_dict(), 'optimizer': optimizer.state_dict(),
                'scaler': scaler.state_dict(), 'config': asdict(config), 'characters': vocab.characters,
                'epoch': epoch + 1, 'validation_loss': losses['validation'], 'best_validation_loss': best,
                'stale': stale, 'seed': args.seed, 'experimental': True, 'arguments': arguments,
                'tiny_overfit_only': bool(args.limit), 'selection_sha256': selection_sha,
                'training_sha256': hashlib.sha256((manifests / 'train.jsonl').read_bytes()).hexdigest(),
                'rng_state': torch.get_rng_state(), 'cuda_rng_state': torch.cuda.get_rng_state_all() if args.device.startswith('cuda') else None}
            save_checkpoint(output / 'latest.pt', checkpoint)
            if improved:
                save_checkpoint(output / 'best.pt', checkpoint)
            if stale >= args.patience:
                break
        status.update(state='completed', best_validation_loss=best, updated_at=time.time())
        write_json(output / 'status.json', status)
    except BaseException as exc:
        status.update(state='failed', error=str(exc), traceback=traceback.format_exc(), updated_at=time.time())
        write_json(output / 'status.json', status)
        raise
    print(f"Checkpoint: {output / 'best.pt'}. Run free-generation evaluation before serving.")


if __name__ == '__main__':
    main()
