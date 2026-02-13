export DOCKER_BUILDKIT=1
IMAGES = mmb-debian:latest mmb-static:latest mmb-wasm:latest
#these are auto-generated when running the dockerfile build stages.
BUILD_TOOLS = ghcr.io/webassembly/wasi-sdk:latest debian:bullseye-slim

.PHONY: help image-build k3s-import reset hard-reset results-clean status

BLUE   := \033[1;36m
GREEN  := \033[1;32m
YELLOW := \033[1;38;5;178m
RESET  := \033[0m
BOLD   := \033[1m

all: help

image-build: ## Build all variants and import to k3s (requires sudo)
	docker build -t mmb-debian:latest .
	docker build --target static -t mmb-static:latest .
	docker build --target wasm -t mmb-wasm:latest .
	$(MAKE) k3s-import

k3s-import:
	@echo "Importing to k3s..."
	docker save $(IMAGES) | sudo k3s ctr images import -

reset: ## Remove built images from local storage and k3s
	docker rmi -f $(IMAGES) || true
	docker image prune -f
	sudo k3s ctr images rm $(addprefix docker.io/library/,$(IMAGES)) || true

hard-reset: reset ## Remove everything including Dockerfile-generated build tools
	docker rmi -f $(BUILD_TOOLS) || true
	docker image prune -a -f

results-clean: ## Remove the ./results directory
	sudo rm -rf ./results

help: ## Show this help message
	@echo  ""
	@echo  "$(BOLD)Usage:$(RESET) make $(BLUE)<target>$(RESET)"
	@echo  "-----------------------------------------------------------"
	@echo  ""
	@echo  "$(BOLD)Build & Deployment$(RESET)"
	@grep -E '^[a-zA-Z_-]+:.*?## Build.*$$' $(MAKEFILE_LIST) | awk 'BEGIN {FS = ":.*?## "}; {printf "  $(BLUE)%-20s$(RESET) %s\n", $$1, $$2}'
	@echo  ""
	@echo  "$(BOLD)Cleanup & Maintenance$(RESET)"
	@grep -E '^[a-zA-Z_-]+:.*?## Remove.*$$' $(MAKEFILE_LIST) | awk 'BEGIN {FS = ":.*?## "}; {printf "  $(GREEN)%-20s$(RESET) %s\n", $$1, $$2}'
	@echo  ""
	@echo  "$(BOLD)Information$(RESET)"
	@grep -E '^[a-zA-Z_-]+:.*?## Show.*$$' $(MAKEFILE_LIST) | awk 'BEGIN {FS = ":.*?## "}; {printf "  $(YELLOW)%-20s$(RESET) %s\n", $$1, $$2}'
	@echo  ""

status: ## Show images' status in Docker and k3s storage
	@printf "\n$(BOLD)MMB IMAGE STATUS$(RESET)\n"
	@printf -- "--------------------------------------------\n"
	@printf "$(BOLD)%-25s %-11s %-10s$(RESET)\n" "IMAGE" "DOCKER" "K3S"
	@D=$$(docker images --format "{{.Repository}}:{{.Tag}}"); \
	K=$$(sudo k3s ctr images list); \
	for i in $(IMAGES); do \
		d="[    ]"; k="[    ]"; dc="$(RESET)"; kc="$(RESET)"; \
		echo "$$D" | grep -q "$$i" && { d="[ ok ]"; dc="$(GREEN)"; }; \
		echo "$$K" | grep -q "$$i" && { k="[ ok ]"; kc="$(GREEN)"; }; \
		printf "%-25s %b%-10s%b %b%-10s%b\n" "$$i" "$$dc" "$$d" "$(RESET)" "$$kc" "$$k" "$(RESET)"; \
	done
	@echo ""