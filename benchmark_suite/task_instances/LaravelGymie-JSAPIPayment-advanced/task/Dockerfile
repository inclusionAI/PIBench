FROM php:8.4-cli-bookworm
ENV DEBIAN_FRONTEND=noninteractive

RUN apt-get update && apt-get install -y --no-install-recommends \
        bash curl git jq unzip ca-certificates sqlite3 sudo \
        libfreetype6-dev libicu-dev libjpeg62-turbo-dev libonig-dev \
        libpng-dev libsqlite3-dev libzip-dev \
        python3 python3-pip python3-venv \
    && docker-php-ext-configure gd --with-freetype --with-jpeg \
    && docker-php-ext-install bcmath gd intl mbstring pdo_mysql pdo_sqlite zip \
    && apt-get clean && rm -rf /var/lib/apt/lists/*

COPY --from=composer:2 /usr/bin/composer /usr/bin/composer

RUN curl -fsSL https://deb.nodesource.com/setup_22.x | bash - \
    && apt-get install -y --no-install-recommends nodejs \
    && rm -rf /var/lib/apt/lists/*

RUN python3 -m venv /opt/venv
ENV PATH="/opt/venv/bin:$PATH"
RUN pip install --no-cache-dir cryptography requests==2.32.3 pytest==8.3.4

ENV COMPOSER_ALLOW_SUPERUSER=1
RUN useradd --create-home --shell /bin/bash agent || true \
    && echo "agent ALL=(ALL) NOPASSWD:ALL" > /etc/sudoers.d/agent \
    && chmod 0440 /etc/sudoers.d/agent \
    && mkdir -p /workspace /output \
    && chmod 777 /workspace /output

WORKDIR /workspace
