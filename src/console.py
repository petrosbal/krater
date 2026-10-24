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

"""console.py

Builds the text of every line on screen, from banner to closing
block. Prints absolutely nothing.
"""

import platform
from collections import Counter
from datetime import datetime, timedelta
from decimal import Decimal

import results
from config import CONFIG_FILE, RUNNER_SLEEP, RUNNER_TAIL_SLEEP

REASON_WORDS = {
    "OOMKilled": "ran out of memory",
    "Error": "exited with an error",
    "DeadlineExceeded": "hit the time limit",
    "Completed": "exited without a result",
    "": "no reason given"
}

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

def banner(run: dict, files: list[dict], combinations: list[dict], pending: list,
           governor: str, model: str) -> str:
    host = platform.uname()
    total_trials = len(files) * len(combinations) * run['trials']
    trials_saved = total_trials - len(pending)
    floor = len(pending) * (RUNNER_SLEEP + run['warmup'] + run['duration'] + RUNNER_TAIL_SLEEP)
    ceiling = len(pending) * run['timeout']
    folder = results.path(run['name'], files[0]['environment']).parent

    rows = [("started", current_datetime()),
            ("host", f"{host.node}, {host.system} {host.release}"),
            ("cpu", f"{model} ({host.machine})"),
            ("governor", governor),
            None,
            ("trials", (f"{len(files)} environments x {len(combinations)} param combinations "
                        f"x {run['trials']} = {total_trials}"))]
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

def widths(files: list[dict], combinations: list[dict]) -> tuple[int, int, int]:
    return (max(len(f['environment']['target']) for f in files),
            max(len(f['environment']['runtime_class']) for f in files),
            max(len(results.trial_key(c)) for c in combinations))

def trial_label(file: dict, combination: dict, widths: tuple[int, int, int]) -> str:
    t_width, rc_width, k_width = widths
    return (f"{file['environment']['target']:<{t_width}}  "
            f"{file['environment']['runtime_class']:<{rc_width}}  "
            f"{results.trial_key(combination):<{k_width}}  ")

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
    if results.trial_is_done(entry):
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
            entries = results.saved_trials(file, combination, trial_count).values()
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
            entries.extend(results.saved_trials(file, combination, run['trials']).values())
    trials_failed = sum(1 for e in entries if 'failure_reason' in e)
    trials_left = len(results.pending_trials(files, combinations, run['trials']))

    still_to_run = f", {trials_left} still to run" if trials_left else ""
    incomplete = "incomplete this session:\n" + "\n".join(to_rerun) + "\n" if to_rerun else ""

    return (f"{len(entries)} of {total_trials} trials saved "
            f"({len(entries) - trials_failed} ok, {trials_failed} failed and saved as data){still_to_run}\n"
            f"{incomplete}"
            f"\n{summary_table(files, combinations, run['trials'])}\n"
            f"\n{ending} {now} after {rounded_duration(elapsed)}")

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

def fit_refusal_text(run: dict, node_name: str, unrequested: dict[str, Decimal]) -> str:
    return (f"node {node_name} can't fit cpu = {run['cpu']}, memory = {run['memory']}\n"
            f"it has cpu = {int(unrequested['cpu'] * 1000)}m, "
            f"memory = {int(unrequested['memory'] / 2**20)}Mi left unrequested\n"
            f"lower cpu or memory in {CONFIG_FILE}")
