FROM ubuntu:22.04
ENV DEBIAN_FRONTEND=noninteractive

RUN apt-get update && apt-get install -y --no-install-recommends \
    bash curl git jq ca-certificates wget gnupg2 lsb-release \
    python3 python3-pip python3-venv python3-dev \
    openjdk-8-jdk maven \
    mysql-server mysql-client \
    sudo xvfb \
    && rm -rf /var/lib/apt/lists/*

RUN curl -fsSL https://deb.nodesource.com/setup_18.x | bash - \
    && apt-get install -y --no-install-recommends nodejs \
    && rm -rf /var/lib/apt/lists/*

RUN python3 -m venv /opt/venv
ENV PATH="/opt/venv/bin:$PATH"

RUN pip install --no-cache-dir \
    pytest==8.3.4 \
    requests==2.31.0 \
    beautifulsoup4==4.12.3 \
    lxml==5.1.0 \
    cryptography==42.0.5 \
    playwright==1.41.0

ENV PLAYWRIGHT_BROWSERS_PATH=/opt/ms-playwright
RUN playwright install chromium \
    && playwright install-deps chromium \
    && chmod -R a+rX /opt/ms-playwright

RUN npm config set registry https://registry.npmmirror.com

RUN mkdir -p /root/.m2 \
    && printf '<settings>\n  <mirrors>\n    <mirror>\n      <id>aliyun</id>\n      <mirrorOf>central</mirrorOf>\n      <url>https://maven.aliyun.com/repository/public</url>\n    </mirror>\n  </mirrors>\n</settings>\n' > /root/.m2/settings.xml

ENV JAVA_HOME=/usr/lib/jvm/java-8-openjdk-amd64
ENV PATH="$JAVA_HOME/bin:$PATH"

RUN useradd --create-home --shell /bin/bash agent || true \
    && mkdir -p /workspace /output \
    && chmod 777 /workspace /output /tmp

WORKDIR /workspace
