"""Static code checks (rubrics S1-S5) over the agent workspace.

Writes /output/static_checks.json. Heuristic checks; each result carries a
message explaining the evidence so reviewers can audit false positives.
"""
import json
import os
import re
import subprocess
import sys

WORKSPACE = sys.argv[1] if len(sys.argv) > 1 else "/workspace"
OUTPUT_DIR = sys.argv[2] if len(sys.argv) > 2 else "/output"

SCAN_DIRS = ["app", "config", "routes", "database", "bootstrap"]
PRIVATE_KEY_RE = re.compile(r"-----BEGIN (RSA |EC |ENCRYPTED )?PRIVATE KEY-----")


def iter_files(base, subdirs, exts):
    for sub in subdirs:
        root_dir = os.path.join(base, sub)
        for root, dirs, files in os.walk(root_dir):
            dirs[:] = [d for d in dirs if d not in ("vendor", "node_modules", ".git")]
            for name in files:
                if any(name.endswith(ext) for ext in exts):
                    yield os.path.join(root, name)


def read(path):
    try:
        with open(path, errors="replace") as f:
            return f.read()
    except OSError:
        return ""


def git_tracked_files():
    try:
        out = subprocess.check_output(["git", "ls-files"], cwd=WORKSPACE)
        return out.decode("utf-8", "replace").splitlines()
    except Exception:
        return []


def check_dep_sdk():
    composer = {}
    try:
        composer = json.loads(read(os.path.join(WORKSPACE, "composer.json")))
    except ValueError:
        pass
    deps = list((composer.get("require") or {}).keys()) + list((composer.get("require-dev") or {}).keys())
    alipay_deps = [d for d in deps if "alipay" in d.lower()]
    if alipay_deps:
        return True, "composer 依赖中存在支付宝 SDK: %s" % ", ".join(alipay_deps)
    has_alipay_ref = False
    has_client_capability = False
    hits = []
    for path in iter_files(WORKSPACE, ["app", "config"], [".php"]):
        content = read(path)
        lower = content.lower()
        if "alipay" in lower:
            has_alipay_ref = True
            if ("openssl_sign" in lower or "http::" in lower or "guzzlehttp" in lower
                    or "curl_init" in lower or "->post(" in lower or "->asform(" in lower):
                has_client_capability = True
                hits.append(os.path.relpath(path, WORKSPACE))
    if has_alipay_ref and has_client_capability:
        return True, "代码中存在支付宝网关 HTTP 调用/RSA 签名封装: %s" % ", ".join(hits[:5])
    if has_alipay_ref:
        return False, "代码提到 alipay 但未发现 SDK 依赖或 HTTP/签名调用能力，疑似本地 fake"
    return False, "未发现支付宝 SDK 依赖或网关调用代码"


def check_config_env():
    hits = []
    for path in iter_files(WORKSPACE, ["config", "app"], [".php"]):
        content = read(path)
        if re.search(r"env\(\s*['\"]ALIPAY", content) or re.search(r"config\(\s*['\"]alipay", content, re.I):
            hits.append(os.path.relpath(path, WORKSPACE))
    if hits:
        return True, "支付配置通过 env()/config() 读取: %s" % ", ".join(sorted(set(hits))[:5])
    return False, "未发现从环境变量/配置文件读取 ALIPAY 配置的代码"


def check_secret_safe():
    tracked = git_tracked_files()
    if not tracked:
        return False, "无法列出 git 跟踪文件，无法确认密钥安全（test 实现问题，请人工复核）"
    offenders = []
    if ".env" in tracked:
        offenders.append(".env (被提交进版本库)")
    for rel in tracked:
        if rel.startswith(("vendor/", "node_modules/")):
            continue
        path = os.path.join(WORKSPACE, rel)
        if not os.path.exists(path) or os.path.getsize(path) > 2 * 1024 * 1024:
            continue
        if PRIVATE_KEY_RE.search(read(path)):
            offenders.append(rel)
    if offenders:
        return False, "仓库源码中发现私钥/敏感文件: %s" % ", ".join(offenders[:5])
    return True, "git 跟踪的源码中未发现 PEM 私钥块，.env 未入库"


