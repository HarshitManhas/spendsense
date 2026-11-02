"""Run full training and then evaluate its best checkpoint on validation only."""
import argparse
import json
import os
from pathlib import Path
import subprocess
import sys
import time


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--epochs', type=int, default=30)
    parser.add_argument('--resume', action='store_true')
    args = parser.parse_args()
    args.output.mkdir(parents=True, exist_ok=True)
    state = {'pid': os.getpid(), 'state': 'training', 'started_at': time.time()}

    def record():
        state['updated_at'] = time.time()
        temporary = args.output / 'pipeline.json.tmp'
        temporary.write_text(json.dumps(state, indent=2), encoding='utf-8')
        temporary.replace(args.output / 'pipeline.json')

    record()
    command = [sys.executable, '-u', '-m', 'ai_expense_scanner.ml.train',
               '--output', str(args.output), '--epochs', str(args.epochs),
               '--height', '512', '--width', '256', '--batch-size', '2', '--accumulate', '2',
               '--device', 'cuda', '--supervise-unknowns']
    if args.resume:
        command += ['--resume', str(args.output / 'latest.pt')]
    try:
        subprocess.run(command, check=True)
        state['state'] = 'evaluating_validation'; record()
        subprocess.run([sys.executable, '-u', '-m', 'ai_expense_scanner.ml.evaluate',
                        '--checkpoint', str(args.output / 'best.pt'),
                        '--manifest', 'data/manifests/validation.jsonl', '--device', 'cuda',
                        '--output', str(args.output / 'evaluation.json')], check=True)
        state['state'] = 'completed'; record()
    except BaseException as exc:
        state.update(state='failed', error=str(exc)); record()
        raise


if __name__ == '__main__':
    main()
