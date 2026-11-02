import importlib.util
import json
from pathlib import Path

import pytest


spec = importlib.util.spec_from_file_location('ocr_runner', Path(__file__).parents[1] / 'ocr/run.py')
runner = importlib.util.module_from_spec(spec)
spec.loader.exec_module(runner)


@pytest.mark.parametrize('locked_attempts', [2, 10])
def test_atomic_json_retries_locks_and_preserves_previous_file(tmp_path, monkeypatch, locked_attempts):
    destination = tmp_path / 'status.json'
    destination.write_text('{"old": true}')
    replace = Path.replace
    attempts = []

    def locked_replace(source, target):
        attempts.append(source)
        if len(attempts) <= locked_attempts:
            raise PermissionError('temporarily locked')
        return replace(source, target)

    monkeypatch.setattr(Path, 'replace', locked_replace)
    monkeypatch.setattr(runner.time, 'sleep', lambda _: None)
    if locked_attempts == 10:
        with pytest.raises(PermissionError):
            runner.write_json(destination, {'new': True})
        assert json.loads(destination.read_text()) == {'old': True}
        assert len(attempts) == 10
    else:
        runner.write_json(destination, {'new': True})
        assert json.loads(destination.read_text()) == {'new': True}
        assert len(attempts) == 3
