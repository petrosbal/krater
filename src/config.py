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

import yaml
import re

CONFIG_FILE = 'krater.yaml'
ENVIRONMENTS_FILE = "dice/generated/available_environments.yaml"
RUNNER_SLEEP = 2 # the first sleep from workload_runner.h
RUNNER_TAIL_SLEEP = 2 # the last sleep from workload_runner.h
                      # it keeps the container's cgroup alive for the end sample (after BENCH_END)
RUN_KEYS = frozenset({
    "name",
    "params",
    "trials",
    "duration",
    "warmup",
    "timeout",
    "interval",
    "namespace",
    "cpu",
    "memory",
    "runtimes"
})

def load_config() -> tuple[dict, str | None]:
    with open(CONFIG_FILE, 'r') as f:
        try:
            return yaml.safe_load(f), None
        except yaml.YAMLError as e:
            return {}, str(e)

def load_environments() -> list:
    with open(ENVIRONMENTS_FILE, 'r') as f:
        return yaml.safe_load(f)['environments']

def is_number(value) -> bool:
    return isinstance(value, (int, float)) and not isinstance(value, bool)

# yaml keys can be numbers or bools, and sorted() can't compare those with strings
def name_list(names) -> str:
    return ', '.join(sorted(map(str, names)))

def select_environments(environments: list, runtimes: list) -> list:
    return [env for env in environments if env['runtime_class'] in runtimes]

def validate(config, environments) -> str | None:
    if not isinstance(config, dict):
        return "config is empty or not a valid dict"
    if unknown := set(config) - {"run"}:
        return f"unknown top-level keys: {name_list(unknown)}"
    
    run = config.get('run')
    if not isinstance(run, dict):
        return "'run' must be a dict"
    if unknown := run.keys() - RUN_KEYS:
        return f"'run' has unknown keys: {name_list(unknown)}"
    if missing := RUN_KEYS - run.keys():
        return f"'run' missing required keys: {name_list(missing)}"

    duration = run['duration']
    if not is_number(duration) or not duration > 0:
        return f"'duration' must be a positive number, got {duration!r}"

    trials = run['trials']
    if not is_number(trials) or not isinstance(trials, int) or not trials > 0:
        return f"'trials' must be a positive integer, got {trials!r}"

    warmup = run['warmup']
    if not is_number(warmup) or not warmup >= 0:
        return f"'warmup' must be a non-negative number, got {warmup!r}"

    timeout = run['timeout']
    timeout_lb = duration + warmup + RUNNER_SLEEP
    if not is_number(timeout) or not isinstance(timeout, int):
        return f"'timeout' must be an integer, got {timeout!r}"
    if not timeout > timeout_lb:
        return f"'timeout' must be above duration + warmup + {RUNNER_SLEEP} ({timeout_lb}), got {timeout!r}"

    interval = run['interval']
    if not is_number(interval) or not interval >= 0.1:
        return f"'interval' must be a number >= 0.1, got {interval!r}"

    for key in ["cpu", "memory", "namespace"]:
        if not isinstance(run[key], str) or run[key].strip() == '':
            return f"'{key}' must be a non-empty string, got {run[key]!r}"

    name = run['name']
    if not isinstance(name, str):
        return f"'name' must be a string, got {name!r}"
    if not re.fullmatch(r'[a-zA-Z0-9][a-zA-Z0-9_\-]*', name):
        return ("'name' must start with a letter or digit "
                    "and hold only letters, digits, _ and -")

    runtimes = run['runtimes']
    if not isinstance(runtimes, list) or runtimes == []:
        return "'runtimes' must be a non-empty list"
    if not all(isinstance(runtime, str) for runtime in runtimes):
        return "'runtimes' must contain strings only"

    available = {env['runtime_class'] for env in environments}
    if unknown := set(runtimes) - available:
        return (f"unknown runtimes detected: {name_list(unknown)} "
                 f"(available runtimes are: {name_list(available)})")

    return validate_params(run['params'])


def validate_params(params) -> str | None:
    if not isinstance(params, dict):
        return f"'params' must be a dict, got {params!r}"

    for name, valuelist in params.items():
        if not isinstance(name, str) or not re.fullmatch(r'[a-zA-Z][a-zA-Z0-9_]*', name):
            return f"parameter name {name!r} must be a letter followed by letters, digits or _"
        if name.startswith("KRATER_"):
            return f"parameter name {name!r} is reserved: use a different prefix"
        if not isinstance(valuelist, list):
            return f"values for parameter {name!r} must be in a list"
        if valuelist == []:
            return f"no values for parameter {name!r}"
        for value in valuelist:
            if not is_number(value) and not isinstance(value, str):
                return f"values for parameter {name!r} must be numbers or strings"
            if isinstance(value, str) and any(c in value for c in [',', '=']):
                return f"value {value!r} contains ',' or '='"
        # the same number written differently, like 256 and 256.0
        if len(valuelist) != len(set(valuelist)):
            return f"parameter {name!r} has duplicate values"
        # values that look the same to the pod, like 256 and '256'
        if len(valuelist) != len({str(v) for v in valuelist}):
            return f"parameter {name!r} has duplicate values"