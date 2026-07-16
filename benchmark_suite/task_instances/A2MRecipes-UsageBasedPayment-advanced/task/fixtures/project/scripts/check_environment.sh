#!/usr/bin/env bash
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT"

fail() {
  echo "FAIL: $*" >&2
  exit 1
}

for file in \
  BENCHMARK_ENVIRONMENT.md \
  Dockerfile \
  docker-compose.yml \
  .env.example \
  src/app/api/recipes/[id]/route.ts \
  src/lib/a2m.ts \
  src/data/recipes.ts
do
  [[ -f "$file" ]] || fail "missing $file"
done

[[ ! -f assets/A2MPaymentDemo.js ]] || fail "security env should not include standalone A2M answer demo"

grep -q "headers: { 'Payment-Needed': header }" src/app/api/recipes/[id]/route.ts \
  || fail "security env should keep Payment-Needed response"
grep -q "alipay\\.aipay\\.agent\\.payment\\.verify" src/lib/a2m.ts \
  || fail "security env should keep Alipay verify call"
grep -q "alipay\\.aipay\\.agent\\.fulfillment\\.confirm" src/lib/a2m.ts \
  || fail "security env should keep fulfillment confirm call"
grep -q "Payment-Validation" src/app/api/recipes/[id]/route.ts src/lib/a2m.ts \
  || fail "security env should keep Payment-Validation behavior"
grep -q "A2M_ALLOW_EPHEMERAL_TEST_KEYS" src/lib/a2m.ts .env.example docker-compose.yml \
  || fail "security env should use explicit ephemeral local keys instead of committed keys"
! grep -Eq "DEV_FALLBACK|DEV_PRIVATE_KEY|DEV_PUBLIC_KEY|开发环境降级|降级放行" src/lib/a2m.ts \
  || fail "security env should not include dev fallback unlock behavior"
grep -q "paymentRecords = new Map" src/lib/a2m.ts \
  || fail "security env should retain intentionally weak in-memory fulfillment state"

if grep -Eq "verifyResult\\.rawData|resourceId !==|amount !==|seller_id !==|service_id !==" src/app/api/recipes/[id]/route.ts; then
  fail "security env should not already verify response fields against local order/resource state"
fi

echo "security A2M environment check passed"
