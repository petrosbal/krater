import subprocess
import time
import json
import os
import threading
import argparse
import re
import yaml
from datetime import datetime, timezone

class CgroupHandler:
    
    def __init__(self, pod_name, namespace):
        self.path = None
        self._find_path(pod_name, namespace)

    # determines the exact cgroup path for a running container.
    # approach: ask containerd for the host PID via its task table (runtime agnostic!)
    # then read /proc/<pid>/cgroup directly.
    def _find_path(self, pod_name, namespace):
        # first get the container ID from the pod status
        container_id_raw = kubectl_output(["get", "pod", pod_name, "-n", namespace,
                                           "-o", "jsonpath={.status.containerStatuses[0].containerID}"])
        if not container_id_raw:
            raise RuntimeError(f"Could not get container ID for pod {pod_name}")
        container_id = container_id_raw.removeprefix("containerd://")

        # then get the host PID from containerd's task table.
        # k3s ctr queries containerd directly
        # and the shim should report the PID regardless of what each runtime does with cgroups
        result = subprocess.run(["k3s", "ctr", "-n", "k8s.io", "tasks", "ls"],
                                capture_output=True, text=True)
        if result.returncode != 0:
            raise RuntimeError(f"k3s ctr tasks ls failed: {result.stderr.strip()}")

        pid = None
        for line in result.stdout.splitlines():
            parts = line.split()
            if parts and parts[0] == container_id:
                pid = int(parts[1])
                break

        if pid is None:
            raise RuntimeError(f"Container {container_id[:12]} not found in containerd task list")

        # finally, read the actual cgroup path from the kernel.
        # /proc/<pid>/cgroup cannot lie about where the process is
        # cgroup v2 format: "0::/path"
        try:
            with open(f"/proc/{pid}/cgroup") as f:
                for line in f:
                    if line.startswith("0::"):
                        self.path = "/sys/fs/cgroup" + line.strip().removeprefix("0::")
                        break
        except FileNotFoundError:
            raise RuntimeError(f"Process {pid} not found in /proc. container may have already exited")

        if self.path is None:
            raise RuntimeError(f"No cgroup v2 entry found in /proc/{pid}/cgroup")

        print(f"   [cgroup] pid={pid}, path={self.path}")

    # captures a timestamped snapshot of cgroup v2 metrics by parsing them directly from the relevant files
    def read_stats(self):
        ts = time.time()
        metrics = {"timestamp": ts}
        try:
            # cpu usage, user, system, throttled
            with open(os.path.join(self.path, "cpu.stat")) as f:
                for line in f:
                    k, v = line.strip().split()
                    if k in ["usage_usec", "user_usec", "system_usec", "nr_throttled"]:
                        metrics[k] = int(v)

            # ram: total usage (cache + RSS)
            with open(os.path.join(self.path, "memory.current")) as f:
                metrics["mem_bytes"] = int(f.read().strip())

            # ram: RSS (anonymous memory only)
            with open(os.path.join(self.path, "memory.stat")) as f:
                for line in f:
                    parts = line.split()
                    if parts[0] == "anon":
                        metrics["rss_bytes"] = int(parts[1])
                        break

        except FileNotFoundError as e:
            print(f"   [cgroup] file not found during read: {e.filename}")
            return None
        except PermissionError:
            print(f"   [cgroup] permission denied. are you root?")
            return None
        except Exception as e:
            print(f"   [cgroup] unexpected error reading stats: {type(e).__name__}: {e}")

        return metrics

# ---------------
# kubectl helpers
# ---------------


from pathlib import Path
DEFAULT_KUBECONFIG = os.environ.get("KUBECONFIG", "/etc/rancher/k3s/k3s.yaml")

# executes a kubectl command via subprocess, returns full process result
def kubectl(cmd_args, env=None, capture_output=True, check=False, input_bytes=None):
    env = env or os.environ.copy()
    if "KUBECONFIG" not in env:
        env["KUBECONFIG"] = DEFAULT_KUBECONFIG

    if not Path(env["KUBECONFIG"]).exists():
        print(f"WARNING: KUBECONFIG not found at {env['KUBECONFIG']}")
    
    return subprocess.run(["kubectl"] + cmd_args, text=True, env=env,
                          stdout=subprocess.PIPE if capture_output else subprocess.DEVNULL,
                          stderr=subprocess.PIPE, 
                          check=check,
                          input=input_bytes)

