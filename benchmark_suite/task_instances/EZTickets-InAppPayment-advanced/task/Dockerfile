FROM ubuntu:24.04
ENV DEBIAN_FRONTEND=noninteractive

RUN apt-get update && apt-get install -y --no-install-recommends \
    bash ca-certificates curl wget git jq unzip xz-utils procps sudo \
    python3 python3-pip python3-venv python3-dev \
    mysql-server mysql-client \
    && rm -rf /var/lib/apt/lists/*

RUN curl -fsSL https://deb.nodesource.com/setup_22.x | bash - \
    && apt-get install -y --no-install-recommends nodejs \
    && rm -rf /var/lib/apt/lists/*
RUN npm install -g npm@10.9.7 \
    && npm config set fund false \
    && npm config set audit false \
    && npm config set progress false

RUN git clone https://github.com/flutter/flutter.git -b 3.7.12 --depth 1 /opt/flutter || true
ENV PATH="/opt/flutter/bin:/opt/flutter/bin/cache/dart-sdk/bin:${PATH}"
RUN (flutter config --no-analytics \
      && flutter precache --no-android --no-ios --no-web --no-linux --no-windows --no-macos --no-fuchsia \
      && dart --version && flutter --version \
      && chmod -R a+rwX /opt/flutter) || true

RUN git config --system safe.directory '*'

RUN python3 -m venv /opt/venv
ENV PATH="/opt/venv/bin:$PATH"
RUN pip install --no-cache-dir pytest==8.3.4 pytest-json-ctrf==0.3.6

RUN useradd --create-home --shell /bin/bash agent || true
RUN echo 'agent ALL=(ALL) NOPASSWD:ALL' > /etc/sudoers.d/agent && chmod 440 /etc/sudoers.d/agent

RUN mkdir -p /workspace /output /var/run/mysqld \
    && chmod 777 /workspace /output /tmp /var/run/mysqld

WORKDIR /workspace
