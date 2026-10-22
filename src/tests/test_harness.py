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

@pytest.mark.parametrize("was_stopped, trials_left, expected", [
    (False, 0, 0),
    (False, 1, 2),
    (True, 0, 130),
    (True, 1, 130),
])
def test_exit_code(was_stopped, trials_left, expected):
    assert harness.exit_code(was_stopped, trials_left) == expected

DRY_RUN_REFUSAL_ROWS = {
    "the namespace is missing": (
        'Error from server (NotFound): error when creating "STDIN": '
        'namespaces "krater-testing" not found',
        "\nto create it, run:\nkubectl create namespace krater-testing",
    ),
    "a different thing is not found": (
        'Error from server (Forbidden): error when creating "STDIN": '
        'pods "krater-dry-run" is forbidden: pod rejected: RuntimeClass "wasmedgee" not found',
        "",
    ),
    "a bad cpu value": (
        'The Pod "krater-dry-run" is invalid: '
        'spec.containers[0].resources.limits[cpu]: Invalid value: "lots"',
        "",
    ),
}

@pytest.mark.parametrize("error_text, hint",
    DRY_RUN_REFUSAL_ROWS.values(), ids=DRY_RUN_REFUSAL_ROWS.keys(),
)
def test_dry_run_refusal_text(error_text, hint):
    run = {'cpu': '1000m', 'memory': '1024Mi', 'namespace': 'krater-testing'}
    environment = {'target': 'native', 'runtime_class': 'default'}
    first_line = ("dry run for native on default failed with "
                  "cpu = 1000m, memory = 1024Mi in namespace 'krater-testing'\n")

    text = harness.dry_run_refusal_text(run, environment, RuntimeError(error_text))
    assert text == f"{first_line}kubernetes error: {error_text}{hint}"

BOXED_ROWS = {
    "rows wider than the title": (
        "t", ["abcd", "", "ab"],
        "┌─ t ──┐\n"
        "│ abcd │\n"
        "│      │\n"
        "│ ab   │\n"
        "└──────┘",
    ),
    "a title wider than the rows": (
        "title", ["ab"],
        "┌─ title ─┐\n"
        "│ ab      │\n"
        "└─────────┘",
    ),
}

@pytest.mark.parametrize("title, lines, expected",
    BOXED_ROWS.values(), ids=BOXED_ROWS.keys(),
)
def test_boxed(title, lines, expected):
    assert harness.boxed(title, lines) == expected
