#!/usr/bin/env bash
set -uo pipefail

GREEN=$'\033[1;32m'
RED=$'\033[1;31m'
RESET=$'\033[0m'

missing=0

printf "\n- DEPENDENCY CHECK -\n"
printf -- "--------------------------------------------\n"

# docker check
if command -v docker >/dev/null 2>&1; then
    printf "  %s[ok]%s docker\n" "${GREEN}" "${RESET}"
else
    printf "  %s[!!]%s docker         - not found  (curl -fsSL https://get.docker.com | sh)\n" "${RED}" "${RESET}"; missing=1
fi

# k3s check and version
if command -v k3s >/dev/null 2>&1; then
    K3S_MINOR=$(k3s --version 2>/dev/null | grep -oP 'v1\.\K[0-9]+')
    if [ -n "$K3S_MINOR" ] && [ "$K3S_MINOR" -ge 34 ]; then
        printf "  %s[ok]%s k3s v1.%s (≥ v1.34)\n" "${GREEN}" "${RESET}" "${K3S_MINOR}"
    else
        printf "  %s[!!]%s k3s - v1.34+ required (found v1.%s)\n" "${RED}" "${RESET}" "${K3S_MINOR}"; missing=1
    fi
else
    printf "  %s[!!]%s k3s            - not found  (curl -sfL https://get.k3s.io | sh -)\n" "${RED}" "${RESET}"; missing=1
fi

# kubectl check
if command -v kubectl >/dev/null 2>&1; then
    printf "  %s[ok]%s kubectl\n" "${GREEN}" "${RESET}"
else
    printf "  %s[!!]%s kubectl - not found\n" "${RED}" "${RESET}"; missing=1
fi

# python3 and version check
if command -v python3 >/dev/null 2>&1; then
    PY_MINOR=$(python3 -c "import sys; print(sys.version_info.minor)" 2>/dev/null)
    PY_MAJOR=$(python3 -c "import sys; print(sys.version_info.major)" 2>/dev/null)
    if [ "$PY_MAJOR" -eq 3 ] && [ "$PY_MINOR" -ge 8 ]; then
        printf "  %s[ok]%s python 3.%s (≥ 3.8)\n" "${GREEN}" "${RESET}" "${PY_MINOR}"
    else
        printf "  %s[!!]%s python3 - 3.8+ required (found 3.%s)\n" "${RED}" "${RESET}" "${PY_MINOR}"; missing=1
    fi
else
    printf "  %s[!!]%s python3 - not found\n" "${RED}" "${RESET}"; missing=1
fi

# pyyaml check
if python3 -c "import yaml" 2>/dev/null; then
    printf "  %s[ok]%s pyyaml\n" "${GREEN}" "${RESET}"
else
    printf "  %s[!!]%s pyyaml         - not found (pip install pyyaml)\n" "${RED}" "${RESET}"; missing=1
fi

# shims check
if test -f /usr/local/bin/containerd-shim-wasmtime-v1 \
    && test -f /usr/local/bin/containerd-shim-wasmedge-v1 \
    && test -f /usr/local/bin/containerd-shim-wasmer-v1; then
    printf "  %s[ok]%s shim binaries\n" "${GREEN}" "${RESET}"
else
    printf "  %s[!!]%s shim binaries  - not found in /usr/local/bin, run: make setup-wasm\n" "${RED}" "${RESET}"; missing=1
fi

# runtimeclasses check
if sudo kubectl get runtimeclass wasmtime wasmedge wasmer >/dev/null 2>&1; then
    printf "  %s[ok]%s runtimeclasses\n" "${GREEN}" "${RESET}"
else
    printf "  %s[!!]%s runtimeclasses - not found, run: make setup-wasm\n" "${RED}" "${RESET}"; missing=1
fi

printf "\n"
exit $missing
