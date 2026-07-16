# edoc-h5-env-basic

Case: `wap-basic-appointment`

This is the basic H5/WAP payment integration environment. It is based on the MIT licensed eDoc doctor appointment system. The original appointment flow can create bookings, but it does not include an Alipay H5/WAP payment implementation.

## Task Intent

Add mobile-browser Alipay payment to the patient appointment flow. A patient should create an appointment, receive a mobile payment handoff, complete payment, and only then have the appointment confirmed by a trusted server-side notification or query.

## Expected Stable Entry Points

- `GET /login.php`
- `GET /patient/schedule.php`
- `GET /patient/booking.php?id={schedule_id}`
- `POST /patient/booking-complete.php`
- Agent should add `POST /patient/alipay-h5/payment.php`
- Agent should add `GET /patient/alipay-h5/pay.php?out_trade_no=...`
- Agent should add `POST /alipay/h5/notify.php`

## Start

```bash
bash start.sh
curl -i http://localhost:8131/health.php
```

## Default Accounts

- Admin: `admin@edoc.com` / `123`
- Doctor: `doctor@edoc.com` / `123`
- Patient: `patient@edoc.com` / `123`

