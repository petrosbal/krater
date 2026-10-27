# Configuration

`krater.yaml`, at the repository root, has two sections:

* **build**: read by DICE, which derives the Dockerfile and the environments from it.
* **run**: read by the harness, which runs the benchmark session.

`make run` and `make build-images` regenerate DICE files first. After editing `build`, run `make build-images`. Editing `run` needs nothing else.

Unknown or missing keys are refused, and the refusal names the key.

## Build

| Section | Setting | Description |
|---|---|---|
| `workload` | | The one workload every target is built from. |
| | `language` | `c` or `rust`. KRATER supports C workloads for now, see [workloads/README.md](../workloads/README.md). |
| | `source` | Path to the workload's source file, relative to the repository root. Its file name without the extension names every image, as `krater:<name>_<target>`. |
| | `optimization_level` | `0` to `3`, translated into each toolchain's own flag syntax. |
| `targets` | | A non-empty list. Each target is one image built from the workload. To leave a target out, comment it out. |
| | `name` | Unique among the targets. Lowercase letters and digits, separated by `.`, `_`, `__` or `-`. |
| | `code_format` | `native` or `wasm`. |
| | `link_mode` | `dynamic` or `static`. Required for `native`, refused for `wasm`. |
| | `aot_compiler` | `wasmedge`. Only for a C `wasm` target, which then runs under the runtime of the same name. |

## Run

| Setting | Description |
|---|---|
| `runtimes` | The runtime classes to run, out of those DICE generated. `default` is runc. |
| `params` | Each workload parameter with a list of values. Every combination gets its own trials, and each value reaches the pod as an environment variable named after the parameter. |
| `trials` | Trials per environment and parameter combination. |
| `duration` | Seconds of the workload's measured loop. Set it to 0 to run the unit only once per trial. |
| `warmup` | Seconds of unmeasured loop before it, `0` for none. |
| `timeout` | Seconds before Kubernetes ends the pod. |
| `interval` | Seconds between cgroup samples. |
| `namespace` | The Kubernetes namespace for the trial pod. It must already exist. |
| `cpu` | The pod's CPU request and limit, as a Kubernetes quantity (for instance, `1000m` is one core, `1000` a thousand cores). |
| `memory` | The pod's memory request and limit, as a Kubernetes quantity (for instance, `1024Mi`). |
| `name` | Results go to `results/<name>/`. Running again under the same name resumes the run, and more trials, parameter values or runtimes extend it. Changing `duration`, `warmup`, `timeout`, `interval`, `cpu` or `memory` under the same name is refused. |
