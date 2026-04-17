# -----------------
# INTERNAL BUILDERS
# -----------------

# -- C builder (native & static) --
FROM debian:bullseye-20260406-slim AS builder-c
RUN apt-get update && apt-get install -y gcc libc6-dev
WORKDIR /build
COPY ./src/bench.c .
# 1. native compile
RUN gcc -O2 -o bench_debian bench.c -lm
# 2. static compile (for the scratch image)
RUN gcc -O2 -static -o bench_static bench.c -lm

# -- wasm builder --
FROM ghcr.io/webassembly/wasi-sdk:wasi-sdk-32 AS builder-wasm
WORKDIR /build
COPY ./src/bench.c .
# 3. wasm compile
RUN $CC -O2 -o bench.wasm bench.c -lm


# ------------
# FINAL IMAGES
# ------------

# ---------------------------------------------------------
# 1. DEBIAN DCI
# INPUT:   bench_debian (from builder stage)
# PROCESS: multi-stage build (runs inside debian-slim)
# OUTPUT:  docker image (~80MB) containing the binary + debian shared libraries
# WHY:     a standard, real-world Linux containerised application
# ---------------------------------------------------------
FROM debian:bullseye-20260406-slim AS debian
COPY --from=builder-c /build/bench_debian /bench
ENTRYPOINT ["/bench"]


# ---------------------------------------------------------
# 2. SCRATCH (STATIC)
# INPUT:   bench_static (from builder stage - statically linked)
# PROCESS: single-stage copy (no OS, no shell, no libraries)
# OUTPUT:  docker image (~20KB) containing only the executable
# WHY:     minimal runtime overhead. no userspace dependencies
# ---------------------------------------------------------
FROM scratch AS static
COPY --from=builder-c /build/bench_static /bench
ENTRYPOINT ["/bench"]


# ---------------------------------------------------------
# 3. WASM
# INPUT:   bench.wasm (from wasi-sdk builder stage)
# PROCESS: WASI runtime execution
# OUTPUT:  docker image (~100KB)
# WHY:     whole point of this thesis...!
# ---------------------------------------------------------
FROM scratch AS wasm
COPY --from=builder-wasm /build/bench.wasm /
ENTRYPOINT ["/bench.wasm"]


# ---------------------------------------------------------
# DEFAULT TARGET
# Ensures 'docker build .' defaults to the debian image
# ---------------------------------------------------------
FROM debian AS default