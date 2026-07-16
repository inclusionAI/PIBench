'use strict';
/*
 * integration_tests.js — black-box HTTP contract tests against the agent's hardened
 * backend running on 127.0.0.1:3331, with the mock Alipay gateway injected via
 * ALIPAY_GATEWAY. Implementation-agnostic: only asserts on the fixed HTTP contract
 * from instruction.md, never on internal data models.
 *
 * Output: writes /output/integration_results.json:
 *   { "results": [ {id, name, passed, message, evidence}, ... ],
 *     "signing": {notify_ok, query_ok, ...} }
 *
 * Fairness:
 *  - Tests that REQUIRE a valid signed notify/gateway response first run a
 *    sign self-test. If that prerequisite fails, the affected rubric fails with
 *    a clear prerequisite message instead of being excluded from the score.
 *  - We seed our own test buyers A/B and reserved bookings directly in MySQL using
 *    the project's bcryptjs, so we don't depend on unknown seed passwords.
 */
const http = require('http');
const fs = require('fs');
const path = require('path');
const crypto = require('crypto');
const { execFileSync } = require('child_process');
const { loadKeys, buildNotify } = require('./sign_util');

const BASE = process.env.BACKEND_BASE || 'http://127.0.0.1:3331';
const BACKEND_DIR = process.env.BACKEND_DIR || '/workspace/ez_tickets_backend';
const KEYS_DIR = process.env.ALIPAY_MOCK_KEYS || '/output/alipay_keys';
const STATE_FILE = process.env.ALIPAY_MOCK_STATE || '/output/alipay_mock_state.json';
const OUT = process.env.OUTPUT_DIR || '/output';

const APP_ID = process.env.ALIPAY_APP_ID || 'eval_app_2026';
const SECRET_JWT = process.env.SECRET_JWT || 'eval_secret_jwt';
const ALIPAY_AMOUNT_DIVISOR = Number(process.env.ALIPAY_AMOUNT_DIVISOR || 100);
const TEST_PRICE_MINOR = 1200;
const TEST_PRICE_ALIPAY = alipayAmountFromMinor(TEST_PRICE_MINOR);
const BUYER_A_ALIPAY_ID = '2088EVALBUYERA';
const BUYER_B_ALIPAY_ID = '2088EVALBUYERB';

function alipayAmountFromMinor(value) {
  return (Number(value || 0) / ALIPAY_AMOUNT_DIVISOR).toFixed(2);
}

const results = [];
function record(id, name, passed, message, evidence) {
  results.push({ id, name, passed: !!passed, status: passed ? 'pass' : 'fail', message: message || '', evidence: evidence || [] });
}
function failPrereq(id, name, message) {
  record(id, name, false, message || '前置条件未满足，无法验证目标行为', ['sign_selftest.json', 'integration_results.json']);
}

// ---------- tiny HTTP client ----------
function request(method, url, { headers = {}, body, form } = {}) {
  return new Promise((resolve) => {
    const u = new URL(url);
    let payload = null;
    const h = { ...headers };
    if (form) {
      payload = require('querystring').stringify(form);
      h['Content-Type'] = 'application/x-www-form-urlencoded';
    } else if (body !== undefined) {
      payload = typeof body === 'string' ? body : JSON.stringify(body);
      h['Content-Type'] = h['Content-Type'] || 'application/json';
    }
    if (payload) h['Content-Length'] = Buffer.byteLength(payload);
    const req = http.request(
      { hostname: u.hostname, port: u.port, path: u.pathname + u.search, method, headers: h, timeout: 30000 },
      (res) => {
        let data = '';
        res.on('data', (c) => { data += c; });
        res.on('end', () => {
          let json = null;
          try { json = JSON.parse(data); } catch (_e) { /* non-json */ }
          resolve({ status: res.statusCode, text: data, json });
        });
      }
    );
    req.on('error', (e) => resolve({ status: 0, text: String(e), json: null, error: e }));
    req.on('timeout', () => { req.destroy(); resolve({ status: 0, text: 'timeout', json: null }); });
    if (payload) req.write(payload);
    req.end();
  });
}

const sleep = (ms) => new Promise((r) => setTimeout(r, ms));

// ---------- payment URL helpers ----------
function paymentUrl(otn, suffix) {
  const base = '/api/v1/payments/alipay/' + encodeURIComponent(otn);
  return BASE + (suffix ? base + '/' + suffix : base);
}


// ---------- mock gateway state control ----------
function setState(obj) {
  fs.writeFileSync(STATE_FILE, JSON.stringify(obj, null, 2));
}
function getState() {
  try { return JSON.parse(fs.readFileSync(STATE_FILE, 'utf8')); } catch (_e) { return {}; }
}
function mergeState(otn, patch) {
  const s = getState();
  s[otn] = { ...(s[otn] || {}), ...patch };
  setState(s);
}

