import json

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
MANIFEST_RUN = {
    'namespace': 'bench',
    'cpu': '500m',
    'memory': '256Mi',
    'timeout': 90,
    'trials': 30,
    'duration': 60,
}

MANIFEST_VARS = {'size': '256', 'KRATER_DURATION': '60.0', 'KRATER_WARMUP': '10.0'}

POD_MANIFEST_ROWS = {
    "runc: no runtimeClassName": (
        {'target': 'native', 'image': 'krater:matmul_native', 'runtime_class': 'default'},
        {
            'apiVersion': 'v1',
            'kind': 'Pod',
            'metadata': {'name': 'krater-trial', 'namespace': 'bench'},
            'spec': {
                'restartPolicy': 'Never',
                'activeDeadlineSeconds': 90,
                'terminationGracePeriodSeconds': 0,
                'containers': [{
                    'name': 'krater-workload',
                    'image': 'krater:matmul_native',
                    'imagePullPolicy': 'Never',
                    'env': [
                        {'name': 'size', 'value': '256'},
                        {'name': 'KRATER_DURATION', 'value': '60.0'},
                        {'name': 'KRATER_WARMUP', 'value': '10.0'},
                    ],
                    'resources': {
                        'requests': {'cpu': '500m', 'memory': '256Mi'},
                        'limits': {'cpu': '500m', 'memory': '256Mi'},
                    },
                }],
            },
        },
    ),
    "shim: runtimeClassName set": (
        {'target': 'wasm', 'image': 'krater:matmul_wasm', 'runtime_class': 'wasmtime'},
        {
            'apiVersion': 'v1',
            'kind': 'Pod',
            'metadata': {'name': 'krater-trial', 'namespace': 'bench'},
            'spec': {
                'restartPolicy': 'Never',
                'activeDeadlineSeconds': 90,
                'terminationGracePeriodSeconds': 0,
                'runtimeClassName': 'wasmtime',
                'containers': [{
                    'name': 'krater-workload',
                    'image': 'krater:matmul_wasm',
                    'imagePullPolicy': 'Never',
                    'env': [
                        {'name': 'size', 'value': '256'},
                        {'name': 'KRATER_DURATION', 'value': '60.0'},
                        {'name': 'KRATER_WARMUP', 'value': '10.0'},
                    ],
                    'resources': {
                        'requests': {'cpu': '500m', 'memory': '256Mi'},
                        'limits': {'cpu': '500m', 'memory': '256Mi'},
                    },
                }],
            },
        },
    ),
}

@pytest.mark.parametrize("environment, expected",
    POD_MANIFEST_ROWS.values(), ids=POD_MANIFEST_ROWS.keys(),
)
def test_pod_manifest(environment, expected):
    assert pod.manifest(environment, MANIFEST_VARS, MANIFEST_RUN) == expected

def test_dry_run(monkeypatch):
    calls = []
    def fake_kubectl(*args, stdin=None):
        calls.append((args, stdin))
    monkeypatch.setattr(pod, 'kubectl', fake_kubectl)

    manifest = {'metadata': {'name': 'krater-trial', 'namespace': 'bench'}, 'spec': {}}
    pod.dry_run(manifest)

    assert len(calls) == 1
    args, stdin = calls[0]
    assert args == ('apply', '--dry-run=server', '-f', '-')
    assert json.loads(stdin)['metadata']['name'] == 'krater-dry-run'
    assert manifest['metadata']['name'] == 'krater-trial'
