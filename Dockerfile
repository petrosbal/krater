# =================
# INTERNAL BUILDERS
# =================

# -- C builder (native & static) --
FROM debian:bullseye-slim AS builder-c
RUN apt-get update && apt-get install -y gcc libc6-dev
WORKDIR /build
COPY ./src/mmb.c .
# 1. native compile
RUN gcc -O3 -o mmb_debian mmb.c -lm
# 2. static compile (for the scratch image)
RUN gcc -O3 -static -o mmb_static mmb.c -lm

# -- wasm builder --
FROM ghcr.io/webassembly/wasi-sdk:latest AS builder-wasm
WORKDIR /build
COPY ./src/mmb.c .
# 3. wasm compile
RUN $CC -O3 -o mmb.wasm mmb.c -lm


# ============
# FINAL IMAGES
# ============

# ---------------------------------------------------------
# 1. DEBIAN DCI
# INPUT:   mmb_debian (from builder stage)
# PROCESS: multi-stage build (runs inside debian-slim)
# OUTPUT:  docker image (~80MB) containing the binary + debian shared libraries
# WHY:     a standard, real-world Linux containerised application
# ---------------------------------------------------------
FROM debian:bullseye-slim AS debian
COPY --from=builder-c /build/mmb_debian /mmb
ENTRYPOINT ["/mmb"]


# ---------------------------------------------------------
# 2. SCRATCH (STATIC)
# INPUT:   mmb_static (from builder stage - statically linked)
# PROCESS: single-stage copy (no OS, no shell, no libraries)
# OUTPUT:  docker image (~20KB) containing only the executable
# WHY:     minimal runtime overhead. no userspace dependencies
# ---------------------------------------------------------
FROM scratch AS static
COPY --from=builder-c /build/mmb_static /mmb
ENTRYPOINT ["/mmb"]


# ---------------------------------------------------------
# 3. WASM
# INPUT:   mmb.wasm (from wasi-sdk builder stage)
# PROCESS: WASI runtime execution
# OUTPUT:  docker image (~100KB)
# WHY:     we 'll find out soon enough
# ---------------------------------------------------------
FROM scratch AS wasm
COPY --from=builder-wasm /build/mmb.wasm /
ENTRYPOINT ["/mmb.wasm"]


# ---------------------------------------------------------
# DEFAULT TARGET
# Ensures 'docker build .' defaults to the debian image
# ---------------------------------------------------------
FROM debian AS default