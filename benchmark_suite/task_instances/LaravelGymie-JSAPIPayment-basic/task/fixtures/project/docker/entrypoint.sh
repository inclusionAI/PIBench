#!/usr/bin/env bash
set -euo pipefail

if [ ! -f .env ]; then
    cp .env.example .env
fi

set_laravel_env() {
    local key="$1"
    local value="${!key:-}"

    if [ -z "$value" ]; then
        return
    fi

    ENV_KEY="$key" ENV_VALUE="$value" php <<'PHP'
<?php
$path = '.env';
$key = getenv('ENV_KEY');
$value = getenv('ENV_VALUE');
$encoded = preg_match('/[\s#"\'\\\\]/', $value)
    ? '"' . addcslashes($value, "\\\"\n\r") . '"'
    : $value;
$line = $key . '=' . $encoded;
$contents = file_exists($path) ? file_get_contents($path) : '';
$pattern = '/^' . preg_quote($key, '/') . '=.*/m';

if (preg_match($pattern, $contents)) {
    $contents = preg_replace($pattern, $line, $contents);
} else {
    $contents .= (str_ends_with($contents, "\n") ? '' : "\n") . $line . "\n";
}

file_put_contents($path, $contents);
PHP
}

for env_key in \
    APP_NAME APP_ENV APP_DEBUG APP_URL APP_LOCALE \
    DB_CONNECTION DB_DATABASE \
    SESSION_DRIVER CACHE_STORE QUEUE_CONNECTION MAIL_MAILER
do
    set_laravel_env "$env_key"
done

mkdir -p storage/app storage/framework/cache storage/framework/sessions storage/framework/views storage/logs bootstrap/cache

PHP_MEMORY_LIMIT="${PHP_MEMORY_LIMIT:-512M}"

run_artisan() {
    php -d "memory_limit=${PHP_MEMORY_LIMIT}" artisan "$@"
}

if [ "${DB_CONNECTION:-}" = "sqlite" ]; then
    mkdir -p "$(dirname "${DB_DATABASE:-/var/www/html/storage/app/database.sqlite}")"
    touch "${DB_DATABASE:-/var/www/html/storage/app/database.sqlite}"
fi

run_artisan package:discover --ansi

if ! grep -q '^APP_KEY=base64:' .env; then
    run_artisan key:generate --force --ansi
fi

run_artisan storage:link --force >/dev/null 2>&1 || true
run_artisan optimize:clear --ansi

if [ "${GYMIE_RESET_DATABASE:-false}" = "true" ] || [ ! -f storage/app/.gymie_seeded ]; then
    run_artisan migrate:fresh --seed --force --ansi
    run_artisan shield:generate --all --panel=admin --ansi
    touch storage/app/.gymie_seeded
else
    run_artisan migrate --force --ansi
fi

exec "$@"
