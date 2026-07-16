'use strict';
/*
 * mock_alipay_gateway.js — a local stand-in for the Alipay OpenAPI gateway.
 *
 * The backend's alipay-sdk posts form-encoded requests here (method, biz_content,
 * sign, ...). We DO NOT verify the merchant signature strictly (the SDK already
 * proves the agent signed with the injected key by virtue of using ALIPAY_GATEWAY),
 * but we DO record every request so integration tests can assert the backend
 * actually called the gateway (rubric I1/I13/L2: "uses runtime ALIPAY_GATEWAY").
 *
 * Behaviour per out_trade_no is controlled by a JSON state file (ALIPAY_MOCK_STATE)
 * that integration tests rewrite between steps:
 *   { "<out_trade_no>": { "trade_status": "TRADE_SUCCESS"|"WAIT_BUYER_PAY"|...,
 *                          "total_amount": "12.00", "refunds": {...} } }
 *
 * Default (no entry) -> WAIT_BUYER_PAY (i.e. "处理中 / 未支付"), so a backend that
 * fakes success without consulting the gateway will be caught.
 *
 * Responses are signed with the alipay PRIVATE key so the backend's
 * alipay-sdk (configured with the alipay PUBLIC key) verifies them.
 *
 * Env:
 *   ALIPAY_MOCK_PORT   (default 8765)
 *   ALIPAY_MOCK_KEYS   keys dir (keys.json)
 *   ALIPAY_MOCK_STATE  path to JSON state file
 *   ALIPAY_MOCK_LOG    path to request log (JSONL)
 */
const http = require('http');
const fs = require('fs');
const querystring = require('querystring');
const { loadKeys, signGatewayResponse } = require('./sign_util');

const PORT = Number(process.env.ALIPAY_MOCK_PORT || 8765);
const KEYS_DIR = process.env.ALIPAY_MOCK_KEYS || '/output/alipay_keys';
const STATE_FILE = process.env.ALIPAY_MOCK_STATE || '/output/alipay_mock_state.json';
const LOG_FILE = process.env.ALIPAY_MOCK_LOG || '/output/replay-requests.log';

const keys = loadKeys(KEYS_DIR);

function readState() {
  try {
    return JSON.parse(fs.readFileSync(STATE_FILE, 'utf8'));
  } catch (_e) {
    return {};
  }
}

function logReq(entry) {
  try {
    fs.appendFileSync(LOG_FILE, JSON.stringify(entry) + '\n');
  } catch (_e) { /* ignore */ }
}

function respond(res, methodResponseKey, node) {
  const body = signGatewayResponse(methodResponseKey, node, keys.alipay_private_pem);
  res.writeHead(200, { 'Content-Type': 'application/json; charset=utf-8' });
  res.end(body);
}

function handle(method, biz, res) {
  const state = readState();
  const otn = biz.out_trade_no || biz.outTradeNo;
  const entry = (otn && state[otn]) || {};

  if (method === 'alipay.trade.query') {
    const tradeStatus = entry.trade_status || 'WAIT_BUYER_PAY';
    const node = {
      code: '10000',
      msg: 'Success',
      out_trade_no: otn || '',
      trade_no: entry.trade_no || (otn ? 'MOCK' + otn : 'MOCK0'),
      trade_status: tradeStatus,
      total_amount: entry.total_amount || '0.00',
      buyer_logon_id: entry.buyer_logon_id || 'buyer@example.com',
      buyer_user_id: entry.buyer_user_id || '2088MOCKBUYER0001',
    };
    return respond(res, 'alipay_trade_query_response', node);
  }

  if (method === 'alipay.trade.refund') {
    // Echo back a refund response controlled by integration-test state.
    const fundChange = entry.refund_fund_change || 'Y';
    const node = {
      code: entry.refund_code || '10000',
      msg: entry.refund_msg || 'Success',
      out_trade_no: otn || '',
      trade_no: entry.trade_no || (otn ? 'MOCK' + otn : 'MOCK0'),
      refund_fee: String(biz.refund_amount || biz.refundAmount || '0.00'),
      total_amount: entry.total_amount || '0.00',
      fund_change: fundChange,
      refund_status: entry.refund_status || (fundChange === 'Y' ? 'REFUND_SUCCESS' : 'REFUND_PROCESSING'),
    };
    return respond(res, 'alipay_trade_refund_response', node);
  }

  if (method === 'alipay.trade.fastpay.refund.query') {
    const fundChange = entry.refund_fund_change || 'Y';
    const node = {
      code: entry.refund_query_code || '10000',
      msg: entry.refund_query_msg || 'Success',
      out_trade_no: otn || '',
      out_request_no: biz.out_request_no || biz.outRequestNo || '',
      refund_amount: String(biz.refund_amount || '0.00'),
      total_amount: entry.total_amount || '0.00',
      fund_change: fundChange,
      refund_status: entry.refund_query_status || (fundChange === 'Y' ? 'REFUND_SUCCESS' : 'REFUND_PROCESSING'),
    };
    return respond(res, 'alipay_trade_fastpay_refund_query_response', node);
  }

  // Unknown method: still 10000 so we don't masquerade as a network error,
  // but mark it so tests can notice.
  return respond(res, 'alipay_unknown_response', {
    code: '40004', msg: 'Business Failed', sub_msg: 'unsupported mock method: ' + method,
  });
}

const server = http.createServer((req, res) => {
  let chunks = '';
  req.on('data', (d) => { chunks += d; });
  req.on('end', () => {
    let queryParams = {};
    let bodyParams = {};
    try {
      const u = new URL(req.url, 'http://127.0.0.1');
      queryParams = Object.fromEntries(u.searchParams.entries());
    } catch (_e) { queryParams = {}; }
    try {
      bodyParams = querystring.parse(chunks);
    } catch (_e) { bodyParams = {}; }
    const params = {
      ...queryParams,
      ...bodyParams,
    };
    if (!params.biz_content && params.bizContent) {
      params.biz_content = params.bizContent;
    }
    let biz = {};
    try {
      biz = params.biz_content ? JSON.parse(params.biz_content) : {};
    } catch (_e) { biz = {}; }
    const method = params.method || '';
    logReq({
      ts: new Date().toISOString(),
      method,
      app_id: params.app_id,
      sign_type: params.sign_type,
      has_sign: !!params.sign,
      biz_content: biz,
    });
    try {
      handle(method, biz, res);
    } catch (e) {
      res.writeHead(500, { 'Content-Type': 'application/json' });
      res.end(JSON.stringify({ error: String(e) }));
    }
  });
});

server.listen(PORT, '127.0.0.1', () => {
  process.stdout.write(`mock alipay gateway listening on 127.0.0.1:${PORT}\n`);
});
