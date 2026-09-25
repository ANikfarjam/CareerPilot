# Sandbox image the agents execute code in. Built and run through the
# `sandbox` / `sandbox-cpu` services in docker-compose.yml:
#   docker compose build sandbox        # CUDA + torch/transformers
#   docker compose build sandbox-cpu    # no GPU, no torch (fast, for testing)

ARG BASE_IMAGE=nvidia/cuda:12.6.3-cudnn-runtime-ubuntu24.04
FROM ${BASE_IMAGE}

ARG WITH_TORCH=1
ARG TORCH_INDEX=https://download.pytorch.org/whl/cu126

ENV DEBIAN_FRONTEND=noninteractive \
    PATH=/opt/venv/bin:$PATH \
    PIP_NO_CACHE_DIR=1

RUN apt-get update \
    && apt-get install -y --no-install-recommends python3 python3-venv ca-certificates \
    && rm -rf /var/lib/apt/lists/*

RUN python3 -m venv /opt/venv \
    && pip install requests httpx beautifulsoup4 lxml pandas pyyaml

RUN if [ "$WITH_TORCH" = "1" ]; then \
        pip install torch --index-url ${TORCH_INDEX} \
        && pip install transformers accelerate safetensors ; \
    fi

# Runs as uid 1000 with a read-only root fs; HOME and the working dir are a
# tmpfs mounted at /workspace (see docker-compose.yml). The container only
# idles; code is run with `docker exec ... bash -s` / `python3 -`.
WORKDIR /workspace
