import pytest

import trial

def test_trial_env():
    combination = {'size': 256}
    value = trial.env(combination, 2, 0)
    expected = {'size': '256', 'KRATER_DURATION': '2.0', 'KRATER_WARMUP': '0.0'}
    assert value == expected
    assert combination == {'size': 256}

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
    assert trial.parse_result(texts) == expected
