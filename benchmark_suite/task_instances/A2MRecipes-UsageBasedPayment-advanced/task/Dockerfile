FROM node:22-bookworm
ENV DEBIAN_FRONTEND=noninteractive
ENV NEXT_TELEMETRY_DISABLED=1

RUN apt-get update && apt-get install -y --no-install-recommends \
    bash curl git jq ca-certificates rsync procps \
    python3 python3-pip python3-venv python3-dev \
    && rm -rf /var/lib/apt/lists/*

RUN python3 -m venv /opt/venv
ENV PATH="/opt/venv/bin:$PATH"
RUN pip install --no-cache-dir --upgrade pip \
    && pip install --no-cache-dir requests==2.32.3 pytest==8.3.4

RUN corepack enable && corepack prepare pnpm@9.0.0 --activate

RUN mkdir -p /workspace /output && chmod -R 777 /workspace /output
WORKDIR /workspace
