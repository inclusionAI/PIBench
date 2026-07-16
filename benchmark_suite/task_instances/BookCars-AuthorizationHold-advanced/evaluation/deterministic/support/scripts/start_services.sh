#!/usr/bin/env bash
# Start BookCars services via docker compose (DinD) and seed test data.
# Usage: start_services.sh <workspace> <output_dir>
set -uo pipefail

WORKSPACE="${1:-/workspace}"
OUTPUT_DIR="${2:-/output}"
CASE_DIR="$(cd "$(dirname "$0")/.." && pwd)"
COMPOSE_PROJECT="bcpreauth-task"

cd "$WORKSPACE"

# Generate .env.docker files from examples (do NOT overwrite agent-provided ones)
generate_env() {
  local svc=$1
  local src="./$svc/.env.docker.example"
  local dst="./$svc/.env.docker"
  if [ ! -f "$dst" ]; then
    if [ ! -f "$src" ]; then
      echo "WARNING: $src not found, skipping"
      return
    fi
    sed "s|http://localhost:4002|http://localhost:9102|g" "$src" > "$dst"
  fi
}

generate_env "backend"
generate_env "frontend"

normalize_web_env() {
  local dst=$1
  [ -f "$dst" ] || return
  sed -i \
    -e 's|http://[0-9][0-9.]*:9102|http://localhost:9102|g' \
    -e 's|http://[0-9][0-9.]*:8102|http://localhost:9102|g' \
    -e 's|http://localhost:4002|http://localhost:9102|g' \
    "$dst"
}

normalize_frontend_gateway() {
  local dst="./frontend/.env.docker"
  [ -f "$dst" ] || return
  if grep -q '^VITE_BC_PAYMENT_GATEWAY=' "$dst"; then
    sed -i -E 's|^VITE_BC_PAYMENT_GATEWAY=.*|VITE_BC_PAYMENT_GATEWAY=Alipay # Stripe, PayPal or Alipay|' "$dst"
  else
    printf '\nVITE_BC_PAYMENT_GATEWAY=Alipay # Stripe, PayPal or Alipay\n' >> "$dst"
  fi
}

normalize_backend_env() {
  local dst="./backend/.env.docker"
  [ -f "$dst" ] || return
  if grep -q '^BC_AUTH_COOKIE_DOMAIN=' "$dst"; then
    sed -i -E 's|^BC_AUTH_COOKIE_DOMAIN=.*|BC_AUTH_COOKIE_DOMAIN=localhost|' "$dst"
  else
    printf '\nBC_AUTH_COOKIE_DOMAIN=localhost\n' >> "$dst"
  fi
  if grep -q '^BC_ADMIN_HOST=' "$dst"; then
    sed -i -E 's|^BC_ADMIN_HOST=.*|BC_ADMIN_HOST=http://localhost:9103/ # very important, otherwise admin auth will not work|' "$dst"
  else
    printf '\nBC_ADMIN_HOST=http://localhost:9103/ # very important, otherwise admin auth will not work\n' >> "$dst"
  fi
  if grep -q '^BC_FRONTEND_HOST=' "$dst"; then
    sed -i -E 's|^BC_FRONTEND_HOST=.*|BC_FRONTEND_HOST=http://localhost:9104/ # very important, otherwise frontend auth will not work|' "$dst"
  else
    printf '\nBC_FRONTEND_HOST=http://localhost:9104/ # very important, otherwise frontend auth will not work\n' >> "$dst"
  fi
  if grep -q '^BC_FRONTEND_HOST_PUBLIC=' "$dst"; then
    sed -i -E 's|^BC_FRONTEND_HOST_PUBLIC=.*|BC_FRONTEND_HOST_PUBLIC=http://localhost:9104|' "$dst"
  else
    printf '\nBC_FRONTEND_HOST_PUBLIC=http://localhost:9104\n' >> "$dst"
  fi
}

normalize_web_env "./frontend/.env.docker"
normalize_frontend_gateway
normalize_backend_env

rm -f "$OUTPUT_DIR/backend_ready" "$OUTPUT_DIR/frontend_ready"

echo "Starting docker compose backend stack (project: $COMPOSE_PROJECT)..."
docker compose -p "$COMPOSE_PROJECT" down --remove-orphans 2>/dev/null || true
if ! docker compose -p "$COMPOSE_PROJECT" up --build -d bc-backend 2>&1 | tail -n 80; then
    echo "ERROR: docker compose backend up --build failed"
    docker compose -p "$COMPOSE_PROJECT" logs --tail=80 2>/dev/null || true
    exit 1
fi

# Wait for backend before running integration tests.
MAX_WAIT=300
INTERVAL=5
ELAPSED=0
BACKEND_READY=false

