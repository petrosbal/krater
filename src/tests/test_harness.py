import pytest
from pathlib import Path
from harness import combinations, trial_env, trial_key, results_path

def test_combinations():
    value = combinations({'size': [5, 10], 'mode': ['a', 'b']})
    expected = [{'size': 5,  'mode': 'a'},
                {'size': 5,  'mode': 'b'},
                {'size': 10, 'mode': 'a'},
                {'size': 10, 'mode': 'b'},]
    assert value == expected

def test_combinations_without_params():
    assert combinations({}) == [{}]

def test_trial_env():
    combination = {'size': 256}
    value = trial_env(combination, 2, 0)
    expected = {'size': '256', 'KRATER_DURATION': '2.0', 'KRATER_WARMUP': '0.0'}
    assert value == expected
    assert combination == {'size': 256}

@pytest.mark.parametrize("input, expected", [
    ({},                         ''),
    ({'size': 256},              'size = 256'),
    ({'size': 256, 'mode': 'a'}, 'mode = a, size = 256')
])
def test_trial_key(input, expected):
    assert trial_key(input) == expected

@pytest.mark.parametrize("name, environment, expected", [
    ('benchmark_1', 
     {'image': 'krater:matmul_wasm', 'runtime_class': 'wasmtime'},
     Path('results/benchmark_1/krater_matmul_wasm_wasmtime.json')),
    ('b', 
     {'image': 'reg/krater:x', 'runtime_class': 'default'},
     Path('results/b/reg_krater_x_default.json')),
])
def test_results_path(name, environment, expected):
    assert results_path(name, environment) == expected