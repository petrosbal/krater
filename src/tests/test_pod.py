import pytest
import pod

PARSE_LOG_LINE_ROWS = {
    "offset, nine digits": (
        "2026-10-12T14:03:21.123456789+03:00 BENCH_START",
        (1791803001.1234567, 'BENCH_START'),
    ),
    "trailing zeros": (
        "2026-10-12T14:03:21.302406800+03:00 BENCH_END",
        (1791803001.3024068, 'BENCH_END'),
    ),
    "utc node, nine digits": (
        "2026-10-12T11:03:21.123456789Z x",
        (1791803001.1234567, 'x'),
    ),
    "utc node, zero fraction": (
        "2026-10-12T11:03:21.000000000Z hello world",
        (1791803001.0, 'hello world'),
    ),
    "empty printed line": (
        "2026-10-12T14:03:21.500000000+03:00 ",
        (1791803001.5, ''),
    ),
    "negative half-hour offset": (
        "2026-10-12T05:33:21.500000000-05:30 x",
        (1791803001.5, 'x'),
    ),
}

@pytest.mark.parametrize("line, expected",
    PARSE_LOG_LINE_ROWS.values(), ids=PARSE_LOG_LINE_ROWS.keys(),
)
def test_parse_log_line(line, expected):
    assert pod.parse_log_line(line) == expected