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

from pathlib import Path
import threading
import time

def find_cgroup(container_id: str, root_path: Path = Path("/sys/fs/cgroup")) -> Path:
    if container_id == "":
        raise RuntimeError("container_id is empty")
    
    matches = list(root_path.rglob(f"*{container_id}*"))
    if len(matches) != 1:
        raise RuntimeError(f"found {len(matches)} matches for container {container_id[:12]!r}")
    return matches[0]

def read_flat_file(path: Path) -> dict[str, int]:
    return {line.split()[0]: int(line.split()[1]) for line in path.read_text().splitlines()}

def missing_fields(cgroup_path: Path) -> set[str]:
    missing = set()
    if not (cgroup_path / "memory.peak").exists():
        missing.add("peak_memory_bytes")
    if "kernel" not in read_flat_file(cgroup_path / "memory.stat"):
        missing.add("kernel_memory_bytes")
    if "nice_usec" not in read_flat_file(cgroup_path / "cpu.stat"):
        missing.add("nice_seconds")
    return missing

def take_sample(cgroup_path: Path, missing: set[str]) -> dict | None:
    try:
        mem = read_flat_file(cgroup_path / "memory.stat")
        cpu = read_flat_file(cgroup_path / "cpu.stat")
        # the line for cpu_wait_usec looks like "some avg10=0.00 avg60=0.00 avg300=0.00 total=3048408"
        cpu_wait_usec = int((cgroup_path / "cpu.pressure").read_text().split()[4].split("=")[1])

        return {
            "timestamp": time.time(),
            # cpu
            "cpu_seconds": cpu['usage_usec'] / 1_000_000,
            "user_seconds": cpu['user_usec'] / 1_000_000,
            "system_seconds": cpu['system_usec'] / 1_000_000,
            "throttled_seconds": cpu['throttled_usec'] / 1_000_000,
            "cpu_wait_seconds": cpu_wait_usec / 1_000_000,
            # threads
            "threads": int((cgroup_path / "pids.current").read_text()),
            # memory
            "memory_bytes": int((cgroup_path / "memory.current").read_text()),
            "page_faults": mem['pgfault'],
            "major_page_faults": mem['pgmajfault'],
            "anon_memory_bytes": mem['anon'],
            # these dont exist in all kernels
            "kernel_memory_bytes": None if "kernel_memory_bytes" in missing else mem['kernel'],
            "nice_seconds": None if "nice_seconds" in missing else cpu['nice_usec'] / 1_000_000,
            "peak_memory_bytes": None if "peak_memory_bytes" in missing else int((cgroup_path / "memory.peak").read_text()),
        }
    except (OSError, ValueError, KeyError, IndexError):
        return None

def sample_until(cgroup_path: Path, missing: set[str], interval: float, stop: threading.Event, samples: list) -> None:
    while not stop.is_set():
        if sample := take_sample(cgroup_path, missing):
            samples.append(sample)
        stop.wait(interval)
