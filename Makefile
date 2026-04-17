export DOCKER_BUILDKIT=1
IMAGES = krater-debian:latest krater-static:latest krater-wasm:latest
#these are auto-generated when running the dockerfile build stages.
BUILD_TOOLS = ghcr.io/webassembly/wasi-sdk:wasi-sdk-32 debian:bullseye-20260406-slim

.PHONY: help image-build k3s-import reset hard-reset results-clean status setup-wasm setup-docker run check-deps

BLUE    := \033[1;36m
GREEN   := \033[1;32m
YELLOW  := \033[1;38;5;178m
RED     := \033[1;31m
MAGENTA := \033[1;35m
RESET   := \033[0m

all: help

image-build: ## Build all variants and import to k3s (requires sudo)
	docker build -t krater-debian:latest .
	docker build --target static -t krater-static:latest .
	docker build --target wasm -t krater-wasm:latest .
	$(MAKE) k3s-import

k3s-import:
	@echo "Importing to k3s..."
	bash -o pipefail -c 'docker save $(IMAGES) | sudo k3s ctr images import -'

reset: ## Remove built images from local storage and k3s
	docker rmi -f $(IMAGES) || true
	sudo k3s ctr images rm $(addprefix docker.io/library/,$(IMAGES)) || true

hard-reset: reset results-clean ## Remove everything including Dockerfile-generated build tools and results
	docker rmi -f $(BUILD_TOOLS) || true
	docker image prune -f

check-deps: ## Check all required tools are installed
	@printf "\n- DEPENDENCY CHECK -\n"
	@printf -- "--------------------------------------------\n"
	@missing=0; \
	command -v docker  >/dev/null 2>&1 && printf "  $(GREEN)[ok]$(RESET) docker\n"  || { printf "  $(RED)[!!]$(RESET) docker  — not found\n";  missing=1; }; \
	command -v k3s     >/dev/null 2>&1 && printf "  $(GREEN)[ok]$(RESET) k3s\n"     || { printf "  $(RED)[!!]$(RESET) k3s     — not found\n";     missing=1; }; \
	command -v kubectl >/dev/null 2>&1 && printf "  $(GREEN)[ok]$(RESET) kubectl\n" || { printf "  $(RED)[!!]$(RESET) kubectl — not found\n"; missing=1; }; \
	command -v python3 >/dev/null 2>&1 && printf "  $(GREEN)[ok]$(RESET) python3\n" || { printf "  $(RED)[!!]$(RESET) python3 — not found\n"; missing=1; }; \
	python3 -c "import yaml" 2>/dev/null && printf "  $(GREEN)[ok]$(RESET) pyyaml\n" || { printf "  $(RED)[!!]$(RESET) pyyaml         — not found (pip install pyyaml)\n"; missing=1; }; \
	{ test -f /opt/kwasm/bin/containerd-shim-wasmtime-v1 && test -f /opt/kwasm/bin/containerd-shim-wasmedge-v1 && test -f /opt/kwasm/bin/containerd-shim-wasmer-v1; } && printf "  $(GREEN)[ok]$(RESET) shim binaries\n" || { printf "  $(RED)[!!]$(RESET) shim binaries  — not found in /opt/kwasm/bin, is KWasm installed?\n"; missing=1; }; \
	{ test -L /usr/local/bin/containerd-shim-wasmtime-v1 && test -L /usr/local/bin/containerd-shim-wasmedge-v1 && test -L /usr/local/bin/containerd-shim-wasmer-v1; } && printf "  $(GREEN)[ok]$(RESET) shim symlinks\n" || { printf "  $(RED)[!!]$(RESET) shim symlinks  — missing in /usr/local/bin, run: make setup-wasm\n"; missing=1; }; \
	kubectl get runtimeclass wasmtime wasmedge wasmer >/dev/null 2>&1 && printf "  $(GREEN)[ok]$(RESET) runtimeclasses\n" || { printf "  $(RED)[!!]$(RESET) runtimeclasses — not found, is KWasm installed?\n"; missing=1; }; \
	printf "\n"; \
	exit $$missing

setup-docker: ## Set up Docker to run without sudo (needs re-login)
	sudo usermod -aG docker $(USER)
	@echo "Done. Log out and back in (or run 'newgrp docker') for the change to take effect."

setup-wasm: ## Set up WASM shim symlinks in /usr/local/bin (requires sudo, K3s, KWasm)
	sudo ln -sf /opt/kwasm/bin/containerd-shim-wasmtime-v1 /usr/local/bin/containerd-shim-wasmtime-v1
	sudo ln -sf /opt/kwasm/bin/containerd-shim-wasmedge-v1 /usr/local/bin/containerd-shim-wasmedge-v1
	sudo ln -sf /opt/kwasm/bin/containerd-shim-wasmer-v1 /usr/local/bin/containerd-shim-wasmer-v1

run: ## Run the full benchmark suite (requires sudo)
	sudo python3 src/metaorchestrator.py

results-clean: ## Remove the results directory contents (requires sudo)
	sudo rm -rf results/*

help: ## Show this help message
	@echo  ""
	@echo  "Usage: make $(BLUE)<target>$(RESET)"
	@echo  "-----------------------------------------------------------"
	@echo  ""
	@echo  "Setup"
	@grep -E '^[a-zA-Z_-]+:.*?## (Check|Set up).*$$' $(MAKEFILE_LIST) | awk 'BEGIN {FS = ":.*?## "}; {printf "  $(MAGENTA)%-20s$(RESET) %s\n", $$1, $$2}'
	@echo  ""
	@echo  "Build & Deployment"
	@grep -E '^[a-zA-Z_-]+:.*?## Build.*$$' $(MAKEFILE_LIST) | awk 'BEGIN {FS = ":.*?## "}; {printf "  $(BLUE)%-20s$(RESET) %s\n", $$1, $$2}'
	@echo  ""
	@echo  "Run"
	@grep -E '^[a-zA-Z_-]+:.*?## Run.*$$' $(MAKEFILE_LIST) | awk 'BEGIN {FS = ":.*?## "}; {printf "  $(GREEN)%-20s$(RESET) %s\n", $$1, $$2}'
	@echo  ""
	@echo  "Cleanup & Maintenance"
	@grep -E '^[a-zA-Z_-]+:.*?## Remove.*$$' $(MAKEFILE_LIST) | awk 'BEGIN {FS = ":.*?## "}; {printf "  $(RED)%-20s$(RESET) %s\n", $$1, $$2}'
	@echo  ""
	@echo  "Information"
	@grep -E '^[a-zA-Z_-]+:.*?## Show.*$$' $(MAKEFILE_LIST) | awk 'BEGIN {FS = ":.*?## "}; {printf "  $(YELLOW)%-20s$(RESET) %s\n", $$1, $$2}'
	@echo  ""

status: ## Show images' status in Docker and k3s storage
	@printf "\n- KRATER IMAGE STATUS -\n"
	@printf -- "--------------------------------------------\n"
	@printf "%-25s %-11s %-10s\n" "IMAGE" "DOCKER" "K3S"
	@D=$$(docker images --format "{{.Repository}}:{{.Tag}}"); \
	K=$$(sudo k3s ctr images list); \
	for i in $(IMAGES); do \
		d="[    ]"; k="[    ]"; dc="$(RESET)"; kc="$(RESET)"; \
		echo "$$D" | grep -q "$$i" && { d="[ ok ]"; dc="$(GREEN)"; }; \
		echo "$$K" | grep -q "$$i" && { k="[ ok ]"; kc="$(GREEN)"; }; \
		printf "%-25s %b%-10s%b %b%-10s%b\n" "$$i" "$$dc" "$$d" "$(RESET)" "$$kc" "$$k" "$(RESET)"; \
	done
	@echo ""