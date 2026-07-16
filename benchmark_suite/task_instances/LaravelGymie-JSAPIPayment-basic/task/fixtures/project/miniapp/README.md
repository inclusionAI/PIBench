# Gymie Mini Program Starter

Native mini program source for the Gymie membership-card benchmark.

The starter lists plans and creates a local membership order. It does not ship
with payment provider code; benchmark tasks can add that integration on top of
the existing business flow.

## Runtime

- Mini Program page: `pages/membership/index`
- Backend API base: `config.js`
- List plans: `GET /api/membership-checkout/plans`
- Create order: `POST /api/membership-checkout/orders`
- Check status: `GET /api/membership-checkout/orders/{checkout_no}`

For a real device run, set `apiBase` to an HTTPS domain configured in the mini
program request domain whitelist.