while [ $ELAPSED -lt $MAX_WAIT ]; do
    sleep $INTERVAL
    ELAPSED=$((ELAPSED + INTERVAL))

    if [ "$BACKEND_READY" = false ] && curl -sf http://localhost:9102/api/settings > /dev/null 2>&1; then
        BACKEND_READY=true
        echo "  [${ELAPSED}s] Backend ready (port 9102)"
    fi

    if [ "$BACKEND_READY" = true ]; then
        break
    fi

    echo "  [${ELAPSED}s] Waiting for backend..."
done

if [ "$BACKEND_READY" != true ]; then
    echo "ERROR: Backend not ready after ${MAX_WAIT}s"
    docker compose -p "$COMPOSE_PROJECT" logs --tail=80 2>/dev/null || true
    exit 1
fi
touch "$OUTPUT_DIR/backend_ready"

echo "Backend ready. Seeding demo data..."
MONGO_CONTAINER="${COMPOSE_PROJECT}-mongo-1"
BACKEND_CONTAINER="${COMPOSE_PROJECT}-bc-backend-1"
MONGO_URI="mongodb://admin:admin@localhost:27017/bookcars?authSource=admin"

if [ -f "$WORKSPACE/seed.js" ]; then
    docker cp "$WORKSPACE/seed.js" "$MONGO_CONTAINER:/seed.js" \
        && docker exec "$MONGO_CONTAINER" mongosh "$MONGO_URI" --quiet --file /seed.js \
        || echo "WARNING: seed.js failed"
fi

if [ -f "$WORKSPACE/seed-images.sh" ]; then
    docker cp "$WORKSPACE/seed-images.sh" "$BACKEND_CONTAINER:/tmp/seed-images.sh" 2>/dev/null \
        && docker exec "$BACKEND_CONTAINER" sh /tmp/seed-images.sh 2>/dev/null \
        || echo "WARNING: seed-images.sh failed"
fi

# Seed a test booking (needed by integration tests: freeze/query need a real bookingId)
echo "Seeding test booking..."
docker cp "$CASE_DIR/scripts/seed_booking.js" "$MONGO_CONTAINER:/seed_booking.js" || true
BOOKING_OUT="$(docker exec "$MONGO_CONTAINER" mongosh "$MONGO_URI" --quiet --file /seed_booking.js 2>&1 || true)"
echo "$BOOKING_OUT"
BOOKING_ID="$(echo "$BOOKING_OUT" | grep -o 'BOOKING_ID:[0-9a-f]*' | head -1 | cut -d: -f2)"
CAR_ID="$(echo "$BOOKING_OUT" | grep -o 'CAR_ID:[0-9a-f]*' | head -1 | cut -d: -f2)"
LOCATION_ID="$(echo "$BOOKING_OUT" | grep -o 'LOCATION_ID:[0-9a-f]*' | head -1 | cut -d: -f2)"
if [ -n "$BOOKING_ID" ]; then
    echo "$BOOKING_ID" > "$OUTPUT_DIR/test_booking_id.txt"
    printf '{"bookingId": "%s", "carId": "%s", "locationId": "%s"}\n' \
        "$BOOKING_ID" "$CAR_ID" "$LOCATION_ID" > "$OUTPUT_DIR/test_ids.json"
    echo "Test booking id: $BOOKING_ID"
else
    echo "WARNING: could not seed test booking (integration tests will fall back)"
fi

echo "Starting frontend for E2E (project: $COMPOSE_PROJECT)..."
if docker compose -p "$COMPOSE_PROJECT" up --build -d bc-frontend 2>&1 | tail -n 80; then
    ELAPSED=0
    FRONTEND_READY=false
    while [ $ELAPSED -lt $MAX_WAIT ]; do
        sleep $INTERVAL
        ELAPSED=$((ELAPSED + INTERVAL))

        if curl -sf http://localhost:9104/ > /dev/null 2>&1; then
            FRONTEND_READY=true
            echo "  [${ELAPSED}s] Frontend ready (port 9104)"
            break
        fi

        echo "  [${ELAPSED}s] Waiting for frontend..."
    done

    if [ "$FRONTEND_READY" = true ]; then
        touch "$OUTPUT_DIR/frontend_ready"
    else
        echo "WARNING: Frontend not ready after ${MAX_WAIT}s; E2E will be marked infra"
        docker compose -p "$COMPOSE_PROJECT" logs bc-frontend --tail=80 2>/dev/null || true
    fi
else
    echo "WARNING: docker compose frontend up --build failed; E2E will be marked infra"
    docker compose -p "$COMPOSE_PROJECT" logs bc-frontend --tail=80 2>/dev/null || true
fi

exit 0
