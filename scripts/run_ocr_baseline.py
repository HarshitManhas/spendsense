"""Run isolated local OCR, then score fields in the main project environment."""
import argparse
import hashlib
import json
import os
from pathlib import Path
import subprocess
import sys
import time

from ai_expense_scanner import ocr_fields


def main():
    p = argparse.ArgumentParser()
    p.add_argument('--inputs', type=Path, default=Path('artifacts/ocr/validation'))
    p.add_argument('--output', type=Path, default=Path('artifacts/ocr/validation-baseline'))
    p.add_argument('--resume', action='store_true')
    p.add_argument('--no-mkldnn', action='store_true')
    args = p.parse_args()
    args.output.mkdir(parents=True, exist_ok=True)
    rule_path = Path(ocr_fields.__file__)
    rule_hash = hashlib.sha256(rule_path.read_bytes()).hexdigest()
    state = {'pid': os.getpid(), 'state': 'recognizing', 'started_at': time.time(), 'rule_sha256': rule_hash}

    def record(**values):
        state.update(values, updated_at=time.time())
        temporary = args.output / 'pipeline.json.tmp'
        temporary.write_text(json.dumps(state, indent=2), encoding='utf-8')
        temporary.replace(args.output / 'pipeline.json')

    record()
    python = Path('ocr/.venv/Scripts/python.exe' if os.name == 'nt' else 'ocr/.venv/bin/python')
    command = [str(python.resolve()), '-u', 'ocr/run.py', '--requests', str(args.inputs / 'requests.jsonl'), '--output', str(args.output)]
    if args.resume: command.append('--resume')
    if args.no_mkldnn: command.append('--no-mkldnn')
    try:
        subprocess.run(command, check=True)
        if hashlib.sha256(rule_path.read_bytes()).hexdigest() != rule_hash:
            raise ValueError('Field rules changed during this run; preserve the OCR cache and evaluate as a new experiment')
        record(state='evaluating_fields')
        subprocess.run([sys.executable, '-u', '-m', 'ai_expense_scanner.ocr_evaluate',
                        '--inputs', str(args.inputs), '--run', str(args.output)], check=True)
        record(state='completed')
    except BaseException as exc:
        record(state='failed', error=str(exc))
        raise


if __name__ == '__main__': main()