// ---------- DB seeding via project deps ----------
function seedDb() {
  // Use a small Node script run inside backend dir so it sees project node_modules.
  const script = `
const bcrypt = require('bcryptjs');
const mysql = require('mysql2/promise');
const TEST_PRICE_MINOR = ${JSON.stringify(TEST_PRICE_MINOR)};
(async () => {
  const conn = await mysql.createConnection({
    host: process.env.DB_HOST || '127.0.0.1',
    port: Number(process.env.DB_PORT || 3306),
    user: process.env.DB_USER || 'root',
    password: process.env.DB_PASS || '',
    database: process.env.DB_DATABASE || 'ez_tickets',
    multipleStatements: true,
  });
  const hash = bcrypt.hashSync('Eval#Pass123', 8);
  // Buyer A and Buyer B (distinct owners). Use high ids to avoid clashing with seed.
  for (const [id, email] of [[9001,'evalA@eztickets.local'],[9002,'evalB@eztickets.local']]) {
    await conn.query(
      "INSERT INTO users (user_id, full_name, email, password, address, contact, role) VALUES (?,?,?,?,?,?, 'api_user') " +
      "ON DUPLICATE KEY UPDATE email=VALUES(email), password=VALUES(password)",
      [id, 'Eval Buyer ' + id, email, hash, 'Karachi', '+923000000000']
    );
  }
  // Find an existing show id (any) to attach bookings to.
  const [shows] = await conn.query('SELECT show_id FROM shows ORDER BY show_id LIMIT 1');
  const showId = shows.length ? shows[0].show_id : 1;
  // Reserved bookings for buyer A and Buyer B. Extra ids keep hidden safety
  // cases independent from each other instead of reusing the same payment row.
  const bk = [
    [90011, 9001, showId, "A", 11, TEST_PRICE_MINOR],
    [90012, 9001, showId, "A", 12, TEST_PRICE_MINOR],
    [90013, 9001, showId, "A", 13, TEST_PRICE_MINOR],
    [90014, 9001, showId, "A", 14, TEST_PRICE_MINOR],
    [90015, 9001, showId, "A", 15, TEST_PRICE_MINOR],
    [90016, 9001, showId, "A", 16, TEST_PRICE_MINOR],
    [90017, 9001, showId, "A", 17, TEST_PRICE_MINOR],
    [90018, 9001, showId, "A", 18, TEST_PRICE_MINOR],
    [90019, 9001, showId, "A", 19, TEST_PRICE_MINOR],
    [90020, 9001, showId, "A", 20, TEST_PRICE_MINOR],
    [90021, 9002, showId, "B", 11, 1500],
  ];
  for (const [bid, uid, sid, seatRow, seatNumber, price] of bk) {
    await conn.query(
      "INSERT INTO bookings (booking_id, user_id, show_id, seat_row, seat_number, price, booking_status, booking_datetime) " +
      "VALUES (?,?,?,?,?,?, 'reserved', NOW()) " +
      "ON DUPLICATE KEY UPDATE user_id=VALUES(user_id), show_id=VALUES(show_id), seat_row=VALUES(seat_row), seat_number=VALUES(seat_number), price=VALUES(price), booking_status='reserved'",
      [bid, uid, sid, seatRow, seatNumber, price]
    );
  }
  console.log(JSON.stringify({ ok: true, showId }));
  await conn.end();
})().catch((e) => { console.error('SEED_ERROR ' + (e && e.message)); process.exit(3); });
`;
  const scriptPath = path.join(BACKEND_DIR, '.eval_seed_db.js');
  fs.writeFileSync(scriptPath, script);
  const outStr = execFileSync('node', [scriptPath], {
    cwd: BACKEND_DIR,
    env: process.env,
    encoding: 'utf8',
  });
  return JSON.parse(outStr.trim().split('\n').pop());
}

// JWT for a seeded user (HS256, payload {user_id}). Mirrors the backend's auth.
function tokenFor(userId) {
  const b64 = (o) => Buffer.from(JSON.stringify(o)).toString('base64url');
  const head = b64({ alg: 'HS256', typ: 'JWT' });
  const body = b64({ user_id: userId });
  const sig = crypto.createHmac('sha256', SECRET_JWT).update(`${head}.${body}`).digest('base64url');
  return `${head}.${body}.${sig}`;
}
const authH = (uid) => ({ Authorization: 'Bearer ' + tokenFor(uid) });

// Pull out_trade_no from a create-payment response — the unified identifier for all alipay operations.
function extractPaymentId(resp) {
  const body = (resp.json && (resp.json.body || resp.json)) || {};
  const cands = [body.out_trade_no, body.outTradeNo,
                 resp.json && resp.json.out_trade_no, resp.json && resp.json.outTradeNo];
  for (const c of cands) if (c !== undefined && c !== null && String(c).length) return String(c);
  return null;
}
function extractOutTradeNo(resp) {
  const body = (resp.json && (resp.json.body || resp.json)) || {};
  return body.out_trade_no || body.outTradeNo || null;
}
function extractStatus(resp) {
  const body = (resp.json && (resp.json.body || resp.json)) || {};
  return (body.trade_status || body.tradeStatus || body.status || body.payment_status || '').toString();
}
const isPaidStatus = (s) =>
  /paid|success|trade_success|trade_finished|confirmed|completed/i.test(s || '');
const isRefundedStatus = (s) =>
  /refunded|refund_success|trade_refund|cancelled|canceled/i.test(s || '');
const isPartialRefundStatus = (s) =>
  /partial|partially_refunded|refunding/i.test(s || '');
const isPendingStatus = (s) =>
  /pending|processing|paying|wait_buyer_pay/i.test(s || '');
