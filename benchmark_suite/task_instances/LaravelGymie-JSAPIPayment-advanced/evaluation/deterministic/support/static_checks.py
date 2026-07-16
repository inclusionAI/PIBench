"""Static safety checks for the JSAPI trade-security case.

These checks complement the HTTP integration tests. They intentionally focus on
source-level safety contracts that are hard to prove through a demo Alipay flow:
SDK usage, no fake verification bypass, stable routes, buyer ownership and
refund/accounting state modelling.
"""
import json
import re
import sys
from pathlib import Path

PROJECT_DIR = Path(sys.argv[1]) if len(sys.argv) > 1 else Path('/workspace')
OUTPUT_DIR = Path(sys.argv[2]) if len(sys.argv) > 2 else Path('/output')
RESULTS = []


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
        'evidence': evidence or ['static_checks.py'],
    }
    RESULTS.append(item)
    print('[static] %s %s: %s' % ('PASS' if passed else 'FAIL', rid, message))


def text(path):
    try:
        return (PROJECT_DIR / path).read_text(encoding='utf-8', errors='ignore')
    except OSError:
        return ''


def all_php_text():
    parts = []
    for root in ['app', 'routes', 'database']:
        base = PROJECT_DIR / root
        if base.exists():
            for p in base.rglob('*.php'):
                try:
                    parts.append('\n// FILE: %s\n%s' % (p.relative_to(PROJECT_DIR), p.read_text(encoding='utf-8', errors='ignore')))
                except OSError:
                    pass
    return '\n'.join(parts)


def changed_text():
    code_dir = OUTPUT_DIR / 'code_files'
    if not code_dir.exists():
        return all_php_text()
    parts = []
    for p in code_dir.rglob('*'):
        if p.is_file() and p.suffix in {'.php', '.env', '.js', '.ts', '.vue'}:
            try:
                parts.append('\n// FILE: %s\n%s' % (p.relative_to(code_dir), p.read_text(encoding='utf-8', errors='ignore')))
            except OSError:
                pass
    return '\n'.join(parts) or all_php_text()


SRC = all_php_text()
SRC_LOWER = SRC.lower()
CHANGED = changed_text()
CHANGED_LOWER = CHANGED.lower()
ROUTES = text('routes/api.php') + '\n' + text('routes/web.php')
SERVICE = text('app/Services/Alipay/AlipayJsapiPaymentService.php')
CONTROLLER = text('app/Http/Controllers/AlipayJsapiMembershipController.php')
COMPOSER = text('composer.json')


def check_sdk_and_gateway_contract():
    sdk_terms = ['alipaytradecreaterequest', 'alipaytradequeryrequest', 'alipaytraderefundrequest', 'verifyNotify'.lower(), 'aopclient']
    found = [t for t in sdk_terms if t in (SERVICE + COMPOSER).lower()]
    record(
        'static.jsapi_safety_dep_sdk',
        '使用支付宝 SDK/开放接口完成 JSAPI 交易链路',
        'functionality',
        len(found) >= 4,
        '识别到 SDK/接口能力: %s' % (found or '无'),
        ['app/Services/Alipay/AlipayJsapiPaymentService.php', 'composer.json'],
    )


def check_stable_routes():
    norm = ROUTES.replace('"', "'").replace(' ', '').replace('\n', '').lower()
    required = {
        'api prefix alipay-jsapi': "prefix('alipay-jsapi')",
        'plans': "get('/plans'",
        'orders create': "post('/orders'",
        'order status': "get('/orders/{order:out_trade_no}'",
        'client result': "post('/orders/{order:out_trade_no}/client-result'",
        'sync': "post('/orders/{order:out_trade_no}/sync'",
        'refund': "post('/orders/{order:out_trade_no}/refund'",
        'notify': "post('/notify'",
    }
    missing = [label for label, token in required.items() if token not in norm]
    record(
        'static.jsapi_stable_endpoint_security',
        '保留题面固定 API 入口',
        'functionality',
        not missing,
        '缺失固定入口: %s' % (missing or '无'),
        ['routes/api.php', 'routes/web.php'],
    )


def check_no_fake_bypass():
    suspicious = []
    patterns = [
        (r'verifynotify\s*\([^)]*\)\s*\{[^{}]{0,240}return\s+true\s*;', 'verifyNotify 直接 return true'),
        (r'rsacheck[^\n{]*\{[^{}]{0,240}return\s+true\s*;', 'rsaCheck 直接 return true'),
        (r'result_code[^\n]{0,80}9000[\s\S]{0,600}markpaid\s*\(', '客户端 9000 直接 markPaid'),
        (r'trade_status[^\n]{0,120}trade_success[\s\S]{0,500}markpaid\s*\([^\)]*\)[\s\S]{0,500}return\s+[\'\"]success', '通知成功缺少前置校验迹象'),
    ]
    compact = CHANGED_LOWER
    for pattern, label in patterns:
        if re.search(pattern, compact):
            suspicious.append(label)
    fake_tokens = ['sk-']
    leaked = [t for t in fake_tokens if t in CHANGED_LOWER]
    if leaked:
        suspicious.append('疑似提交真实密钥/私钥: %s' % leaked)
    record(
        'static.jsapi_no_fake_bypass',
        '不通过伪造成功绕过支付安全校验',
        'security',
        not suspicious,
        '危险绕过迹象: %s' % (suspicious or '无'),
        ['changed_files.txt', 'code_files'],
    )


