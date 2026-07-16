FROM ubuntu:24.04
ENV DEBIAN_FRONTEND=noninteractive

RUN apt-get update && apt-get install -y --no-install-recommends \
    bash curl git jq ca-certificates openssl sudo psmisc \
    python3 python3-pip python3-venv python3-dev \
    postgresql postgresql-contrib \
    && rm -rf /var/lib/apt/lists/*

RUN curl -fsSL https://deb.nodesource.com/setup_22.x | bash - \
    && apt-get install -y --no-install-recommends nodejs \
    && rm -rf /var/lib/apt/lists/*

RUN npm install -g pnpm@9.15.9

RUN python3 -m venv /opt/venv && /opt/venv/bin/pip install --no-cache-dir pytest==8.3.4
ENV PATH="/opt/venv/bin:$PATH"

RUN useradd --create-home --shell /bin/bash agent || true \
    && mkdir -p /workspace /output \
    && chmod 777 /workspace /output /tmp \
    && echo "agent ALL=(ALL) NOPASSWD:ALL" >/etc/sudoers.d/payskills-agent

WORKDIR /workspace
