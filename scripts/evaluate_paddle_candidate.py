"""Evaluate an exported recognizer on complete receipts; never activate it automatically."""
import argparse
import hashlib
import json
import os
from pathlib import Path
import subprocess
import sys
import time


def main():
    p=argparse.ArgumentParser()
    p.add_argument('--training-run',type=Path,default=Path('artifacts/paddle-finetune/run-v1'))
    p.add_argument('--output',type=Path,default=Path('artifacts/ocr/validation-finetuned-v1'))
    p.add_argument('--wait',action='store_true',help='Wait up to 12 hours for the training/export pipeline')
    args=p.parse_args()
    root=Path.cwd().resolve();run=args.training_run.resolve();output=args.output.resolve()
    if output.exists(): p.error('Use a new receipt evaluation output directory.')
    status_path=run/'receipt-status.json'
    state={'pid':os.getpid(),'started_at':time.time(),'app_model_changed':False}
    def update(stage,**values):
        state.update(state=stage,updated_at=time.time(),**values)
        temp=status_path.with_suffix('.json.tmp');temp.write_text(json.dumps(state,indent=2));temp.replace(status_path)
    try:
        deadline=time.monotonic()+(43200 if args.wait else 0)
        while True:
            training=json.loads((run/'status.json').read_text())
            if training['state']=='completed': break
            if training['state']=='failed': raise RuntimeError('Training failed; inspect its status/logs before evaluation')
            if time.monotonic()>=deadline: raise TimeoutError('Training/export has not completed')
            update('waiting_for_training',training_stage=training['state'])
            time.sleep(20)
        parser=root/'src/ai_expense_scanner/ocr_fields.py'
        frozen_hash='dd2ef158aecb5bee03e7f845c00380fb6d734eef7762e999ae348c3cf0251751'
        if hashlib.sha256(parser.read_bytes()).hexdigest()!=frozen_hash: raise ValueError('Frozen field parser changed')
        env={**os.environ,'PYTHONIOENCODING':'utf-8'}
        update('recognizing_receipts')
        with (run/'receipt-inference.log').open('w',encoding='utf-8') as log:
            subprocess.run([str(root/'ocr/.venv/Scripts/python.exe'),'-u','ocr/run.py','--requests',
                'artifacts/ocr/validation/requests.jsonl','--output',str(output),
                '--recognition-model-dir',str(run/'inference')],cwd=root,env=env,stdout=log,stderr=subprocess.STDOUT,check=True)
        update('scoring_fields')
        with (run/'receipt-evaluation.log').open('w',encoding='utf-8') as log:
            subprocess.run([sys.executable,'-m','ai_expense_scanner.ocr_evaluate','--inputs','artifacts/ocr/validation',
                '--run',str(output)],cwd=root,env=env,stdout=log,stderr=subprocess.STDOUT,check=True)
        before=json.loads((root/'artifacts/ocr/validation-baseline/evaluation.json').read_text())
        after=json.loads((output/'evaluation.json').read_text())
        for key in ['manifest_sha256','samples','rule_sha256']:
            if before[key]!=after[key]: raise ValueError(f'Comparison mismatch: {key}')
        before_fields=before['fields'];after_fields=after['fields']
        if set(before_fields)!=set(after_fields): raise ValueError('Field sets differ')
        if any(before_fields[k]['labeled']!=after_fields[k]['labeled'] for k in before_fields):
            raise ValueError('Field denominators differ')
        comparison={'baseline':before['overall_labeled_fields'],'finetuned':after['overall_labeled_fields'],
            'fields':{k:{'baseline':before_fields[k]['correct'],'finetuned':after_fields[k]['correct'],
                         'labeled':before_fields[k]['labeled']} for k in before_fields},
            'ocr_errors':after['ocr_errors'],'app_model_changed':False,'test_used':False,
            'currency_real_receipt_accuracy':'not measured: missing labels',
            'improved_overall':after['overall_labeled_fields']['correct']>before['overall_labeled_fields']['correct']}
        (run/'receipt-comparison.json').write_text(json.dumps(comparison,indent=2))
        update('completed',comparison=comparison)
        print(json.dumps(comparison),flush=True)
    except BaseException as exc:
        update('failed',error_type=type(exc).__name__,error=str(exc));raise


if __name__=='__main__': main()
