FROM node:22-bookworm

ENV DEBIAN_FRONTEND=noninteractive

RUN apt-get update && apt-get install -y --no-install-recommends \
    bash curl git jq ca-certificates sudo procps \
    python3 python3-pip python3-venv python3-dev \
    openssl \
    && rm -rf /var/lib/apt/lists/*

RUN python3 -m venv /opt/venv
ENV PATH="/opt/venv/bin:$PATH"
RUN pip install --no-cache-dir --upgrade pip \
    && pip install --no-cache-dir requests==2.32.3 pytest==8.3.4 pytest-json-ctrf==0.3.6

RUN useradd --create-home --shell /bin/bash agent || true \
    && mkdir -p /workspace /output \
    && chmod 777 /workspace /output /tmp

WORKDIR /workspace
