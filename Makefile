export DOCKER_BUILDKIT=1
IMAGES = krater-debian:latest krater-static:latest krater-wasm:latest krater-wasm-aot:latest

RUNWASI_VERSION := 0.6.0
ARCH            := $(shell uname -m)

.PHONY: help build-images remove-images teardown clean-results status setup-wasm teardown-wasm setup-docker run check-deps config

BLUE    := \033[1;36m
GREEN   := \033[1;32m
YELLOW  := \033[1;38;5;178m
RED     := \033[1;31m
MAGENTA := \033[1;35m
RESET   := \033[0m

all: help

build-images: ## Build all variants and import to k3s *
	docker build --target debian -t krater-debian:latest .
	docker build --target static -t krater-static:latest .
	docker build --target wasm -t krater-wasm:latest .
	docker build --target wasm-aot -t krater-wasm-aot:latest .
	@echo "Importing to k3s..."
	@bash -o pipefail -c 'docker save $(IMAGES) | sudo k3s ctr images import - > /dev/null'

check-deps: ## Check all required tools are installed
	@bash scripts/check-deps.sh

setup-wasm: ## Set up WASM shim binaries and restart K3s *
	@sudo bash scripts/setup-wasm.sh $(RUNWASI_VERSION) $(ARCH)

setup-docker: ## Set up Docker to run without sudo (needs re-login)
	sudo usermod -aG docker $(USER)
	@echo "Done. Log out and back in (or run 'newgrp docker') for the change to take effect."

config: ## Configure benchmark (opens bench_config.yaml in default editor)
	@$${EDITOR:-nano} src/bench_config.yaml

run: ## Run the full benchmark suite *
	sudo python3 src/metaorchestrator.py
	@if [ -n "$(SUDO_UID)" ]; then chown -R $(SUDO_UID):$(SUDO_GID) results/; fi

clean-results: ## Remove the results directory contents *
	sudo rm -rf results/*

remove-images: ## Remove built images from local Docker and k3s storage
	docker rmi -f $(IMAGES) || true
	sudo k3s ctr images rm $(addprefix docker.io/library/,$(IMAGES)) || true

teardown-wasm: ## Uninstall WASM shim binaries from /usr/local/bin *
	@sudo bash scripts/teardown-wasm.sh

teardown: remove-images clean-results teardown-wasm ## Remove images, results and WASM shims (full reset)

help: ## Show this help message
	@bash scripts/banner.sh
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
	@echo  "Benchmark"
	@grep -E '^[a-zA-Z_-]+:.*?## (Configure|Run).*$$' $(MAKEFILE_LIST) | awk 'BEGIN {FS = ":.*?## "}; {printf "  $(GREEN)%-20s$(RESET) %s\n", $$1, $$2}'
	@echo  ""
	@echo  "Cleanup & Maintenance"
	@grep -E '^[a-zA-Z_-]+:.*?## (Remove|Uninstall).*$$' $(MAKEFILE_LIST) | awk 'BEGIN {FS = ":.*?## "}; {printf "  $(RED)%-20s$(RESET) %s\n", $$1, $$2}'
	@echo  ""
	@echo  "Information"
	@grep -E '^[a-zA-Z_-]+:.*?## Show.*$$' $(MAKEFILE_LIST) | awk 'BEGIN {FS = ":.*?## "}; {printf "  $(YELLOW)%-20s$(RESET) %s\n", $$1, $$2}'
	@echo  ""
	@echo  "* requires sudo"
	@echo  ""

status: ## Show images' status in Docker and k3s storage
	@bash scripts/status.sh $(IMAGES)