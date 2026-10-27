# Getting started

This guide goes from a fresh clone to a first results file. Run every command from the repository root.

## Install the tools

KRATER runs on Linux with cgroup v2. It also needs `make`, Docker, k3s, SWI-Prolog and Python 3.10 or newer. On Ubuntu or Debian:

```bash
sudo apt update && sudo apt install make curl swi-prolog-nox python3-yaml
curl -fsSL https://get.docker.com | sh
curl -sfL https://get.k3s.io | sh -s - --write-kubeconfig-mode 644
```

`--write-kubeconfig-mode 644` lets `kubectl` reach k3s without `sudo`.

Then let Docker run without `sudo`, and reboot:

```bash
make setup-docker
```

## Check the machine

```bash
make check-deps
```

Every line should be `[ok]`. If one says `run: make setup-wasm`, run that command. It asks for `sudo`, installs the Wasm shims and restarts k3s. Repeat `make check-deps` until it prints the next step.

## Build the images

```bash
make build-images
make status
```

The first build pulls the builder images and takes longer. At the end it asks for `sudo` to import the images into k3s, and `make status` may ask again to read them.

## Start the run

```bash
make run
```

The committed `krater.yaml` is a short demo, one trial per environment and size. KRATER checks the config, the cluster and every environment, then shows the session and asks `continue? [y/N]`. Answer `y` to start. `Ctrl-C` stops it at any point, and `make run` again with the same `name` picks up where it stopped.

Each environment's trials go to one file in `results/demo/`, and everything the session printed goes to `results/demo/demo.log`. [RESULTS.md](RESULTS.md) describes both, and [CONFIGURATION.md](CONFIGURATION.md) explains every key for a full experiment.

To benchmark your own workload, see [workloads/README.md](../workloads/README.md).
