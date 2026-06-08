# -----------------
# INTERNAL BUILDERS
# -----------------
ARG OPTIMIZATION_LEVEL=3
# ftp.nl.debian.org avoids Fastly CDN (deb.debian.org), which has poor peering in some regions
ARG DEBIAN_MIRROR=ftp.nl.debian.org

# --------------------------------------------------------------------
# -- C builder (native & static) --
FROM debian:bullseye-20260406-slim AS builder-c
ARG OPTIMIZATION_LEVEL
ARG DEBIAN_MIRROR
RUN sed -i "s/deb.debian.org/${DEBIAN_MIRROR}/g" /etc/apt/sources.list \
    && apt-get update && apt-get install -y gcc libc6-dev
WORKDIR /build
COPY ./src/bench.c .

# 1. native compile
RUN gcc -O${OPTIMIZATION_LEVEL} -o bench_debian bench.c -lm
# 2. static compile (for the scratch image)
RUN gcc -O${OPTIMIZATION_LEVEL} -static -o bench_static bench.c -lm

# --------------------------------------------------------------------
# -- WASM builder --
FROM ghcr.io/webassembly/wasi-sdk:wasi-sdk-32 AS builder-wasm
ARG OPTIMIZATION_LEVEL
WORKDIR /build
COPY ./src/bench.c .

# 3. wasm compile
RUN $CC -O${OPTIMIZATION_LEVEL} -o bench.wasm bench.c -lm


# --------------------------------------------------------------------
# -- WASM AOT builder (Universal WASM via wasmedge compile) --
FROM debian:bullseye-20260406-slim AS builder-wasm-aot
ARG OPTIMIZATION_LEVEL
ARG DEBIAN_MIRROR
RUN sed -i "s/deb.debian.org/${DEBIAN_MIRROR}/g" /etc/apt/sources.list \
    && apt-get update && apt-get install -y curl && rm -rf /var/lib/apt/lists/*
RUN curl -sSfL https://github.com/WasmEdge/WasmEdge/releases/download/0.14.1/WasmEdge-0.14.1-ubuntu20.04_x86_64.tar.gz \
    | tar -xz -C /usr/local --strip-components=1
WORKDIR /build
COPY --from=builder-wasm /build/bench.wasm .
RUN wasmedge compile --optimize ${OPTIMIZATION_LEVEL} bench.wasm bench_aot.wasm


# ------------
# FINAL IMAGES
# ------------

# ---------------------------------------------------------
# 1. DEBIAN DCI
# INPUT:   bench_debian (from builder stage)
# PROCESS: multi-stage build (runs inside debian-slim)
# OUTPUT:  docker image (~30MB) containing the binary + debian shared libraries
# WHY:     a standard, real-world Linux containerised application
# ---------------------------------------------------------
FROM debian:bullseye-20260406-slim AS debian
COPY --from=builder-c /build/bench_debian /bench
ENTRYPOINT ["/bench"]


# ---------------------------------------------------------
# 2. SCRATCH (STATIC)
# INPUT:   bench_static (from builder stage - statically linked)
# PROCESS: single-stage copy (no OS, no shell, no libraries)
# OUTPUT:  docker image (~350kB) containing only the executable
# WHY:     minimal runtime overhead. no userspace dependencies
# ---------------------------------------------------------
FROM scratch AS static
COPY --from=builder-c /build/bench_static /bench
ENTRYPOINT ["/bench"]


# ---------------------------------------------------------
# 3. WASM
# INPUT:   bench.wasm (from wasi-sdk builder stage)
# PROCESS: WASI runtime execution
# OUTPUT:  docker image (~75kB)
# WHY:     whole point of this thesis...!
# ---------------------------------------------------------
FROM scratch AS wasm
COPY --from=builder-wasm /build/bench.wasm /
ENTRYPOINT ["/bench.wasm"]


# ---------------------------------------------------------
# 4. WASM AOT (Universal WASM)
# INPUT:   bench_aot.wasm (wasmedge compile output - valid .wasm with embedded native AOT section)
# PROCESS: WASI runtime via wasmedge RuntimeClass; shim detects and executes AOT section
# OUTPUT:  docker image (~2MB) containing the Universal WASM binary
# WHY:     isolates LLVM AOT backend (wasmedge) vs Cranelift JIT (wasmtime/wasmer);
#          same source and OPTIMIZATION_LEVEL as krater-wasm
# ---------------------------------------------------------
FROM scratch AS wasm-aot
COPY --from=builder-wasm-aot /build/bench_aot.wasm /bench_aot.wasm
ENTRYPOINT ["/bench_aot.wasm"]