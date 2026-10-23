export DOCKER_BUILDKIT=1
IMAGES = $(shell python3 scripts/images.py list)

RUNWASI_VERSION := 0.6.0
ARCH            := $(shell uname -m)

.PHONY: help build-images dockerfile-generation remove-images teardown clear-results status setup-wasm teardown-wasm setup-docker run check-deps config

BLUE    := \033[1;36m
GREEN   := \033[1;32m
YELLOW  := \033[1;38;5;178m
RED     := \033[1;31m
MAGENTA := \033[1;35m
RESET   := \033[0m

all: help

build-images: ## Build all targets and import to k3s *
	python3 scripts/images.py build
	@echo "Importing to k3s..."
	@bash -o pipefail -c 'docker save $(IMAGES) | sudo k3s ctr images import - > /dev/null'

dockerfile-generation: ## Generate dice/generated/ from build.yaml *
	@swipl dice/main.pl --arch=$(ARCH)

check-deps: ## Check all required tools are installed
	@bash scripts/check-deps.sh

setup-wasm: ## Set up WASM shim binaries and restart K3s *
	@sudo bash scripts/setup-wasm.sh $(RUNWASI_VERSION) $(ARCH)

setup-docker: ## Set up Docker to run without sudo (needs re-login)
	sudo usermod -aG docker $(USER)
	@echo "Done. Log out and back in (or run 'newgrp docker') for the change to take effect."

config: ## Configure benchmark (opens krater.yaml in default editor)
	@$${EDITOR:-nano} krater.yaml

run: ## Run the full benchmark suite
	python3 src/krater.py

clear-results: ## Remove the results directory contents
	rm -rf ./results/*

remove-images: ## Remove built images from local Docker and k3s storage
	docker rmi -f $(IMAGES) || true
	sudo k3s ctr images rm $(addprefix docker.io/library/,$(IMAGES)) || true

teardown-wasm: ## Uninstall WASM shim binaries from /usr/local/bin *
	@sudo bash scripts/teardown-wasm.sh

teardown: remove-images clear-results teardown-wasm ## Remove images, results and WASM shims (full reset)

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