import io

import pytest

import krater
import trial


def test_param_combinations():
    value = krater.param_combinations({'size': [5, 10], 'mode': ['a', 'b']})
    expected = [{'size': 5,  'mode': 'a'},
                {'size': 5,  'mode': 'b'},
                {'size': 10, 'mode': 'a'},
                {'size': 10, 'mode': 'b'},]
    assert value == expected

def test_param_combinations_without_params():
    assert krater.param_combinations({}) == [{}]

def test_run_rounds_stops_properly(monkeypatch, capsys):
    def keyboard_interrupt(run, environment, combination, trial_num):
        raise KeyboardInterrupt
    monkeypatch.setattr(trial, 'conduct', keyboard_interrupt)

    run = {'trials': 1}
    files = [{'environment': {'target': 'wasm', 'runtime_class': 'wasmtime'}}]
    combinations = [{'size': 1024}]
    pending = [(1, files[0], combinations[0])]
    loop_started = 0.0
    assert krater.run_rounds(run, files, combinations, pending, loop_started) == ([], True)

    captured = capsys.readouterr()
    assert captured.out.endswith("size = 1024  \n")
    assert captured.err == "stopped by Ctrl-C\n"


@pytest.mark.parametrize("was_stopped, trials_left, expected", [
    (False, 0, 0),
    (False, 1, 2),
    (True, 0, 130),
    (True, 1, 130),
])
def test_exit_code(was_stopped, trials_left, expected):
    assert krater.exit_code(was_stopped, trials_left) == expected

def test_stream_gets_logged():
    stdout = io.StringIO()
    stderr = io.StringIO()
    log = io.StringIO()

    stdout_writer = krater.LoggedStream(stdout, log)
    stderr_writer = krater.LoggedStream(stderr, log)

    print("1", file=stdout_writer)
    print("2", file=stderr_writer)
    print("3", file=stdout_writer)

    assert stdout.getvalue() == '1\n3\n'
    assert stderr.getvalue() == '2\n'
    assert log.getvalue() == '1\n2\n3\n'
