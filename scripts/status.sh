#!/usr/bin/env bash
set -uo pipefail

GREEN=$'\033[1;32m'
RESET=$'\033[0m'

D=$(docker images --format "{{.Repository}}:{{.Tag}}")
K=$(sudo k3s ctr images list --quiet)

printf "\n- KRATER IMAGE STATUS -\n"
printf -- "----------------------------------------------------------\n"
printf "%-40s %-11s %-10s\n" "IMAGE" "DOCKER" "K3S"

# no images listed means nothing is ready either
all_ready=$(( $# > 0 ))
for image in "$@"; do
    d="[    ]"; k="[    ]"; dc="$RESET"; kc="$RESET"
    echo "$D" | grep -qxF "$image" && { d="[ ok ]"; dc="$GREEN"; }
    echo "$K" | grep -qxF "docker.io/library/$image" && { k="[ ok ]"; kc="$GREEN"; }
    [ "$k" = "[ ok ]" ] || all_ready=0
    printf "%-40s ${dc}%-10s${RESET} ${kc}%-10s${RESET}\n" "$image" "$d" "$k"
done
printf "\n"
if [ "$all_ready" -eq 1 ]; then
    printf "next: make run\n\n"
else
    printf "run make build-images\n\n"
fi
