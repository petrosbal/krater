import pytest
import os
import json
from pathlib import Path
from config import RUN_KEYS
import harness

def test_every_run_key_is_placed():
    assert RUN_KEYS - set(harness.SETTINGS) == {"name", "params", "runtimes", "trials", "namespace"}

def test_combinations():
    value = harness.param_combinations({'size': [5, 10], 'mode': ['a', 'b']})
    expected = [{'size': 5,  'mode': 'a'},
                {'size': 5,  'mode': 'b'},
                {'size': 10, 'mode': 'a'},
                {'size': 10, 'mode': 'b'},]
    assert value == expected

def test_combinations_without_params():
    assert harness.param_combinations({}) == [{}]

def test_trial_env():
    combination = {'size': 256}
    value = harness.trial_env(combination, 2, 0)
    expected = {'size': '256', 'KRATER_DURATION': '2.0', 'KRATER_WARMUP': '0.0'}
    assert value == expected
    assert combination == {'size': 256}

@pytest.mark.parametrize("combination, expected", [
    ({},                         ''),
    ({'size': 256},              'size = 256'),
    ({'size': 256, 'mode': 'a'}, 'mode = a, size = 256')
])
def test_trial_key(combination, expected):
    assert harness.trial_key(combination) == expected

@pytest.mark.parametrize("name, environment, expected", [
    ('benchmark_1', 
     {'image': 'krater:matmul_wasm', 'runtime_class': 'wasmtime'},
     Path('results/benchmark_1/krater_matmul_wasm_wasmtime.json')),
    ('b', 
     {'image': 'reg/krater:x', 'runtime_class': 'default'},
     Path('results/b/reg_krater_x_default.json')),
])
def test_results_path(name, environment, expected):
    assert harness.results_path(name, environment) == expected

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
    assert harness.results_header(RESULTS_HEADER_RUN, RESULTS_HEADER_ENVIRONMENT) == {
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
    file, problem = harness.file_for({**RESULTS_HEADER_RUN, 'name': 'b'}, RESULTS_HEADER_ENVIRONMENT)
    expected = {**harness.results_header(RESULTS_HEADER_RUN, RESULTS_HEADER_ENVIRONMENT),
                'trials': {}}

    assert file == expected
    assert problem == None

def test_file_for_reopens_a_saved_file(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    saved = {**harness.results_header(RESULTS_HEADER_RUN, RESULTS_HEADER_ENVIRONMENT),
             'trials': {'size = 64': [{'trial': 1}]}}
    harness.save_results(harness.results_path('b', RESULTS_HEADER_ENVIRONMENT), saved)
    file, problem = harness.file_for({**RESULTS_HEADER_RUN, 'name': 'b'}, RESULTS_HEADER_ENVIRONMENT)

    assert file == saved
    assert problem == None

def test_file_for_refuses_a_changed_setting(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    saved = {**harness.results_header(RESULTS_HEADER_RUN, RESULTS_HEADER_ENVIRONMENT),
             'trials': {}}
    harness.save_results(harness.results_path('b', RESULTS_HEADER_ENVIRONMENT), saved)
    file, problem = harness.file_for({**RESULTS_HEADER_RUN, 'name': 'b', 'cpu': '500m'},
                                     RESULTS_HEADER_ENVIRONMENT)

    assert file == None
    assert problem == ("Existing results file (results/b/krater_matmul_wasm_wasmtime.json) does not match this run:\n"
                       "settings:\n"
                       "  file has [('cpu', '999m')]\n"
                       "  config has [('cpu', '500m')]\n"
                       "set the config back, use a new run name, or move the file")

def test_keep_entry_saves_a_done_entry(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    run = {**RESULTS_HEADER_RUN, 'name': 'b'}
    file, _ = harness.file_for(run, RESULTS_HEADER_ENVIRONMENT)
    assert file is not None
    entry = {'trial': 1, 'failure_reason': 'OOMKilled'}
    done = harness.keep_entry(run, file, {'size': 64}, entry)

    assert done is True
    assert file['trials'] == {'size = 64': [entry]}
    assert harness.file_for(run, RESULTS_HEADER_ENVIRONMENT) == (file, None)

def test_keep_entry_drops_an_entry_that_is_not_done(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    run = {**RESULTS_HEADER_RUN, 'name': 'b'}
    file, _ = harness.file_for(run, RESULTS_HEADER_ENVIRONMENT)
    assert file is not None
    done = harness.keep_entry(run, file, {'size': 64}, {'trial': 1, 'failure_reason': 'Completed'})

    assert done is False
    assert file['trials'] == {}
    assert not harness.results_path('b', RESULTS_HEADER_ENVIRONMENT).exists()

# keep_entry saves before it touches file, so a failed save can't leave
# an entry in memory that the disk doesn't have
def test_keep_entry_failed_save_leaves_file_unchanged(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    run = {**RESULTS_HEADER_RUN, 'name': 'b'}
    file, problem = harness.file_for(run, RESULTS_HEADER_ENVIRONMENT)
    assert file is not None

    def failing_save(path, results):
        raise OSError("disk full")
    monkeypatch.setattr(harness, 'save_results', failing_save)

    with pytest.raises(OSError):
        harness.keep_entry(run, file, {'size': 64}, {'trial': 1, 'failure_reason': 'OOMKilled'})
    assert file['trials'] == {}

def test_run_rounds_stops_properly(monkeypatch, capsys):
    def keyboard_interrupt(run, environment, combination, trial_num):
        raise KeyboardInterrupt
    monkeypatch.setattr(harness, 'run_trial', keyboard_interrupt)

    run = {'trials': 1}
    files = [{'environment': {'target': 'wasm', 'runtime_class': 'wasmtime'}}]
    combinations = [{'size': 1024}]
    pending = [(1, files[0], combinations[0])]
    loop_started = 0.0
    assert harness.run_rounds(run, files, combinations, pending, loop_started) == ([], True)

    captured = capsys.readouterr()
    assert captured.out.endswith("size = 1024  \n")
    assert captured.err == "stopped by Ctrl-C\n"

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
    assert harness.header_mismatch(stored, HEADER) == expected

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
    assert harness.trial_is_done(entry) is expected

def test_load_missing_file(tmp_path):
    assert harness.load_results(tmp_path / "r.json") is None

def test_save_then_load(tmp_path: Path):
    path = tmp_path/"x"/"y"/"r.json"
    harness.save_results(path, {"a": 1})
    harness.save_results(path, {"a": 2})
    assert harness.load_results(path) == {"a": 2}
    assert os.listdir(path.parent) == ['r.json']

def test_load_corrupt_file_crashes(tmp_path):
    path = tmp_path/"r.json"
    path.write_text('{"a": 1')
    with pytest.raises(json.JSONDecodeError):
        harness.load_results(path)

def test_failed_save_keeps_file(tmp_path):
    path = tmp_path/"r.json"
    harness.save_results(path, {"a": 1})
    with pytest.raises(TypeError):
        harness.save_results(path, {"b": object()})
    assert harness.load_results(path) == {"a": 1}

PARSE_RESULT_ROWS = {
    "normal result": (
        ['MAIN_START', 'BENCH_START', 'BENCH_END', 'BENCH_RESULT {"units": 5, "valid": true}'],
        {'units': 5, 'valid': True},
    ),
    "no result line": (
        ['MAIN_START', 'BENCH_START'],
        None,
    ),
    "broken json": (
        ['BENCH_RESULT {"units": 5'],
        None,
    ),
    "noise before it": (
        ['libunwind: __unw_add_dynamic_fde: bad fde', 'BENCH_RESULT {"a": 1}'],
        {'a': 1},
    ),
    "json but not an object": (
        ['BENCH_RESULT [1, 2]'],
        None,
    ),
    "empty object counts": (
        ['BENCH_RESULT {}'],
        {},
    ),
    "first one wins": (
        ['BENCH_RESULT {"a": 1}', 'BENCH_RESULT {"a": 2}'],
        {'a': 1},
    ),
    "similar line before it": (
        ['BENCH_RESULTS follow', 'BENCH_RESULT {"a": 1}'],
        {'a': 1},
    ),
}

@pytest.mark.parametrize("texts, expected",
    PARSE_RESULT_ROWS.values(), ids=PARSE_RESULT_ROWS.keys(),
)
def test_parse_result(texts, expected):
    assert harness.parse_result(texts) == expected

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
    pending = harness.pending_trials(files, combinations, trials)
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
    assert harness.saved_trials(file, {'size': 64}, trials) == expected


DESCRIBE_REASON_ROWS = {
    "a failure that counts as done": ('DeadlineExceeded', 'hit the time limit (DeadlineExceeded)'),
    "a reason that reruns":          ('Completed',        'exited without a result (Completed)'),
    "no reason, words only":         ('',                 'no reason given'),
    "an unknown term, as is":        ('StartError',       'StartError'),
}
@pytest.mark.parametrize("reason, expected",
    DESCRIBE_REASON_ROWS.values(), ids=DESCRIBE_REASON_ROWS.keys(),
)
def test_describe_reason(reason, expected):
    assert harness.describe_reason(reason) == expected

WINDOW = {'bench_start': 103.0, 'bench_end': 105.0}

TRIAL_OUTCOME_ROWS = {
    "a result, saved": (
        {'result': {}, 'times': WINDOW, 'samples': [{'timestamp': 101.0}, {'timestamp': 105.1}]},
        75.4321, 'ok           75.4 s'),
    "a workload failure, saved as data": (
        {'result': None, 'failure_reason': 'DeadlineExceeded'},
        120.3, 'failed      120.3 s  hit the time limit (DeadlineExceeded), saved as data'),
    "a reason that reruns": (
        {'result': None, 'failure_reason': 'Completed'},
        74.84, 'incomplete   74.8 s  exited without a result (Completed), runs again next time'),
    "a result, but the samples missed the window": (
        {'result': {}, 'times': WINDOW, 'samples': [{'timestamp': 104.0}]},
        3.14159, 'incomplete    3.1 s  samples missed the measured window, runs again next time'),
}
@pytest.mark.parametrize("entry, seconds, expected",
    TRIAL_OUTCOME_ROWS.values(), ids=TRIAL_OUTCOME_ROWS.keys(),
)
def test_trial_outcome(entry, seconds, expected):
    assert harness.trial_outcome(entry, seconds) == expected