"""Test-side Alipay gateway mock for POS safety bases.

This server is intentionally separate from the business app. It simulates the
Alipay unified gateway enough for tests to exercise signing, amount binding,
order binding, pending/failure states, duplicate notifications, and query paths.
"""
import argparse
import base64
import json
import subprocess
import tempfile
import time
import urllib.parse
import urllib.request
import urllib.error
from http.server import BaseHTTPRequestHandler
try:
    from http.server import ThreadingHTTPServer
except ImportError:
    import socketserver
    from http.server import HTTPServer
    class ThreadingHTTPServer(socketserver.ThreadingMixIn, HTTPServer):
        daemon_threads = True
from pathlib import Path
from typing import Any
ROOT = Path(__file__).resolve().parent
KEY_DIR = ROOT / 'mock_keys'
ALIPAY_PRIVATE_KEY = KEY_DIR / 'mock_alipay_private_key.pem'
ALIPAY_PUBLIC_KEY = KEY_DIR / 'mock_alipay_public_key.pem'
MERCHANT_PUBLIC_KEY = KEY_DIR / 'mock_merchant_public_key.pem'
TRADES = {}
REFUNDS = {}
SCENARIOS = {}
NOTIFY_LOG = []
GATEWAY_REQUESTS = []

def now_text():
    return time.strftime('%Y-%m-%d %H:%M:%S')

def trade_no(out_trade_no):
    return 'MOCK' + str(abs(hash(out_trade_no))).zfill(18)[-18:]

def compact_json(value):
    return json.dumps(value, ensure_ascii=False, separators=(',', ':'))

def sign_bytes(data, private_key=ALIPAY_PRIVATE_KEY):
    proc = subprocess.run(['openssl', 'dgst', '-sha256', '-sign', str(private_key)], input=data.encode('utf-8'), check=True, stdout=subprocess.PIPE)
    return base64.b64encode(proc.stdout).decode('ascii')

def verify_signature(data, signature, public_key=MERCHANT_PUBLIC_KEY):
    try:
        with tempfile.NamedTemporaryFile() as sig_file:
            sig_file.write(base64.b64decode(signature))
            sig_file.flush()
            proc = subprocess.run(['openssl', 'dgst', '-sha256', '-verify', str(public_key), '-signature', sig_file.name], input=data.encode('utf-8'), stdout=subprocess.PIPE, stderr=subprocess.DEVNULL)
            return proc.returncode == 0
    except Exception:
        return False

def sorted_sign_content(params):
    return '&'.join((f'{key}={params[key]}' for key in sorted(params) if key not in {'sign', 'sign_type'} and params[key] != ''))

def request_sign_contents(params):
    def build(skip_sign_type):
        ignored = {'sign'}
        if skip_sign_type:
            ignored.add('sign_type')
        return '&'.join((f'{key}={params[key]}' for key in sorted(params) if key not in ignored and params[key] != ''))
    contents = [build(False), build(True)]
    return list(dict.fromkeys(contents))

def infer_scenario(out_trade_no):
    explicit = SCENARIOS.get(out_trade_no)
    if explicit:
        return explicit
    lowered = out_trade_no.lower()
    for name in ('wrong_amount', 'bad_signature', 'unsigned', 'wait', 'fail', 'gateway_error', 'query_timeout', 'code_only'):
        if lowered.endswith(name) or lowered.endswith(name.replace('_', '')):
            return name
    return 'success'

def money(value):
    return f'{float(value):.2f}'

def find_trade_by_no(value):
    for trade in TRADES.values():
        if trade.get('trade_no') == value:
            return trade
    return None

def response_name(method):
    return method.replace('.', '_') + '_response'

def gateway_body(method, response_obj, scenario='success'):
    key = response_name(method)
    response_json = compact_json(response_obj)
    if scenario == 'unsigned':
        return f'{{"{key}":{response_json}}}'.encode('utf-8')
    sign_src = response_json
    if scenario == 'bad_signature':
        sign_src = response_json + ':bad'
    signature = sign_bytes(sign_src)
    return f'{{"{key}":{response_json},"sign":"{signature}"}}'.encode('utf-8')

def error_response(method, code, sub_code, sub_msg):
    return gateway_body(method, {'code': code, 'msg': 'Business Failed', 'sub_code': sub_code, 'sub_msg': sub_msg})

def parse_biz(params):
    raw = params.get('biz_content', '{}')
    try:
        return json.loads(raw)
    except json.JSONDecodeError:
        return {}

