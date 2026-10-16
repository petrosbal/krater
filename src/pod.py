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

import json
import subprocess
import threading
import time
from datetime import datetime
from collections.abc import Iterator

POD_NAME = "krater-trial"

def parse_log_line(line: str) -> tuple[float, str]:
    stamp, text = line.split(' ', maxsplit=1)
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
    cmd_result = subprocess.run(["kubectl", *args], input=stdin, capture_output=True, text=True)
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
    kubectl("delete", "pod", POD_NAME, "-n", namespace, "--grace-period=0", "--force", "--ignore-not-found")

def failure_reason(namespace: str) -> str:
    pod_reason = kubectl("get", "pod", POD_NAME, "-n", namespace, 
                         "-o", "jsonpath={.status.reason}")
    container_reason = kubectl("get", "pod", POD_NAME, "-n", namespace, 
                               "-o", "jsonpath={.status.containerStatuses[0].state.terminated.reason}")
    return pod_reason or container_reason # first non empty one

def stream_logs(namespace: str, timeout: float) -> Iterator[tuple[float, str]]:
    proc = subprocess.Popen(["kubectl", "logs", "-f", "--timestamps", POD_NAME, "-n", namespace],
                            stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
    assert proc.stdout is not None and proc.stderr is not None
    watchdog = threading.Timer(timeout, proc.kill)
    watchdog.start()

    try:
        for line in proc.stdout:
            yield parse_log_line(line.removesuffix("\n"))
        if proc.wait() > 0:
            raise RuntimeError(proc.stderr.read().strip())
    finally:
        watchdog.cancel()
        proc.kill()
        proc.wait()

def dry_run(manifest: dict) -> None:
    delete(manifest['metadata']['namespace'])
    kubectl("apply", "--dry-run=server", "-f", "-", stdin=json.dumps(manifest))