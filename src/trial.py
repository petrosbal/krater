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
import threading

import cgroup
import pod

MARKER_TIMES = {
    "MAIN_START": "main_start",
    "BENCH_START": "bench_start",
    "BENCH_END": "bench_end"
}

BENCH_RESULT_PREFIX = "BENCH_RESULT "

def env(combination: dict, duration, warmup) -> dict:
    variables = {k: str(v) for k, v in combination.items()}
    variables['KRATER_DURATION'] = str(float(duration))
    variables['KRATER_WARMUP'] = str(float(warmup))
    return variables

def parse_result(texts: list[str]) -> dict | None:
    for text in texts:
        if text.startswith(BENCH_RESULT_PREFIX):
            try:
                result = json.loads(text.removeprefix(BENCH_RESULT_PREFIX))
                return result if isinstance(result, dict) else None
            except json.JSONDecodeError:
                return None
    return None

def manifest(run: dict, environment: dict, combination: dict) -> dict:
    trial_vars = env(combination, run['duration'], run['warmup'])
    return pod.manifest(environment, trial_vars, run)

def conduct(run: dict, environment: dict, combination: dict, trial_num: int) -> dict:
    pod_manifest = manifest(run, environment, combination)
    stop = threading.Event()
    samples = []
    times = {}
    monitor = None
    failure_reason = None

    try:
        times["applied"] = pod.start(pod_manifest)
        container_id = pod.container_id(run['namespace'], run['timeout'])
        cgroup_path = cgroup.find_cgroup(container_id)
        missing = cgroup.missing_fields(cgroup_path)
        monitor = threading.Thread(
            target = cgroup.sample_until,
            args = (cgroup_path, missing, run['interval'], stop, samples)
        )
        monitor.start()
        texts = []
        # the deadline's kill ends the stream a few seconds late
        # a watchdog that fires first would leave the failure reason empty
        for stamp, text in pod.stream_logs(run['namespace'], run['timeout'] + 10):
            texts.append(text)
            if text in MARKER_TIMES:
                times[MARKER_TIMES[text]] = stamp
                sample_at_marker = cgroup.take_sample(cgroup_path, missing)
                if sample_at_marker is not None:
                    samples.append(sample_at_marker)

        result = parse_result(texts)
        if result is None:
            failure_reason = pod.failure_reason(run['namespace'])

    finally:
        stop.set()
        if monitor is not None:
            monitor.join()
        pod.delete(run['namespace'])

    # two writers fill samples, the sampler thread and the marker samples
    # so they arrive out of order
    samples.sort(key = lambda s: s['timestamp'])
    entry = { "trial": trial_num,
              "times": times,
              "log": texts,
              "result": result,
              "samples": samples}
    if failure_reason is not None:
        entry['failure_reason'] = failure_reason

    return entry