def ensure_trade(out_trade_no, total_amount, subject='Bill Express'):
    trade = TRADES.get(out_trade_no)
    if not trade:
        trade = {'out_trade_no': out_trade_no, 'trade_no': trade_no(out_trade_no), 'total_amount': money(total_amount), 'subject': subject, 'buyer_user_id': '2088000000000001', 'buyer_logon_id': 'buyer****@sandbox.example', 'trade_status': 'WAIT_BUYER_PAY', 'notify_count': 0}
        TRADES[out_trade_no] = trade
    return trade

def scenario_status(scenario):
    if scenario == 'success' or scenario in {'wrong_amount', 'bad_signature', 'unsigned'}:
        return 'TRADE_SUCCESS'
    if scenario == 'wait':
        return 'WAIT_BUYER_PAY'
    return 'TRADE_CLOSED'

def precreate(params):
    biz = parse_biz(params)
    out_trade_no = str(biz.get('out_trade_no', ''))
    if not out_trade_no:
        return error_response('alipay.trade.precreate', '40004', 'ACQ.INVALID_PARAMETER', 'out_trade_no required')
    scenario = infer_scenario(out_trade_no)
    if scenario == 'gateway_error':
        return error_response('alipay.trade.precreate', '40004', 'ACQ.SYSTEM_ERROR', 'mock gateway error')
    trade = ensure_trade(out_trade_no, money(biz.get('total_amount', '0.00')), str(biz.get('subject', 'Bill Express')))
    response = {'code': '10000', 'msg': 'Success', 'out_trade_no': out_trade_no, 'qr_code': f'https://qr.alipay.mock/{urllib.parse.quote(out_trade_no)}'}
    return gateway_body('alipay.trade.precreate', response, scenario if scenario in {'bad_signature', 'unsigned'} else 'success')

def pay(params):
    biz = parse_biz(params)
    out_trade_no = str(biz.get('out_trade_no', ''))
    auth_code = str(biz.get('auth_code', ''))
    scene = str(biz.get('scene', 'bar_code'))
    if not out_trade_no or not auth_code or scene != 'bar_code':
        return error_response('alipay.trade.pay', '40004', 'ACQ.INVALID_PARAMETER', 'invalid barcode payment request')
    scenario = infer_scenario(out_trade_no)
    if scenario == 'gateway_error':
        return error_response('alipay.trade.pay', '40004', 'ACQ.SYSTEM_ERROR', 'mock gateway error')
    trade = ensure_trade(out_trade_no, money(biz.get('total_amount', '0.00')), str(biz.get('subject', 'Bill Express')))
    status = scenario_status(scenario)
    trade['trade_status'] = status
    amount = money(float(trade['total_amount']) + 1) if scenario == 'wrong_amount' else trade['total_amount']
    if status == 'TRADE_SUCCESS':
        response = {'code': '10000', 'msg': 'Success', 'out_trade_no': out_trade_no, 'trade_no': trade['trade_no'], 'trade_status': status, 'total_amount': amount, 'buyer_user_id': trade['buyer_user_id'], 'buyer_logon_id': trade['buyer_logon_id']}
    elif status == 'WAIT_BUYER_PAY':
        response = {'code': '10003', 'msg': 'Order Success Pay Inprocess', 'out_trade_no': out_trade_no, 'trade_no': trade['trade_no'], 'trade_status': status}
    else:
        response = {'code': '40004', 'msg': 'Business Failed', 'sub_code': 'ACQ.PAYMENT_AUTH_CODE_INVALID', 'sub_msg': 'mock payment failed', 'out_trade_no': out_trade_no, 'trade_status': status}
    return gateway_body('alipay.trade.pay', response, scenario if scenario in {'bad_signature', 'unsigned'} else 'success')

def query(params):
    biz = parse_biz(params)
    out_trade_no = str(biz.get('out_trade_no', ''))
    method = 'alipay.trade.query'
    scenario = infer_scenario(out_trade_no)
    if scenario == 'query_timeout':
        time.sleep(6)
    trade = TRADES.get(out_trade_no)
    if not trade:
        return error_response(method, '40004', 'ACQ.TRADE_NOT_EXIST', 'trade not exist')
    status = scenario_status(scenario)
    trade['trade_status'] = status
    amount = money(float(trade['total_amount']) + 1) if scenario == 'wrong_amount' else trade['total_amount']
    if scenario == 'code_only':
        response = {'code': '10000', 'msg': 'Success', 'out_trade_no': out_trade_no, 'trade_no': trade['trade_no'], 'total_amount': amount}
        return gateway_body(method, response, 'success')
    response = {'code': '10000', 'msg': 'Success', 'out_trade_no': out_trade_no, 'trade_no': trade['trade_no'], 'trade_status': status, 'total_amount': amount, 'buyer_user_id': trade['buyer_user_id'], 'buyer_logon_id': trade['buyer_logon_id']}
    return gateway_body(method, response, scenario if scenario in {'bad_signature', 'unsigned'} else 'success')

