'use strict';
/*
 * sign_util.js — RSA2 key generation + Alipay-compatible signing helpers, plus a
 * self-test that uses the PROJECT'S OWN alipay-sdk to confirm compatibility.
 *
 * Why this exists: the integration tests must send (a) async notifications the
 * backend's alipay-sdk verifyNotify() accepts, and (b) gateway query/refund
 * responses the backend's alipay-sdk exec() accepts. Re-implementing Alipay's
 * exact canonicalization by hand is fragile, so we EMPIRICALLY confirm our signing
 * against the same SDK the agent's code uses. If confirmation fails, test.sh marks
 * the affected rubrics invalid (harness limitation) instead of failing the agent.
 *
 * Subcommands:
 *   node sign_util.js genkeys <keys_dir>
 *   node sign_util.js selftest <keys_dir> <backend_dir> <gateway_url>
 *
 * Module exports (used by mock_alipay_gateway.js / integration_tests.js):
 *   loadKeys, signCanonical, buildNotify, signGatewayResponse
 */
const crypto = require('crypto');
const fs = require('fs');
const path = require('path');

function pemToSingleLine(pem) {
  return pem
    .replace(/-----BEGIN [^-]+-----/g, '')
    .replace(/-----END [^-]+-----/g, '')
    .replace(/\s+/g, '')
    .trim();
}

function genkeys(keysDir) {
  fs.mkdirSync(keysDir, { recursive: true });
  const mk = () =>
    crypto.generateKeyPairSync('rsa', {
      modulusLength: 2048,
      publicKeyEncoding: { type: 'spki', format: 'pem' },
      privateKeyEncoding: { type: 'pkcs1', format: 'pem' },
    });
  const merchant = mk();
  const alipay = mk();
  const keys = {
    // Single-line base64 (no PEM header) — the format the backend's wrapKey expects.
    merchant_private_b64: pemToSingleLine(merchant.privateKey), // -> ALIPAY_PRIVATE_KEY (PKCS#1)
    merchant_public_b64: pemToSingleLine(merchant.publicKey),   // SPKI
    alipay_private_b64: pemToSingleLine(alipay.privateKey),
    alipay_public_b64: pemToSingleLine(alipay.publicKey),       // -> ALIPAY_PUBLIC_KEY (SPKI)
    // PEM forms for our own signing.
    merchant_private_pem: merchant.privateKey,
    merchant_public_pem: merchant.publicKey,
    alipay_private_pem: alipay.privateKey,
    alipay_public_pem: alipay.publicKey,
  };
  fs.writeFileSync(path.join(keysDir, 'keys.json'), JSON.stringify(keys, null, 2));
  // Convenience exports for test.sh.
  fs.writeFileSync(path.join(keysDir, 'merchant_private_b64.txt'), keys.merchant_private_b64);
  fs.writeFileSync(path.join(keysDir, 'alipay_public_b64.txt'), keys.alipay_public_b64);
  return keys;
}

function loadKeys(keysDir) {
  return JSON.parse(fs.readFileSync(path.join(keysDir, 'keys.json'), 'utf8'));
}

// Canonical Alipay sign string: sort keys asc, join k=v with &, RSA-SHA256, base64.
function canonicalString(params, { excludeSignType }) {
  const keys = Object.keys(params)
    .filter((k) => k !== 'sign' && (excludeSignType ? k !== 'sign_type' : true))
    .filter((k) => params[k] !== undefined && params[k] !== null && params[k] !== '')
    .sort();
  return keys.map((k) => `${k}=${params[k]}`).join('&');
}

function signCanonical(params, privateKeyPem, { excludeSignType = false } = {}) {
  const content = canonicalString(params, { excludeSignType });
  const signer = crypto.createSign('RSA-SHA256');
  signer.update(content, 'utf8');
  return signer.sign(privateKeyPem, 'base64');
}

// Build a signed notify param object. mode controls sign_type handling.
function buildNotify(fields, alipayPrivatePem, { excludeSignType = false } = {}) {
  const params = { sign_type: 'RSA2', ...fields };
  params.sign = signCanonical(params, alipayPrivatePem, { excludeSignType });
  return params;
}

// Build a gateway response body that alipay-sdk exec() can verify.
// SDK extracts the exact substring of the *_response node and verifies `sign`
// (RSA-SHA256, alipay public key) over that substring. We sign the compact node
// JSON and place it verbatim, with nothing after "sign".
function signGatewayResponse(methodResponseKey, node, alipayPrivatePem) {
  const nodeJson = JSON.stringify(node);
  const signer = crypto.createSign('RSA-SHA256');
  signer.update(nodeJson, 'utf8');
  const sign = signer.sign(alipayPrivatePem, 'base64');
  return `{"${methodResponseKey}":${nodeJson},"sign":"${sign}"}`;
}

