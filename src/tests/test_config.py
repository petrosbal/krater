from config import load_config
def test_load_config():
    value = load_config()
    assert isinstance(value['run'], dict)
