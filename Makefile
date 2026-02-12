export DOCKER_BUILDKIT=1
IMAGES = mmb-debian:latest mmb-static:latest mmb-wasm:latest

.PHONY: dall ddebian dstatic dwasm dclean kclean resclean

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

# attention! it deletes every pod in the cluster
kclean:
	kubectl delete pods --all --force --grace-period=0

resclean:
	sudo rm -rf ./results