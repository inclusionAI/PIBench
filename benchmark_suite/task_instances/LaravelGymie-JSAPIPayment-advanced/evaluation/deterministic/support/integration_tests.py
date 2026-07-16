"""HTTP integration checks for the Laravel Gymie JSAPI security case.

The tests run the real Laravel app against a case-local fake Alipay OpenAPI
sandbox. The fake gateway gives deterministic create/query/refund responses and
lets the checker send signed notify payloads, so hard cases cover payment safety
semantics instead of demo-only shortcuts.
"""
import json
import os
import socket
import subprocess
import sys
import time
import uuid
import urllib.parse
from pathlib import Path

import requests

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import sign_utils  # noqa: E402

PROJECT_DIR = Path(sys.argv[1]) if len(sys.argv) > 1 else Path('/workspace')
OUTPUT_DIR = Path(sys.argv[2]) if len(sys.argv) > 2 else Path('/output')
BASE = ''
GATEWAY_PORT = os.environ.get('GATEWAY_PORT', '8234')
GATEWAY_ADMIN = 'http://127.0.0.1:%s/admin' % GATEWAY_PORT
GATEWAY_LOG = Path(os.environ.get('GATEWAY_LOG', str(OUTPUT_DIR / 'gateway_requests.jsonl')))
KEY_DIR = Path(os.environ.get('ALIPAY_KEY_DIR', '/opt/alipay-keys'))
APP_ID = os.environ.get('ALIPAY_APP_ID', '2021003100000001')
MINIAPP_APP_ID = os.environ.get('ALIPAY_MINIAPP_APP_ID', '2021004100666666')
SELLER_ID = os.environ.get('ALIPAY_SELLER_ID', '2088201111222233')
RESULTS = []
SERVER = None
SERVER_LOG = None

DOWNSTREAM_CHECKS = [
    ('integration.jsapi_create_order_contract', 'JSAPI 下单返回可拉起交易字段', 'functionality'),
    ('integration.jsapi_client_result_not_final', '客户端支付结果不能作为最终成功', 'security'),
    ('integration.jsapi_sync_pending_not_fake_paid', '查单处理中不能伪造成支付成功', 'security'),
    ('integration.jsapi_terminal_state_guard', '已支付终态不能被客户端失败覆盖', 'correctness'),
    ('integration.jsapi_invalid_notify_rejected', '非法异步通知不能入账', 'security'),
    ('integration.jsapi_signed_notify_field_mismatch_rejected', '合法签名但关键字段不匹配不能入账', 'security'),
    ('integration.jsapi_notify_idempotent_no_double_fulfillment', '重复成功通知不能重复履约', 'correctness'),
    ('integration.jsapi_unpaid_refund_rejected', '未支付订单不能退款且不得调用退款网关', 'security'),
    ('integration.jsapi_partial_refund_accounting', '部分退款不能直接记为全额退款', 'correctness'),
    ('integration.jsapi_refund_out_request_no', '退款使用外部幂等请求号且不能重复累计', 'correctness'),
    ('integration.jsapi_refund_fund_change_required', '退款成功接口但资金未变动不能累计退款', 'security'),
    ('integration.jsapi_refund_same_request_no_amount_conflict', '同一退款请求号不能用不同金额覆盖原记录', 'correctness'),
    ('integration.jsapi_cumulative_over_refund_rejected', '多次部分退款累计超额必须拒绝', 'security'),
    ('integration.jsapi_full_refund_terminal_not_reopened', '全额退款终态不能被后续支付成功覆盖', 'security'),
    ('integration.jsapi_over_refund_rejected', '超额退款必须拒绝且不改写资金状态', 'security'),
]


def record_downstream_runtime_unavailable():
    existing = {item.get('id') for item in RESULTS}
    for rid, name, dimension in DOWNSTREAM_CHECKS:
        if rid not in existing:
            record(rid, name, dimension, False, 'runtime 未启动，无法验证')


def record(rid, name, dimension, passed, message, evidence=None):
    item = {
        'id': rid,
        'name': name,
        'dimension': dimension,
        'type': 'hard',
        'passed': bool(passed),
        'score': 1 if passed else 0,
        'max_score': 1,
        'message': message,
        'evidence': evidence or ['integration_results.json', 'server.log'],
    }
    RESULTS.append(item)
    print('[integration] %s %s: %s' % ('PASS' if passed else 'FAIL', rid, message))


def sh(cmd, timeout=300):
    proc = subprocess.run(
        cmd,
        cwd=str(PROJECT_DIR),
        shell=True,
        timeout=timeout,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
    )
    return proc.returncode, proc.stdout.decode('utf-8', 'replace')