def check_secret_safety():
    env_like = []
    for p in (OUTPUT_DIR / 'code_files').rglob('*') if (OUTPUT_DIR / 'code_files').exists() else []:
        if p.name == '.env' or p.suffix in {'.pem', '.key'}:
            env_like.append(str(p.relative_to(OUTPUT_DIR / 'code_files')))
    leaked_literals = []
    for token in ['sk-']:
        if token.lower() in CHANGED_LOWER:
            leaked_literals.append(token)
    ok = not env_like and not leaked_literals
    record(
        'static.jsapi_secret_safe_safety',
        '凭证不硬编码、不提交环境密钥',
        'security',
        ok,
        '提交的敏感文件/字面量: files=%s literals=%s' % (env_like or '无', leaked_literals or '无'),
        ['code_files'],
    )


def check_state_and_accounting_model():
    terms = {
        'paid': ['paid', 'trade_success'],
        'failed': ['failed', 'closed', 'canceled', 'cancelled'],
        'refunded': ['refunded'],
        'partial': ['partial_refund', 'partially_refunded', 'partial_refunded', 'refund_amount', 'refunded_amount'],
    }
    found = {k: any(t in SRC_LOWER for t in vals) for k, vals in terms.items()}
    ok = all(found.values())
    record(
        'static.jsapi_state_machine_model',
        '订单状态机区分支付、失败、全额退款和部分退款',
        'correctness',
        ok,
        '状态/字段覆盖: %s' % found,
        ['app', 'database/migrations'],
    )


def check_buyer_owner_model():
    buyer_terms = ['buyer_id', 'buyer_open_id', 'buyer_user_id', 'buyer_logon_id', 'openid', 'user_id']
    compare_terms = ['!=', '!==', 'where(', 'abort(', 'throw', 'unauthorized', 'forbidden', 'owner']
    has_buyer = any(t in SRC_LOWER for t in buyer_terms)
    has_guard = has_buyer and any(t in SRC_LOWER for t in compare_terms)
    record(
        'static.jsapi_buyer_owner_guard',
        '交易回查和通知处理包含买家/订单归属保护',
        'security',
        has_guard,
        'buyer 字段=%s，保护逻辑迹象=%s' % (has_buyer, has_guard),
        ['app', 'database/migrations'],
    )


def check_query_and_refund_contracts():
    query_terms = ['querytrade', 'alipay.trade.query', 'tradequery']
    has_query_capability = any(t in SRC_LOWER for t in query_terms)
    compensation_patterns = [
        r'function\s+sync\s*\([^)]*\)[\s\S]{0,2200}(querytrade|reconcile|confirmfrom|gateway)',
        r'(clientresult|client-result)[\s\S]{0,2200}(querytrade|reconcile|confirmfrom|gateway)',
    ]
    has_compensation_entry = any(re.search(pattern, SRC_LOWER) for pattern in compensation_patterns)
    query_ok = has_query_capability and has_compensation_entry
    record(
        'static.jsapi_query_compensation',
        '同步/补偿入口主动调用查单确认最终状态',
        'correctness',
        bool(query_ok),
        '查单能力=%s，补偿入口=%s' % (has_query_capability, has_compensation_entry),
        ['app/Http/Controllers/AlipayJsapiMembershipController.php'],
    )
    refund_id_terms = ['out_request_no', 'refund_request_no', 'refund_no', 'idempotency']
    fund_terms = ['fund_change', 'refund_fee', 'send_back_fee', 'refund_amount', 'refunded_amount']
    refund_ok = any(t in SRC_LOWER for t in refund_id_terms) and any(t in SRC_LOWER for t in fund_terms)
    record(
        'static.jsapi_refund_idempotency_accounting',
        '退款具备幂等请求号和实际资金变动口径',
        'correctness',
        refund_ok,
        '退款幂等字段=%s，资金字段=%s' % (
            [t for t in refund_id_terms if t in SRC_LOWER] or '无',
            [t for t in fund_terms if t in SRC_LOWER] or '无',
        ),
        ['app', 'database/migrations'],
    )


try:
    check_sdk_and_gateway_contract()
    check_stable_routes()
    check_no_fake_bypass()
    check_secret_safety()
    check_state_and_accounting_model()
    check_buyer_owner_model()
    check_query_and_refund_contracts()
except Exception as exc:
    record('static.checker_crash', '静态检查器自身异常', 'infrastructure', False, repr(exc))

OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
(OUTPUT_DIR / 'static_checks.json').write_text(json.dumps(RESULTS, ensure_ascii=False, indent=2), encoding='utf-8')