# runs kubectl and returns the clean stdout string or None if the command fails
def kubectl_output(cmd_args, env=None):
    try:
        return kubectl(cmd_args, env=env, capture_output=True, check=True).stdout.strip()
    except subprocess.CalledProcessError:
        return None

# self explanatory
def kubectl_pod_exists(pod_name, namespace, env=None):
    res = kubectl(["get", "pod", pod_name, "-n", namespace], env=env, capture_output=False)
    return res.returncode == 0


class PodOrchestrator:
    # prepares output dir and loads any existing checkpoint data
    def __init__(self, args):
        self.args = args
        self.results_file = args.output
        os.makedirs(os.path.dirname(args.output) or ".", exist_ok=True)
        self.results = self._load_checkpoint()

    # attempts to load previous results from json to allow resuming from where you left off
    def _load_checkpoint(self):
        if not os.path.exists(self.results_file):
            return {}
        
        try:
            with open(self.results_file, "r") as f:
                return json.load(f)
        except json.JSONDecodeError as e:
            print(f"   [checkpoint] file corrupted (JSON error): {e}")
            backup_name = f"{self.results_file}.bak"
            os.rename(self.results_file, backup_name)
            print(f"   [checkpoint] corrupted file moved to {backup_name}")
        except OSError as e:
            print(f"   [checkpoint] OS error loading file: {e}")

        return {}
        

    # dumps the currently gathered results to the json file (after every trial)
    def _save_checkpoint(self):
        with open(self.results_file, "w") as f:
            json.dump(self.results, f, indent=2)

    # constructs the pod manifest dict, configuring name, image, args and resources
    def create_pod_yaml(self, pod_name, size, duration, warmup):
        cpu_val = self.args.cpu
        mem_val = self.args.memory
        pod_spec = {
            "restartPolicy": "Never",
            "containers": [{
                "name": "bench",
                "image": self.args.image,
                "imagePullPolicy": "Never",
                "args": ["w" if warmup else "nw", str(size), str(duration)],
                "resources": {
                    "requests": {"cpu": cpu_val, "memory": mem_val},
                    "limits":   {"cpu": cpu_val, "memory": mem_val}
                }
            }]
        }
        if self.args.runtime_class != "default":
            pod_spec["runtimeClassName"] = self.args.runtime_class
        return {"apiVersion": "v1", "kind": "Pod",
                "metadata": {"name": pod_name, "namespace": self.args.ns},
                "spec": pod_spec}

    # scrapes the container logs with regex to get metrics from the benchmark itself
    # there must have been a better way to do this. anyway
    def parse_output(self, stdout):
            metrics = {"raw_output": stdout}
            mapping = {"iterations": int, "throughput_mflops": float, "valid": lambda x: x.upper()=="PASSED"}
            patterns = {
                "iterations": r"iterations:\s*(\d+)",
                "throughput_mflops": r"throughput:\s*([\d.]+)",
                "valid": r"calculation check:\s*(\w+)"
            }
            for key, pat in patterns.items():
                m = re.search(pat, stdout, re.IGNORECASE)
                if m:
                    try:
                        metrics[key] = mapping[key](m.group(1))
                    except Exception:
                        metrics[key] = None
            return metrics

    # manages the pod's lifecycle
    # maybe it does too much. clears stale instances, deploys new pod, polls the api
    def prepare_pod(self, pod_name, manifest, env):
        # 1. cleanup
        kubectl(["delete","pod",pod_name,"-n",self.args.ns,"--grace-period=0","--force"], env=env, capture_output=False)
        time.sleep(2)

        # 2. launch
        print("   launching pod...") # PRINT KEPT
        kubectl(["apply","-f","-"], env=env, check=True, capture_output=False, input_bytes=yaml.dump(manifest))

        # 3. wait for UID
        print("   waiting for pod uid...") # PRINT KEPT
        uid = None
        start_wait = time.time()
        while uid is None:
            if time.time() - start_wait > 30: raise TimeoutError("timed out waiting for UID")
            uid = kubectl_output(["get","pod",pod_name,"-n",self.args.ns,"-o","jsonpath={.metadata.uid}"], env)
            time.sleep(0.5)
        print(f"   pod uid: {uid}") # PRINT KEPT

        # 4. wait for Running
        print("   waiting for container to start...") # PRINT KEPT
        start_wait = time.time()
        phase = None
        while True:
            if time.time() - start_wait > 60: raise TimeoutError("timed out waiting for Running state")
            phase = kubectl_output(["get","pod",pod_name,"-n",self.args.ns,"-o","jsonpath={.status.phase}"], env)
            if phase in ("Running", "Succeeded"): break
            if phase == "Failed": raise RuntimeError("Pod failed to start")
            time.sleep(0.5)

        # get the exact container start time from the runtime rather than relying on when
        # our polling loop happened to observe the transition (which would be up to 0.5s off)
        if phase == "Running":
            ts_path = "jsonpath={.status.containerStatuses[0].state.running.startedAt}"
        else:
            ts_path = "jsonpath={.status.containerStatuses[0].state.terminated.startedAt}"

        ts_raw = kubectl_output(["get","pod",pod_name,"-n",self.args.ns,"-o",ts_path], env)
        if not ts_raw:
            raise RuntimeError(f"could not get container startedAt timestamp for pod {pod_name}")
        running_time = datetime.fromisoformat(ts_raw.replace("Z", "+00:00")).timestamp()

        return uid, CgroupHandler(pod_name, self.args.ns), running_time

    # polls cgroup stats and appends them in a list until main thread signals stop
    def monitor_cgroup(self, cgroup, interval, stop_event, samples):
        while not stop_event.is_set():
            s = cgroup.read_stats()
            if s: samples.append(s)
            time.sleep(interval)

    # processes the raw timestamped snapshots and calculates more trial metrics
    def compute_additional_metrics(self, trial_entry):
            samples = trial_entry.get("samples", [])
            phases = trial_entry.get("phases", {})
            
            if not samples: return None, "No cgroup samples"
            if phases.get("running_time") is None or phases.get("start") is None:
                return None, "Running/start timestamps missing"
            
            mem_values = []
            cpu_cores = []
            throttled_list = []

            for i, s in enumerate(samples):
                mem = s.get("mem_bytes")
                cpu = s.get("usage_usec") if "usage_usec" in s else s.get("cpu_usec")
                throttled = s.get("nr_throttled", 0)

                if mem is None or cpu is None: continue
                mem_values.append(mem)
                throttled_list.append(throttled)
                
                if i > 0:
                    prev = samples[i-1]
                    prev_cpu = prev.get("usage_usec") if "usage_usec" in prev else prev.get("cpu_usec")
                    dt = s["timestamp"] - prev["timestamp"]
                    
                    if dt > 0 and prev_cpu is not None:
                        diff = cpu - prev_cpu
                        cpu_cores.append((diff / dt) / 1_000_000)

            if not mem_values: return None, "No valid metrics"
            
            cold_start = phases["running_time"] - phases["start"]
            throttled_events = (throttled_list[-1] - throttled_list[0]) if len(throttled_list) > 1 else 0

            return {
                "peak_mem_bytes": max(mem_values),
                "avg_mem_bytes": sum(mem_values)/len(mem_values),
                "avg_cpu_cores": sum(cpu_cores)/len(cpu_cores) if cpu_cores else 0,
                "cold_start_time": cold_start,
                "throttled_events": throttled_events
            }, None

    # handles log streaming and monitoring sync
    def _execute_benchmark(self, pod_name, env, cgroup, stop_event, samples, phase_ts):
        monitor_started = False
        t_mon = threading.Thread(target=self.monitor_cgroup, args=(cgroup, self.args.interval, stop_event, samples))
        print("   streaming logs...")
        stdout_lines = []

        proc = subprocess.Popen(
            ["kubectl", "logs", "-f", pod_name, "-n", self.args.ns],
            stdout=subprocess.PIPE, text=True, env=env
        )

        try:
            for line in iter(proc.stdout.readline, ''):
                print(f"   [pod] {line.strip()}")
                stdout_lines.append(line)

                if "BENCH_START" in line and not monitor_started:
                    phase_ts["bench_start"] = time.time()
                    t_mon.start()
                    monitor_started = True
                    print("   [monitor] STARTED")

                if "BENCH_END" in line and monitor_started:
                    phase_ts["end"] = time.time()
                    stop_event.set()
                    print("   [monitor] STOPPED (waiting for final metrics...)")

        finally:
            if monitor_started:
                stop_event.set()
                if t_mon.is_alive():
                    t_mon.join()
            proc.terminate()
            proc.communicate()
        
        return "".join(stdout_lines)

    # handles parsing, metrics calculation and saving
    def _process_and_save_results(self, trial_idx, matrix_size, suffix, phase_ts, raw_output, samples):
        parsed = self.parse_output(raw_output)
        trial_entry = {
            "trial": trial_idx,
            "phases": phase_ts,
            "parsed_metrics": parsed,
            "samples": samples
        }

        additional, _ = self.compute_additional_metrics(trial_entry)
        if additional:
            trial_entry["additional_metrics"] = additional
        
        key = f"{matrix_size}_{suffix}"
        if key not in self.results:
            self.results[key] = []

        self.results[key].append(trial_entry)
        self._save_checkpoint()

    # handles full pod cleanup after the trial, so that there arent any conflicts at the next one
    def _cleanup_pod(self, pod_name, env):
        print("   cleanup...")
        kubectl(["delete", "pod", pod_name, "-n", self.args.ns, "--grace-period=0", "--force"], env=env)
        for _ in range(15):
            if not kubectl_pod_exists(pod_name, self.args.ns, env):
                break
            time.sleep(1)


    # the big guns. orchestrates a single experiment
    def run_trial(self, trial_idx, matrix_size, warmup):
        suffix = 'w' if warmup else 'nw'
        pod_name = f"bench-{self.args.runtime_class}-{matrix_size}-{trial_idx}-{suffix}"
        print(f"\n--- trial {trial_idx}: {pod_name} (size={matrix_size}) ---")

        env = os.environ.copy()
        if "KUBECONFIG" not in env:
            env["KUBECONFIG"] = DEFAULT_KUBECONFIG
        manifest = self.create_pod_yaml(pod_name, matrix_size, self.args.duration, warmup)
        phase_ts = {"start": time.time()}

        try:
            uid, cgroup, running_time = self.prepare_pod(pod_name, manifest, env)
            phase_ts["running_time"] = running_time
            
            stop_event = threading.Event()
            samples = []
            raw_output = self._execute_benchmark(pod_name, env, cgroup, stop_event, samples, phase_ts)

            self._process_and_save_results(trial_idx, matrix_size, suffix, phase_ts, raw_output, samples)
            print("   trial saved.")


        except Exception as e:
            print(f"   [error] trial failed: {e}")
        
        finally:
            self._cleanup_pod(pod_name, env)

    # quick console report showing completion status
    def print_summary(self):

        print("\n" + "="*50)
        print(f"  SUMMARY CHECKER: {self.results_file}")
        print("="*50)
        suffix = 'w' if self.args.warmup else 'nw'
        for size in self.args.sizes:
            key = f"{size}_{suffix}"
            count = len(self.results.get(key, []))
            print(f"{key:<15} | Completed: {count}/{self.args.trials}")