def check_provider_model():
    trade_hit = []
    paid_hit = []
    trade_patterns = [
        "trade_no", "alipay_trade", "gateway_trade", "provider_trade",
        "provider_transaction", "transaction_id", "payment_reference",
        "payment_intent", "payment_no", "tradeno",
    ]
    for path in iter_files(WORKSPACE, ["database", "app"], [".php"]):
        content = read(path)
        lower = content.lower()
        rel = os.path.relpath(path, WORKSPACE)
        # Factories/seeders can mention paid states without proving the real
        # order/payment model can persist a provider transaction and paid state.
        if rel.startswith("database/factories/") or rel.startswith("database/seeders/"):
            continue
        if any(pattern in lower for pattern in trade_patterns):
            trade_hit.append(rel)
        if re.search(r"[\'\"](paid|trade_success|completed|fulfilled)[\'\"]|STATUS_PAID|paid_at", content, re.I):
            paid_hit.append(rel)
    if trade_hit and paid_hit:
        return True, "订单/支付模型可表达支付交易标识(%s)与支付完成状态(%s)" % (trade_hit[0], paid_hit[0])
    missing = []
    if not trade_hit:
        missing.append("支付交易标识字段")
    if not paid_hit:
        missing.append("支付完成状态/paid_at 字段")
    return False, "模型/迁移中缺少: %s（忽略 factory/seed 假数据，最终以集成链路和 LLM judge 复核）" % "、".join(missing)


def check_miniapp_pay_call():
    has_trade_pay = []
    has_trade_no = []
    for path in iter_files(WORKSPACE, ["miniapp"], [".js"]):
        content = read(path)
        rel = os.path.relpath(path, WORKSPACE)
        if re.search(r"\btradePay\s*\(|my\.tradePay", content):
            has_trade_pay.append(rel)
        if "tradeNO" in content:
            has_trade_no.append(rel)
    if has_trade_pay and has_trade_no:
        return True, "小程序端调用原生支付(%s)且使用 tradeNO 字段(%s)" % (has_trade_pay[0], has_trade_no[0])
    missing = []
    if not has_trade_pay:
        missing.append("my.tradePay 调用")
    if not has_trade_no:
        missing.append("tradeNO 字段读取")
    return False, "小程序代码缺少: %s" % "、".join(missing)


CHECKS = [
    ("static.jsapi_dep_sdk", "SDK/OpenAPI 客户端接入", "functionality", check_dep_sdk),
    ("static.jsapi_config_env", "支付配置来自运行时配置", "security", check_config_env),
    ("static.jsapi_secret_safe", "不提交真实密钥", "security", check_secret_safe),
    ("static.jsapi_provider_model", "支付方式接入订单模型", "functionality", check_provider_model),
    ("static.jsapi_miniapp_pay_call", "小程序端存在原生支付调用", "functionality", check_miniapp_pay_call),
]


def main():
    results = []
    for rid, name, dimension, fn in CHECKS:
        try:
            passed, message = fn()
        except Exception as exc:  # a broken check is a test bug, not agent failure
            passed, message = False, "static check 自身异常（test 实现问题）: %r" % exc
        results.append({
            "id": rid,
            "name": name,
            "dimension": dimension,
            "type": "hard",
            "passed": bool(passed),
            "score": 1 if passed else 0,
            "max_score": 1,
            "message": message,
            "evidence": ["patch.diff", "code_files/"],
        })
        print("[static] %s %s: %s" % ("PASS" if passed else "FAIL", rid, message))
    with open(os.path.join(OUTPUT_DIR, "static_checks.json"), "w") as f:
        json.dump(results, f, indent=2, ensure_ascii=False)


if __name__ == "__main__":
    main()
