#!/usr/bin/env bash
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT"

fail() {
  echo "FAIL: $*" >&2
  exit 1
}

require_file() {
  [[ -f "$1" ]] || fail "missing $1"
}

for file in \
  BENCHMARK_ENVIRONMENT.md \
  app/Http/Controllers/MembershipCheckoutController.php \
  app/Models/MembershipCheckoutOrder.php \
  database/migrations/2026_06_08_000100_create_membership_checkout_orders_table.php \
  miniapp/pages/membership/index.js \
  miniapp/pages/membership/index.axml \
  routes/api.php \
  routes/web.php
do
  require_file "$file"
done

[[ ! -d app/Services/Alipay ]] || fail "basic starter should not include an Alipay service implementation"

if grep -R -E "AlipayTrade|alipay\\.trade|JSAPI_PAY|my\\.tradePay\\(|tradeNO|op_app_id|ALIPAY_JSAPI|buyer_open_id|alipay-jsapi|alipaysdk/openapi" \
  app routes config database miniapp resources composer.json docker-compose.yml .env.example >/dev/null; then
  fail "basic starter contains Alipay JSAPI/payment implementation hints"
fi

grep -q "Route::post('/orders'" routes/api.php || fail "missing order creation route"
grep -q "membership-checkout" routes/api.php || fail "missing membership checkout API prefix"
grep -q "Create Order" miniapp/pages/membership/index.axml || fail "missing mini program order button"

echo "basic JSAPI environment check passed"
