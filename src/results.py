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

"""results.py

Reads, judges and saves the results files. The only module that writes them,
and a save replaces the file whole, so a crash can't corrupt them.
"""

import json
import os
from pathlib import Path

from config import is_number

# workload failures, saved as data. they count as done
DONE_REASONS = frozenset({"OOMKilled", "Error", "DeadlineExceeded"})

SETTINGS = ("duration", "warmup", "timeout", "cpu", "memory", "interval")

def trial_key(combination: dict) -> str:
    return ', '.join(f"{k} = {v}" for k,v in sorted(combination.items()))

def path(name: str, environment: dict) -> Path:
    safe_image_name = environment['image'].replace(':', '_').replace('/', '_')
    return Path("results") / name / f"{safe_image_name}_{environment['runtime_class']}.json"

def header(run: dict, environment: dict) -> dict:
    return {"environment": environment,
            "settings": {key: run[key] for key in SETTINGS}}

def header_mismatch(stored: dict, header: dict) -> str | None:
    if not isinstance(stored, dict):
        return f"expected stored file to be a dict, got {type(stored).__name__}"

    for section, expected_section in header.items():
        stored_section = stored.get(section, {})
        if not isinstance(stored_section, dict):
            return f"stored section {section!r} is not a dict"

        for key, value in stored_section.items():
            if not is_number(value) and not isinstance(value, str):
                return f"value of key {key!r} in section {section!r} ({value!r}) is not a number or string"

        only_in_file = sorted(stored_section.items() - expected_section.items())
        only_in_config = sorted(expected_section.items() - stored_section.items())
        if only_in_file or only_in_config:
            return (f"{section}:\n"
                    f"  file has {only_in_file}\n"
                    f"  config has {only_in_config}")

    trials = stored.get('trials')
    if not isinstance(trials, dict):
        return f"expected 'trials' section in stored file to be a dict, got {type(trials).__name__}"
    return None

def trial_is_done(entry: dict) -> bool:
    if entry.get('failure_reason') in DONE_REASONS:
        return True
    if entry.get('result') is None:
        return False
    times = entry.get('times', {})
    start = times.get('bench_start')
    end = times.get('bench_end')
    if start is None or end is None:
        return False

    timestamps = [sample['timestamp'] for sample in entry.get('samples', [])]
    if timestamps == []:
        return False
    return min(timestamps) <= start and max(timestamps) >= end

def load(path: Path) -> dict | None:
    if not path.exists():
        return None
    with open(path, "r") as f:
        return json.load(f)

def save(path: Path, results: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_name(path.name + ".tmp")

    with open(tmp, "w") as f:
        json.dump(results, f, indent=2)
    os.replace(tmp, path)

def file_for(run: dict, environment: dict) -> tuple[dict | None, str | None]:
    file_path = path(run['name'], environment)
    expected_header = header(run, environment)
    stored_file = load(file_path)

    if stored_file is None:
        return {**expected_header, 'trials': {}}, None
    if (mismatch := header_mismatch(stored_file, expected_header)) is not None:
        return None, (f"existing results file ({file_path}) does not match this run:\n"
                      f"{mismatch}\n"
                      "set the config back, use a new run name, or move the file")
    return stored_file, None

# an entry holds trial, times, log, result and samples, plus failure_reason when there's one.
# trial.conduct builds every entry, this module just judges and saves it
def keep_entry(run: dict, file: dict, combination: dict, entry: dict) -> bool:
    if not trial_is_done(entry):
        return False
    key = trial_key(combination)
    entries = file['trials'].get(key, [])  + [entry]
    file_path = path(run['name'], file['environment'])

    trials = file['trials'].copy()
    trials[key] = entries
    save(file_path, {**file, 'trials': trials})

    file['trials'] = trials
    return True

def saved_trials(file: dict, combination: dict, trial_count: int) -> dict[int, dict]:
    entries = file['trials'].get(trial_key(combination), [])
    return {entry['trial']: entry for entry in entries if 1 <= entry['trial'] <= trial_count}

def pending_trials(files: list[dict], combinations: list[dict], trial_count: int) -> list[tuple[int, dict, dict]]:
    pending = []
    for n in range(1, trial_count + 1):
        for file in files:
            for combination in combinations:
                if n not in saved_trials(file, combination, trial_count):
                    pending.append((n, file, combination))
    return pending
