# Gymie Alipay Mini Program

Native Alipay Mini Program checkout for the Gymie membership-card JSAPI payment benchmark.

## Runtime

- Mini Program page: `pages/membership/index`
- Backend API base: `config.js`
- Create order: `POST /api/alipay-jsapi/orders`
- Pay: `my.tradePay({ tradeNO })`
- Confirm: `POST /api/alipay-jsapi/orders/{out_trade_no}/sync`
- Unsafe client result endpoint: `POST /api/alipay-jsapi/orders/{out_trade_no}/client-result`
- Demo complete: `POST /api/alipay-jsapi/orders/{out_trade_no}/demo-complete`
- Refund: `POST /api/alipay-jsapi/orders/{out_trade_no}/refund`

For real sandbox or production, set `apiBase` to an HTTPS domain configured in the Alipay Mini Program request domain whitelist. The backend must run with `ALIPAY_JSAPI_DEMO_MODE=false` and valid Alipay app keys.