def pick_free_port():
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        sock.bind(('127.0.0.1', 0))
        return sock.getsockname()[1]


def plans_ready(timeout=3):
    try:
        r = requests.get(BASE + '/api/alipay-jsapi/plans', timeout=timeout)
    except requests.RequestException as exc:
        return False, '/plans 请求异常: %r' % exc
    if r.status_code != 200:
        return False, '/plans HTTP %d' % r.status_code
    body = json_body(r)
    plans = body.get('plans') if isinstance(body, dict) else None
    if not isinstance(plans, list) or not plans:
        return False, '/plans JSON 缺少非空 plans 列表'
    return True, 'HTTP 200 plans=%d' % len(plans)


def start_server():
    global SERVER, SERVER_LOG, BASE
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    port = pick_free_port()
    BASE = 'http://127.0.0.1:%s' % port
    SERVER_LOG = open(OUTPUT_DIR / 'server.log', 'w', encoding='utf-8')
    SERVER = subprocess.Popen(
        ['php', 'artisan', 'serve', '--host=127.0.0.1', '--port=%s' % port, '--no-reload'],
        cwd=str(PROJECT_DIR),
        stdout=SERVER_LOG,
        stderr=subprocess.STDOUT,
    )
    for _ in range(45):
        time.sleep(1)
        if SERVER.poll() is not None:
            return False
        ok, _ = plans_ready(timeout=3)
        if ok:
            return True
    return False


def stop_server():
    global SERVER, SERVER_LOG
    if SERVER and SERVER.poll() is None:
        SERVER.terminate()
        try:
            SERVER.wait(timeout=10)
        except subprocess.TimeoutExpired:
            SERVER.kill()
    if SERVER_LOG:
        SERVER_LOG.close()


def json_body(resp):
    try:
        return resp.json()
    except Exception:
        return {}


def order_from_body(body):
    if isinstance(body, dict):
        return body.get('order') or body.get('data') or body
    return {}


def order_status(out_trade_no):
    r = requests.get(BASE + '/api/alipay-jsapi/orders/' + urllib.parse.quote(out_trade_no), timeout=10)
    body = json_body(r)
    return r.status_code, order_from_body(body), body


def read_gateway_log():
    entries = []
    try:
        for line in GATEWAY_LOG.read_text(encoding='utf-8', errors='ignore').splitlines():
            try:
                entries.append(json.loads(line))
            except ValueError:
                pass
    except OSError:
        pass
    return entries


def gateway_refund_count(order):
    out_trade_no = str((order or {}).get('out_trade_no') or '')
    return sum(
        1
        for entry in read_gateway_log()
        if entry.get('method') == 'alipay.trade.refund'
        and str((entry.get('biz_content') or {}).get('out_trade_no') or '') == out_trade_no
    )


def refund_rejected_response(resp):
    if resp is None:
        return False
    if resp.status_code in (400, 401, 403, 409, 422):
        return True
    body = json_body(resp)
    text = json.dumps(body, ensure_ascii=False).lower() if body else (resp.text or '').lower()
    return resp.status_code == 200 and any(term in text for term in [
        'not_refundable',
        'not refundable',
        'only paid',
        'exceed',
        'over_refund',
        'already fully',
        'reject',
        'failed',
    ])


def gateway_trade(order):
    try:
        trades = requests.get(GATEWAY_ADMIN + '/trades', timeout=5).json()
    except Exception:
        return None
    for trade in trades:
        if trade.get('out_trade_no') == order.get('out_trade_no'):
            return trade
    return None


def gateway_set_status(order, status):
    try:
        requests.post(GATEWAY_ADMIN + '/set_trade_status', data={
            'out_trade_no': order.get('out_trade_no'),
            'status': status,
        }, timeout=5)
    except requests.RequestException:
        pass


def gateway_set_refund_mode(mode):
    try:
        requests.post(GATEWAY_ADMIN + '/set_refund_mode', data={'mode': mode}, timeout=5)
    except requests.RequestException:
        pass


def create_order(label='Benchmark Buyer'):
    plans_resp = requests.get(BASE + '/api/alipay-jsapi/plans', timeout=10)
    plans = (json_body(plans_resp).get('plans') or []) if plans_resp.status_code == 200 else []
    usable = [p for p in plans if p.get('id') and float(p.get('amount') or 0) > 0]
    if not usable:
        return None, 'no usable plan from /plans'
    plan = usable[0]
    payload = {
        'plan_id': plan['id'],
        'buyer_name': label,
        'buyer_email': 'bench-jsapi@example.com',
        'buyer_contact': '13800138000',
        'buyer_id': '2088102100000001',
        'buyer_open_id': 'bench-open-id-1',
    }
    r = requests.post(BASE + '/api/alipay-jsapi/orders', json=payload, timeout=30)
    body = json_body(r)
    order = order_from_body(body)
    if r.status_code not in (200, 201) or not order.get('out_trade_no'):
        return None, 'POST /orders status=%s body=%s' % (r.status_code, str(body)[:500])
    return order, ''


