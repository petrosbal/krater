#!/usr/bin/env bash
set -euo pipefail

RED=$'\033[1;31m'
GREEN=$'\033[1;32m'
RESET=$'\033[0m'

printf "${RED}Removing WASM runtime support...${RESET}\n"
rm -f /usr/local/bin/containerd-shim-wasmtime-v1 \
      /usr/local/bin/containerd-shim-wasmedge-v1 \
      /usr/local/bin/containerd-shim-wasmer-v1
rm -rf /opt/kwasm/
printf "${GREEN}Done. Shim binaries removed.\n"
printf "Note: RuntimeClasses are managed by K3s and cannot be removed.${RESET}\n"
