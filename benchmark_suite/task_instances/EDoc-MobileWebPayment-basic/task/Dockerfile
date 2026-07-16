FROM php:8.2-cli

ENV DEBIAN_FRONTEND=noninteractive

RUN docker-php-ext-install mysqli pdo pdo_mysql

RUN { \
      echo "output_buffering=4096"; \
      echo "display_errors=On"; \
      echo "log_errors=On"; \
    } > /usr/local/etc/php/conf.d/edoc.ini

RUN apt-get update && apt-get install -y --no-install-recommends \
      bash curl git jq ca-certificates sudo procps \
      python3 python3-pip python3-venv \
      mariadb-server mariadb-client \
    && rm -rf /var/lib/apt/lists/*

RUN pip3 install --no-cache-dir --break-system-packages \
      requests==2.32.4 pytest==8.4.1

RUN useradd --create-home --shell /bin/bash agent \
    && echo "agent ALL=(ALL) NOPASSWD:ALL" > /etc/sudoers.d/agent \
    && chmod 0440 /etc/sudoers.d/agent

RUN mkdir -p /workspace /output /var/lib/edoc-mysql /var/run/mysqld \
    && chown -R agent:agent /workspace /output /var/lib/edoc-mysql /var/run/mysqld \
    && chmod 0777 /workspace /output /var/run/mysqld

WORKDIR /workspace
