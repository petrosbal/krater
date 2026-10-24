# Automatically generated from krater.yaml with the power of Prolog.
# You probably don't want to edit this file.

FROM gcc:14-trixie AS builder_gcc
WORKDIR /build
COPY src/workload_runner.h workload_runner.h
COPY workloads/matmul/matmul.c matmul.c
RUN gcc -O3 -s -o matmul matmul.c
RUN gcc -O3 -s -static -o matmul_static matmul.c

FROM ghcr.io/webassembly/wasi-sdk:wasi-sdk-32 AS builder_wasi_sdk
WORKDIR /build
COPY src/workload_runner.h workload_runner.h
COPY workloads/matmul/matmul.c matmul.c
RUN $CC -O3 -Wl,--strip-all -o matmul.wasm matmul.c

FROM debian:trixie-slim AS builder_wasmedge
ADD https://github.com/WasmEdge/WasmEdge/releases/download/0.14.1/WasmEdge-0.14.1-ubuntu20.04_x86_64.tar.gz /tmp/wasmedge.tar.gz
RUN tar -xzf /tmp/wasmedge.tar.gz -C /usr/local --strip-components=1
WORKDIR /build
COPY --from=builder_wasi_sdk /build/matmul.wasm .
RUN wasmedge compile --optimize 3 matmul.wasm matmul_aot.wasm

FROM debian:trixie-slim AS native
COPY --from=builder_gcc /build/matmul /matmul
ENTRYPOINT ["/matmul"]

FROM scratch AS native-static
COPY --from=builder_gcc /build/matmul_static /matmul_static
ENTRYPOINT ["/matmul_static"]

FROM scratch AS wasm
COPY --from=builder_wasi_sdk /build/matmul.wasm /matmul.wasm
ENTRYPOINT ["/matmul.wasm"]

FROM scratch AS wasm-aot
COPY --from=builder_wasmedge /build/matmul_aot.wasm /matmul_aot.wasm
ENTRYPOINT ["/matmul_aot.wasm"]