def build_notify_params(order, overrides=None, tamper_after_sign=None, exclude_sign_type=True):
    alipay_priv = sign_utils.load_private_key(str(KEY_DIR / 'alipay_private_key.pem'))
    amount = str(order.get('amount') or '0.00')
    params = {
        'notify_time': time.strftime('%Y-%m-%d %H:%M:%S'),
        'notify_type': 'trade_status_sync',
        'notify_id': uuid.uuid4().hex,
        'app_id': APP_ID,
        'auth_app_id': MINIAPP_APP_ID,
        'charset': 'utf-8',
        'version': '1.0',
        'sign_type': 'RSA2',
        'trade_no': order.get('tradeNO') or order.get('trade_no') or '20260616000000000001',
        'out_trade_no': order.get('out_trade_no'),
        'trade_status': 'TRADE_SUCCESS',
        'total_amount': amount,
        'receipt_amount': amount,
        'buyer_pay_amount': amount,
        'buyer_id': '2088102100000001',
        'buyer_open_id': 'bench-open-id-1',
        'seller_id': SELLER_ID,
        'subject': 'Gymie membership',
        'gmt_payment': time.strftime('%Y-%m-%d %H:%M:%S'),
    }
    if overrides:
        params.update(overrides)
    params['sign'] = sign_utils.sign_params(params, alipay_priv, exclude_sign_type=exclude_sign_type)
    if tamper_after_sign:
        params.update(tamper_after_sign)
    return params


def send_signed_notify(order, overrides=None, tamper_after_sign=None):
    last = None
    for exclude in (True, False):
        params = build_notify_params(order, overrides=overrides, tamper_after_sign=tamper_after_sign,
                                     exclude_sign_type=exclude)
        try:
            last = requests.post(BASE + '/alipay-jsapi/notify', data=params, timeout=20)
        except requests.RequestException:
            continue
        if last.text.strip().lower() == 'success':
            return last
    return last


def prepare_paid_order(label='Paid Buyer'):
    order, err = create_order(label)
    if not order:
        return None, err
    gateway_set_status(order, 'TRADE_SUCCESS')
    resp = send_signed_notify(order)
    _, fresh, _ = order_status(order['out_trade_no'])
    if not resp or resp.text.strip().lower() != 'success' or not is_paid(fresh.get('status')):
        return None, 'unable to prepare paid order: notify=%s status=%s' % (
            getattr(resp, 'status_code', None), fresh.get('status'))
    return fresh, ''


def db_count(table):
    db = PROJECT_DIR / 'database' / 'database.sqlite'
    code = "$db=new PDO('sqlite:%s'); echo $db->query('SELECT COUNT(*) FROM %s')->fetchColumn();" % (db, table)
    try:
        out = subprocess.check_output(['php', '-r', code], cwd=str(PROJECT_DIR), stderr=subprocess.DEVNULL)
        return int((out.decode().strip() or '0'))
    except Exception:
        return None


def fulfillment_counts():
    return {table: db_count(table) for table in ('members', 'subscriptions', 'invoices', 'invoice_transactions')}


def is_paid(status):
    return str(status or '').lower() in {'paid', 'success', 'completed', 'trade_success'}


def test_runtime():
    rc, out = sh('php -d memory_limit=768M artisan migrate:fresh --seed --force', timeout=900)
    if rc != 0:
        record('integration.jsapi_runtime_boot', 'Laravel 服务可迁移并启动', 'functionality', False,
               'migrate:fresh --seed 失败 exit=%s tail=%s' % (rc, out[-500:]))
        return False
    ok = start_server()
    if not ok:
        record('integration.jsapi_runtime_boot', 'Laravel 服务可迁移并启动', 'functionality', False,
               'php artisan serve 启动超时或退出，见 server.log/migrate.log')
        return False
    ok, detail = plans_ready(timeout=10)
    record('integration.jsapi_runtime_boot', 'Laravel 服务可迁移并启动', 'functionality', ok, detail)
    return ok


