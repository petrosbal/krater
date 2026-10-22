import json
import os
from pathlib import Path

import pytest

import results
from config import RUN_KEYS

def test_every_run_key_is_placed():
    assert RUN_KEYS - set(results.SETTINGS) == {"name", "params", "runtimes", "trials", "namespace"}

@pytest.mark.parametrize("combination, expected", [
    ({},                         ''),
    ({'size': 256},              'size = 256'),
    ({'size': 256, 'mode': 'a'}, 'mode = a, size = 256')
])
def test_trial_key(combination, expected):
    assert results.trial_key(combination) == expected

@pytest.mark.parametrize("name, environment, expected", [
    ('benchmark_1', 
     {'image': 'krater:matmul_wasm', 'runtime_class': 'wasmtime'},
     Path('results/benchmark_1/krater_matmul_wasm_wasmtime.json')),
    ('b', 
     {'image': 'reg/krater:x', 'runtime_class': 'default'},
     Path('results/b/reg_krater_x_default.json')),
])
def test_results_path(name, environment, expected):
    assert results.results_path(name, environment) == expected

RESULTS_HEADER_RUN = {
    'duration': 59,
    'warmup': 9,
    'cpu': '999m',
    'memory': '1023Mi',
    'interval': 0.2,
    'trials': 30,
    'timeout': 119,
    'namespace': 'default',
}

RESULTS_HEADER_ENVIRONMENT = {
    'target': 'wasm',
    'image': 'krater:matmul_wasm',
    'runtime_class': 'wasmtime',
}

def test_results_header():
    assert results.results_header(RESULTS_HEADER_RUN, RESULTS_HEADER_ENVIRONMENT) == {
        'environment': {
            'target': 'wasm',
            'image': 'krater:matmul_wasm',
            'runtime_class': 'wasmtime',
        },
        'settings': {
            'duration': 59,
            'warmup': 9,
            'timeout': 119,
            'cpu': '999m',
            'memory': '1023Mi',
            'interval': 0.2,
        },
    }

