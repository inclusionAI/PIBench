#!/usr/bin/env node
/*
 * Mock Alipay OpenAPI gateway for integration tests.
 * Responds to any gateway method (e.g. alipay.trade.query) with a signed
 * success payload: {"<method>_response":{...},"sign":"<RSA2 over the exact
 * JSON substring>"} — the same shape alipay-sdk's validateSign expects.
 *
 * Usage: node mock_alipay_gateway.js <port> <private_key_pem_path> <request_log_path>
 */
const http = require('http');
const fs = require('fs');
const crypto = require('crypto');
const { URL } = require('url');

const port = parseInt(process.argv[2] || '8765', 10);
const privateKeyPem = fs.readFileSync(process.argv[3], 'utf8');
const logPath = process.argv[4] || '/output/alipay-mock-requests.log';

function logLine(obj) {
    try {
        fs.appendFileSync(logPath, JSON.stringify(obj) + '\n');
    } catch (e) { /* logging must never kill the mock */ }
}

function buildResponse(method, bizContent) {
    let biz = {};
    try { biz = JSON.parse(bizContent || '{}'); } catch (e) { biz = {}; }
    const outTradeNo = biz.out_trade_no || 'UNKNOWN';
    const payload = {
        code: '10000',
        msg: 'Success',
        out_trade_no: outTradeNo,
        trade_no: 'MOCKTRADE' + Date.now(),
        buyer_logon_id: 'wfq***@sandbox.com',
        trade_status: 'TRADE_SUCCESS',
        total_amount: biz.total_amount || '800.00',
    };
    const key = (method || 'alipay.unknown').replace(/\./g, '_') + '_response';
    const payloadStr = JSON.stringify(payload);
    const sign = crypto.sign('RSA-SHA256', Buffer.from(payloadStr, 'utf8'), privateKeyPem)
        .toString('base64');
    // Exact string concatenation matters: the SDK verifies the raw substring.
    return `{"${key}":${payloadStr},"sign":"${sign}"}`;
}

const server = http.createServer((req, res) => {
    let body = '';
    req.on('data', (chunk) => { body += chunk; });
    req.on('end', () => {
        const u = new URL(req.url, `http://127.0.0.1:${port}`);
        const params = new URLSearchParams(body);
        for (const [k, v] of u.searchParams) {
            if (!params.has(k)) params.set(k, v);
        }
        const method = params.get('method') || '';
        const bizContent = params.get('biz_content') || '';
        logLine({
            time: new Date().toISOString(),
            path: u.pathname,
            method,
            biz_content: bizContent,
            app_id: params.get('app_id') || null,
        });
        const responseBody = buildResponse(method, bizContent);
        res.writeHead(200, { 'Content-Type': 'application/json;charset=utf-8' });
        res.end(responseBody);
    });
});

server.listen(port, '127.0.0.1', () => {
    console.log(`mock alipay gateway listening on 127.0.0.1:${port}`);
});
