"""Free-running extraction evaluation; known fields only, no invented labels."""
import argparse
from collections import Counter
import hashlib
import json
from pathlib import Path

import torch

from .model import ExpenseModel, ModelConfig
from .train import ReceiptDataset
from .vocabulary import Vocabulary
from .parsing import parse_prediction
from .metrics import equivalent


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--checkpoint', type=Path, default=Path('artifacts/best.pt'))
    parser.add_argument('--manifest', type=Path, default=Path('data/manifests/validation.jsonl'))
    parser.add_argument('--data', default='data')
    parser.add_argument('--output', type=Path, default=Path('artifacts/evaluation.json'))
    parser.add_argument('--limit', type=int)
    parser.add_argument('--device', default='cuda' if torch.cuda.is_available() else 'cpu')
    parser.add_argument('--threads', type=int, default=2)
    args = parser.parse_args()
    torch.set_num_threads(args.threads)
    checkpoint = torch.load(args.checkpoint, map_location='cpu', weights_only=True)
    config = ModelConfig(**checkpoint['config']); vocab = Vocabulary(checkpoint['characters'])
    model = ExpenseModel(len(vocab), config); model.load_state_dict(checkpoint['state_dict']); model.to(args.device).eval()
    dataset = ReceiptDataset(args.manifest, args.data, vocab, config, args.limit)
    correct, denominators = Counter(), Counter()
    parse_valid, eos, full_count, full_correct = 0, 0, 0, 0
    predictions = []
    for index, record in enumerate(dataset.records):
        image, _, _ = dataset[index]
        ids = model.generate(image.unsqueeze(0).to(args.device))[0].tolist()
        decoded = vocab.decode(ids)
        eos += vocab.EOS in ids
        try:
            prediction = parse_prediction(decoded).model_dump()
            parse_valid += 1
        except (ValueError, TypeError): prediction = {}
        receipt_correct, labeled = True, 0
        for key, state in record['label_states'].items():
            if state not in {'labeled', 'verified_absent'}: continue
            field = f"{record['source']}.{key}"; denominators[field] += 1; labeled += 1
            matched = equivalent(key, record['targets'][key], prediction.get(key)) and bool(prediction)
            correct[field] += matched; receipt_correct &= matched
        if labeled == 5:
            full_count += 1; full_correct += receipt_correct
        predictions.append({'id': record['id'], 'generated': decoded, 'expected': record['targets'],
                            'label_states': record['label_states'], 'known_fields_correct': bool(receipt_correct)})
        print(json.dumps({'evaluated': index + 1, 'samples': len(dataset), 'valid_schema': parse_valid}), flush=True)
    report = {'samples': len(dataset), 'valid_schema': parse_valid, 'terminated_with_eos': eos,
        'fields': {key: {'correct': correct[key], 'labeled': total, 'accuracy': correct[key] / total} for key, total in denominators.items()},
        'full_receipt': {'correct': full_correct, 'fully_labeled': full_count},
        'checkpoint_sha256': hashlib.sha256(args.checkpoint.read_bytes()).hexdigest(),
        'manifest_sha256': hashlib.sha256(args.manifest.read_bytes()).hexdigest(),
        'tiny_overfit_only': checkpoint.get('tiny_overfit_only', False), 'limited_run': bool(args.limit),
        'device': args.device, 'predictions': predictions}
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(report, indent=2), encoding='utf-8')
    print(json.dumps(report, indent=2))


if __name__ == '__main__': main()
