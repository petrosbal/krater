import pytest

import console

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
    assert console.describe_reason(reason) == expected

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
    assert console.trial_outcome(entry, seconds) == expected

DRY_RUN_REFUSAL_ROWS = {
    "the namespace is missing": (
        ('Error from server (NotFound): error when creating "STDIN": '
         'namespaces "krater-testing" not found'),
        "\nto create it, run:\nkubectl create namespace krater-testing",
    ),
    "a different thing is not found": (
        ('Error from server (Forbidden): error when creating "STDIN": '
         'pods "krater-dry-run" is forbidden: pod rejected: RuntimeClass "wasmedgee" not found'),
        "",
    ),
    "a bad cpu value": (
        ('The Pod "krater-dry-run" is invalid: '
         'spec.containers[0].resources.limits[cpu]: Invalid value: "lots"'),
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

    text = console.dry_run_refusal_text(run, environment, RuntimeError(error_text))
    assert text == f"{first_line}kubernetes error: {error_text}{hint}"

BOXED_ROWS = {
    "rows wider than the title": (
        "t", ["abcd", "", "ab"],
        ("┌─ t ──┐\n"
         "│ abcd │\n"
         "│      │\n"
         "│ ab   │\n"
         "└──────┘"),
    ),
    "a title wider than the rows": (
        "title", ["ab"],
        ("┌─ title ─┐\n"
         "│ ab      │\n"
         "└─────────┘"),
    ),
}

@pytest.mark.parametrize("title, lines, expected",
    BOXED_ROWS.values(), ids=BOXED_ROWS.keys(),
)
def test_boxed(title, lines, expected):
    assert console.boxed(title, lines) == expected
