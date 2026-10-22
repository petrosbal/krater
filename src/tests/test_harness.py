import pytest
import harness

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


@pytest.mark.parametrize("was_stopped, trials_left, expected", [
    (False, 0, 0),
    (False, 1, 2),
    (True, 0, 130),
    (True, 1, 130),
])
def test_exit_code(was_stopped, trials_left, expected):
    assert harness.exit_code(was_stopped, trials_left) == expected
