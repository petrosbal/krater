import pytest
from config import load_config, validate

def test_blueprint_passes():
    assert validate(load_config()) is None

def test_refuses_empty_config():
    assert validate(None) == "config is empty or not a valid dict"

def test_refuses_unknown_top_level_key():
    config = load_config()
    config['build'] = {}
    assert validate(config) == "unknown top-level keys: build"

def test_refuses_run_not_a_dict():
    config = load_config()
    config['run'] = [1]
    assert validate(config) == "'run' must be a dict"

def test_refuses_unknown_run_key():
    config = load_config()
    config['run']['foo'] = 1
    assert validate(config) == "'run' has unknown keys: foo"

def test_refuses_missing_run_key():
    config = load_config()
    del config['run']['timeout']
    assert validate(config) == "'run' missing required keys: timeout"

@pytest.mark.parametrize("key, value, expected", [
    ("duration",  0,            "'duration' must be a positive number, got 0"),
    ("trials",    True,         "'trials' must be a positive integer, got True"),
    ("warmup",    -1,           "'warmup' must be a non-negative number, got -1"),
    ("interval",  float('nan'), "'interval' must be a number >= 0.1, got nan"),
    ("cpu",       "",           "'cpu' must be a non-empty string, got ''"),
    ("memory",    1024,         "'memory' must be a non-empty string, got 1024"),
    ("namespace", " ",          "'namespace' must be a non-empty string, got ' '"),
    ("name",      69,           "'name' must be a string, got 69"),
    ("name",      "../x",       "'name' must start with a letter or digit and hold only letters, digits, _ and -"),
    ("name",      "bench\n",    "'name' must start with a letter or digit and hold only letters, digits, _ and -"),
    ("timeout",   120.0,        "'timeout' must be an integer, got 120.0"),
    ("timeout",   72,           "'timeout' must be above duration + warmup + 2 (72), got 72")

])
def test_refuses_bad_run_value(key, value, expected):
    config = load_config()
    config['run'][key] = value
    assert validate(config) == expected