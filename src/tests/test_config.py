import pytest

from config import load_config, load_environments, validate

ENVIRONMENTS = load_environments()

def mock_config() -> dict:
    return {'run': {
        'name': "mock",
        'runtimes': ["default", "wasmtime", "wasmedge", "wasmer"],
        'params': {'size': [256, 1024]},
        'trials': 30,
        'duration': 60,
        'warmup': 10,
        'timeout': 120,
        'interval': 0.2,
        'namespace': "mock-namespace",
        'cpu': "1000m",
        'memory': "1024Mi"
    }}

def test_blueprint_passes():
    config, problem = load_config()
    assert problem is None
    assert validate(config, ENVIRONMENTS) is None

def test_refuses_empty_config():
    assert validate(None, ENVIRONMENTS) == "config is empty or not a valid dict"

def test_refuses_unknown_top_level_key():
    config = mock_config()
    config['rnu'] = {}
    assert validate(config, ENVIRONMENTS) == "unknown top-level keys: rnu"

def test_accepts_dice_build_section():
    config = mock_config()
    config['build'] = {}
    assert validate(config, ENVIRONMENTS) is None

def test_refuses_run_not_a_dict():
    config = mock_config()
    config['run'] = [1]
    assert validate(config, ENVIRONMENTS) == "'run' must be a dict"

def test_refuses_unknown_run_key():
    config = mock_config()
    config['run']['foo'] = 1
    assert validate(config, ENVIRONMENTS) == "'run' has unknown keys: foo"

def test_refuses_bool_run_key():
    config = mock_config()
    config['run'][True] = 1
    assert validate(config, ENVIRONMENTS) == "'run' has unknown keys: True"

def test_refuses_missing_run_key():
    config = mock_config()
    del config['run']['timeout']
    assert validate(config, ENVIRONMENTS) == "'run' missing required keys: timeout"

@pytest.mark.parametrize("key, value, expected", [
    ("duration",  0,                 "'duration' must be a positive number, got 0"),
    ("trials",    True,              "'trials' must be a positive integer, got True"),
    ("trials",    2.5,               "'trials' must be a positive integer, got 2.5"),
    ("warmup",    -1,                "'warmup' must be a non-negative number, got -1"),
    ("interval",  float('nan'),      "'interval' must be a number >= 0.1, got nan"),
    ("cpu",       "",                "'cpu' must be a non-empty string, got ''"),
    ("memory",    1024,              "'memory' must be a non-empty string, got 1024"),
    ("namespace", " ",               "'namespace' must be a non-empty string, got ' '"),
    ("name",      69,                "'name' must be a string, got 69"),
    ("name",      "../x",            "'name' must start with a letter or digit and hold only letters, digits, _ and -"),
    ("name",      "bench\n",         "'name' must start with a letter or digit and hold only letters, digits, _ and -"),
    ("timeout",   120.0,             "'timeout' must be an integer, got 120.0"),
    ("timeout",   True,              "'timeout' must be an integer, got True"),
    ("timeout",   72,                "'timeout' must be above duration + warmup + 2 (72), got 72"),
    ("params",    [256],             "'params' must be a dict, got [256]"),
    ("params",    {1: [256]},        "parameter name 1 must be a letter followed by letters, digits or _"),
    ("params",    {"size\n": [1]},   "parameter name 'size\\n' must be a letter followed by letters, digits or _"),
    ("params",    {"KRATER_N": [1]}, "parameter name 'KRATER_N' is reserved: use a different prefix"),
    ("params",    {"n": 256},        "values for parameter 'n' must be in a list"),
    ("params",    {"n": []},         "no values for parameter 'n'"),
    ("params",    {"n": [1, True]},  "values for parameter 'n' must be numbers or strings"),
    ("params",    {"n": [1, "1"]},   "parameter 'n' has duplicate values"),
    ("params",    {"n": [1, 1.0]},   "parameter 'n' has duplicate values"),
    ("params",    {"n": ["a,b"]},    "value 'a,b' contains ',' or '='"),
    ("params",    {"n": ["x=1"]},    "value 'x=1' contains ',' or '='"),
    ("runtimes",  [],                "'runtimes' must be a non-empty list"),
    ("runtimes",  "wasmtime",        "'runtimes' must be a non-empty list"),
    ("runtimes",  ["wasmtime", 1],   "'runtimes' must contain strings only"),
    ("runtimes",  ["wasmtime", "a"], "unknown runtimes detected: a (available runtimes are: default, wasmedge, wasmer, wasmtime)"),
])
def test_refuses_bad_run_value(key, value, expected):
    config = mock_config()
    config['run'][key] = value
    assert validate(config, ENVIRONMENTS) == expected

@pytest.mark.parametrize("key, value", [
    ("warmup",   0),
    ("interval", 0.1),
    ("timeout",  73),
    ("trials",   1),
    ("params",   {}),
])
def test_accepts_edge_value(key, value):
    config = mock_config()
    config['run'][key] = value
    assert validate(config, ENVIRONMENTS) is None