# -------------------
# Main
# -------------------
if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--image", required=True)
    parser.add_argument("--runtime_class", required=True)
    parser.add_argument("--ns", default="default")
    parser.add_argument("--output", default="bench_results.json")
    parser.add_argument("--sizes", nargs='+', type=int, default=[512, 1024])
    parser.add_argument("--trials", type=int, default=5)
    parser.add_argument("--duration", type=float, default=10.0)
    parser.add_argument("--interval", type=float, default=1.0)
    parser.add_argument("--warmup", action='store_true')
    parser.add_argument("--cpu", default="1000m")
    parser.add_argument("--memory", default="1024Mi")
    args = parser.parse_args()

    # cgroup access needs root. force sudo
    if os.geteuid() != 0:
        print("error: run with sudo")
        exit(1)

    # init orchestrators
    orch = PodOrchestrator(args)
    suffix = 'w' if args.warmup else 'nw'

    # iterates sizes, checks checkpoints, runs trails
    for size in args.sizes:
        key = f"{size}_{suffix}"
        stored_data = orch.results.get(key, [])
        
        # smart resume. checks if trial is already valid in json
        completed_trials = {
            e['trial'] for e in stored_data 
            if e.get("parsed_metrics", {}).get("valid") and e.get("additional_metrics")
        }

        for i in range(args.trials):
            if i in completed_trials:
                print(f"--- trial {i} for {key} already done (valid), skipping. ---")
                continue
            
            orch.run_trial(i, size, args.warmup)

    orch.print_summary()
    print("\nbenchmark suite done.")