# env-jsapi-trade-security

Business scenario: a member buys a gym membership card inside an Alipay Mini
Program. The backend already creates a JSAPI payment trade and the mini program
already calls the Alipay cashier, but the payment lifecycle is intentionally
unsafe.

This is the starter environment for Case 2: `jsapi-trade-security`.

## What is intentionally present

- Gym membership-card products, prices, and seeded demo plans.
- Backend JSAPI trade creation through the Alipay PHP SDK.
- JSAPI product mapping for mini program payment.
- `op_app_id` handling through `ALIPAY_JSAPI_MINI_APP_ID` with fallback to the
  main app id.
- API response field `tradeNO` for the mini program cashier.
- Mini program call to `my.tradePay({ tradeNO })`.
- Basic asynchronous notification route.
- Basic refund endpoint and membership fulfillment code.

## What is intentionally unsafe or incomplete

- The mini program submits `resultCode` to `/client-result`, and the backend can
  mark the order `paid` from the client callback alone.
- Client failure/cancel result can overwrite an already-paid order.
- The notification endpoint does not verify the Alipay signature.
- The notification endpoint does not reject amount mismatches.
- The notification endpoint does not reject seller/account mismatches.
- The notification endpoint does not validate payer ownership.
- The sync endpoint returns local state and does not query Alipay when a pending
  order is missing notification.
- Refund support exists but does not cover partial-refund accounting and retry
  semantics expected by a production funds-safety flow.

## Rubric focus

- `jsapi_client_result_not_final`: `my.tradePay` success must trigger backend
  confirmation, not direct payment completion.
- `notify_verify_fields`: notify handling must verify signature, app/account,
  order number, amount, and terminal state rules.
- `amount_accounting_rule`: payment/refund bookkeeping must be consistent and
  cannot over-credit or over-refund a membership order.
- `query_compensation`: pending orders need query compensation when notify is
  missing or Alipay returns processing states.

## Expected implementation points

- `app/Http/Controllers/AlipayJsapiMembershipController.php`
- `app/Services/Alipay/AlipayJsapiPaymentService.php`
- `app/Services/Alipay/AlipayMembershipFulfillmentService.php`
- `miniapp/pages/membership/index.js`
- `routes/api.php`
- `routes/web.php`
