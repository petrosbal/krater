import yaml
import subprocess
import sys
from pathlib import Path

YAML_FILE = "src/bench_config.yaml"
SCRIPT_NAME = "src/single_env_bench.py"
PYTHON_EXEC = sys.executable # i use the orchestrator's interpreter for the single env script

WARMUP_DURATION       = 5   # seconds. matches warmup loop in mmb.c
POD_OVERHEAD_ESTIMATE = 15  # seconds per trial (delete, apply, uid/running wait, cleanup)

# k (lowercase) is the canonical K8s prefix (not a typo)
SUFFIX_MAP = [
    ("Ki", 1024), ("Mi", 1024**2), ("Gi", 1024**3), ("Ti", 1024**4),
    ("k",  1000), ("M",  1000**2), ("G",  1000**3), ("T",  1000**4),
]

REQUIRED_SHARED_KEYS = frozenset({
    "results_subfolder_name",
    "sizes",
    "trials",
    "duration",
    "warmup",
    "interval",
    "namespace",
    "cpu",
    "memory",
})

REQUIRED_ENV_KEYS = frozenset({"image", "runtime_class"})

def load_config(path):
    with open(path, 'r') as f:
        return yaml.safe_load(f)

def validate_config(config):
    # top-level structure
    if not isinstance(config, dict):
        print("YAML error: config is empty or not a valid mapping")
        return False

    # environments: must be a non-empty list of valid entries
    envs = config.get("environments")
    if not isinstance(envs, list) or not envs:
        print("YAML error: 'environments' must be a non-empty list")
        return False

    for i, env in enumerate(envs):
        if not isinstance(env, dict):
            print(f"YAML error: environments[{i}] must be a mapping")
            return False
        env_keys = set(env)
        if missing := REQUIRED_ENV_KEYS - env_keys:
            print(f"YAML error: environments[{i}] missing required keys: {', '.join(sorted(missing))}")
            return False
        if unknown := env_keys - REQUIRED_ENV_KEYS:
            print(f"YAML error: environments[{i}] has unknown keys: {', '.join(sorted(unknown))}")
            return False

    # shared_args: must be a mapping with exactly the required keys
    shared = config.get("shared_args")
    if not isinstance(shared, dict):
        print("YAML error: 'shared_args' must be a mapping")
        return False

    shared_keys = set(shared)
    if missing := REQUIRED_SHARED_KEYS - shared_keys:
        print(f"YAML error: 'shared_args' missing required keys: {', '.join(sorted(missing))}")
        return False
    if unknown := shared_keys - REQUIRED_SHARED_KEYS:
        print(f"YAML error: 'shared_args' has unknown keys: {', '.join(sorted(unknown))}")
        return False

    return True

def check_oom(sizes, memory_str):
    limit = parse_memory_bytes(memory_str)
    for n in sizes:
        required = 3 * n * n * 8
        if required > limit:
            print(f"OOM: N={n} needs {required // 1024**2}Mi for matrix allocation alone, limit is {limit // 1024**2}Mi")
            return False
    return True

def parse_memory_bytes(s):
    s = str(s)
    for suffix, mult in SUFFIX_MAP:
        if s.endswith(suffix):
            return int(s[:-len(suffix)]) * mult
    return int(s)

def estimate_duration(config):
    shared = config['shared_args']
    warmup = WARMUP_DURATION if shared['warmup'] else 0
    per_trial = shared['duration'] + warmup + POD_OVERHEAD_ESTIMATE
    return len(config['environments']) * len(shared['sizes']) * shared['trials'] * per_trial

def format_duration(seconds):
    h, rem = divmod(int(seconds), 3600)
    m, s = divmod(rem, 60)
    if h > 0: return f"{h}h {m}m"
    if m > 0: return f"{m}m {s}s"
    return f"{s}s"

def construct_command(script_path, shared_args, env_args):
    # merge arguments
    final_args = shared_args.copy()
    final_args.update(env_args)

    # remove non-script, orchestrator-only arg
    subfolder = final_args.pop('results_subfolder_name')

    # handle output dir & filename
    # for instance, results/test_bench/mmb-debian_default.json
    output_dir = Path("results") / subfolder
    output_dir.mkdir(parents=True, exist_ok=True)

    # clean the image name a bit (mmb-debian:latest -> mmb-debian)
    safe_image_name = final_args['image'].split(':')[0]
    safe_runtime = final_args['runtime_class']
    output_filename = output_dir / f"{safe_image_name}_{safe_runtime}.json"

    # add output to dictionary to get processed by the loop later on
    final_args['output'] = str(output_filename)

    # build the command
    cmd = [PYTHON_EXEC, script_path]

    for key, value in final_args.items():
        arg_flag = f"--{key}"

        if isinstance(value, bool):
            # boolean (flags): either include the flag or not (for the warmup one)
            if value:
                cmd.append(arg_flag)

        elif isinstance(value, list):
            # list (nargs='+'): --sizes 512 1024
            cmd.append(arg_flag)
            cmd.extend([str(v) for v in value])

        else:
            # standard key-value
            cmd.append(arg_flag)
            cmd.append(str(value))

    return cmd

def run():
    if not Path(YAML_FILE).exists():
        print(f"Config file '{YAML_FILE}' not found.")
        return

    try:
        config = load_config(YAML_FILE)
    except yaml.YAMLError as e:
        print(f"YAML error: {e}")
        return
    if not validate_config(config):
        return
    if not check_oom(config['shared_args']['sizes'], config['shared_args']['memory']):
        return

    estimated = estimate_duration(config)
    print(f"Estimated duration: ~{format_duration(estimated)}")
    print("(approximate - does not account for completed checkpoints)")
    if input("Continue? [y/n] ").strip().lower() != 'y':
        print("Aborted.")
        return

    print(f"Orchestrator started. Found {len(config['environments'])} environments.")

    for i, env in enumerate(config['environments'], 1):
        print(f"\n{'='*60}")
        print(f"[run {i}/{len(config['environments'])}] image: {env['image']} | runtime: {env['runtime_class']}")

        try:
            cmd = construct_command(SCRIPT_NAME, config['shared_args'], env)
            subprocess.run(cmd, check=True)

            print("done.")

        except subprocess.CalledProcessError as e:
            print(f"Failed with exit code {e.returncode}. Aborting {env} env, moving to the next one.")
        except Exception as e:
            print(f"Unexpected error: {e}")
            break

    print(f"\n{'='*60}")
    print("Orchestration finished.")

if __name__ == "__main__":
    run()
