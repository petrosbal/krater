#!/usr/bin/env bash
set -euo pipefail

RUNWASI_VERSION=${1:?usage: setup-wasm.sh <version> <arch>}
ARCH=${2:?usage: setup-wasm.sh <version> <arch>}

BLUE=$'\033[1;36m'
GREEN=$'\033[1;32m'
RESET=$'\033[0m'

printf "${BLUE}Installing runwasi v${RUNWASI_VERSION} shims...${RESET}\n"
for shim in wasmtime wasmedge wasmer; do
    printf "  Downloading containerd-shim-${shim}-v1...\n"
    curl -fsSL \
        "https://github.com/containerd/runwasi/releases/download/containerd-shim-${shim}/v${RUNWASI_VERSION}/containerd-shim-${shim}-${ARCH}-linux-musl.tar.gz" \
        -o /tmp/containerd-shim-${shim}.tar.gz
    tar xz -C /usr/local/bin -f /tmp/containerd-shim-${shim}.tar.gz ./containerd-shim-${shim}-v1
    rm /tmp/containerd-shim-${shim}.tar.gz
    printf "  ${GREEN}[ok]${RESET} containerd-shim-${shim}-v1\n"
done

printf "${BLUE}Restarting K3s (killall + start)...${RESET}\n"
k3s-killall.sh
systemctl start k3s

printf "Waiting for K3s API server"
deadline=$(( $(date +%s) + 120 ))
until kubectl get nodes >/dev/null 2>&1; do
    if [ "$(date +%s)" -ge "$deadline" ]; then
        printf "\n"
        printf "ERROR: K3s API server did not become ready within 120s\n" >&2
        kubectl get nodes >&2
        exit 1
    fi
    printf "."
    sleep 2
done
printf " ready\n"

printf "${GREEN}Done. Run 'make check-deps' to verify.${RESET}\n"