def close_or_cancel(method, params):
    biz = parse_biz(params)
    out_trade_no = str(biz.get('out_trade_no', ''))
    trade = TRADES.get(out_trade_no)
    if trade:
        trade['trade_status'] = 'TRADE_CLOSED'
    return gateway_body(method, {'code': '10000', 'msg': 'Success', 'out_trade_no': out_trade_no})

def refund(params):
    method = 'alipay.trade.refund'
    biz = parse_biz(params)
    out_trade_no = str(biz.get('out_trade_no', ''))
    trade_no_value = str(biz.get('trade_no', ''))
    out_request_no = str(biz.get('out_request_no', ''))
    refund_amount = biz.get('refund_amount', biz.get('refund_fee', '0'))
    if not out_trade_no and trade_no_value:
        trade = find_trade_by_no(trade_no_value)
        out_trade_no = trade.get('out_trade_no', '') if trade else ''
    trade = TRADES.get(out_trade_no)
    if not trade or not out_request_no:
        return error_response(method, '40004', 'ACQ.TRADE_NOT_EXIST', 'trade or out_request_no not found')
    if trade.get('trade_status') not in {'TRADE_SUCCESS', 'TRADE_FINISHED'}:
        return error_response(method, '40004', 'ACQ.TRADE_STATUS_ERROR', 'trade is not refundable')
    try:
        refund_fee = round(float(refund_amount), 2)
    except Exception:
        return error_response(method, '40004', 'ACQ.INVALID_PARAMETER', 'invalid refund amount')
    if refund_fee <= 0:
        return error_response(method, '40004', 'ACQ.INVALID_PARAMETER', 'invalid refund amount')

    existing = REFUNDS.get(out_request_no)
    if existing:
        existing['call_count'] = int(existing.get('call_count', 0)) + 1
        return gateway_body(method, {
            'code': '10000',
            'msg': 'Success',
            'out_trade_no': existing['out_trade_no'],
            'trade_no': existing['trade_no'],
            'out_request_no': out_request_no,
            'refund_fee': money(existing['refund_amount']),
            'refund_amount': money(existing['refund_amount']),
            'refunded_amount': money(existing.get('refunded_amount', 0)),
            'fund_change': existing.get('fund_change', 'Y'),
            'refund_status': existing.get('refund_status', 'REFUND_SUCCESS'),
            'gmt_refund_pay': existing.get('gmt_refund_pay', now_text()),
        })

    request_upper = out_request_no.upper()
    refunded_before = float(trade.get('refunded_amount', '0') or 0)
    total_amount = float(trade.get('total_amount', '0') or 0)
    if 'FUND_CHANGE_NO' in request_upper:
        record = {
            'out_trade_no': out_trade_no,
            'trade_no': trade['trade_no'],
            'out_request_no': out_request_no,
            'refund_amount': refund_fee,
            'refunded_amount': refunded_before,
            'fund_change': 'N',
            'refund_status': 'NO_FUND_CHANGE',
            'call_count': 1,
        }
        REFUNDS[out_request_no] = record
        return gateway_body(method, {
            'code': '10000',
            'msg': 'Success',
            'out_trade_no': out_trade_no,
            'trade_no': trade['trade_no'],
            'out_request_no': out_request_no,
            'refund_fee': money(refund_fee),
            'refund_amount': money(refund_fee),
            'refunded_amount': money(refunded_before),
            'fund_change': 'N',
            'refund_status': 'NO_FUND_CHANGE',
        })
    if 'REFUND_UNKNOWN' in request_upper:
        record = {
            'out_trade_no': out_trade_no,
            'trade_no': trade['trade_no'],
            'out_request_no': out_request_no,
            'refund_amount': refund_fee,
            'refunded_amount': refunded_before,
            'fund_change': 'N',
            'refund_status': 'REFUND_PROCESSING',
            'call_count': 1,
        }
        REFUNDS[out_request_no] = record
        return gateway_body(method, {
            'code': '10003',
            'msg': 'Refund Processing',
            'out_trade_no': out_trade_no,
            'trade_no': trade['trade_no'],
            'out_request_no': out_request_no,
            'refund_fee': money(refund_fee),
            'refund_amount': money(refund_fee),
            'refunded_amount': money(refunded_before),
            'fund_change': 'N',
            'refund_status': 'REFUND_PROCESSING',
        })
    if refunded_before + refund_fee > total_amount + 0.001:
        return error_response(method, '40004', 'ACQ.REFUND_AMT_NOT_ENOUGH', 'refund amount exceeds refundable amount')

    refunded_after = round(refunded_before + refund_fee, 2)
    trade['refunded_amount'] = money(refunded_after)
    if refunded_after >= total_amount - 0.001:
        trade['trade_status'] = 'TRADE_CLOSED'
    record = {
        'out_trade_no': out_trade_no,
        'trade_no': trade['trade_no'],
        'out_request_no': out_request_no,
        'refund_amount': refund_fee,
        'refunded_amount': refunded_after,
        'fund_change': 'Y',
        'refund_status': 'REFUND_SUCCESS',
        'gmt_refund_pay': now_text(),
        'call_count': 1,
    }
    REFUNDS[out_request_no] = record
    return gateway_body(method, {
        'code': '10000',
        'msg': 'Success',
        'out_trade_no': out_trade_no,
        'trade_no': trade['trade_no'],
        'out_request_no': out_request_no,
        'refund_fee': money(refund_fee),
        'refund_amount': money(refund_fee),
        'refunded_amount': money(refunded_after),
        'fund_change': 'Y',
        'refund_status': 'REFUND_SUCCESS',
        'trade_status': trade['trade_status'],
        'gmt_refund_pay': record['gmt_refund_pay'],
    })

