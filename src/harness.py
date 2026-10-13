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

import itertools
import json
import os
from pathlib import Path
from config import is_number

# cartesian product. takes {'size': [5, 10], 'mode': ['a', 'b']} and returns
#       1. {'size': 5,  'mode': 'a'}
#       2. {'size': 5,  'mode': 'b'}
#       3. {'size': 10, 'mode': 'a'}
#       4. {'size': 10, 'mode': 'b'}
def combinations(params: dict) -> list[dict]:
    value_combinations = itertools.product(*params.values())
    return [dict(zip(params.keys(), combination)) for combination in value_combinations]

def trial_env(combination: dict, duration, warmup) -> dict:
    env = {k: str(v) for k, v in combination.items()}
    env['KRATER_DURATION'] = str(float(duration))
    env['KRATER_WARMUP'] = str(float(warmup))
    return env

def trial_key(combination: dict) -> str:
    return ', '.join(f"{k} = {v}" for k,v in sorted(combination.items()))

def results_path(name: str, environment: dict) -> Path:
    safe_image_name = environment['image'].replace(':', '_').replace('/', '_')
    return Path("results") / name / f"{safe_image_name}_{environment['runtime_class']}.json"

def results_header(run: dict, environment: dict) -> dict:
    return {"environment": environment, 
            "settings": {key: run[key] for key in ["duration", "warmup", "cpu", "memory", "interval"]}}

def header_mismatch(stored: dict, header: dict) -> str | None:
    if not isinstance(stored, dict):
        return f"expected stored file to be a dict, got {type(stored).__name__}"

    for section in header:
        stored_section = stored.get(section, {})
        if not isinstance(stored_section, dict):
            return f"stored section {section!r} is not a dict"

        for key, value in stored_section.items():
            if not is_number(value) and not isinstance(value, str):
                return f"value of key {key!r} in section {section!r} ({value!r}) is not a number or string"

        only_in_file = sorted(stored_section.items() - header[section].items())
        only_in_config = sorted(header[section].items() - stored_section.items())
        if only_in_file or only_in_config:
            return (f"{section}:\n"
                    f"  file has {only_in_file}\n"
                    f"  config has {only_in_config}\n")

    trials = stored.get('trials')
    if not isinstance(trials, dict):
        return f"expected 'trials' section in stored file to be a dict, got {type(trials).__name__}"

def trial_is_done(entry: dict) -> bool:
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

def load_results(path: Path) -> dict | None:
    if not path.exists():
        return None
    with open(path, "r") as f:
        return json.load(f)

def save_results(path: Path, results: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_name(path.name + ".tmp")

    with open(tmp, "w") as f:
        json.dump(results, f, indent=2)
    os.replace(tmp, path)

def parse_result(texts: list[str]) -> dict | None:
    for text in texts:
        if text.startswith(prefix := "BENCH_RESULT "):
            try:
                result = json.loads(text.removeprefix(prefix))
                return result if isinstance(result, dict) else None
            except json.JSONDecodeError:
                return None
    return None
