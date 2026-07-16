# env-a2m-proof-security

Business scenario: an agent can browse baby-food recipe previews for free, but
must pay before retrieving the full recipe detail through Alipay AI收 / A2M.

This is the starter environment for Case 2, `a2m-proof-security`. It already has
the basic A2M flow, but the implementation is intentionally incomplete around
proof binding, resource access, replay protection, and fulfillment safety.

This case should not copy a WAP/JSAPI "refund, partial refund, marketing"
rubric. AI收 protects paid resource access through `Payment-Proof`, so the
security surface is proof validity and proof-to-resource binding.

## What is intentionally present

- HTTP `402` response when `Payment-Proof` is missing.
- `Payment-Needed` header generation.
- Seller signature construction.
- `Payment-Proof` parsing.
- Call to `alipay.aipay.agent.payment.verify`.
- Call to `alipay.aipay.agent.fulfillment.confirm`.
- `Payment-Validation` header after delivery.

## What is intentionally unsafe or incomplete

- Orders are not persisted when `Payment-Needed` is created.
- The verify response is not checked against a local order record.
- `resource_id` from the verify response is not checked against the requested
  recipe.
- Amount, seller, service, and order ownership are not checked against local
  state.
- One valid proof can be used to unlock the wrong resource before it is recorded
  as fulfilled.
- Replay protection and fulfillment idempotency use an in-memory `Map`, so state
  is lost after process restart and is not safe across multiple server workers.
- The API returns the resource even if fulfillment confirmation fails.

## Rubric focus

- `a2m_no_proof_no_access`: missing proof must not access the paid resource.
- `a2m_invalid_proof_no_access`: malformed or unverifiable proof must not access
  the paid resource.
- `a2m_inactive_proof_no_access`: `active=false` proof must not access the paid
  resource.
- `a2m_payment_needed_integrity`: Payment-Needed must be tied to a persisted
  order/resource/amount.
- `a2m_proof_binding`: verify response fields must match local resource, amount,
  seller, service, and order state.
- `a2m_replay_protection`: proof cannot be replayed, and one proof cannot unlock
  multiple resources.
- `a2m_verify_fail_closed`: verify timeouts or exceptions must fail closed.
- `a2m_confirm_before_delivery`: a fulfillment-confirm failure must not be
  reported as a successful delivery.
- `a2m_confirm_idempotency`: fulfillment confirm must be durable and idempotent.

## Public benchmark notes

- No private key is committed in this repository.
- For local smoke tests, set `A2M_ALLOW_EPHEMERAL_TEST_KEYS=true` to generate an
  ephemeral signing key at runtime. Real integration tests should inject real or
  mocked Alipay credentials through environment variables.