def refund_query(params):
    method = 'alipay.trade.fastpay.refund.query'
    biz = parse_biz(params)
    out_request_no = str(biz.get('out_request_no', ''))
    record = REFUNDS.get(out_request_no)
    if not record:
        return gateway_body(method, {
            'code': '10000',
            'msg': 'Success',
            'out_request_no': out_request_no,
            'refund_status': 'REFUND_PROCESSING',
            'fund_change': 'N',
        })
    return gateway_body(method, {
        'code': '10000',
        'msg': 'Success',
        'out_trade_no': record['out_trade_no'],
        'trade_no': record['trade_no'],
        'out_request_no': out_request_no,
        'refund_fee': money(record['refund_amount']),
        'refund_amount': money(record['refund_amount']),
        'refunded_amount': money(record.get('refunded_amount', 0)),
        'fund_change': record.get('fund_change', 'N'),
        'refund_status': record.get('refund_status', 'REFUND_PROCESSING'),
        'gmt_refund_pay': record.get('gmt_refund_pay', ''),
    })

def signed_notify_payload(trade, scenario):
    amount = money(float(trade['total_amount']) + 1) if scenario == 'wrong_amount' else trade['total_amount']
    fields = {'notify_time': now_text(), 'notify_type': 'trade_status_sync', 'notify_id': f'mock-notify-{int(time.time() * 1000)}', 'app_id': 'mock-app-id', 'charset': 'utf-8', 'version': '1.0', 'sign_type': 'RSA2', 'trade_no': trade['trade_no'], 'out_trade_no': trade['out_trade_no'], 'trade_status': scenario_status(scenario), 'total_amount': amount, 'receipt_amount': amount, 'buyer_id': trade['buyer_user_id'], 'buyer_logon_id': trade['buyer_logon_id']}
    if scenario == 'wrong_app_id':
        fields['app_id'] = 'mock-app-id-other'
    if scenario != 'unsigned':
        sign_src = sorted_sign_content(fields)
        fields['sign'] = sign_bytes(sign_src + (':bad' if scenario == 'bad_signature' else ''))
    return fields

def post_notify(url, payload):
    data = urllib.parse.urlencode(payload).encode('utf-8')
    req = urllib.request.Request(url, data=data, method='POST', headers={'Content-Type': 'application/x-www-form-urlencoded'})
    try:
        with urllib.request.urlopen(req, timeout=5) as resp:
            return (resp.status, resp.read().decode('utf-8', errors='replace'))
    except urllib.error.HTTPError as exc:
        return (exc.code, exc.read().decode('utf-8', errors='replace'))

