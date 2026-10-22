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

from collections import Counter
import itertools
import json
import os
import platform
import sys
import threading
from pathlib import Path
from datetime import timedelta, datetime
import time

from config import (
    CONFIG_FILE,
    RUNNER_SLEEP,
    RUNNER_TAIL_SLEEP,
    is_number,
    load_config,
    load_environments,
    select_environments,
    validate,
)
import cgroup
import pod

# workload failures, saved as data. they count as done
DONE_REASONS = frozenset({"OOMKilled", "Error", "DeadlineExceeded"})

REASON_WORDS = {
    "OOMKilled": "ran out of memory",
    "Error": "exited with an error",
    "DeadlineExceeded": "hit the time limit",
    "Completed": "exited without a result",
    "": "no reason given"
}

MARKER_TIMES = {
    "MAIN_START": "main_start",
    "BENCH_START": "bench_start",
    "BENCH_END": "bench_end"
}

BENCH_RESULT_PREFIX = "BENCH_RESULT "

SETTINGS = ("duration", "warmup", "timeout", "cpu", "memory", "interval")

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

def trial_key(combination: dict) -> str:
    return ', '.join(f"{k} = {v}" for k,v in sorted(combination.items()))

def results_path(name: str, environment: dict) -> Path:
    safe_image_name = environment['image'].replace(':', '_').replace('/', '_')
    return Path("results") / name / f"{safe_image_name}_{environment['runtime_class']}.json"

def results_header(run: dict, environment: dict) -> dict:
    return {"environment": environment, 
            "settings": {key: run[key] for key in SETTINGS}}

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
                    f"  config has {only_in_config}")

    trials = stored.get('trials')
    if not isinstance(trials, dict):
        return f"expected 'trials' section in stored file to be a dict, got {type(trials).__name__}"

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

def file_for(run: dict, environment: dict) -> tuple[dict | None, str | None]:
    path = results_path(run['name'], environment)
    header = results_header(run, environment)
    stored = load_results(path)

    if stored is None:
        return {**header, 'trials': {}}, None
    if (mismatch := header_mismatch(stored, header)) is not None:
        return None, (f"existing results file ({path}) does not match this run:\n"
                      f"{mismatch}\n"
                      "set the config back, use a new run name, or move the file")
    return stored, None

def keep_entry(run: dict, file: dict, combination: dict, entry: dict) -> bool:
    if not trial_is_done(entry):
        return False
    key = trial_key(combination)
    entries = file['trials'].get(key, [])  + [entry]
    path = results_path(run['name'], file['environment'])

    trials = file['trials'].copy()
    trials[key] = entries
    save_results(path, {**file, 'trials': trials})

    file['trials'] = trials
    return True

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

def current_datetime() -> str:
    return datetime.now().isoformat(sep=' ', timespec='seconds')

def rounded_duration(seconds: float) -> timedelta:
    return timedelta(seconds=round(seconds))

def boxed(title: str, lines: list[str]) -> str:
    inner_width = max(len(title) + 2, *(len(line) for line in lines))
    top = f"┌─ {title} " + "─" * (inner_width - len(title) - 1) + "┐"
    middle = [f"│ {line:<{inner_width}} │" for line in lines]
    bottom = "└" + "─" * (inner_width + 2) + "┘"
    return "\n".join([top, *middle, bottom])

def banner(run: dict, files: list[dict], combinations: list[dict], pending: list) -> str:
    host = platform.uname()
    total_trials = len(files) * len(combinations) * run['trials']
    trials_saved = total_trials - len(pending)
    floor = len(pending) * (RUNNER_SLEEP + run['warmup'] + run['duration'] + RUNNER_TAIL_SLEEP)
    ceiling = len(pending) * run['timeout']
    folder = results_path(run['name'], files[0]['environment']).parent

    rows = [("started", current_datetime()),
            ("host", f"{host.node}, {host.system} {host.release}"),
            ("cpu", f"{cgroup.cpu_model()} ({host.machine})"),
            ("governor", cgroup.cpu_governor()),
            None,
            ("trials", f"{len(files)} environments x {len(combinations)} param combinations "
                       f"x {run['trials']} = {total_trials}")]
    if trials_saved:
        rows.append(("resumed", f"{trials_saved} saved by an earlier run, {len(pending)} to run now"))
    rows += [("each", f"{run['warmup']} s warmup, {run['duration']} s duration, timeout at {run['timeout']} s"),
             ("estimate", f"{rounded_duration(floor)} to {rounded_duration(ceiling)}"),
             ("results", f"{folder}/")]

    label_width = max(len(row[0]) for row in rows if row is not None)
    lines = ["" if row is None else f"{row[0]:<{label_width}}  {row[1]}" for row in rows]
    title = f'KRATER run "{run["name"]}" ({CONFIG_FILE})'

    return ("\n" + boxed(title, lines) + "\n"
            "Ctrl-C stops safely at any time. Run the same command to continue.")

def user_confirmation() -> bool:
    print('continue? [y/N]\n> ', end='', flush=True, file=sys.stderr)
    try:
        answer = input().strip().lower()
    except EOFError:
        sys.exit("\nno answer (stdin closed). to run unattended: yes | python3 src/harness.py")
    return answer in ['y', 'yes']

def widths(files: list[dict], combinations: list[dict]) -> tuple[int, int, int]:
    return (max(len(f['environment']['target']) for f in files),
            max(len(f['environment']['runtime_class']) for f in files),
            max(len(trial_key(c)) for c in combinations))

