# Automatically generated from build.yaml with the power of Prolog.
# You probably don't want to edit this file.

FROM gcc:14-trixie AS builder_gcc
WORKDIR /build
COPY src/bench.c bench.c
COPY src/workload_runner.h workload_runner.h
RUN gcc -O3 -s -o bench bench.c
RUN gcc -O3 -s -static -o bench_static bench.c

FROM ghcr.io/webassembly/wasi-sdk:wasi-sdk-32 AS builder_wasi_sdk
WORKDIR /build
COPY src/bench.c bench.c
COPY src/workload_runner.h workload_runner.h
RUN $CC -O3 -Wl,--strip-all -o bench.wasm bench.c

FROM debian:trixie-slim AS builder_wasmedge
ADD https://github.com/WasmEdge/WasmEdge/releases/download/0.14.1/WasmEdge-0.14.1-ubuntu20.04_x86_64.tar.gz /tmp/wasmedge.tar.gz
RUN tar -xzf /tmp/wasmedge.tar.gz -C /usr/local --strip-components=1
WORKDIR /build
COPY --from=builder_wasi_sdk /build/bench.wasm .
RUN wasmedge compile --optimize 3 bench.wasm bench_aot.wasm

FROM debian:trixie-slim AS native
COPY --from=builder_gcc /build/bench /bench
ENTRYPOINT ["/bench"]

FROM scratch AS native-static
COPY --from=builder_gcc /build/bench_static /bench_static
ENTRYPOINT ["/bench_static"]

FROM scratch AS wasm
COPY --from=builder_wasi_sdk /build/bench.wasm /bench.wasm
ENTRYPOINT ["/bench.wasm"]

FROM scratch AS wasm-aot
COPY --from=builder_wasmedge /build/bench_aot.wasm /bench_aot.wasm
ENTRYPOINT ["/bench_aot.wasm"]
