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
import sys
import threading
import time

from config import (
    load_config,
    load_environments,
    select_environments,
    validate,
)
import cgroup
import pod
import results
from console import (
    banner,
    closing_block,
    dry_run_refusal_text,
    outcome_line,
    round_line,
    trial_identity,
    trial_label,
    trial_outcome,
    widths,
)

MARKER_TIMES = {
    "MAIN_START": "main_start",
    "BENCH_START": "bench_start",
    "BENCH_END": "bench_end"
}

BENCH_RESULT_PREFIX = "BENCH_RESULT "

# cartesian product. takes {'size': [5, 10], 'mode': ['a', 'b']} and returns
#       1. {'size': 5,  'mode': 'a'}
#       2. {'size': 5,  'mode': 'b'}
#       3. {'size': 10, 'mode': 'a'}
#       4. {'size': 10, 'mode': 'b'}
def param_combinations(params: dict) -> list[dict]:
    value_combinations = itertools.product(*params.values())
    return [dict(zip(params.keys(), combination)) for combination in value_combinations]

def trial_env(combination: dict, duration, warmup) -> dict:
    env = {k: str(v) for k, v in combination.items()}
    env['KRATER_DURATION'] = str(float(duration))
    env['KRATER_WARMUP'] = str(float(warmup))
    return env

def parse_result(texts: list[str]) -> dict | None:
    for text in texts:
        if text.startswith(BENCH_RESULT_PREFIX):
            try:
                result = json.loads(text.removeprefix(BENCH_RESULT_PREFIX))
                return result if isinstance(result, dict) else None
            except json.JSONDecodeError:
                return None
    return None

def trial_manifest(run: dict, environment: dict, combination: dict) -> dict:
    trial_vars = trial_env(combination, run['duration'], run['warmup'])
    return pod.manifest(environment, trial_vars, run)

def run_trial(run: dict, environment: dict, combination: dict, trial_num: int) -> dict:
    manifest = trial_manifest(run, environment, combination)
    stop = threading.Event()
    samples = []
    times = {}
    monitor = None
    failure_reason = None

    try:
        times["applied"] = pod.start(manifest)
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

def user_confirmation() -> bool:
    print('continue? [y/N]\n> ', end='', flush=True, file=sys.stderr)
    try:
        answer = input().strip().lower()
    except EOFError:
        sys.exit("\nno answer (stdin closed). to run unattended: yes | python3 src/harness.py")
    return answer in ['y', 'yes']

def run_rounds(run: dict, files: list[dict], combinations: list[dict], pending: list,
               loop_started: float) -> tuple[list[str], bool]:
    current_round = 0
    to_rerun = []
    col_widths = widths(files, combinations)
    try:
        for k, (n, file, combination) in enumerate(pending, 1):
            if n != current_round:
                print(round_line(n, run['trials'], k, len(pending), time.time() - loop_started))
                current_round = n

            label = trial_label(file, combination, col_widths)
            line = trial_identity(k, len(pending), label)
            print(line, end='', flush=True)

            trial_start = time.time()
            try:
                entry = run_trial(run, file['environment'], combination, n)
            # kubectl(), find_cgroup() and stream_logs() throw Runtime
            # a cgroup file that vanished or kubectl missing would be OS
            # and a bad log timestamp would be Value
            except (RuntimeError, OSError, ValueError) as e:
                error_text = str(e).split('\n')[0] or type(e).__name__
                outcome = outcome_line('incomplete', time.time() - trial_start, f"{error_text}, runs again next time")
                print(outcome)
                to_rerun.append(line + outcome)
                continue

            was_kept = results.keep_entry(run, file, combination, entry)
            outcome = trial_outcome(entry, time.time() - trial_start)
            print(outcome)

            if not was_kept:
                to_rerun.append(line + outcome)
    except KeyboardInterrupt:
        print(flush=True)
        print("stopped by Ctrl-C", file=sys.stderr)
        return to_rerun, True

    return to_rerun, False

def exit_code(was_stopped: bool, trials_left: int) -> int:
    if was_stopped:
        return 130
    elif trials_left > 0:
        return 2
    return 0

def main() -> None:
    config, problem = load_config()
    if problem is not None:
        sys.exit(f"config: {problem}")

    environments = load_environments()
    problem = validate(config, environments)
    if problem is not None:
        sys.exit(f"config: {problem}")

    run = config['run']
    selected_envs = select_environments(environments, run['runtimes'])
    combinations = param_combinations(run['params'])

    files = []
    for environment in selected_envs:
        file, problem = results.file_for(run, environment) 
        if problem is not None:
            sys.exit(problem)
        files.append(file)

    try:
        phase = pod.phase(run['namespace'])
    except RuntimeError as e:
        sys.exit(f"can't reach kubernetes: {e}")
    if phase in ["Pending", "Running"]:
        sys.exit(f"pod {pod.POD_NAME} is {phase} in namespace '{run['namespace']}', "
                 "probably another harness running a trial\n"
                 "wait for it to finish, or if no harness is running, run:\n"
                 f"kubectl delete pod {pod.POD_NAME} -n {run['namespace']}")

    for env in selected_envs:
        try:
            pod.dry_run(trial_manifest(run, env, combinations[0]))
        except RuntimeError as e:
            sys.exit(dry_run_refusal_text(run, env, e))

    pending = results.pending_trials(files, combinations, run['trials'])
    if pending:
        print(banner(run, files, combinations, pending, cgroup.cpu_governor(), cgroup.cpu_model()), flush=True)
        if not user_confirmation():
            sys.exit("nothing ran")
    else:
        print(f"run \"{run['name']}\" is complete, nothing to run")

    loop_started = time.time()
    to_rerun, was_stopped = run_rounds(run, files, combinations, pending, loop_started)

    print(closing_block(run, files, combinations, to_rerun, 
                        time.time() - loop_started, 'stopped' if was_stopped else 'finished'))
    trials_left = len(results.pending_trials(files, combinations, run['trials']))
    sys.exit(exit_code(was_stopped, trials_left))

if __name__ == "__main__":
    # Ctrl-C before the rounds, while loading, in the dry run or at the prompt
    # run_rounds handles it during the rounds
    try:
        main()
    except KeyboardInterrupt:
        print("\nstopped by Ctrl-C", file=sys.stderr)
        sys.exit(130)