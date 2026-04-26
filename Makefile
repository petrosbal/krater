export DOCKER_BUILDKIT=1
IMAGES = krater-debian:latest krater-static:latest krater-wasm:latest
#these are auto-generated when running the dockerfile build stages.
BUILD_TOOLS = ghcr.io/webassembly/wasi-sdk:wasi-sdk-32 debian:bullseye-20260406-slim

RUNWASI_VERSION := 0.6.0
ARCH            := $(shell uname -m)

.PHONY: help image-build k3s-import reset hard-reset results-clean status setup-wasm teardown-wasm setup-docker run check-deps

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
	@bash scripts/check-deps.sh

setup-docker: ## Set up Docker to run without sudo (needs re-login)
	sudo usermod -aG docker $(USER)
	@echo "Done. Log out and back in (or run 'newgrp docker') for the change to take effect."

setup-wasm: ## Set up WASM shim binaries and restart K3s (requires sudo)
	@bash scripts/setup-wasm.sh $(RUNWASI_VERSION) $(ARCH)

teardown-wasm: ## Remove WASM shim binaries — creates clean slate (requires sudo)
	@bash scripts/teardown-wasm.sh

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
	@bash scripts/status.sh $(IMAGES)