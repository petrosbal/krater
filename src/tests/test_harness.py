import pytest
import os
import json
from pathlib import Path
import harness

def test_combinations():
    value = harness.combinations({'size': [5, 10], 'mode': ['a', 'b']})
    expected = [{'size': 5,  'mode': 'a'},
                {'size': 5,  'mode': 'b'},
                {'size': 10, 'mode': 'a'},
                {'size': 10, 'mode': 'b'},]
    assert value == expected

def test_combinations_without_params():
    assert harness.combinations({}) == [{}]

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
    'timeout': 120,
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
            'cpu': '999m',
            'memory': '1023Mi',
            'interval': 0.2,
        },
    }

def test_own_file_passes_header_check(tmp_path):
    path = tmp_path / "r.json"
    header = harness.results_header(RESULTS_HEADER_RUN, RESULTS_HEADER_ENVIRONMENT)
    harness.save_results(path, {**header, 'trials': {}})
    loaded = harness.load_results(path)
    assert loaded is not None
    assert harness.header_mismatch(loaded, header) is None


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
         "  config has [('cpu', '1000m')]\n"),
    ),
    "field only in file": (
        {'environment': {'target': 'wasm'},
         'settings': {'cpu': '1000m', 'duration': 2, 'governor': 'x'},
         'trials': {}},
        ("settings:\n"
         "  file has [('governor', 'x')]\n"
         "  config has []\n"),
    ),
    "field only in config": (
        {'environment': {'target': 'wasm'},
         'settings': {'cpu': '1000m'},
         'trials': {}},
        ("settings:\n"
         "  file has []\n"
         "  config has [('duration', 2)]\n"),
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
         "  config has [('target', 'wasm')]\n"),
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