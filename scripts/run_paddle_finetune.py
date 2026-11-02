"""Baseline -> receipt fine-tuning -> evaluation -> export, without app activation.

Run with .tools/paddle-training/Scripts/python.exe from the project root.
The pinned upstream trainer is in .tools/PaddleOCR (v3.7.0).
"""
import argparse
import copy
import hashlib
import json
import os
from pathlib import Path
import re
import subprocess
import sys
import time

import yaml


def main():
    p = argparse.ArgumentParser()
    p.add_argument('--output', type=Path, default=Path('artifacts/paddle-finetune/run-v1'))
    p.add_argument('--epochs', type=int, default=3)
    p.add_argument('--batch-size', type=int, default=8)
    p.add_argument('--learning-rate', type=float, default=0.00002)
    p.add_argument('--baseline-run', type=Path, help='Reuse a completed matching pretrained evaluation')
    args = p.parse_args()
    root = Path.cwd().resolve(); upstream = root / '.tools/PaddleOCR'
    output = args.output.resolve()
    if output.exists(): p.error('Use a new output directory; existing runs are immutable.')
    output.mkdir(parents=True)
    config = yaml.safe_load((upstream / 'configs/rec/PP-OCRv5/multi_language/en_PP-OCRv5_mobile_rec.yaml').read_text(encoding='utf-8'))
    weight = root / 'artifacts/paddle-finetune/pretrained/en_PP-OCRv5_mobile_rec_pretrained.pdparams'
    expected = 'e25c9536f39791dfbd2f005f7e0fbbc2652d35b79bae999740059d93fec8e950'
    if hashlib.sha256(weight.read_bytes()).hexdigest() != expected: raise ValueError('Pretrained weight hash mismatch')
    dataset = root/'data/paddle-finetune'
    global_config = config['Global']
    global_config.update(use_gpu=True, epoch_num=args.epochs, distributed=False, seed=42, max_text_length=64,
        pretrained_model=weight.with_suffix('').as_posix(), save_model_dir=(output/'checkpoints').as_posix(),
        save_inference_dir=(output/'inference').as_posix(), save_epoch_step=1, eval_batch_epoch=1,
        eval_batch_step=[0, 1000], print_batch_step=10, cal_metric_during_train=False,
        character_dict_path=(upstream/'ppocr/utils/dict/ppocrv5_en_dict.txt').as_posix())
    config['Architecture']['Head']['head_list'][1]['NRTRHead']['max_text_length'] = 64
    config['Optimizer']['lr'].update(learning_rate=args.learning_rate, warmup_epoch=0)
    config['Metric'].update(ignore_space=False, is_filter=False)
    transforms = [
        {'DecodeImage': {'img_mode': 'BGR', 'channel_first': False}},
        {'MultiLabelEncode': {'gtc_encode': 'NRTRLabelEncode'}},
        {'RecResizeImg': {'image_shape': [3,48,320]}},
        {'KeepKeys': {'keep_keys': ['image','label_ctc','label_gtc','length','valid_ratio']}},
    ]
    for section, filename in [('Train','train'),('Eval','validation')]:
        cfg = config[section]
        cfg.pop('sampler', None)
        cfg['dataset'] = {'name':'SimpleDataSet','data_dir':dataset.as_posix(),
            'label_file_list':[(dataset/f'{filename}.txt').as_posix()], 'transforms':copy.deepcopy(transforms)}
        if section == 'Train':
            cfg['dataset']['label_file_list'].append((dataset/'currency/train.txt').as_posix())
            cfg['dataset']['transforms'].insert(1, {'RecAug': {'tia_prob':.1,'crop_prob':0,'reverse_prob':0,
                'noise_prob':.1,'jitter_prob':.1,'blur_prob':.1,'hsv_aug_prob':.1}})
        cfg['loader'] = {'shuffle':section=='Train','drop_last':section=='Train',
            'batch_size_per_card':args.batch_size if section=='Train' else 24,'num_workers':0}
    config_path = output/'config.yml'
    config_path.write_text(yaml.safe_dump(config,sort_keys=False),encoding='utf-8')
    audit = {'upstream_commit':subprocess.check_output(['git','rev-parse','HEAD'],cwd=upstream,text=True).strip(),
             'pretrained_sha256':expected,'dataset':json.loads((dataset/'audit.json').read_text()),
             'currency_data':json.loads((dataset/'currency/audit.json').read_text()),
             'config_sha256':hashlib.sha256(config_path.read_bytes()).hexdigest(),
             'python':sys.executable, 'test_used':False, 'app_model_changed':False}
    (output/'provenance.json').write_text(json.dumps(audit,indent=2),encoding='utf-8')
    state = {'pid':os.getpid(),'started_at':time.time(),'state':'starting'}
    def status(stage, **values):
        state.update(state=stage,updated_at=time.time(),**values)
        tmp=output/'status.json.tmp';tmp.write_text(json.dumps(state,indent=2));tmp.replace(output/'status.json')
    def run(stage, tool, overrides=None, config_file=config_path):
        status(stage)
        cmd=[sys.executable,'-u',str(upstream/tool),'-c',str(config_file)]
        if overrides: cmd+=['-o',*overrides]
        env={**os.environ,'PYTHONIOENCODING':'utf-8','FLAGS_allocator_strategy':'auto_growth','OMP_NUM_THREADS':'4'}
        with (output/f'{stage}.log').open('w',encoding='utf-8') as log:
            subprocess.run(cmd,cwd=upstream,stdout=log,stderr=subprocess.STDOUT,env=env,check=True)
    def metric(stage):
        text=(output/f'{stage}.log').read_text(encoding='utf-8')
        matches=re.findall(r'\bacc:([0-9.]+)',text)
        if not matches: raise ValueError(f'No evaluation metric in {stage}')
        return float(matches[-1])
    try:
        if args.baseline_run:
            previous_config=yaml.safe_load((args.baseline_run/'config.yml').read_text(encoding='utf-8'))
            previous_audit=json.loads((args.baseline_run/'provenance.json').read_text(encoding='utf-8'))
            for section in ['Eval','Architecture','Metric','PostProcess']:
                if previous_config[section]!=config[section]: raise ValueError(f'Baseline {section} differs')
            for key in ['max_text_length','pretrained_model','character_dict_path','use_space_char']:
                if previous_config['Global'][key]!=config['Global'][key]: raise ValueError(f'Baseline {key} differs')
            if previous_audit['dataset']!=audit['dataset'] or previous_audit['pretrained_sha256']!=expected:
                raise ValueError('Baseline data or weights differ')
            (output/'baseline.log').write_bytes((args.baseline_run/'baseline.log').read_bytes())
            audit['baseline_reused_from']=args.baseline_run.resolve().as_posix()
            (output/'provenance.json').write_text(json.dumps(audit,indent=2),encoding='utf-8')
        else:
            run('baseline','tools/eval.py')
        baseline = metric('baseline');status('baseline_complete',baseline_exact_accuracy=baseline)
        run('training','tools/train.py')
        checkpoint=(output/'checkpoints/best_accuracy').as_posix()
        run('finetuned','tools/eval.py',[f'Global.checkpoints={checkpoint}'])
        tuned=metric('finetuned')
        currency_config=copy.deepcopy(config)
        currency_config['Eval']['dataset']['label_file_list']=[(dataset/'currency/validation.txt').as_posix()]
        currency_path=output/'currency-eval.yml';currency_path.write_text(yaml.safe_dump(currency_config),encoding='utf-8')
        run('currency_baseline','tools/eval.py',config_file=currency_path)
        run('currency_finetuned','tools/eval.py',[f'Global.checkpoints={checkpoint}'],config_file=currency_path)
        report={'baseline_real_crop_accuracy':baseline,'finetuned_real_crop_accuracy':tuned,
                'baseline_synthetic_currency_accuracy':metric('currency_baseline'),
                'finetuned_synthetic_currency_accuracy':metric('currency_finetuned'),
                'spaces_and_case_scored':True,'full_receipt_evaluation_pending':True,'installed_in_app':False}
        (output/'comparison.json').write_text(json.dumps(report,indent=2))
        run('export','tools/export_model.py',[f'Global.checkpoints={checkpoint}'])
        status('completed',comparison=report)
        print(json.dumps(report),flush=True)
    except BaseException as exc:
        status('failed',error_type=type(exc).__name__,error=str(exc));raise


if __name__ == '__main__': main()
