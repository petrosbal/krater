# Workloads

Each workload is a folder with one source file, for instance `workloads/matmul/matmul.c`. The file name without the extension names every image built from it, as in `krater:matmul_native`. KRATER supports C workloads for now.

## Writing one

A workload includes the runner and defines three functions. The runner owns `main`, the timing and the output.

```c
#include "workload_runner.h"

static void bench_setup(void)  { /* once, before timing */ }
static void bench_unit(void)   { /* the measured unit */ }
static void bench_report(long units, double elapsed) { /* once, after timing */ }
```

* **Read a parameter**: Call `krater_param_int(name, fallback)` in `bench_setup`, or `krater_param_double` for decimals. It returns the parameter's value from `run.params` in `krater.yaml`, or `fallback` when `run.params` doesn't list it.
* **Report a metric**: Call `krater_add_num(name, value)` or `krater_add_bool(name, value)` in `bench_report`. The metric appears in the trial's result next to `units` and `elapsed_seconds`.
* **Stop on an error**: Print the reason to stderr and call `exit(1)`. The trial is saved as failed.

The full API is described at the top of [src/workload_runner.h](../src/workload_runner.h), and [matmul/matmul.c](matmul/matmul.c) is a complete workload.

## Running it

1. Set `build.workload.source` in `krater.yaml` to the new file.
2. Run `make build-images`, then `make status`.
3. Set `run.params` to the workload's parameters, and pick a new `run.name`.
4. Run `make run`.

The metrics are in each trial's `result`, under `results/<name>/`, described in [docs/RESULTS.md](../docs/RESULTS.md).
