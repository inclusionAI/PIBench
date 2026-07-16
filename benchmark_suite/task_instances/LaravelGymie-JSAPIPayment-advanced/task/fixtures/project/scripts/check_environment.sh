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
  app/Http/Controllers/AlipayJsapiMembershipController.php \
  app/Services/Alipay/AlipayJsapiPaymentService.php \
  app/Services/Alipay/AlipayMembershipFulfillmentService.php \
  miniapp/pages/membership/index.js \
  miniapp/pages/membership/index.axml \
  routes/api.php \
  routes/web.php
do
  require_file "$file"
done

rg -q "AlipayTradeCreateRequest" app/Services/Alipay/AlipayJsapiPaymentService.php \
  || fail "safety env should retain basic trade creation"
rg -q "'product_code' => 'JSAPI_PAY'" app/Services/Alipay/AlipayJsapiPaymentService.php \
  || fail "safety env should retain JSAPI product mapping"
rg -q "'op_app_id' => \\\$this->miniAppId\\(\\)" app/Services/Alipay/AlipayJsapiPaymentService.php \
  || fail "safety env should retain op_app_id handling"
rg -q "my\\.tradePay\\(" miniapp/pages/membership/index.js \
  || fail "safety env should retain mini program cashier call"
rg -q "tradeNO: order\\.tradeNO" miniapp/pages/membership/index.js \
  || fail "mini program should use tradeNO field"
rg -q "client-result" routes/api.php miniapp/pages/membership/index.js \
  || fail "expected unsafe client-result flow is missing"

if rg -q "queryTrade\\(" app/Http/Controllers/AlipayJsapiMembershipController.php; then
  fail "safety env should not already implement query compensation in controller"
fi

if rg -q "verifyNotify\\(" app/Http/Controllers/AlipayJsapiMembershipController.php; then
  fail "safety env should not already verify notify in controller"
fi

echo "safety JSAPI environment check passed"