def test_file_for_without_a_file(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    file, problem = results.file_for({**RESULTS_HEADER_RUN, 'name': 'b'}, RESULTS_HEADER_ENVIRONMENT)
    expected = {**results.results_header(RESULTS_HEADER_RUN, RESULTS_HEADER_ENVIRONMENT),
                'trials': {}}

    assert file == expected
    assert problem == None

def test_file_for_reopens_a_saved_file(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    saved = {**results.results_header(RESULTS_HEADER_RUN, RESULTS_HEADER_ENVIRONMENT),
             'trials': {'size = 64': [{'trial': 1}]}}
    results.save_results(results.results_path('b', RESULTS_HEADER_ENVIRONMENT), saved)
    file, problem = results.file_for({**RESULTS_HEADER_RUN, 'name': 'b'}, RESULTS_HEADER_ENVIRONMENT)

    assert file == saved
    assert problem == None

def test_file_for_refuses_a_changed_setting(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    saved = {**results.results_header(RESULTS_HEADER_RUN, RESULTS_HEADER_ENVIRONMENT),
             'trials': {}}
    results.save_results(results.results_path('b', RESULTS_HEADER_ENVIRONMENT), saved)
    file, problem = results.file_for({**RESULTS_HEADER_RUN, 'name': 'b', 'cpu': '500m'},
                                     RESULTS_HEADER_ENVIRONMENT)

    assert file == None
    assert problem == ("existing results file (results/b/krater_matmul_wasm_wasmtime.json) does not match this run:\n"
                       "settings:\n"
                       "  file has [('cpu', '999m')]\n"
                       "  config has [('cpu', '500m')]\n"
                       "set the config back, use a new run name, or move the file")

def test_keep_entry_saves_a_done_entry(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    run = {**RESULTS_HEADER_RUN, 'name': 'b'}
    file, _ = results.file_for(run, RESULTS_HEADER_ENVIRONMENT)
    assert file is not None
    entry = {'trial': 1, 'failure_reason': 'OOMKilled'}
    done = results.keep_entry(run, file, {'size': 64}, entry)

    assert done is True
    assert file['trials'] == {'size = 64': [entry]}
    assert results.file_for(run, RESULTS_HEADER_ENVIRONMENT) == (file, None)

def test_keep_entry_drops_an_entry_that_is_not_done(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    run = {**RESULTS_HEADER_RUN, 'name': 'b'}
    file, _ = results.file_for(run, RESULTS_HEADER_ENVIRONMENT)
    assert file is not None
    done = results.keep_entry(run, file, {'size': 64}, {'trial': 1, 'failure_reason': 'Completed'})

    assert done is False
    assert file['trials'] == {}
    assert not results.results_path('b', RESULTS_HEADER_ENVIRONMENT).exists()

# keep_entry saves before it touches file, so a failed save can't leave
# an entry in memory that the disk doesn't have
def test_keep_entry_failed_save_leaves_file_unchanged(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    run = {**RESULTS_HEADER_RUN, 'name': 'b'}
    file, problem = results.file_for(run, RESULTS_HEADER_ENVIRONMENT)
    assert file is not None

    def failing_save(path, results):
        raise OSError("disk full")
    monkeypatch.setattr(results, 'save_results', failing_save)

    with pytest.raises(OSError):
        results.keep_entry(run, file, {'size': 64}, {'trial': 1, 'failure_reason': 'OOMKilled'})
    assert file['trials'] == {}

HEADER = {
    'environment': {'target': 'wasm'},
    'settings': {'cpu': '1000m', 'duration': 2},
}

HEADER_MISMATCH_ROWS = {
    "matching file": (
        {'environment': {'target': 'wasm'},
         'settings': {'cpu': '1000m', 'duration': 2},
         'trials': {}},
        None,
    ),
    "2.0 equals 2": (
        {'environment': {'target': 'wasm'},
         'settings': {'cpu': '1000m', 'duration': 2.0},
         'trials': {}},
        None,
    ),
    "changed value": (
        {'environment': {'target': 'wasm'},
         'settings': {'cpu': '500m', 'duration': 2},
         'trials': {}},
        ("settings:\n"
         "  file has [('cpu', '500m')]\n"
         "  config has [('cpu', '1000m')]"),
    ),
    "field only in file": (
        {'environment': {'target': 'wasm'},
         'settings': {'cpu': '1000m', 'duration': 2, 'governor': 'x'},
         'trials': {}},
        ("settings:\n"
         "  file has [('governor', 'x')]\n"
         "  config has []"),
    ),
    "field only in config": (
        {'environment': {'target': 'wasm'},
         'settings': {'cpu': '1000m'},
         'trials': {}},
        ("settings:\n"
         "  file has []\n"
         "  config has [('duration', 2)]"),
    ),
    "file not a dict": (
        [1],
        "expected stored file to be a dict, got list",
    ),
    "section not a dict": (
        {'environment': None},
        "stored section 'environment' is not a dict",
    ),
    "value a list": (
        {'environment': {'target': ['wasm']}},
        "value of key 'target' in section 'environment' (['wasm']) is not a number or string",
    ),
    "value a bool": (
        {'environment': {'target': 'wasm'},
         'settings': {'cpu': '1000m', 'duration': True},
         'trials': {}},
        "value of key 'duration' in section 'settings' (True) is not a number or string",
    ),
    "no trials": (
        {'environment': {'target': 'wasm'},
         'settings': {'cpu': '1000m', 'duration': 2}},
        "expected 'trials' section in stored file to be a dict, got NoneType",
    ),
    "old file without header": (
        {'size = 256': []},
        ("environment:\n"
         "  file has []\n"
         "  config has [('target', 'wasm')]"),
    ),
}

@pytest.mark.parametrize("stored, expected",
    HEADER_MISMATCH_ROWS.values(), ids=HEADER_MISMATCH_ROWS.keys(),
)
def test_header_mismatch(stored, expected):
    assert results.header_mismatch(stored, HEADER) == expected

TRIAL_IS_DONE_ROWS = {
    "invalid result is done": (
        {'result': {'valid': False}, 'times': {'bench_start': 103.0, 'bench_end': 105.0},
         'samples': [{'timestamp': 101.0}, {'timestamp': 103.2}, {'timestamp': 105.1}]}, True),
    "no result": (
        {'times': {'bench_start': 103.0, 'bench_end': 105.0},
         'samples': [{'timestamp': 101.0}, {'timestamp': 103.2}, {'timestamp': 105.1}]}, False),
    "empty result is done": (
        {'result': {}, 'times': {'bench_start': 103.0, 'bench_end': 105.0},
         'samples': [{'timestamp': 101.0}, {'timestamp': 103.2}, {'timestamp': 105.1}]}, True),
    "no sample before the window": (
        {'result': {'valid': True}, 'times': {'bench_start': 103.0, 'bench_end': 105.0},
         'samples': [{'timestamp': 103.2}, {'timestamp': 105.1}]}, False),
    "no sample after the window": (
        {'result': {'valid': True}, 'times': {'bench_start': 103.0, 'bench_end': 105.0},
         'samples': [{'timestamp': 101.0}, {'timestamp': 104.9}]}, False),
    "samples exactly on the edges": (
        {'result': {'valid': True}, 'times': {'bench_start': 103.0, 'bench_end': 105.0},
         'samples': [{'timestamp': 103.0}, {'timestamp': 105.0}]}, True),
    "no start marker": (
        {'result': {'valid': True}, 'times': {'bench_end': 105.0},
         'samples': [{'timestamp': 101.0}, {'timestamp': 105.1}]}, False),
    "no end marker": (
        {'result': {'valid': True}, 'times': {'bench_start': 103.0},
         'samples': [{'timestamp': 101.0}, {'timestamp': 105.1}]}, False),
    "no samples": (
        {'result': {'valid': True}, 'times': {'bench_start': 103.0, 'bench_end': 105.0},
         'samples': []}, False),
    "samples out of time order": (
        {'result': {'valid': True}, 'times': {'bench_start': 103.0, 'bench_end': 105.0},
         'samples': [{'timestamp': 105.1}, {'timestamp': 101.0}]}, True),
    "OOMKilled is done": (
        {'failure_reason': 'OOMKilled'}, True),
    "Error is done": (
        {'failure_reason': 'Error'}, True),
    "DeadlineExceeded is done": (
        {'failure_reason': 'DeadlineExceeded'}, True),
    "Completed with no result reruns": (
        {'failure_reason': 'Completed'}, False),
    "empty reason reruns": (
        {'failure_reason': ''}, False),
    "StartError reruns": (
        {'failure_reason': 'StartError'}, False),
}

@pytest.mark.parametrize("entry, expected",
    TRIAL_IS_DONE_ROWS.values(), ids=TRIAL_IS_DONE_ROWS.keys(),
)
def test_trial_is_done(entry, expected):
    assert results.trial_is_done(entry) is expected

def test_load_missing_file(tmp_path):
    assert results.load_results(tmp_path / "r.json") is None

def test_save_then_load(tmp_path: Path):
    path = tmp_path/"x"/"y"/"r.json"
    results.save_results(path, {"a": 1})
    results.save_results(path, {"a": 2})
    assert results.load_results(path) == {"a": 2}
    assert os.listdir(path.parent) == ['r.json']

def test_load_corrupt_file_crashes(tmp_path):
    path = tmp_path/"r.json"
    path.write_text('{"a": 1')
    with pytest.raises(json.JSONDecodeError):
        results.load_results(path)

def test_failed_save_keeps_file(tmp_path):
    path = tmp_path/"r.json"
    results.save_results(path, {"a": 1})
    with pytest.raises(TypeError):
        results.save_results(path, {"b": object()})
    assert results.load_results(path) == {"a": 1}

def results_file(image: str, trials: dict) -> dict:
    return {'environment': {'image': image}, 'trials': trials}

PENDING_TRIALS_ROWS = {
    "a stored trial skips only its own number, size and file": (
        [results_file('native', {'size = 64': [{'trial': 1}]}), results_file('wasm', {})],
        [{'size': 64}, {'size': 512}], 2,
        [                             (1, 'native', {'size': 512}),
         (1, 'wasm',   {'size': 64}), (1, 'wasm',   {'size': 512}),
         (2, 'native', {'size': 64}), (2, 'native', {'size': 512}),
         (2, 'wasm',   {'size': 64}), (2, 'wasm',   {'size': 512})],
    ),
    "a gap before a stored trial is pending": (
        [results_file('native', {'size = 64': [{'trial': 3}]})],
        [{'size': 64}], 3,
        [(1, 'native', {'size': 64}), (2, 'native', {'size': 64})],
    ),
    "the key comes from trial_key": (
        [results_file('native', {'mode = fast, size = 64': [{'trial': 1}]})],
        [{'size': 64, 'mode': 'fast'}], 1,
        [],
    ),
}

@pytest.mark.parametrize("files, combinations, trials, expected",
    PENDING_TRIALS_ROWS.values(), ids=PENDING_TRIALS_ROWS.keys(),
)
def test_pending_trials(files, combinations, trials, expected):
    pending = results.pending_trials(files, combinations, trials)
    got = [(n, file['environment']['image'], combination) for n, file, combination in pending]
    assert got == expected

SAVED_TRIALS_ROWS = {
    "another key is not this cell's": (
        results_file('native', {'size = 512': [{'trial': 1}]}), 2,
        {},
    ),
    "a number above trials is not saved": (
        results_file('native', {'size = 64': [{'trial': 1}, {'trial': 3}]}), 2,
        {1: {'trial': 1}},
    ),
    "a duplicate number counts once, the later entry wins": (
        results_file('native', {'size = 64': [{'trial': 1, 'log': ['a']}, {'trial': 1, 'log': ['b']}]}), 2,
        {1: {'trial': 1, 'log': ['b']}},
    ),
    "a failure is saved like a result": (
        results_file('native', {'size = 64': [{'trial': 1, 'failure_reason': 'OOMKilled'}]}), 1,
        {1: {'trial': 1, 'failure_reason': 'OOMKilled'}},
    ),
}

@pytest.mark.parametrize("file, trials, expected",
    SAVED_TRIALS_ROWS.values(), ids=SAVED_TRIALS_ROWS.keys(),
)
def test_saved_trials(file, trials, expected):
    assert results.saved_trials(file, {'size': 64}, trials) == expected
