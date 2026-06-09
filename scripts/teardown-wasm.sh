#!/usr/bin/env bash
set -euo pipefail

RED=$'\033[1;31m'
GREEN=$'\033[1;32m'
RESET=$'\033[0m'

printf '%sRemoving WASM runtime support...%s\n' "${RED}" "${RESET}"
rm -f /usr/local/bin/containerd-shim-wasmtime-v1 \
      /usr/local/bin/containerd-shim-wasmedge-v1 \
      /usr/local/bin/containerd-shim-wasmer-v1
printf '%sDone. Shim binaries removed.\n' "${GREEN}"
printf 'Note: RuntimeClasses are managed by K3s and cannot be removed.%s\n' "${RESET}"