def trial_label(file: dict, combination: dict, widths: tuple[int, int, int]) -> str:
    t_width, rc_width, k_width = widths
    return (f"{file['environment']['target']:<{t_width}}  "
            f"{file['environment']['runtime_class']:<{rc_width}}  "
            f"{trial_key(combination):<{k_width}}  ")

def trial_identity(k: int, total_session_trials: int, label: str) -> str:
    started_at = datetime.now().strftime('%H:%M:%S')
    return f"  [{k:>{len(str(total_session_trials))}}/{total_session_trials}] {started_at}  {label}"

def describe_reason(reason: str) -> str:
    words = REASON_WORDS.get(reason)
    if words is None:
        return reason
    if reason == "":
        return words
    return f"{words} ({reason})"

def trial_outcome(entry: dict, seconds: float) -> str:
    if trial_is_done(entry):
        if 'failure_reason' not in entry:
            return outcome_line('ok', seconds)
        return outcome_line('failed', seconds, f"{describe_reason(entry['failure_reason'])}, saved as data")
    if 'failure_reason' in entry:
        return outcome_line('incomplete', seconds, f"{describe_reason(entry['failure_reason'])}, runs again next time")
    return outcome_line('incomplete', seconds, "samples missed the measured window, runs again next time")

def round_line(n: int, trial_count: int, k: int, total_session_trials: int, elapsed: float) -> str:
    now = current_datetime()
    trials_done = k - 1
    if trials_done == 0:
        return f"round {n} of {trial_count}, {now}"
    time_left = rounded_duration(elapsed / trials_done * (total_session_trials - trials_done))
    return f"round {n} of {trial_count}, {now} ({rounded_duration(elapsed)} so far, about {time_left} left)"

def summary_table(files: list[dict], combinations: list[dict], trial_count: int) -> str:
    col_widths = widths(files, combinations)
    rows = []
    for file in files:
        for combination in combinations:
            entries = saved_trials(file, combination, trial_count).values()
            failure_words = []
            for e in entries:
                if 'failure_reason' in e:
                    reason = e['failure_reason']
                    failure_words.append(REASON_WORDS.get(reason, reason))
            counts = Counter(failure_words)
            failure_text = ', '.join(f"{count} {words}" for words, count in counts.items())

            saved_text = f"{len(entries):>{len(str(trial_count))}}/{trial_count} saved"
            of_which = f", of which {failure_text}" if failure_text else ""
            rows.append(f"  {trial_label(file, combination, col_widths)}{saved_text}{of_which}")
    return '\n'.join(rows)

def closing_block(run: dict, files: list[dict], combinations: list[dict], to_rerun: list[str],
                  elapsed: float, ending: str) -> str:
    now = current_datetime()
    total_trials = len(files) * len(combinations) * run['trials']
    entries = []
    for file in files:
        for combination in combinations:
            entries.extend(saved_trials(file, combination, run['trials']).values())
    trials_failed = sum(1 for e in entries if 'failure_reason' in e)
    trials_left = len(pending_trials(files, combinations, run['trials']))

    still_to_run = f", {trials_left} still to run" if trials_left else ""
    incomplete = "incomplete this session:\n" + "\n".join(to_rerun) + "\n" if to_rerun else ""

    return (f"{len(entries)} of {total_trials} trials saved "
            f"({len(entries) - trials_failed} ok, {trials_failed} failed and saved as data){still_to_run}\n"
            f"{incomplete}"
            f"\n{summary_table(files, combinations, run['trials'])}\n"
            f"\n{ending} {now} after {rounded_duration(elapsed)}")

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

            was_kept = keep_entry(run, file, combination, entry)
            outcome = trial_outcome(entry, time.time() - trial_start)
            print(outcome)

            if not was_kept:
                to_rerun.append(line + outcome)
    except KeyboardInterrupt:
        print(flush=True)
        print("stopped by Ctrl-C", file=sys.stderr)
        return to_rerun, True

    return to_rerun, False

def outcome_line(status: str, seconds: float, detail: str = '') -> str:
    detail_text = f"  {detail}" if detail else ""
    return f"{status:<10}  {seconds:5.1f} s{detail_text}"

def dry_run_refusal_text(run: dict, environment: dict, error: RuntimeError) -> str:
    namespace = run["namespace"]
    hint = ""
    if f"namespaces \"{namespace}\" not found" in str(error):
        hint = f"\nto create it, run:\nkubectl create namespace {namespace}"
    return (f"dry run for {environment['target']} on {environment['runtime_class']} failed with "
            f"cpu = {run['cpu']}, memory = {run['memory']} in namespace '{namespace}'\n"
            f"kubernetes error: {error}{hint}")

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
        file, problem = file_for(run, environment) 
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

    pending = pending_trials(files, combinations, run['trials'])
    if pending:
        print(banner(run, files, combinations, pending), flush=True)
        if not user_confirmation():
            sys.exit("nothing ran")
    else:
        print(f"run \"{run['name']}\" is complete, nothing to run")

    loop_started = time.time()
    to_rerun, was_stopped = run_rounds(run, files, combinations, pending, loop_started)

    print(closing_block(run, files, combinations, to_rerun, 
                        time.time() - loop_started, 'stopped' if was_stopped else 'finished'))
    trials_left = len(pending_trials(files, combinations, run['trials']))
    sys.exit(exit_code(was_stopped, trials_left))

if __name__ == "__main__":
    # Ctrl-C before the rounds, while loading, in the dry run or at the prompt
    # run_rounds handles it during the rounds
    try:
        main()
    except KeyboardInterrupt:
        print("\nstopped by Ctrl-C", file=sys.stderr)
        sys.exit(130)