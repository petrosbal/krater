import subprocess
import time
import json
import os
import threading
import argparse
import re
import yaml

class CgroupHandler:
    
    # stores pod uid, hunts down cgroup path to prepare for monitoring
    def __init__(self, pod_uid, custom_root = None):
        self.pod_uid = pod_uid
        self.uid_underscore = pod_uid.replace("-", "_")
        self.search_roots = [custom_root] if custom_root else ["/sys/fs/cgroup/kubepods.slice", "/sys/fs/cgroup"]
        self.path = None
        self._find_path()

    # finds location of cpu and ram usage for the running pod
    def _find_path(self):
        targets = [f"pod{self.pod_uid}", f"pod{self.uid_underscore}"]
        found_paths = []
        
        for root_str in self.search_roots:
            root_path = Path(root_str)
            if not root_path.exists():
                continue

            for path in root_path.rglob("*"):
                if any(t in path.name for t in targets):
                    if (path / "cpu.stat").exists() or (path / "cpu.acct.usage()").exists():
                        found_paths.append(path)
                        
        if not found_paths:
                    raise RuntimeError(f"Cgroup path for pod {self.pod_uid} not found")

        # choosing the correct path
        # the pod-level cgroup is the one with the least depth
        # because containers are subfolders in it
        # horrible bug to fix
        self.path = str(min(found_paths, key=lambda p: len(p.parts)))
        
        # determine version based on selected path
        self.version = 2 if (Path(self.path) / "cgroup.controllers").exists() else 1
        print(f"   [cgroup] Selected path: {self.path} (v{self.version})")

    # captures a timestamped snapshot of the metrics by parsing files
    # support cgroup v2 (certainly) and v1 (in theory)
    def read_stats(self):
        ts = time.time()
        metrics = {"timestamp": ts}
        try:
            if self.version == 2: #cgroup v2
                # CPU usage, user, system, throttled
                cpu_stat = os.path.join(self.path, "cpu.stat")
                with open(cpu_stat) as f:
                    for line in f:
                        k, v = line.strip().split()
                        if k in ["usage_usec", "user_usec", "system_usec", "nr_throttled"]:
                            metrics[k] = int(v)
                
                # RAM
                # 1. total usage (cache + RSS)
                with open(os.path.join(self.path, "memory.current")) as f:
                    metrics["mem_bytes"] = int(f.read().strip())
                
                # 2. RSS
                with open(os.path.join(self.path, "memory.stat")) as f:
                    for line in f:
                        parts = line.split()
                        if parts[0] == "anon":
                            metrics["rss_bytes"] = int(parts[1])
                            break

            else: #cgroup v1
                # CPU
                cpu_file = os.path.join(self.path, "cpuacct.usage")
                if os.path.exists(cpu_file):
                    # ns -> usec for compatibility
                    metrics["usage_usec"] = int(open(cpu_file).read().strip()) / 1000
                
                # system CPU
                stat_file = os.path.join(self.path, "cpuacct.stat")
                if os.path.exists(stat_file):
                    with open(stat_file) as f:
                        for line in f:
                            parts = line.split()
                            if parts[0] == "system":
                                # Υποθέτουμε 100Hz (1 tick = 10ms = 10000usec)
                                metrics["system_usec"] = int(parts[1]) * 10000

                # RAM (cache + rss)
                mem_file = os.path.join(self.path, "memory.usage_in_bytes")
                if os.path.exists(mem_file):
                    metrics["mem_bytes"] = int(open(mem_file).read().strip())
                
                # rss
                mem_stat = os.path.join(self.path, "memory.stat")
                if os.path.exists(mem_stat):
                    with open(mem_stat) as f:
                        for line in f:
                            parts = line.split()
                            if parts[0] == "rss":
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
        output_dir = "results"
        os.makedirs(output_dir, exist_ok=True)
        self.results_file = os.path.join(output_dir, os.path.basename(args.output))
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
        running_time = None
        while True:
            if time.time() - start_wait > 60: raise TimeoutError("timed out waiting for Running state")
            phase = kubectl_output(["get","pod",pod_name,"-n",self.args.ns,"-o","jsonpath={.status.phase}"], env)
            if phase == "Running":
                running_time = time.time()
                break
            if phase == "Succeeded": break 
            if phase == "Failed": raise RuntimeError("Pod failed to start")
            time.sleep(0.5)
            
        return uid, CgroupHandler(uid), running_time

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
            if "running_time" not in phases or "start" not in phases:
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
                    proc.wait()
            
            
        finally:
            if monitor_started:
                stop_event.set()
                if t_mon.is_alive():
                    t_mon.join()
        
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
    parser.add_argument("--kubeconfig", default=None, help="Optional path to KUBECONFIG")
    parser.add_argument("--cpu", default="1000m")
    parser.add_argument("--memory", default="1024Mi")
    args = parser.parse_args()

    # custom kubeconfig support (goes to the helpers via env)
    if args.kubeconfig:
        os.environ["KUBECONFIG_PATH"] = args.kubeconfig

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