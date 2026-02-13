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

def construct_command(script_path, shared_args, env_args):
    # 1. Merge arguments
    final_args = shared_args.copy()
    final_args.update(env_args)

    # 2. remove non-script, orcehstrator-only arg
    subfolder = final_args.pop('results_subfolder_name', 'results')
    
    # 3. handle output dir & filename
    # e.g. ./initial/mmb-debian_default.json
    output_dir = Path(subfolder)
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
    environments = config.get('environments', [])
    shared_args = config.get('shared_args', {})

    print(f"Orchestrator started. Found {len(environments)} environments.")
    
    for i, env in enumerate(environments, 1):
        print(f"\n{'='*60}")
        print(f"[Run {i}/{len(environments)}] Image: {env.get('image')} | Runtime: {env.get('runtime_class')}")
        
        try:
            cmd = construct_command(SCRIPT_NAME, shared_args, env)
            #print(f"DEBUG CMD: {' '.join(cmd)}") 
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