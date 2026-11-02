"""Verify restart behavior with genuine optimization and a small model."""
import json
import sys

import pytest

torch = pytest.importorskip('torch')
from ai_expense_scanner.ml import train
from ai_expense_scanner.ml.model import ModelConfig
from ai_expense_scanner.ml.vocabulary import Vocabulary
from ai_expense_scanner.ml.data import adapt, serialize_target
from PIL import Image


def test_explicit_abstention_objective_keeps_unknown_values_null(tmp_path, monkeypatch):
    record = {'id': 'sroie:train:0', 'source': 'sroie', 'split': 'train', 'index': 0,
              **adapt({'entities': {'company': 'Shop', 'total': '1.00'}}, 'sroie')}
    manifest = tmp_path / 'train.jsonl'
    manifest.write_text(json.dumps(record))
    text, _ = serialize_target(record['targets'], record['label_states'])
    vocab = Vocabulary.build([text])
    monkeypatch.setattr(train, 'load_from_disk', lambda _: {'train': [{'image': Image.new('RGB', (16, 16))}]})
    masked = train.ReceiptDataset(manifest, tmp_path, vocab, ModelConfig(height=16, width=16))
    abstaining = train.ReceiptDataset(manifest, tmp_path, vocab, ModelConfig(height=16, width=16), supervise_unknowns=True)
    assert masked[0][2].eq(-100).any()
    assert not abstaining[0][2].eq(-100).any()
    decoded = json.loads(vocab.decode(abstaining[0][2].tolist()))
    assert decoded['tax'] is None and decoded['currency'] is None
    assert decoded['total'] == '1.00'


def test_resume_matches_uninterrupted_training(tmp_path, monkeypatch):
    vocab = Vocabulary.build(['{"total":"1"}'])
    (tmp_path / 'vocabulary.json').write_text(json.dumps(vocab.characters))
    (tmp_path / 'train.jsonl').write_text('{}\n')

    class TinyDataset:
        records = [{'id': 'one'}, {'id': 'two'}, {'id': 'three'}]

        def __init__(self, *args, **kwargs): pass
        def __len__(self): return len(self.records)
        def __getitem__(self, index):
            return torch.full((3, 16, 16), index / 2), torch.tensor([1, 4 + index]), torch.tensor([4 + index, 2])

    monkeypatch.setattr(train, 'ReceiptDataset', TinyDataset)
    monkeypatch.setattr(train, 'ModelConfig', lambda **kwargs: ModelConfig(
        height=16, width=16, dimension=16, heads=2, layers=1, feedforward=32, dropout=.1, max_length=16))

    def run(directory, epochs, resume=False):
        arguments = ['train', '--manifests', str(tmp_path), '--output', str(directory),
                     '--epochs', str(epochs), '--batch-size', '1', '--accumulate', '2', '--device', 'cpu']
        if resume: arguments += ['--resume', str(directory / 'latest.pt')]
        monkeypatch.setattr(sys, 'argv', arguments)
        train.main()
        return torch.load(directory / 'latest.pt', weights_only=True)

    expected = run(tmp_path / 'continuous', 2)
    run(tmp_path / 'resumed', 1)
    actual = run(tmp_path / 'resumed', 2, resume=True)
    assert actual['epoch'] == 2
    for key, parameter in expected['state_dict'].items():
        assert torch.equal(parameter, actual['state_dict'][key]), key
    assert json.loads((tmp_path / 'resumed' / 'status.json').read_text())['state'] == 'completed'
