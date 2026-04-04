import yaml
import subprocess
import sys
import os
from pathlib import Path

YAML_FILE = "src/bench_config.yaml"
SCRIPT_NAME = "src/single_env_bench.py"
PYTHON_EXEC = sys.executable # i use the orchestrator's interpreter for the single env script

def load_config(path):
    with open(path, 'r') as f:
        return yaml.safe_load(f)

def validate_config(config):
    errors = []

    envs = config.get("environments")
    if not isinstance(envs, list) or not envs:
        errors.append("'environments' must be a non-empty list")
    else:
        for i, env in enumerate(envs):
            if not isinstance(env, dict):
                errors.append(f"environments[{i}] must be a mapping")
                continue
            for key in ("image", "runtime_class"):
                if key not in env:
                    errors.append(f"environments[{i}] missing required key: '{key}'")

    shared = config.get("shared_args")
    if not isinstance(shared, dict):
        errors.append("'shared_args' must be a mapping")
    elif "results_subfolder_name" not in shared:
        errors.append("shared_args missing required key: 'results_subfolder_name'")

    if errors:
        print("Config validation failed:")
        for e in errors:
            print(f"  - {e}")
        return False
    return True

def construct_command(script_path, shared_args, env_args):
    # 1. Merge arguments
    final_args = shared_args.copy()
    final_args.update(env_args)

    # 2. remove non-script, orchestrator-only arg
    subfolder = final_args.pop('results_subfolder_name')

    # 3. handle output dir & filename
    # e.g. results/test_bench/mmb-debian_default.json
    output_dir = Path("results") / subfolder
    output_dir.mkdir(parents=True, exist_ok=True)
    
    # clean the image name a bit (mmb-debian:latest -> mmb-debian)
    safe_image_name = final_args.get('image', 'unknown').split(':')[0]
    safe_runtime = final_args.get('runtime_class', 'default')
    output_filename = output_dir / f"{safe_image_name}_{safe_runtime}.json"
    
    # add output to dictionary to get processed by the loop later on
    final_args['output'] = str(output_filename)

    # build the command
    cmd = [PYTHON_EXEC, script_path]

    for key, value in final_args.items():
        if key == "namespace":
            arg_flag = "--ns"
        else:
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
    if not os.path.exists(YAML_FILE):
        print(f"Config file '{YAML_FILE}' not found.")
        return

    config = load_config(YAML_FILE)
    if not validate_config(config):
        return
    environments = config.get('environments', [])
    shared_args = config.get('shared_args', {})

    print(f"Orchestrator started. Found {len(environments)} environments.")
    
    for i, env in enumerate(environments, 1):
        print(f"\n{'='*60}")
        print(f"[Run {i}/{len(environments)}] Image: {env.get('image')} | Runtime: {env.get('runtime_class')}")
        
        try:
            cmd = construct_command(SCRIPT_NAME, shared_args, env)
            subprocess.run(cmd, check=True)
            
            print(f"SUCCESS!")

        except subprocess.CalledProcessError as e:
            print(f"Failed with exit code {e.returncode}. Aborting {env} env, moving to the next one.")
            continue
        except Exception as e:
            print(f"Unexpected error: {e}")
            break

    print(f"\n{'='*60}")
    print("Orchestration finished.")

if __name__ == "__main__":
    run()