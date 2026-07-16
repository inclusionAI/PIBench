FROM ubuntu:22.04

RUN apt-get update && apt-get install -y \
    ca-certificates \
    curl \
    git \
    unzip \
    xz-utils \
    docker.io \
    docker-compose-plugin \
    && rm -rf /var/lib/apt/lists/*

RUN git clone https://github.com/flutter/flutter.git -b 3.7.12 --depth 1 /opt/flutter
ENV PATH="/opt/flutter/bin:/opt/flutter/bin/cache/dart-sdk/bin:${PATH}"
RUN flutter precache --no-android --no-ios --no-web --no-linux --no-windows --no-macos --no-fuchsia
RUN dart --version && flutter --version

COPY ez_tickets/ /workspace/ez_tickets/
COPY docker-compose.yml /workspace/docker-compose.yml
COPY Dockerfile.backend /workspace/Dockerfile.backend
COPY start.sh /workspace/start.sh
WORKDIR /workspace

RUN chmod +x /workspace/start.sh
