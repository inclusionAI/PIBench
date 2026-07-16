# edoc-h5-env-safety

Case: `EDoc-MobileWebPayment-advanced`

This is the H5/WAP payment safety environment. It has a runnable appointment payment flow, but several safety and accounting behaviors are intentionally incomplete.

## Known Gaps To Fix

- Browser `return_url` can incorrectly mark an appointment paid.
- Browser `quit_url` can incorrectly mark an appointment failed/cancelled.
- Notification verification is incomplete and does not fully validate signature, amount, order, app, seller, and trade status.
- Unknown query states are treated too aggressively.
- Repeated pending payment attempts are not modeled carefully enough.
- Refund handling is too shallow and relies mainly on success code.
- Partial refund idempotency and refund request number strategy need hardening.
- Refund success must not rely only on code `10000`; fund change, amount, request number, order, and trade identity must be verified.

## Stable Entry Points

- `POST /patient/alipay-h5/payment.php`
- `GET /patient/alipay-h5/pay.php?out_trade_no=...`
- `GET /patient/alipay-h5/return.php?out_trade_no=...`
- `GET /patient/alipay-h5/quit.php?out_trade_no=...`
- `POST /patient/alipay-h5/sync.php`
- `POST /alipay/h5/notify.php`
- `POST /admin/alipay-h5/refund.php`
- `POST /admin/alipay-h5/refund-query.php`

## Start

```bash
bash start.sh
curl -i http://localhost:8132/health.php
```

## Default Accounts

- Admin: `admin@edoc.com` / `123`
- Doctor: `doctor@edoc.com` / `123`
- Patient: `patient@edoc.com` / `123`
