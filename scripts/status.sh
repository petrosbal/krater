#!/usr/bin/env bash
set -uo pipefail

GREEN=$'\033[1;32m'
RESET=$'\033[0m'

printf "\n- KRATER IMAGE STATUS -\n"
printf -- "--------------------------------------------\n"
printf "%-25s %-11s %-10s\n" "IMAGE" "DOCKER" "K3S"

D=$(docker images --format "{{.Repository}}:{{.Tag}}")
K=$(sudo k3s ctr images list)

for image in "$@"; do
    d="[    ]"; k="[    ]"; dc="$RESET"; kc="$RESET"
    echo "$D" | grep -q "$image" && { d="[ ok ]"; dc="$GREEN"; }
    echo "$K" | grep -q "$image" && { k="[ ok ]"; kc="$GREEN"; }
    printf "%-25s ${dc}%-10s${RESET} ${kc}%-10s${RESET}\n" "$image" "$d" "$k"
done
printf "\n"
