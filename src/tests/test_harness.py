import pytest
import harness
import trial

def test_combinations():
    value = harness.param_combinations({'size': [5, 10], 'mode': ['a', 'b']})
    expected = [{'size': 5,  'mode': 'a'},
                {'size': 5,  'mode': 'b'},
                {'size': 10, 'mode': 'a'},
                {'size': 10, 'mode': 'b'},]
    assert value == expected

def test_combinations_without_params():
    assert harness.param_combinations({}) == [{}]

def test_run_rounds_stops_properly(monkeypatch, capsys):
    def keyboard_interrupt(run, environment, combination, trial_num):
        raise KeyboardInterrupt
    monkeypatch.setattr(trial, 'conduct', keyboard_interrupt)

    run = {'trials': 1}
    files = [{'environment': {'target': 'wasm', 'runtime_class': 'wasmtime'}}]
    combinations = [{'size': 1024}]
    pending = [(1, files[0], combinations[0])]
    loop_started = 0.0
    assert harness.run_rounds(run, files, combinations, pending, loop_started) == ([], True)

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
    assert harness.exit_code(was_stopped, trials_left) == expected
