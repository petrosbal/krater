#!/usr/bin/env bash
set -uo pipefail

GREEN=$'\033[1;32m'
RED=$'\033[1;31m'
RESET=$'\033[0m'

missing=0

printf "\n- DEPENDENCY CHECK -\n"
printf -- "--------------------------------------------\n"

command -v docker >/dev/null 2>&1 \
    && printf "  ${GREEN}[ok]${RESET} docker\n" \
    || { printf "  ${RED}[!!]${RESET} docker  — not found\n"; missing=1; }

if command -v k3s >/dev/null 2>&1; then
    K3S_MINOR=$(k3s --version 2>/dev/null | grep -oP 'v1\.\K[0-9]+')
    if [ -n "$K3S_MINOR" ] && [ "$K3S_MINOR" -ge 34 ]; then
        printf "  ${GREEN}[ok]${RESET} k3s v1.${K3S_MINOR} (≥ v1.34)\n"
    else
        printf "  ${RED}[!!]${RESET} k3s — v1.34+ required (found v1.${K3S_MINOR})\n"; missing=1
    fi
else
    printf "  ${RED}[!!]${RESET} k3s — not found\n"; missing=1
fi

command -v kubectl >/dev/null 2>&1 \
    && printf "  ${GREEN}[ok]${RESET} kubectl\n" \
    || { printf "  ${RED}[!!]${RESET} kubectl — not found\n"; missing=1; }

if command -v python3 >/dev/null 2>&1; then
    PY_MINOR=$(python3 -c "import sys; print(sys.version_info.minor)" 2>/dev/null)
    PY_MAJOR=$(python3 -c "import sys; print(sys.version_info.major)" 2>/dev/null)
    if [ "$PY_MAJOR" -eq 3 ] && [ "$PY_MINOR" -ge 8 ]; then
        printf "  ${GREEN}[ok]${RESET} python 3.${PY_MINOR} (≥ 3.8)\n"
    else
        printf "  ${RED}[!!]${RESET} python3 — 3.8+ required (found 3.${PY_MINOR})\n"; missing=1
    fi
else
    printf "  ${RED}[!!]${RESET} python3 — not found\n"; missing=1
fi

python3 -c "import yaml" 2>/dev/null \
    && printf "  ${GREEN}[ok]${RESET} pyyaml\n" \
    || { printf "  ${RED}[!!]${RESET} pyyaml         — not found (pip install pyyaml)\n"; missing=1; }

{ test -f /usr/local/bin/containerd-shim-wasmtime-v1 \
    && test -f /usr/local/bin/containerd-shim-wasmedge-v1 \
    && test -f /usr/local/bin/containerd-shim-wasmer-v1; } \
    && printf "  ${GREEN}[ok]${RESET} shim binaries\n" \
    || { printf "  ${RED}[!!]${RESET} shim binaries  — not found in /usr/local/bin, run: make setup-wasm\n"; missing=1; }

kubectl get runtimeclass wasmtime wasmedge wasmer >/dev/null 2>&1 \
    && printf "  ${GREEN}[ok]${RESET} runtimeclasses\n" \
    || { printf "  ${RED}[!!]${RESET} runtimeclasses — not found, run: make setup-wasm\n"; missing=1; }

printf "\n"
exit $missing
