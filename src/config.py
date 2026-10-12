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
RUNNER_SLEEP = 2 # from workload_runner.h
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

def load_config() -> dict:
    with open(CONFIG_FILE, 'r') as f:
        return yaml.safe_load(f)

def is_number(value) -> bool:
    return isinstance(value, (int, float)) and not isinstance(value, bool)

def validate(config) -> str | None:
    if not isinstance(config, dict):
        return "config is empty or not a valid dict"
    if unknown := set(config) - {"run"}:
        return f"unknown top-level keys: {', '.join(sorted(unknown))}"
    
    run = config.get('run')
    if not isinstance(run, dict):
        return "'run' must be a dict"
    if unknown := run.keys() - RUN_KEYS:
        return f"'run' has unknown keys: {', '.join(sorted(unknown))}"
    if missing := RUN_KEYS - run.keys():
        return f"'run' missing required keys: {', '.join(sorted(missing))}"

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
        return (f"'name' must be a string, got {name!r}")
    if not re.fullmatch(r'^[a-zA-Z0-9][a-zA-Z0-9_\-]*$', name):
        return ("'name' must start with a letter or digit "
                    "and hold only letters, digits, _ and -")