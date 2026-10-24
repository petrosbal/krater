# Results

Each environment gets one JSON file, `results/<name>/krater_<workload>_<target>_<runtime>.json`, for instance `results/demo/krater_matmul_native_default.json`. `<name>` is `run.name` in `krater.yaml`.

```
{
  "environment": {"target": "native", "image": "krater:matmul_native", "runtime_class": "default"},
  "settings": {"duration": 5, "warmup": 0, "timeout": 120, "cpu": "1000m", "memory": "1024Mi", "interval": 0.2},
  "trials": {
    "size = 256": [
      {
        "trial": 1,
        "times": {"applied": ..., "main_start": ..., "bench_start": ..., "bench_end": ...},
        "log": ["MAIN_START", "BENCH_START", "BENCH_END", "BENCH_RESULT {...}"],
        "result": {"units": 2968, "elapsed_seconds": 5.0005, "throughput_mflops": 19915.8, "valid": true},
        "samples": [{"timestamp": ..., "cpu_seconds": ..., ...}, ...]
      }
    ]
  }
}
```

## File

* **environment**: The target, image and runtime class. The workload's name is in the image.
* **settings**: The `duration`, `warmup`, `timeout`, `cpu`, `memory` and `interval` the trials ran with, as written in `krater.yaml`.
* **trials**: The trials, keyed by parameter combination, for instance `"size = 256"`. Several parameters are sorted by name and joined by `, `.

## Trial

* **trial**: The trial's number, from 1.
* **times**: Epoch seconds. `applied` is when the harness created the pod, and `main_start`, `bench_start` and `bench_end` are when the pod printed each marker.
* **log**: Every line the pod printed, stderr included.
* **result**: `units`, `elapsed_seconds` and the workload's own metrics. `units` is how many times `bench_unit` ran in the measured window, and `elapsed_seconds` is the time it took, measured by the runner.
* **failure_reason**: `OOMKilled`, `Error` or `DeadlineExceeded`. Only on a failed trial, whose `result` is `null` and whose `times` may lack the later markers.
* **samples**: cgroup values in time order, taken every `interval` and right after each marker.

All times come from the clock of the machine the harness and the pod share.

## Measured window

The measured window runs from `bench_start` to `bench_end`. Samples start before it and end about two seconds after it. The window's first sample is the last one at or before `bench_start`, and its last sample is the first one at or after `bench_end`. Every trial with a result has both.

## Sample

Each sample has a `timestamp` in epoch seconds. A counter is the total since the container started, and the difference between two samples is what happened in between. A reading is the value at that moment, and the peak is the highest memory use since the container started.

| Field | Kind | Source |
|---|---|---|
| `cpu_seconds` | counter | `cpu.stat` `usage_usec` |
| `user_seconds` | counter | `cpu.stat` `user_usec` |
| `system_seconds` | counter | `cpu.stat` `system_usec` |
| `throttled_seconds` | counter | `cpu.stat` `throttled_usec` |
| `nice_seconds` | counter | `cpu.stat` `nice_usec` |
| `cpu_wait_seconds` | counter | `cpu.pressure` `some` `total` |
| `page_faults` | counter | `memory.stat` `pgfault` |
| `major_page_faults` | counter | `memory.stat` `pgmajfault` |
| `threads` | reading | `pids.current` |
| `memory_bytes` | reading | `memory.current` |
| `anon_memory_bytes` | reading | `memory.stat` `anon` |
| `kernel_memory_bytes` | reading | `memory.stat` `kernel` |
| `peak_memory_bytes` | peak | `memory.peak` |

`nice_seconds`, `kernel_memory_bytes` and `peak_memory_bytes` are `null` on kernels that don't provide them.

## Saved trials

A file holds every trial that has a result and samples covering its window, and every trial that failed with one of the three reasons. Any other trial runs again on the next `make run` with the same `run.name`.