def test_create_order_contract():
    order, err = create_order()
    if not order:
        record('integration.jsapi_create_order_contract', 'JSAPI 下单返回可拉起交易字段', 'functionality', False, err)
        return None
    has_trade = bool(order.get('tradeNO') or order.get('trade_no'))
    waiting = str(order.get('status') or '').lower() in {'created', 'waiting_payment', 'pending', 'wait_buyer_pay'}
    trade = gateway_trade(order)
    entries = [e for e in read_gateway_log() if e.get('method') == 'alipay.trade.create']
    gateway_ok = bool(trade) and any(e.get('sign_valid') for e in entries)
    ok = has_trade and waiting and gateway_ok
    record('integration.jsapi_create_order_contract', 'JSAPI 下单返回可拉起交易字段', 'functionality', ok,
           'out_trade_no=%s status=%s tradeNO_present=%s gateway_create=%s' % (
               order.get('out_trade_no'), order.get('status'), has_trade, gateway_ok))
    return order


def test_client_result_not_final():
    order, err = create_order('Client Result Buyer')
    if not order:
        record('integration.jsapi_client_result_not_final', '客户端支付结果不能作为最终成功', 'security', False, err)
        return
    out_trade_no = order['out_trade_no']
    r = requests.post(BASE + '/api/alipay-jsapi/orders/%s/client-result' % urllib.parse.quote(out_trade_no),
                      json={'result_code': '9000'}, timeout=20)
    _, fresh, _ = order_status(out_trade_no)
    status = str(fresh.get('status') or '').lower()
    paid_markers = [fresh.get('paid_at'), fresh.get('member'), fresh.get('subscription_id'), fresh.get('invoice_id')]
    ok = r.status_code < 500 and status not in {'paid', 'success', 'completed'} and not any(paid_markers)
    record('integration.jsapi_client_result_not_final', '客户端支付结果不能作为最终成功', 'security', ok,
           'client-result HTTP=%s 后状态=%s paid_artifacts=%s' % (r.status_code, status, [bool(x) for x in paid_markers]))


def test_sync_pending_not_fake_paid():
    order, err = create_order('Sync Pending Buyer')
    if not order:
        record('integration.jsapi_sync_pending_not_fake_paid', '查单处理中不能伪造成支付成功', 'security', False, err)
        return
    failures = []
    for gateway_status in ('WAIT_BUYER_PAY', 'UNKNOWN'):
        gateway_set_status(order, gateway_status)
        r = requests.post(BASE + '/api/alipay-jsapi/orders/%s/sync' % urllib.parse.quote(order['out_trade_no']),
                          json={}, timeout=30)
        _, fresh, _ = order_status(order['out_trade_no'])
        status = str(fresh.get('status') or '').lower()
        paid_markers = [fresh.get('paid_at'), fresh.get('member'), fresh.get('subscription_id'), fresh.get('invoice_id')]
        if not (r.status_code < 500 and status not in {'paid', 'success', 'completed'} and not any(paid_markers)):
            failures.append('%s -> HTTP=%s status=%s paid=%s' % (gateway_status, r.status_code, status, [bool(x) for x in paid_markers]))
    record('integration.jsapi_sync_pending_not_fake_paid', '查单处理中不能伪造成支付成功', 'security', not failures,
           'pending/unknown 均未推进 paid' if not failures else '; '.join(failures))


def test_terminal_state_guard():
    order, err = prepare_paid_order('Terminal Guard Buyer')
    if not order:
        record('integration.jsapi_terminal_state_guard', '已支付终态不能被客户端失败覆盖', 'correctness', False, err)
        return
    out_trade_no = order['out_trade_no']
    before = str(order.get('status') or '').lower()
    requests.post(BASE + '/api/alipay-jsapi/orders/%s/client-result' % urllib.parse.quote(out_trade_no),
                  json={'result_code': '6001'}, timeout=20)
    _, fresh, _ = order_status(out_trade_no)
    after = str(fresh.get('status') or '').lower()
    ok = before == 'paid' and after == 'paid'
    record('integration.jsapi_terminal_state_guard', '已支付终态不能被客户端失败覆盖', 'correctness', ok,
           'before=%s after_cancel_result=%s' % (before, after))


