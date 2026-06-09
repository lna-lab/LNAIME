# =============================================================================
# LNAIME Tier-2 faithful-conversion container (AzooKey Zenzai + CUDA sm_120)
# Strategy: hazkey-pinned pair (converter fork @8b4befc + 7ka-hiira/llama.cpp
# @10295c26), llama.cpp as SHARED libs with GGML_CUDA=ON (hazkey's Vulkan flipped
# to CUDA), then `swift build --traits Zenzai`.
# De-risk order: build llama.cpp CUDA FIRST (cheap to fail) before the Swift download.
#   docker build -t lnaime-zenzai:cuda .
# =============================================================================
FROM nvidia/cuda:12.8.1-devel-ubuntu24.04 AS build

ARG CUDA_ARCH=120
ARG CONVERTER_REF=8b4befc
ARG LLAMA_REF=10295c26a2a18c3c48863b179c5e6bf34a4057d1
ARG SWIFT_VERSION=swift-6.2-RELEASE
ENV DEBIAN_FRONTEND=noninteractive

RUN apt-get update && apt-get install -y --no-install-recommends \
        binutils git curl wget ca-certificates unzip gnupg2 \
        libc6-dev libcurl4-openssl-dev libedit2 libgcc-13-dev libpython3-dev \
        libsqlite3-0 libstdc++-13-dev libxml2-dev libncurses-dev libz3-dev \
        pkg-config tzdata zlib1g-dev build-essential cmake ninja-build \
    && rm -rf /var/lib/apt/lists/*

# ---- DE-RISK: build llama.cpp CUDA shared libs FIRST -------------------------
RUN nvcc --list-gpu-arch | grep -q compute_120 && echo "sm_120 supported"
RUN git clone https://github.com/7ka-hiira/llama.cpp.git /src/llama.cpp \
    && git -C /src/llama.cpp checkout ${LLAMA_REF}
RUN cmake -S /src/llama.cpp -B /src/llama-build -G Ninja \
        -DCMAKE_BUILD_TYPE=Release \
        -DBUILD_SHARED_LIBS=ON \
        -DGGML_BACKEND_DL=ON \
        -DGGML_CPU=ON \
        -DGGML_NATIVE=OFF \
        -DGGML_CPU_ALL_VARIANTS=ON \
        -DLLAMA_CURL=OFF \
        -DLLAMA_STANDALONE=OFF \
        -DGGML_VULKAN=OFF \
        -DGGML_CUDA=ON \
        -DGGML_HIP=OFF \
        -DCMAKE_CUDA_ARCHITECTURES=${CUDA_ARCH} \
    && cmake --build /src/llama-build -j"$(nproc)"
RUN set -eux; \
    mkdir -p /opt/zenzai/libllama/backends /tmp/_so; \
    find /src/llama-build -name 'lib*.so*' -exec cp -av {} /tmp/_so/ \; ; \
    echo "=== produced .so ==="; ls -l /tmp/_so; \
    cp -av /tmp/_so/libllama.so* /opt/zenzai/libllama/ 2>/dev/null || true; \
    cp -av /tmp/_so/libggml.so* /tmp/_so/libggml-base.so* /opt/zenzai/libllama/ 2>/dev/null || true; \
    for f in /tmp/_so/libggml-cpu*.so*; do [ -e "$f" ] && cp -av "$f" /opt/zenzai/libllama/backends/; done; \
    cp -av /tmp/_so/libggml-cuda.so* /opt/zenzai/libllama/backends/; \
    echo "=== staged libllama ==="; ls -lR /opt/zenzai/libllama

# ---- Swift 6.2 toolchain ----------------------------------------------------
RUN set -eux; \
    url="https://download.swift.org/swift-6.2-release/ubuntu2404/${SWIFT_VERSION}/${SWIFT_VERSION}-ubuntu24.04.tar.gz"; \
    curl -fSL "$url" -o /tmp/swift.tar.gz; \
    mkdir -p /opt/swift; \
    tar -xzf /tmp/swift.tar.gz -C /opt/swift --strip-components=1; \
    rm /tmp/swift.tar.gz
ENV PATH="/opt/swift/usr/bin:${PATH}"
RUN swift --version

# ---- converter fork (recursive for the bundled dictionary) ------------------
RUN git clone https://github.com/7ka-hiira/AzooKeyKanaKanjiConverter.git /src/converter \
    && git -C /src/converter checkout ${CONVERTER_REF} \
    && git -C /src/converter submodule update --init --recursive

# ---- our wrapper ------------------------------------------------------------
WORKDIR /app
COPY Package.swift /app/Package.swift
COPY Sources /app/Sources
RUN swift build -c release \
        --traits Zenzai \
        -Xlinker -L/opt/zenzai/libllama \
    && cp .build/release/lnaime-zenzai /opt/zenzai/lnaime-zenzai
# place the SPM resource bundle (default dictionary) NEXT TO the binary so
# withDefaultDictionary() finds it at runtime.
RUN cp -r /app/.build/release/*.resources /opt/zenzai/ 2>/dev/null || true; \
    cp -r /app/.build/release/*.bundle /opt/zenzai/ 2>/dev/null || true; \
    ls -la /opt/zenzai

# ---- runtime ----------------------------------------------------------------
FROM nvidia/cuda:12.8.1-runtime-ubuntu24.04 AS runtime
ENV DEBIAN_FRONTEND=noninteractive
RUN apt-get update && apt-get install -y --no-install-recommends \
        libcurl4 libpython3.12 libxml2 libstdc++6 libsqlite3-0 libedit2 ca-certificates \
    && rm -rf /var/lib/apt/lists/*

COPY --from=build /opt/zenzai /opt/zenzai
COPY --from=build /opt/swift/usr/lib/swift/linux /opt/swift-rt/linux
ENV LD_LIBRARY_PATH=/opt/swift-rt/linux:/opt/zenzai/libllama:${LD_LIBRARY_PATH}
ENV GGML_BACKEND_DIR=/opt/zenzai/libllama/backends/
ENV ZENZ_DEVICE=CUDA0
ENV ZENZ_WEIGHT=/models/zenz.gguf

WORKDIR /opt/zenzai
ENTRYPOINT ["/opt/zenzai/lnaime-zenzai"]
