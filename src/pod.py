# Copyright (C) 2026 Petros Baloglou, University of Macedonia

# This program is free software: you can redistribute it and/or modify
# it under the terms of the GNU General Public License as published by
# the Free Software Foundation, either version 3 of the License, or
# (at your option) any later version.

# This program is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
# GNU General Public License for more details.

# You should have received a copy of the GNU General Public License
# along with this program.  If not, see <https://www.gnu.org/licenses/>.

"""pod.py

Runs every kubectl call. The only module that starts a process,
and a failed call raises RuntimeError for the caller to judge.
"""

import json
import subprocess
import threading
import time
from collections.abc import Iterator
from datetime import datetime
from decimal import Decimal

POD_NAME = "krater-trial"
DRY_RUN_POD_NAME = "krater-dry-run"

def parse_log_line(line: str) -> tuple[float, str]:
    stamp, text = line.split(' ', maxsplit=1)
    # 3.10's fromisoformat takes neither Z nor nine fraction digits
    # so the fraction's cut out and added back as a float
    if stamp.endswith("Z"):
        offset = "+00:00"
        fraction = stamp[19:-1]
    else:
        offset = stamp[-6:]
        fraction = stamp[19:-6]
    return datetime.fromisoformat(stamp[:19] + offset).timestamp() + float("0" + fraction), text

def manifest(environment: dict, trial_vars: dict, run: dict) -> dict:
    env = [{"name": key, "value": value} for key, value in trial_vars.items()]
    resources = {r: run[r] for r in ["cpu", "memory"]}
    spec = {
        "restartPolicy": "Never",
        "activeDeadlineSeconds": run['timeout'],
        "terminationGracePeriodSeconds": 0,
        "containers": [{
            "name": "krater-workload",
            "image": environment['image'],
            "imagePullPolicy": "Never",
            "env": env,
            "resources": {"requests": resources, "limits": resources}
        }]
    }

    if environment['runtime_class'] != "default":
        spec['runtimeClassName'] = environment['runtime_class']

    return {"apiVersion": "v1",
            "kind": "Pod",
            "metadata": {"name": POD_NAME, "namespace": run['namespace']},
            "spec": spec}

def kubectl(*args: str, stdin: str | None = None) -> str:
    cmd_result = subprocess.run(["kubectl", *args], input=stdin, capture_output=True, text=True, check=False)
    if cmd_result.returncode != 0:
        raise RuntimeError(cmd_result.stderr.strip())
    return cmd_result.stdout

def start(manifest: dict) -> float:
    delete(manifest['metadata']['namespace'])
    kubectl("apply", "-f", "-", stdin=json.dumps(manifest))
    return time.time()

def container_id(namespace: str, timeout: int) -> str:
    jsonpath = "jsonpath={.status.containerStatuses[0].containerID}"
    return kubectl("wait", f"pod/{POD_NAME}", "-n", namespace,
            f"--for={jsonpath}", f"--timeout={timeout}s",
            "-o", jsonpath).removeprefix("containerd://")

def delete(namespace: str) -> None:
    kubectl("delete", "pod", POD_NAME, "-n", namespace,
            "--grace-period=0", "--force", "--ignore-not-found")

def phase(namespace: str) -> str:
    return kubectl("get", "pod", POD_NAME, "-n", namespace, "-o",
                   "jsonpath={.status.phase}", "--ignore-not-found")

def failure_reason(namespace: str) -> str:
    pod_reason = kubectl("get", "pod", POD_NAME, "-n", namespace,
                         "-o", "jsonpath={.status.reason}")
    container_reason = kubectl("get", "pod", POD_NAME, "-n", namespace,
                               "-o", "jsonpath={.status.containerStatuses[0].state.terminated.reason}")
    # a deadline sets only the pod's reason
    # OOMKilled and Error set only the container's
    return pod_reason or container_reason

def stream_logs(namespace: str, timeout: float) -> Iterator[tuple[float, str]]:
    proc = subprocess.Popen(["kubectl", "logs", "-f", "--timestamps", POD_NAME, "-n", namespace],
                            stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True, errors="replace")
    assert proc.stdout is not None and proc.stderr is not None
    watchdog = threading.Timer(timeout, proc.kill)
    watchdog.start()

    try:
        for line in proc.stdout:
            yield parse_log_line(line.removesuffix("\n"))
        # the watchdog's kill exits negative and just ends the stream
        # only kubectl's own failure exits above 0
        if proc.wait() > 0:
            raise RuntimeError(proc.stderr.read().strip())
    finally:
        watchdog.cancel()
        proc.kill()
        proc.wait()

def dry_run(manifest: dict) -> None:
    metadata = {**manifest['metadata'], 'name': DRY_RUN_POD_NAME}
    dry_manifest = {**manifest, 'metadata': metadata}
    kubectl("apply", "--dry-run=server", "-f", "-", stdin=json.dumps(dry_manifest))

QUANTITY_SUFFIXES = {
    "n": Decimal("1e-9"), "u": Decimal("1e-6"), "m": Decimal("1e-3"),
    "k": Decimal(10**3), "M": Decimal(10**6), "G": Decimal(10**9),
    "T": Decimal(10**12), "P": Decimal(10**15), "E": Decimal(10**18),
    "Ki": Decimal(2**10), "Mi": Decimal(2**20), "Gi": Decimal(2**30),
    "Ti": Decimal(2**40), "Pi": Decimal(2**50), "Ei": Decimal(2**60),
}
# never rejects or validates input, its only quantities the server accepted
# (only called after the dry run has succeeded)
def parse_quantity(quantity: str) -> Decimal:
    for suffix, factor in QUANTITY_SUFFIXES.items():
        if quantity.endswith(suffix):
            number = quantity.removesuffix(suffix)
            return Decimal(number) * factor
    return Decimal(quantity)

def fits_on(cpu: str, memory: str, unrequested: dict[str, Decimal]) -> bool:
    cpu_fits = parse_quantity(cpu) <= unrequested['cpu']
    memory_fits = parse_quantity(memory) <= unrequested['memory']
    return cpu_fits and memory_fits

# skips init containers and RuntimeClass overhead, this cluster has neither
# count them once a cluster does
def unrequested(allocatable: dict, pods: list) -> dict[str, Decimal]:
    left = {resource: parse_quantity(allocatable[resource])
            for resource in ['cpu', 'memory']}
    for pod in pods:
        for container in pod['spec']['containers']:
            requests = container.get('resources', {}).get('requests', {})
            for resource in ['cpu', 'memory']:
                left[resource] -= parse_quantity(requests.get(resource, "0"))
    return left

def non_terminated_pods_on(node_name: str) -> list:
    selector = f"spec.nodeName={node_name},status.phase!=Succeeded,status.phase!=Failed"
    pods_json = kubectl("get", "pods", "-A", "--field-selector", selector, "-o", "json")
    return json.loads(pods_json)['items']

def unrequested_on(node_name: str) -> dict[str, Decimal]:
    node_json = kubectl("get", "node", node_name, "-o", "json")
    allocatable = json.loads(node_json)['status']['allocatable']
    return unrequested(allocatable, non_terminated_pods_on(node_name))