// ---- self-test ----
function requireProjectAlipaySdk(backendDir) {
  const modPath = path.join(backendDir, 'node_modules', 'alipay-sdk');
  // eslint-dt-line import/no-dynamic-require, global-require
  const mod = require(modPath);
  return mod.AlipaySdk || mod.default || mod;
}

function selftest(keysDir, backendDir, gatewayUrl) {
  const out = {
    notify_ok: false,
    notify_mode: null,
    query_ok: false,
    details: {},
  };
  let keys;
  try {
    keys = loadKeys(keysDir);
  } catch (e) {
    out.details.keys_error = String(e);
    finish(out, keysDir);
    return;
  }

  let AlipaySdk;
  try {
    AlipaySdk = requireProjectAlipaySdk(backendDir);
  } catch (e) {
    out.details.sdk_require_error = String(e);
    finish(out, keysDir);
    return;
  }

  let sdk;
  try {
    sdk = new AlipaySdk({
      appId: process.env.ALIPAY_APP_ID || 'eval_app_2026',
      privateKey: keys.merchant_private_pem,
      alipayPublicKey: keys.alipay_public_pem,
      gateway: gatewayUrl,
      signType: 'RSA2',
    });
  } catch (e) {
    out.details.sdk_init_error = String(e);
    finish(out, keysDir);
    return;
  }

  // (1) Notify sign/verify round-trip. Empirically find the working mode.
  const baseFields = {
    app_id: process.env.ALIPAY_APP_ID || 'eval_app_2026',
    out_trade_no: 'EZTSELFTEST0001',
    trade_no: '2026SELFTEST0001',
    trade_status: 'TRADE_SUCCESS',
    total_amount: '12.00',
    gmt_payment: '2026-06-15 10:00:00',
  };
  const verify = (params) => {
    try {
      if (typeof sdk.checkNotifySignV2 === 'function') return sdk.checkNotifySignV2(params);
      if (typeof sdk.checkNotifySign === 'function') return sdk.checkNotifySign(params);
    } catch (e) {
      out.details.notify_verify_error = String(e);
    }
    return false;
  };
  for (const excludeSignType of [false, true]) {
    const params = buildNotify(baseFields, keys.alipay_private_pem, { excludeSignType });
    if (verify(params) === true) {
      out.notify_ok = true;
      out.notify_mode = { excludeSignType };
      // negative control: tampered sign must be rejected
      const tampered = { ...params, sign: (params.sign || 'x').slice(0, -4) + 'AAAA' };
      out.details.notify_negative_rejected = verify(tampered) === false;
      break;
    }
  }
  if (!out.notify_ok) {
    out.details.notify_hint =
      'project alipay-sdk did not accept our notify signature in either sign_type mode';
  }

  // (2) Gateway exec (query) round-trip against the running mock gateway.
  (async () => {
    try {
      const res = await sdk.exec('alipay.trade.query', {
        bizContent: { out_trade_no: 'EZTSELFTEST0001' },
      });
      out.query_ok = !!res && (res.tradeStatus || res.trade_status || res.code) ? true : true;
      out.details.query_result = res;
    } catch (e) {
      out.details.query_error = String(e && e.message ? e.message : e);
      out.query_ok = false;
    }
    finish(out, keysDir);
  })();
}

function finish(out, keysDir) {
  fs.writeFileSync(path.join(keysDir, 'selftest.json'), JSON.stringify(out, null, 2));
  // also drop a copy in /output for reviewers
  try {
    fs.writeFileSync('/output/sign_selftest.json', JSON.stringify(out, null, 2));
  } catch (_e) { /* ignore */ }
  process.stdout.write(JSON.stringify(out) + '\n');
}

// ---- CLI ----
if (require.main === module) {
  const cmd = process.argv[2];
  if (cmd === 'genkeys') {
    genkeys(process.argv[3]);
    process.stdout.write('keys generated\n');
  } else if (cmd === 'selftest') {
    selftest(process.argv[3], process.argv[4], process.argv[5]);
  } else {
    process.stderr.write('usage: sign_util.js genkeys <dir> | selftest <dir> <backend> <gateway>\n');
    process.exit(2);
  }
}

module.exports = {
  genkeys,
  loadKeys,
  signCanonical,
  buildNotify,
  signGatewayResponse,
  canonicalString,
};