function responseIndicatesBusinessFailure(resp) {
  const body = resp && resp.json ? JSON.stringify(resp.json) : '';
  const text = `${resp && resp.text || ''} ${body}`;
  return (resp.status >= 400 && resp.status < 500)
    || /success["']?\s*:\s*false|fail|failed|error|reject|forbid|unauthori[sz]ed|not.?paid|unpaid|pending|cannot|invalid|不允许|未支付|无权|拒绝/i.test(text);
}

// Create a fresh pending payment for buyer A; returns {pid, otn, createResp}.
async function createPaymentForA(bookingIds = [90011]) {
  // booking create may be needed if reserved ones were consumed; re-seed reserved state.
  const bookingBody = {
    booking_id: bookingIds[0],
    booking_ids: bookingIds,
    bookings: bookingIds,
    payment_method: 'alipay',
    amount: bookingIds.length * TEST_PRICE_MINOR,
    payment_datetime: '2026-06-15 10:00:00',
    user_id: 9001,
    show_id: SHOW_ID,
  };
  const resp = await request('POST', `${BASE}/api/v1/payments/alipay/create`, { headers: authH(9001), body: bookingBody });
  const otn = extractPaymentId(resp);
  return { resp, pid: otn, otn };
}

let SHOW_ID = 1;
let SIGNING = { notify_ok: false, query_ok: false };

// ---------- the test suite ----------
async function main() {
  // load signing self-test verdict (written earlier by sign_util selftest)
  try {
    SIGNING = JSON.parse(fs.readFileSync(path.join(OUT, 'sign_selftest.json'), 'utf8'));
  } catch (_e) { SIGNING = { notify_ok: false, query_ok: false }; }

  let keys = null;
  try { keys = loadKeys(KEYS_DIR); } catch (_e) { /* handled per-test */ }

  // ---- runtime smoke: movies reachable; create/query checked below ----
  const movies = await request('GET', `${BASE}/api/v1/movies`);

  // seed DB (buyers + reserved bookings)
  try {
    const seeded = seedDb();
    SHOW_ID = seeded.showId || 1;
  } catch (e) {
    record('SEED', 'DB 播种', false, 'seedDb failed: ' + (e && e.message), ['backend_start.log']);
  }

  // ---- create a baseline pending payment ----
  let base = await createPaymentForA([90011]);
  const createOk = base.resp.status >= 200 && base.resp.status < 300 && !!base.otn;
  const otn = base.otn;
  const pid = otn; // pid and otn are the same: out_trade_no is the unified identifier

  // ---- I1: service builds & runs; movies/payment create/payment get reachable ----
  let getOk = false;
  let getStatus = 'skipped';
  if (pid) {
    const g = await request('GET', paymentUrl(pid), { headers: authH(9001) });
    getOk = g.status === 200 && !!g.json;
    getStatus = String(g.status);
  }
  record('I1', '基础接口契约与支付查询', movies.status === 200 && createOk && getOk,
    `GET /movies -> ${movies.status}; POST /payments/alipay/create -> ${base.resp.status}; GET /payments/alipay/:otn -> ${getStatus}; otn=${base.otn}`,
    ['backend.log', 'integration_results.json']);

  // ---- I2: client confirm does NOT make it paid ----
  if (pid) {
    // ensure gateway still says not-paid for this otn
    if (otn) mergeState(otn, { trade_status: 'WAIT_BUYER_PAY', total_amount: TEST_PRICE_ALIPAY });
    const c = await request('POST', paymentUrl(pid, 'confirm'),
      { headers: authH(9001), body: { client_result_code: '9000' } });
    const st = await statusOf(pid, 9001);
    const notPaid = !isPaidStatus(st);
    const confirmReached = getOk && c.status >= 200 && c.status < 500 && c.status !== 404;
    record('I2', '客户端成功回调不能直接履约', confirmReached && notPaid,
      `confirm -> ${c.status}; status after confirm = "${st}"; payment_query_ok=${getOk}`, []);
  } else {
    failPrereq('I2', '客户端成功回调不能直接履约', '无 payment id');
  }

  // ---- I7 / I8 depend on signing ----
  if (!SIGNING.notify_ok) {
    failPrereq('I7', '有效通知推进支付成功', '签名自检未通过，无法执行通知验签测试');
    failPrereq('I5', '通知关键字段不匹配必须拒绝', '签名自检未通过，无法执行通知验签测试');
    failPrereq('I4', '无效签名通知必须拒绝', '签名自检未通过，无法执行通知验签测试');
    failPrereq('I12', '重复通知或查单幂等', '签名自检未通过，无法执行通知验签测试');
    failPrereq('I11', '终态不被旧通知覆盖', '签名自检未通过，无法执行通知验签测试');
  } else {
    await notifyTests(keys, pid, otn);
  }

  // ---- I8 query compensation (needs query_ok) ----
  await queryCompensationTest(pid, otn);

  // ---- I3: client failure/cancel callback cannot override paid terminal state ----
  if (pid) {
    const before = await statusOf(pid, 9001);
    if (isPaidStatus(before)) {
      const cfail = await request('POST', paymentUrl(pid, 'confirm'),
        { headers: authH(9001), body: { client_result_code: '6001' } });
      const after = await statusOf(pid, 9001);
      record('I3', '失败或取消回调不能覆盖终态', isPaidStatus(after),
        `client cancel after paid -> ${cfail.status}; before="${before}"; after="${after}"`, []);
    } else {
      failPrereq('I3', '失败或取消回调不能覆盖终态', '支付尚未进入 paid，无法验证终态保护');
    }
  } else {
    failPrereq('I3', '失败或取消回调不能覆盖终态', '无 payment id');
  }

  // ---- I6: ownership — buyer B cannot drive buyer A's payment ----
  if (pid) {
    const c = await request('POST', paymentUrl(pid, 'confirm'),
      { headers: authH(9002), body: { client_result_code: '9000' } });
    const st = await statusOf(pid, 9001);
    const ownerResourceExists = getOk;
    const rejected = ownerResourceExists && (c.status === 401 || c.status === 403 || c.status === 404 || !isPaidStatus(st));
    record('I6', '跨用户订单操作必须拒绝', rejected,
      `B confirm A's payment -> ${c.status}; A status still "${st}"; owner_payment_query_ok=${ownerResourceExists}`, []);
  } else {
    failPrereq('I6', '跨用户订单操作必须拒绝', '无 payment id');
  }

  // ---- I10: no duplicate active payment before confirm ----
  if (createOk && otn) {
    const dup = await createPaymentForA([90011]);
    // Acceptable: reuse same otn, or 4xx/409, or otherwise not a brand-new valid trade.
    const sameOtn = dup.otn && otn && dup.otn === otn;
    const refused = dup.resp.status >= 400;
    record('I10', '待支付订单防重复支付', !!(sameOtn || refused),
      `dup create -> ${dup.resp.status}; otn=${dup.otn} (orig ${otn})`, []);
  } else {
    record('I10', '待支付订单防重复支付', false,
      '基础支付创建未成功，无法验证重复支付防护',
      ['backend.log', 'integration_results.json']);
  }

  // ---- refund + amount tests need a PAID payment. Drive via sync(query=success). ----
  await refundTests(pid, otn);

  // ---- extra App Pay safety counterexamples ----
  await additionalSafetyTests(keys);

  // ---- finalize ----
  const payload = { results, signing: SIGNING, base_url: BASE };
  fs.writeFileSync(path.join(OUT, 'integration_results.json'), JSON.stringify(payload, null, 2));
  process.stdout.write(`integration tests done: ${results.length} checks\n`);
}

async function statusOf(pid, uid) {
  const g = await request('GET', paymentUrl(pid), { headers: authH(uid) });
  return extractStatus(g);
}

// Drive a payment to paid via sync against a success-returning gateway.
async function driveToPaidViaSync(pid, otn) {
  if (otn) mergeState(otn, { trade_status: 'TRADE_SUCCESS', total_amount: TEST_PRICE_ALIPAY, buyer_user_id: '2088EVALBUYERA' });
  const s = await request('POST', paymentUrl(pid, 'sync'),
    { headers: authH(9001), body: {} });
  await sleep(200);
  const st = await statusOf(pid, 9001);
  return { syncResp: s, status: st };
}

async function queryCompensationTest(pid, otn) {
  if (!pid) { failPrereq('I8', '查单补偿推进支付成功', '无 payment id'); failPrereq('I9', '处理中状态保持 pending', '无 payment id'); return; }
  if (!SIGNING.query_ok) {
    failPrereq('I8', '查单补偿推进支付成功', '网关查单签名自检未通过，无法执行查单补偿测试');
    failPrereq('I9', '处理中状态保持 pending', '网关查单签名自检未通过，无法执行查单补偿测试');
    return;
  }
  // I9: processing -> stays pending
  if (otn) mergeState(otn, { trade_status: 'WAIT_BUYER_PAY' });
  const s1 = await request('POST', paymentUrl(pid, 'sync'), { headers: authH(9001), body: {} });
  const st1 = await statusOf(pid, 9001);
  const syncReached = s1.status >= 200 && s1.status < 300;
  const statusReadable = st1.length > 0;
  record('I9', '处理中状态保持 pending', syncReached && statusReadable && isPendingStatus(st1),
    `sync(processing) -> ${s1.status}; status="${st1}"`, ['replay-requests.log']);

  // I8: gateway success -> sync compensates to paid
  const r = await driveToPaidViaSync(pid, otn);
  // evidence the backend actually called the gateway:
  const calledGateway = fs.existsSync(path.join(OUT, 'replay-requests.log')) &&
    fs.readFileSync(path.join(OUT, 'replay-requests.log'), 'utf8').includes('alipay.trade.query');
  record('I8', '查单补偿推进支付成功', isPaidStatus(r.status) && calledGateway,
    `sync(success) -> ${r.syncResp.status}; status="${r.status}"; gateway_called=${calledGateway}`,
    ['replay-requests.log']);
}

async function notifyTests(keys, pid, otn) {
  if (!keys || !otn) {
    failPrereq('I7', '有效通知推进支付成功', '缺少 keys 或 out_trade_no');
    failPrereq('I5', '通知关键字段不匹配必须拒绝', '缺少 keys 或 out_trade_no');
    failPrereq('I4', '无效签名通知必须拒绝', '缺少 keys 或 out_trade_no');
    failPrereq('I12', '重复通知或查单幂等', '缺少 keys 或 out_trade_no');
    failPrereq('I11', '终态不被旧通知覆盖', '缺少 keys 或 out_trade_no');
    return;
  }
  const mode = (SIGNING.notify_mode) || { excludeSignType: false };
  const base = {
    app_id: APP_ID,
    out_trade_no: otn,
    trade_no: 'NOTIFY' + otn,
    trade_status: 'TRADE_SUCCESS',
    total_amount: TEST_PRICE_ALIPAY,
    buyer_user_id: BUYER_A_ALIPAY_ID,
    buyer_logon_id: 'buyer-a@example.com',
    gmt_payment: '2026-06-15 10:00:00',
    seller_id: process.env.ALIPAY_SELLER_ID || '2088SELLEREVAL',
  };
  const notifyUrl = `${BASE}/api/v1/payments/alipay/notify`;

  // I4: invalid signature rejected (tamper the sign)
  {
    const good = buildNotify(base, keys.alipay_private_pem, mode);
    const bad = { ...good, sign: (good.sign || 'x').slice(0, -6) + 'BADBAD' };
    const r = await request('POST', notifyUrl, { form: bad });
    const st = await statusOf(pid, 9001);
    const endpointReached = r.status !== 404;
    const rejected = endpointReached && !isPaidStatus(st) && (r.status >= 400 || /fail/i.test(r.text));
    record('I4', '无效签名通知必须拒绝', rejected,
      `bad-sign notify -> ${r.status}, body="${r.text.slice(0,40)}"; status="${st}"; notify_endpoint_reached=${endpointReached}`, []);
  }

  // I5: valid signature but mismatched field (wrong amount) rejected
  {
    const mism = { ...base, total_amount: '9999.99' };
    const signed = buildNotify(mism, keys.alipay_private_pem, mode);
    const r = await request('POST', notifyUrl, { form: signed });
    const st = await statusOf(pid, 9001);
    const endpointReached = r.status !== 404;
    const rejected = endpointReached && !isPaidStatus(st) && (r.status >= 400 || /fail/i.test(r.text));
    record('I5', '通知关键字段不匹配必须拒绝', rejected,
      `mismatch-amount notify -> ${r.status}; status="${st}"; notify_endpoint_reached=${endpointReached}`, []);
  }

  // I7: valid + matching -> paid, idempotent
  {
    const signed = buildNotify(base, keys.alipay_private_pem, mode);
    const r1 = await request('POST', notifyUrl, { form: signed });
    await sleep(200);
    const st1 = await statusOf(pid, 9001);
    // I12: replay the SAME notify; should not double-apply (still paid, no error 5xx)
    const r2 = await request('POST', notifyUrl, { form: signed });
    await sleep(150);
    const st2 = await statusOf(pid, 9001);
    record('I7', '有效通知推进支付成功', isPaidStatus(st1),
      `valid notify -> ${r1.status}; status="${st1}"`, []);
    record('I12', '重复通知或查单幂等', isPaidStatus(st2) && r2.status < 500,
      `replay notify -> ${r2.status}; status="${st2}"`, []);

    // I11: terminal guard — send a later cancel/failure notify; must NOT override paid
    const fail = { ...base, trade_status: 'TRADE_CLOSED', trade_no: 'NOTIFY' + otn };
    const signedFail = buildNotify(fail, keys.alipay_private_pem, mode);
    const r3 = await request('POST', notifyUrl, { form: signedFail });
    await sleep(150);
    const st3 = await statusOf(pid, 9001);
    record('I11', '终态不被旧通知覆盖', isPaidStatus(st3),
      `closed notify after paid -> ${r3.status}; status="${st3}"`, []);
  }
}

async function refundTests(pid, otn) {
  if (!pid) {
    failPrereq('I13', '退款请求调用支付宝网关', '无 payment id');
    failPrereq('I14', '退款请求号幂等策略', '无 payment id');
    failPrereq('I15', '部分退款与全额退款状态', '无 payment id');
    failPrereq('I16', '金额一致性与超额退款防护', '无 payment id');
    return;
  }
  // Need a paid payment first. Prefer notify path (already paid in I7); else sync.
  let st = await statusOf(pid, 9001);
  if (!isPaidStatus(st)) {
    if (SIGNING.query_ok) {
      const r = await driveToPaidViaSync(pid, otn);
      st = r.status;
    }
  }
  if (!isPaidStatus(st)) {
    failPrereq('I13', '退款请求调用支付宝网关', '无法将支付推进到 paid（依赖 notify/query 签名自检），跳过退款测试');
    failPrereq('I14', '退款请求号幂等策略', '无法将支付推进到 paid（依赖 notify/query 签名自检），跳过退款测试');
    failPrereq('I15', '部分退款与全额退款状态', '无法将支付推进到 paid（依赖 notify/query 签名自检），跳过退款测试');
    failPrereq('I16', '金额一致性与超额退款防护', '无法将支付推进到 paid（依赖 notify/query 签名自检），跳过退款测试');
    return;
  }

  const refundUrl = paymentUrl(pid, 'refund');

  // I13: partial refund hits the gateway refund API
  const partialRequestNo = `${otn || pid}_RF_PARTIAL_EVAL`;
  const r1 = await request('POST', refundUrl, {
    headers: authH(9001),
    body: { amount: 400, out_request_no: partialRequestNo, refund_request_no: partialRequestNo }
  });
  await sleep(150);
  const afterPartial = await statusOf(pid, 9001);
  const refundEntriesAfterPartial = readGatewayEntries('alipay.trade.refund');
  const partialCalls = refundEntriesAfterPartial.filter((entry) => {
    const biz = entry.biz_content || {};
    return String(biz.out_request_no || biz.outRequestNo || '') === partialRequestNo;
  });
  const calledRefund = partialCalls.length >= 1;
  record('I13', '退款请求调用支付宝网关', r1.status < 500 && calledRefund,
    `refund(4) -> ${r1.status}; gateway_refund_called=${calledRefund}; request_no=${partialRequestNo}`, ['replay-requests.log']);

  // I14: retrying the same refund request keeps the same request number and does not create a new strategy.
  const retry = await request('POST', refundUrl, {
    headers: authH(9001),
    body: { amount: 400, out_request_no: partialRequestNo, refund_request_no: partialRequestNo }
  });
  await sleep(150);
  const partialCallsAfterRetry = readGatewayEntries('alipay.trade.refund').filter((entry) => {
    const biz = entry.biz_content || {};
    return String(biz.out_request_no || biz.outRequestNo || '') === partialRequestNo;
  });
  const allRetryCallsUseSameRequestNo = partialCallsAfterRetry.length >= partialCalls.length
    && partialCallsAfterRetry.every((entry) => {
      const biz = entry.biz_content || {};
      return String(biz.out_request_no || biz.outRequestNo || '') === partialRequestNo;
    });
  record('I14', '退款请求号幂等策略',
    retry.status < 500 && partialCallsAfterRetry.length >= 1 && allRetryCallsUseSameRequestNo,
    `retry refund -> ${retry.status}; calls_with_same_request_no=${partialCallsAfterRetry.length}; request_no=${partialRequestNo}`,
    ['replay-requests.log']);

  // I15: partial refund must not be treated as full refund; remaining refund should be distinguishable.
  const fullRequestNo = `${otn || pid}_RF_REMAINING_EVAL`;
  const partialStillActive = isPaidStatus(afterPartial) || isPartialRefundStatus(afterPartial);
  const full = await request('POST', refundUrl, {
    headers: authH(9001),
    body: { amount: 800, out_request_no: fullRequestNo, refund_request_no: fullRequestNo }
  });
  await sleep(150);
  const afterFull = await statusOf(pid, 9001);
  const fullRefundCalls = readGatewayEntries('alipay.trade.refund').filter((entry) => {
    const biz = entry.biz_content || {};
    return String(biz.out_request_no || biz.outRequestNo || '') === fullRequestNo;
  });
  const fullDistinguished = full.status < 500 && fullRefundCalls.length >= 1
    && partialStillActive && !isRefundedStatus(afterPartial) && isRefundedStatus(afterFull);
  record('I15', '部分退款与全额退款状态', fullDistinguished,
    `after partial="${afterPartial}"; remaining refund -> ${full.status}; after full="${afterFull}"; full_request_no=${fullRequestNo}`,
    ['replay-requests.log']);

  // I16: over-refund must be rejected after previous refunds.
  const r2 = await request('POST', refundUrl, { headers: authH(9001), body: { amount: 999999 } });
  const businessRejected = r2.status >= 400 && r2.status < 500;
  record('I16', '金额一致性与超额退款防护', businessRejected,
    `over-refund -> ${r2.status}; status_after_full="${afterFull}"`, []);
}

function notifyMode() {
  return (SIGNING.notify_mode) || { excludeSignType: false };
}

function successNotifyBase(otn) {
  return {
    app_id: APP_ID,
    out_trade_no: otn,
    trade_no: 'NOTIFY' + otn,
    trade_status: 'TRADE_SUCCESS',
    total_amount: TEST_PRICE_ALIPAY,
    buyer_user_id: BUYER_A_ALIPAY_ID,
    buyer_logon_id: 'buyer-a@example.com',
    gmt_payment: '2026-06-15 10:00:00',
    seller_id: process.env.ALIPAY_SELLER_ID || '2088SELLEREVAL',
  };
}

async function freshPaidPayment(bookingId, label) {
  const created = await createPaymentForA([bookingId]);
  if (!created.pid || !created.otn) throw new Error(`${label}: create payment failed`);
  const paid = await driveToPaidViaSync(created.pid, created.otn);
  if (!isPaidStatus(paid.status)) throw new Error(`${label}: cannot drive payment to paid, status=${paid.status}`);
  return created;
}

async function signedNotifyRejectionProbe(bookingId, keys, extra, label) {
  if (!SIGNING.notify_ok || !keys) {
    return { passed: false, detail: `${label}: 签名自检未通过，无法执行签名字段错配测试` };
  }
  const created = await createPaymentForA([bookingId]);
  if (!created.pid || !created.otn) {
    return { passed: false, detail: `${label}: 无法创建 fresh payment` };
  }
  const signed = buildNotify({ ...successNotifyBase(created.otn), ...extra }, keys.alipay_private_pem, notifyMode());
  const r = await request('POST', `${BASE}/api/v1/payments/alipay/notify`, { form: signed });
  await sleep(150);
  const st = await statusOf(created.pid, 9001);
  const rejected = r.status !== 404 && !isPaidStatus(st) && (r.status >= 400 || /fail/i.test(r.text));
  return {
    passed: rejected,
    detail: `${label} notify -> ${r.status}; status="${st}"; endpoint_reached=${r.status !== 404}`,
  };
}

async function additionalSafetyTests(keys) {
  const wrongApp = await signedNotifyRejectionProbe(
    90013, keys, { app_id: 'evil_app_id' }, 'wrong-app-only'
  );
  const wrongSeller = await signedNotifyRejectionProbe(
    90022, keys, { seller_id: 'evil_seller_id' }, 'wrong-seller-only'
  );
  record('I17', '通知 app/seller 身份错配必须拒绝',
    wrongApp.passed && wrongSeller.passed,
    `${wrongApp.detail}; ${wrongSeller.detail}`, []);

  const wrongBuyer = await signedNotifyRejectionProbe(
    90014, keys,
    { buyer_user_id: BUYER_B_ALIPAY_ID, buyer_logon_id: 'buyer-b@example.com' },
    'buyer-mismatch'
  );
  record('I18', '通知买家身份错配必须拒绝', wrongBuyer.passed, wrongBuyer.detail, []);

  // I19: paid is terminal even if a later sync sees a stale non-success status.
  try {
    const paid = await freshPaidPayment(90015, 'I19');
    mergeState(paid.otn, { trade_status: 'WAIT_BUYER_PAY', total_amount: TEST_PRICE_ALIPAY, buyer_user_id: BUYER_A_ALIPAY_ID });
    const sync = await request('POST', paymentUrl(paid.pid, 'sync'), { headers: authH(9001), body: {} });
    await sleep(150);
    const st = await statusOf(paid.pid, 9001);
    record('I19', 'paid 终态不被后续查单降级', isPaidStatus(st),
      `sync(stale WAIT_BUYER_PAY) -> ${sync.status}; status="${st}"`, ['replay-requests.log']);
  } catch (e) {
    failPrereq('I19', 'paid 终态不被后续查单降级', String(e && e.message || e));
  }

  // I20/I21: refund API success code is not enough when fund_change=N / refund query is still uncertain.
  try {
    const paid = await freshPaidPayment(90016, 'I20');
    mergeState(paid.otn, {
      trade_status: 'TRADE_SUCCESS', total_amount: TEST_PRICE_ALIPAY,
      buyer_user_id: BUYER_A_ALIPAY_ID, refund_fund_change: 'N', refund_query_status: 'REFUND_PROCESSING'
    });
    const requestNo = `${paid.otn}_RF_FUND_N`;
    const refund = await request('POST', paymentUrl(paid.pid, 'refund'), {
      headers: authH(9001),
      body: { amount: 400, out_request_no: requestNo, refund_request_no: requestNo }
    });
    await sleep(150);
    const afterRefund = await statusOf(paid.pid, 9001);
    const refundCalls = readGatewayEntries('alipay.trade.refund').filter((entry) => {
      const biz = entry.biz_content || {};
      return String(biz.out_request_no || biz.outRequestNo || '') === requestNo;
    });
    record('I20', 'fund_change=N 不得当作最终退款成功',
      refund.status < 500 && refundCalls.length >= 1 && !isRefundedStatus(afterRefund) && !isPartialRefundStatus(afterRefund),
      `refund fund_change=N -> ${refund.status}; status="${afterRefund}"; refund_calls=${refundCalls.length}`,
      ['replay-requests.log']);

    const retry = await request('POST', paymentUrl(paid.pid, 'refund'), {
      headers: authH(9001),
      body: { amount: 400, out_request_no: requestNo, refund_request_no: requestNo }
    });
    await sleep(150);
    const afterQuery = await statusOf(paid.pid, 9001);
    const queryCalls = readGatewayEntries('alipay.trade.fastpay.refund.query').filter((entry) => {
      const biz = entry.biz_content || {};
      return String(biz.out_request_no || biz.outRequestNo || '') === requestNo;
    });
    record('I21', '退款查询不确定时保持 pending/refunding',
      retry.status < 500 && queryCalls.length >= 1 && !isRefundedStatus(afterQuery) && !isPartialRefundStatus(afterQuery),
      `retry after fund_change=N -> ${retry.status}; refund_query_calls=${queryCalls.length}; status="${afterQuery}"`,
      ['replay-requests.log']);
  } catch (e) {
    failPrereq('I20', 'fund_change=N 不得当作最终退款成功', String(e && e.message || e));
    failPrereq('I21', '退款查询不确定时保持 pending/refunding', String(e && e.message || e));
  }

  // I22: same out_request_no cannot be reused for a different refund amount.
  try {
    const paid = await freshPaidPayment(90017, 'I22');
    const requestNo = `${paid.otn}_RF_CONFLICT`;
    const first = await request('POST', paymentUrl(paid.pid, 'refund'), {
      headers: authH(9001),
      body: { amount: 400, out_request_no: requestNo, refund_request_no: requestNo }
    });
    await sleep(120);
    const second = await request('POST', paymentUrl(paid.pid, 'refund'), {
      headers: authH(9001),
      body: { amount: 500, out_request_no: requestNo, refund_request_no: requestNo }
    });
    await sleep(120);
    const conflictCalls = readGatewayEntries('alipay.trade.refund').filter((entry) => {
      const biz = entry.biz_content || {};
      const req = String(biz.out_request_no || biz.outRequestNo || '');
      const amount = Number(biz.refund_amount || biz.refundAmount || 0);
      return req === requestNo && amount === 500;
    });
    const rejectedOrSuppressed = second.status >= 400 || conflictCalls.length === 0;
    record('I22', '同一退款请求号不同金额必须拒绝',
      first.status < 500 && rejectedOrSuppressed,
      `first refund -> ${first.status}; second different amount -> ${second.status}; conflict_gateway_calls=${conflictCalls.length}`,
      ['replay-requests.log']);
  } catch (e) {
    failPrereq('I22', '同一退款请求号不同金额必须拒绝', String(e && e.message || e));
  }

  // I23: multiple partial refunds are allowed only with different request numbers and bounded total.
  try {
    const paid = await freshPaidPayment(90018, 'I23');
    const req1 = `${paid.otn}_RF_PART1`;
    const req2 = `${paid.otn}_RF_PART2`;
    const req3 = `${paid.otn}_RF_OVER`;
    const first = await request('POST', paymentUrl(paid.pid, 'refund'), {
      headers: authH(9001), body: { amount: 400, out_request_no: req1, refund_request_no: req1 }
    });
    await sleep(120);
    const second = await request('POST', paymentUrl(paid.pid, 'refund'), {
      headers: authH(9001), body: { amount: 800, out_request_no: req2, refund_request_no: req2 }
    });
    await sleep(120);
    const over = await request('POST', paymentUrl(paid.pid, 'refund'), {
      headers: authH(9001), body: { amount: 100, out_request_no: req3, refund_request_no: req3 }
    });
    await sleep(120);
    const calls = readGatewayEntries('alipay.trade.refund').filter((entry) => {
      const biz = entry.biz_content || {};
      const req = String(biz.out_request_no || biz.outRequestNo || '');
      return [req1, req2, req3].includes(req);
    });
    const distinctPartialCalls = new Set(calls.map((entry) => String((entry.biz_content || {}).out_request_no || (entry.biz_content || {}).outRequestNo || '')));
    record('I23', '多次部分退款累计不得超过已付金额',
      first.status < 500 && second.status < 500 && over.status >= 400 && distinctPartialCalls.has(req1) && distinctPartialCalls.has(req2),
      `partial1 -> ${first.status}; partial2 -> ${second.status}; over -> ${over.status}; request_nos=${Array.from(distinctPartialCalls).join(',')}`,
      ['replay-requests.log']);
  } catch (e) {
    failPrereq('I23', '多次部分退款累计不得超过已付金额', String(e && e.message || e));
  }

  // I24: pending/unpaid payments cannot be refunded and must not hit the refund gateway.
  try {
    const pending = await createPaymentForA([90019]);
    if (!pending.pid || !pending.otn) throw new Error('I24: create pending payment failed');
    mergeState(pending.otn, { trade_status: 'WAIT_BUYER_PAY', total_amount: TEST_PRICE_ALIPAY, buyer_user_id: BUYER_A_ALIPAY_ID });
    const requestNo = `${pending.otn}_RF_PENDING_DENY`;
    const beforeCalls = readGatewayEntries('alipay.trade.refund').length;
    const refund = await request('POST', paymentUrl(pending.pid, 'refund'), {
      headers: authH(9001),
      body: { amount: 400, out_request_no: requestNo, refund_request_no: requestNo }
    });
    await sleep(150);
    const afterCalls = readGatewayEntries('alipay.trade.refund').length;
    const st = await statusOf(pending.pid, 9001);
    record('I24', '未支付订单禁止退款',
      responseIndicatesBusinessFailure(refund) && afterCalls === beforeCalls && !isRefundedStatus(st) && !isPartialRefundStatus(st),
      `pending refund -> ${refund.status}; refund_gateway_calls=${afterCalls - beforeCalls}; status="${st}"`,
      ['replay-requests.log']);
  } catch (e) {
    failPrereq('I24', '未支付订单禁止退款', String(e && e.message || e));
  }

  // I25: a different user cannot refund another user's paid payment and must not hit the refund gateway.
  try {
    const paid = await freshPaidPayment(90020, 'I25');
    const requestNo = `${paid.otn}_RF_OTHER_USER_DENY`;
    const beforeCalls = readGatewayEntries('alipay.trade.refund').length;
    const refund = await request('POST', paymentUrl(paid.pid, 'refund'), {
      headers: authH(9002),
      body: { amount: 400, out_request_no: requestNo, refund_request_no: requestNo }
    });
    await sleep(150);
    const afterCalls = readGatewayEntries('alipay.trade.refund').length;
    const st = await statusOf(paid.pid, 9001);
    record('I25', '跨用户禁止退款',
      responseIndicatesBusinessFailure(refund) && afterCalls === beforeCalls && isPaidStatus(st),
      `B refunds A payment -> ${refund.status}; refund_gateway_calls=${afterCalls - beforeCalls}; owner_status="${st}"`,
      ['replay-requests.log']);
  } catch (e) {
    failPrereq('I25', '跨用户禁止退款', String(e && e.message || e));
  }
}

function readLog() {
  try { return fs.readFileSync(path.join(OUT, 'replay-requests.log'), 'utf8'); } catch (_e) { return ''; }
}

function readGatewayEntries(method) {
  return readLog()
    .split(/\n+/)
    .filter(Boolean)
    .map((line) => {
      try { return JSON.parse(line); } catch (_e) { return null; }
    })
    .filter((entry) => entry && (!method || entry.method === method));
}

main().catch((e) => {
  record('FATAL', 'integration harness error', false, String(e && e.stack ? e.stack : e), []);
  try {
    fs.writeFileSync(path.join(OUT, 'integration_results.json'),
      JSON.stringify({ results, signing: SIGNING, fatal: String(e) }, null, 2));
  } catch (_e) { /* ignore */ }
  process.exit(0); // never hard-fail; build_result.py interprets results
});
