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
from pathlib import Path


# cartesian product
# takes {'size': [5, 10], 'mode': ['a', 'b']} and returns
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