def test_invalid_notify_rejected():
    order, err = create_order('Invalid Notify Buyer')
    if not order:
        record('integration.jsapi_invalid_notify_rejected', '非法异步通知不能入账', 'security', False, err)
        return
    r = send_signed_notify(order, tamper_after_sign={'total_amount': str(float(order.get('amount') or 0) + 1)})
    _, fresh, _ = order_status(order['out_trade_no'])
    status = str(fresh.get('status') or '').lower()
    paid_artifacts = [fresh.get('paid_at'), fresh.get('member'), fresh.get('subscription_id'), fresh.get('invoice_id')]
    response_text = r.text.strip().lower()[:80] if r is not None else 'request-error'
    response_ok = r is not None and r.status_code < 500 and response_text != 'success'
    state_ok = status not in {'paid', 'success', 'completed'} and not any(paid_artifacts)
    record('integration.jsapi_invalid_notify_rejected', '非法异步通知不能入账', 'security', response_ok and state_ok,
           'notify_response=%s order_status=%s paid_artifacts=%s' % (response_text, status, [bool(x) for x in paid_artifacts]))


def test_signed_notify_field_mismatch_rejected():
    order, err = create_order('Signed Mismatch Buyer')
    if not order:
        record('integration.jsapi_signed_notify_field_mismatch_rejected', '合法签名但关键字段不匹配不能入账', 'security', False, err)
        return
    cases = [
        {'seller_id': 'wrong-seller'},
        {'app_id': 'wrong-app'},
        {'buyer_id': 'wrong-buyer'},
        {'total_amount': str(float(order.get('amount') or 0) + 1)},
    ]
    failures = []
    for overrides in cases:
        resp = send_signed_notify(order, overrides=overrides)
        _, fresh, _ = order_status(order['out_trade_no'])
        if is_paid(fresh.get('status')):
            failures.append('accepted %s response=%s' % (overrides, getattr(resp, 'text', '')[:40]))
            break
    record('integration.jsapi_signed_notify_field_mismatch_rejected', '合法签名但关键字段不匹配不能入账', 'security', not failures,
           'signed mismatch cases rejected' if not failures else '; '.join(failures))


def test_notify_idempotent_no_double_fulfillment():
    order, err = create_order('Duplicate Notify Buyer')
    if not order:
        record('integration.jsapi_notify_idempotent_no_double_fulfillment', '重复成功通知不能重复履约', 'correctness', False, err)
        return
    before = fulfillment_counts()
    r1 = send_signed_notify(order)
    mid = fulfillment_counts()
    r2 = send_signed_notify(order)
    after = fulfillment_counts()
    _, fresh, _ = order_status(order['out_trade_no'])
    first_ok = r1 is not None and r1.text.strip().lower() == 'success' and is_paid(fresh.get('status'))
    details = []
    first_fulfillment = False
    duplicate_ok = True
    for table in ('members', 'subscriptions', 'invoices', 'invoice_transactions'):
        if before[table] is None or mid[table] is None or after[table] is None:
            continue
        first_delta = mid[table] - before[table]
        second_delta = after[table] - mid[table]
        details.append('%s first=%s second=%s' % (table, first_delta, second_delta))
        if table in ('subscriptions', 'invoices', 'invoice_transactions') and first_delta > 0:
            first_fulfillment = True
        if second_delta != 0:
            duplicate_ok = False
    ok = first_ok and first_fulfillment and duplicate_ok and r2 is not None and r2.status_code < 500
    record('integration.jsapi_notify_idempotent_no_double_fulfillment', '重复成功通知不能重复履约', 'correctness', ok,
           'status=%s counts=%s' % (fresh.get('status'), details))


def test_refund_partial_accounting():
    order, err = prepare_paid_order('Refund Buyer')
    if not order:
        record('integration.jsapi_partial_refund_accounting', '部分退款不能直接记为全额退款', 'correctness', False, err)
        return
    amount = float(order.get('amount') or 0)
    partial = max(round(amount / 2, 2), 0.01)
    gateway_set_refund_mode('success')
    r = requests.post(
        BASE + '/api/alipay-jsapi/orders/%s/refund' % urllib.parse.quote(order['out_trade_no']),
        json={'amount': partial, 'out_request_no': 'bench-refund-%s' % uuid.uuid4().hex[:8]},
        headers={'X-Refund-Token': 'bench-refund-token'},
        timeout=30,
    )
    _, fresh, _ = order_status(order['out_trade_no'])
    status = str(fresh.get('status') or '').lower()
    refund_amount = float(fresh.get('refund_amount') or 0)
    ok = r.status_code in (200, 201) and refund_amount >= partial - 0.01 and status not in {'refunded'}
    record('integration.jsapi_partial_refund_accounting', '部分退款不能直接记为全额退款', 'correctness', ok,
           'refund HTTP=%s amount=%s refund_amount=%s status=%s' % (r.status_code, partial, refund_amount, status))