class Handler(BaseHTTPRequestHandler):
    server_version = 'MockAlipay/1.0'

    def log_message(self, fmt, *args):
        print(f'[{now_text()}] {self.address_string()} {fmt % args}', flush=True)

    def read_payload(self):
        length = int(self.headers.get('Content-Length', '0'))
        body = self.rfile.read(length)
        ctype = self.headers.get('Content-Type', '')
        if 'application/json' in ctype:
            return json.loads(body.decode('utf-8') or '{}')
        parsed = urllib.parse.parse_qs(body.decode('utf-8'), keep_blank_values=True)
        return {key: values[-1] for (key, values) in parsed.items()}

    def gateway_params(self, payload):
        parsed_url = urllib.parse.urlparse(self.path)
        query = urllib.parse.parse_qs(parsed_url.query, keep_blank_values=True)
        params = {key: values[-1] for (key, values) in query.items()}
        params.update({str(k): str(v) for (k, v) in payload.items()})
        return params

    def send_json(self, value, status=200):
        data = compact_json(value).encode('utf-8')
        self.send_response(status)
        self.send_header('Content-Type', 'application/json; charset=utf-8')
        self.send_header('Content-Length', str(len(data)))
        self.end_headers()
        self.wfile.write(data)

    def send_gateway(self, body, status=200):
        self.send_response(status)
        self.send_header('Content-Type', 'application/json; charset=utf-8')
        self.send_header('Content-Length', str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def do_GET(self):
        if self.path == '/__mock/state':
            self.send_json({'trades': TRADES, 'refunds': REFUNDS, 'scenarios': SCENARIOS, 'notify_log': NOTIFY_LOG, 'gateway_requests': GATEWAY_REQUESTS})
            return
        self.send_json({'status': 'ok', 'service': 'mock-alipay'}, 200)

    def do_POST(self):
        payload = self.read_payload()
        if self.path == '/__mock/reset':
            TRADES.clear()
            REFUNDS.clear()
            SCENARIOS.clear()
            NOTIFY_LOG.clear()
            GATEWAY_REQUESTS.clear()
            self.send_json({'success': True})
            return
        if self.path == '/__mock/scenario':
            out_trade_no = str(payload.get('out_trade_no', ''))
            scenario = str(payload.get('scenario', 'success'))
            if not out_trade_no:
                self.send_json({'success': False, 'error': 'out_trade_no required'}, 400)
                return
            SCENARIOS[out_trade_no] = scenario
            self.send_json({'success': True, 'out_trade_no': out_trade_no, 'scenario': scenario})
            return
        if self.path == '/__mock/notify':
            out_trade_no = str(payload.get('out_trade_no', ''))
            notify_url = str(payload.get('notify_url', ''))
            scenario = str(payload.get('scenario', infer_scenario(out_trade_no)))
            trade = TRADES.get(out_trade_no)
            if not trade or not notify_url:
                self.send_json({'success': False, 'error': 'trade and notify_url required'}, 400)
                return
            fields = signed_notify_payload(trade, scenario)
            (status, text) = post_notify(notify_url, fields)
            trade['notify_count'] = int(trade.get('notify_count', 0)) + 1
            NOTIFY_LOG.append({'out_trade_no': out_trade_no, 'scenario': scenario, 'status': status, 'body': text})
            self.send_json({'success': True, 'status': status, 'body': text, 'payload': {k: v for (k, v) in fields.items() if k != 'sign'}})
            return
        if urllib.parse.urlparse(self.path).path != '/gateway.do':
            self.send_json({'error': 'not found'}, 404)
            return
        params = self.gateway_params(payload)
        GATEWAY_REQUESTS.append({
            'method': params.get('method', ''),
            'out_trade_no': parse_biz(params).get('out_trade_no', ''),
            'has_sign': bool(params.get('sign', '')),
        })
        sign = params.get('sign', '')
        if sign and not any(verify_signature(content, sign) for content in request_sign_contents(params)):
            self.send_gateway(error_response(params.get('method', 'alipay.trade.query'), '40002', 'isv.invalid-signature', 'invalid merchant signature'))
            return
        method = params.get('method', '')
        if method == 'alipay.trade.precreate':
            self.send_gateway(precreate(params))
        elif method == 'alipay.trade.pay':
            self.send_gateway(pay(params))
        elif method == 'alipay.trade.query':
            self.send_gateway(query(params))
        elif method == 'alipay.trade.refund':
            self.send_gateway(refund(params))
        elif method == 'alipay.trade.fastpay.refund.query':
            self.send_gateway(refund_query(params))
        elif method in {'alipay.trade.close', 'alipay.trade.cancel'}:
            self.send_gateway(close_or_cancel(method, params))
        else:
            self.send_gateway(error_response(method or 'alipay.trade.query', '40004', 'ACQ.INVALID_PARAMETER', 'unsupported method'))

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--host', default='127.0.0.1')
    parser.add_argument('--port', default=18080, type=int)
    args = parser.parse_args()
    server = ThreadingHTTPServer((args.host, args.port), Handler)
    print(f'MOCK_ALIPAY_READY=http://{args.host}:{args.port}/gateway.do', flush=True)
    server.serve_forever()
if __name__ == '__main__':
    main()
