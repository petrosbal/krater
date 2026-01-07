export DOCKER_BUILDKIT=1
IMAGES = mmb-debian:latest mmb-static:latest mmb-wasm:latest

.PHONY: dall dclean ddebian dstatic dwasm dclean kclean

# dci builds

dall: ddebian dstatic dwasm

ddebian:
	docker build -t mmb-debian:latest .
	@echo "Importing to K3s..."
	docker save mmb-debian:latest | sudo k3s ctr images import -

dstatic:
	docker build --target static -t mmb-static:latest .
	@echo "Importing to K3s..."
	docker save mmb-static:latest | sudo k3s ctr images import -

dwasm:
	docker build --target wasm -t mmb-wasm:latest .
	@echo "Importing to K3s..."
	docker save mmb-wasm:latest | sudo k3s ctr images import -

# cleanup

dclean:
	docker rmi -f $(IMAGES) || true
	docker image prune -f

kclean:
	kubectl delete pods --all --force --grace-period=0