def test_unpaid_refund_rejected():
    order, err = create_order('Unpaid Refund Buyer')
    if not order:
        record('integration.jsapi_unpaid_refund_rejected', '未支付订单不能退款且不得调用退款网关', 'security', False, err)
        return
    gateway_set_refund_mode('success')
    before_gateway = gateway_refund_count(order)
    r = requests.post(
        BASE + '/api/alipay-jsapi/orders/%s/refund' % urllib.parse.quote(order['out_trade_no']),
        json={'amount': 0.01, 'out_request_no': 'bench-unpaid-refund'},
        headers={'X-Refund-Token': 'bench-refund-token'},
        timeout=30,
    )
    after_gateway = gateway_refund_count(order)
    _, fresh, _ = order_status(order['out_trade_no'])
    status = str(fresh.get('status') or '').lower()
    refund_amount = float(fresh.get('refund_amount') or 0)
    no_gateway_call = after_gateway == before_gateway
    state_ok = status not in {'paid', 'success', 'completed', 'refunded', 'partially_refunded'} and refund_amount <= 0.001
    ok = refund_rejected_response(r) and no_gateway_call and state_ok
    record('integration.jsapi_unpaid_refund_rejected', '未支付订单不能退款且不得调用退款网关', 'security', ok,
           'refund HTTP=%s status=%s refund_amount=%s gateway_refund_calls=%s->%s response=%s' % (
               r.status_code, status, refund_amount, before_gateway, after_gateway,
               json.dumps(json_body(r), ensure_ascii=False)[:220]
           ), evidence=['integration_results.json', 'gateway_requests.jsonl'])


def test_refund_idempotency_request_no():
    order, err = prepare_paid_order('Refund Idempotency Buyer')
    if not order:
        record('integration.jsapi_refund_out_request_no', '退款使用外部幂等请求号且不能重复累计', 'correctness', False, err)
        return
    gateway_set_refund_mode('success')
    request_no = 'bench-fixed-refund-no'
    refund_amount = 0.01
    payload = {'amount': refund_amount, 'out_request_no': request_no}
    headers = {'X-Refund-Token': 'bench-refund-token'}
    r1 = requests.post(BASE + '/api/alipay-jsapi/orders/%s/refund' % urllib.parse.quote(order['out_trade_no']),
                       json=payload, headers=headers, timeout=30)
    r2 = requests.post(BASE + '/api/alipay-jsapi/orders/%s/refund' % urllib.parse.quote(order['out_trade_no']),
                       json=payload, headers=headers, timeout=30)
    _, fresh, _ = order_status(order['out_trade_no'])
    second_ok = r2.status_code in (200, 201, 409)
    body1 = json_body(r1)
    body2 = json_body(r2)
    echoed = request_no in json.dumps(body1, ensure_ascii=False) or request_no in json.dumps(body2, ensure_ascii=False)
    recorded_refund = float(fresh.get('refund_amount') or 0)
    first_refund_recorded = recorded_refund >= refund_amount - 0.001
    no_double_accounting = recorded_refund <= refund_amount + 0.001
    ok = r1.status_code in (200, 201) and second_ok and echoed and first_refund_recorded and no_double_accounting
    record('integration.jsapi_refund_out_request_no', '退款使用外部幂等请求号且不能重复累计', 'correctness', ok,
           'request_no=%s first=%s second=%s request_no_echoed=%s first_recorded=%s refund_amount=%s expected_max=%s response1=%s response2=%s' % (
               request_no, r1.status_code, r2.status_code, echoed, first_refund_recorded, recorded_refund, refund_amount,
               json.dumps(json_body(r1), ensure_ascii=False)[:220], json.dumps(json_body(r2), ensure_ascii=False)[:220]
           ), evidence=['integration_results.json', 'gateway_requests.jsonl'])


def test_refund_fund_change_required():
    order, err = prepare_paid_order('Refund Fund Change Buyer')
    if not order:
        record('integration.jsapi_refund_fund_change_required', '退款成功接口但资金未变动不能累计退款', 'security', False, err)
        return
    gateway_set_refund_mode('fund_change_n')
    r = requests.post(
        BASE + '/api/alipay-jsapi/orders/%s/refund' % urllib.parse.quote(order['out_trade_no']),
        json={'amount': 0.01, 'out_request_no': 'bench-fund-change-n'},
        headers={'X-Refund-Token': 'bench-refund-token'},
        timeout=30,
    )
    gateway_set_refund_mode('success')
    _, fresh, _ = order_status(order['out_trade_no'])
    status = str(fresh.get('status') or '').lower()
    refund_amount = float(fresh.get('refund_amount') or 0)
    ok = r.status_code in (200, 201, 400, 409, 422) and status == 'paid' and refund_amount <= 0.001
    record('integration.jsapi_refund_fund_change_required', '退款成功接口但资金未变动不能累计退款', 'security', ok,
           'request_no=bench-fund-change-n refund HTTP=%s status=%s refund_amount=%s response=%s' % (
               r.status_code, status, refund_amount, json.dumps(json_body(r), ensure_ascii=False)[:260]
           ), evidence=['integration_results.json', 'gateway_requests.jsonl'])


def test_refund_same_request_no_amount_conflict():
    order, err = prepare_paid_order('Refund Request Conflict Buyer')
    if not order:
        record('integration.jsapi_refund_same_request_no_amount_conflict', '同一退款请求号不能用不同金额覆盖原记录', 'correctness', False, err)
        return
    gateway_set_refund_mode('success')
    request_no = 'bench-conflict-refund-no'
    first_amount = 0.01
    second_amount = 0.02
    headers = {'X-Refund-Token': 'bench-refund-token'}
    r1 = requests.post(BASE + '/api/alipay-jsapi/orders/%s/refund' % urllib.parse.quote(order['out_trade_no']),
                       json={'amount': first_amount, 'out_request_no': request_no}, headers=headers, timeout=30)
    r2 = requests.post(BASE + '/api/alipay-jsapi/orders/%s/refund' % urllib.parse.quote(order['out_trade_no']),
                       json={'amount': second_amount, 'out_request_no': request_no}, headers=headers, timeout=30)
    _, fresh, _ = order_status(order['out_trade_no'])
    recorded_refund = float(fresh.get('refund_amount') or 0)
    first_recorded = recorded_refund >= first_amount - 0.001
    not_overwritten_or_accumulated = recorded_refund <= first_amount + 0.001
    ok = r1.status_code in (200, 201) and r2.status_code < 500 and first_recorded and not_overwritten_or_accumulated
    record('integration.jsapi_refund_same_request_no_amount_conflict', '同一退款请求号不能用不同金额覆盖原记录', 'correctness', ok,
           'request_no=%s first=%s second=%s refund_amount=%s first_amount=%s second_amount=%s response1=%s response2=%s' % (
               request_no, r1.status_code, r2.status_code, recorded_refund, first_amount, second_amount,
               json.dumps(json_body(r1), ensure_ascii=False)[:220], json.dumps(json_body(r2), ensure_ascii=False)[:220]
           ), evidence=['integration_results.json', 'gateway_requests.jsonl'])


def test_cumulative_over_refund_rejected():
    order, err = prepare_paid_order('Cumulative Over Refund Buyer')
    if not order:
        record('integration.jsapi_cumulative_over_refund_rejected', '多次部分退款累计超额必须拒绝', 'security', False, err)
        return
    amount = float(order.get('amount') or 0)
    first_amount = max(round(amount * 0.6, 2), 0.01)
    second_amount = max(round(amount * 0.6, 2), 0.01)
    gateway_set_refund_mode('success')
    headers = {'X-Refund-Token': 'bench-refund-token'}
    before_gateway = gateway_refund_count(order)
    r1 = requests.post(
        BASE + '/api/alipay-jsapi/orders/%s/refund' % urllib.parse.quote(order['out_trade_no']),
        json={'amount': first_amount, 'out_request_no': 'bench-cumulative-refund-a'},
        headers=headers,
        timeout=30,
    )
    after_first_gateway = gateway_refund_count(order)
    _, after_first, _ = order_status(order['out_trade_no'])
    first_recorded = float(after_first.get('refund_amount') or 0)
    r2 = requests.post(
        BASE + '/api/alipay-jsapi/orders/%s/refund' % urllib.parse.quote(order['out_trade_no']),
        json={'amount': second_amount, 'out_request_no': 'bench-cumulative-refund-b'},
        headers=headers,
        timeout=30,
    )
    after_second_gateway = gateway_refund_count(order)
    _, fresh, _ = order_status(order['out_trade_no'])
    status = str(fresh.get('status') or '').lower()
    final_refund = float(fresh.get('refund_amount') or 0)
    first_ok = r1.status_code in (200, 201) and first_recorded >= first_amount - 0.01
    second_rejected = refund_rejected_response(r2)
    no_second_gateway_call = after_second_gateway == after_first_gateway
    not_over_accounted = final_refund <= amount + 0.001
    no_second_accrual = final_refund <= first_recorded + 0.001
    ok = first_ok and second_rejected and no_second_gateway_call and not_over_accounted and no_second_accrual
    record('integration.jsapi_cumulative_over_refund_rejected', '多次部分退款累计超额必须拒绝', 'security', ok,
           'first=%s second=%s amount=%s first_refund=%s final_refund=%s status=%s gateway_calls=%s->%s->%s response2=%s' % (
               r1.status_code, r2.status_code, amount, first_recorded, final_refund, status,
               before_gateway, after_first_gateway, after_second_gateway,
               json.dumps(json_body(r2), ensure_ascii=False)[:220]
           ), evidence=['integration_results.json', 'gateway_requests.jsonl'])


def test_full_refund_terminal_not_reopened():
    order, err = prepare_paid_order('Full Refund Terminal Buyer')
    if not order:
        record('integration.jsapi_full_refund_terminal_not_reopened', '全额退款终态不能被后续支付成功覆盖', 'security', False, err)
        return
    amount = float(order.get('amount') or 0)
    gateway_set_refund_mode('success')
    r = requests.post(
        BASE + '/api/alipay-jsapi/orders/%s/refund' % urllib.parse.quote(order['out_trade_no']),
        json={'amount': amount, 'out_request_no': 'bench-full-refund-terminal'},
        headers={'X-Refund-Token': 'bench-refund-token'},
        timeout=30,
    )
    _, refunded, _ = order_status(order['out_trade_no'])
    refunded_status = str(refunded.get('status') or '').lower()
    refunded_amount = float(refunded.get('refund_amount') or 0)
    send_signed_notify(refunded)
    requests.post(BASE + '/api/alipay-jsapi/orders/%s/sync' % urllib.parse.quote(order['out_trade_no']),
                  json={}, timeout=30)
    _, fresh, _ = order_status(order['out_trade_no'])
    final_status = str(fresh.get('status') or '').lower()
    final_refund_amount = float(fresh.get('refund_amount') or 0)
    terminal_names = {'refunded', 'fully_refunded', 'full_refunded'}
    refund_recorded = r.status_code in (200, 201) and refunded_amount >= amount - 0.01 and refunded_status in terminal_names
    not_reopened = final_status in terminal_names and final_refund_amount >= amount - 0.01
    record('integration.jsapi_full_refund_terminal_not_reopened', '全额退款终态不能被后续支付成功覆盖', 'security', refund_recorded and not_reopened,
           'refund HTTP=%s refunded_status=%s final_status=%s refund_amount=%s final_refund_amount=%s order_amount=%s' % (
               r.status_code, refunded_status, final_status, refunded_amount, final_refund_amount, amount
           ))


def test_over_refund_rejected():
    order, err = prepare_paid_order('Over Refund Buyer')
    if not order:
        record('integration.jsapi_over_refund_rejected', '超额退款必须拒绝且不改写资金状态', 'security', False, err)
        return
    amount = float(order.get('amount') or 0)
    r = requests.post(
        BASE + '/api/alipay-jsapi/orders/%s/refund' % urllib.parse.quote(order['out_trade_no']),
        json={'amount': round(amount + 1, 2), 'out_request_no': 'bench-over-refund'},
        headers={'X-Refund-Token': 'bench-refund-token'},
        timeout=30,
    )
    _, fresh, _ = order_status(order['out_trade_no'])
    status = str(fresh.get('status') or '').lower()
    refund_amount = float(fresh.get('refund_amount') or 0)
    ok = r.status_code in (400, 409, 422) and status == 'paid' and refund_amount <= 0.001
    record('integration.jsapi_over_refund_rejected', '超额退款必须拒绝且不改写资金状态', 'security', ok,
           'refund HTTP=%s status=%s refund_amount=%s order_amount=%s' % (r.status_code, status, refund_amount, amount))


try:
    if test_runtime():
        test_create_order_contract()
        test_client_result_not_final()
        test_sync_pending_not_fake_paid()
        test_terminal_state_guard()
        test_invalid_notify_rejected()
        test_signed_notify_field_mismatch_rejected()
        test_notify_idempotent_no_double_fulfillment()
        test_unpaid_refund_rejected()
        test_refund_partial_accounting()
        test_refund_idempotency_request_no()
        test_refund_fund_change_required()
        test_refund_same_request_no_amount_conflict()
        test_cumulative_over_refund_rejected()
        test_full_refund_terminal_not_reopened()
        test_over_refund_rejected()
    else:
        record_downstream_runtime_unavailable()
except Exception as exc:
    record('integration.checker_crash', '集成检查器自身异常', 'infrastructure', False, repr(exc))
    record_downstream_runtime_unavailable()
finally:
    stop_server()
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    (OUTPUT_DIR / 'integration_results.json').write_text(json.dumps(RESULTS, ensure_ascii=False, indent=2), encoding='utf-8')
