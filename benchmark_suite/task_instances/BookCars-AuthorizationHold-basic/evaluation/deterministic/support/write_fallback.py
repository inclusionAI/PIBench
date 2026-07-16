#!/usr/bin/env python3
import json, os, sys
from pathlib import Path
phase, case_name, out = sys.argv[1], sys.argv[2], Path(sys.argv[3])
BASIC_INTEGRATION = [("I0","应用启动"),("I1","登录成功"),("I2","freeze 端点"),("I3","query 端点"),("I4","notify 端点"),("I5","freeze 后保存预授权标识"),("I6","notify 后更新预授权状态"),("I7","freeze-query-notify 使用同一预授权标识"),("I8","冻结成功后 booking 进入可服务状态")]
BASIC_E2E = [("E1","预订流程二维码"),("E2","二维码内容 alipays://")]
SAFETY_INTEGRATION = [("I1","应用启动"),("I2","freeze 打到 mock"),("I3","无签名通知被拒"),("I4","错误 app_id 被拒"),("I5","有效签名通过"),("I6","通知幂等"),("I7","终态保护"),("I8","unfreeze 端点"),("I9","query 打到 mock"),("I10","转支付携带 auth_no"),("I11","解冻请求含稳定 out_request_no"),("I12","不存在预订号的通知被拒"),("I13","签名通知字段错配被拒"),("I14","转支付后解冻剩余金额"),("I15","未消费前不能解冻"),("I16","撤销与解冻边界"),("I17","query 非成功态不能入账/解锁")]
SAFETY_E2E = [("E1","预订流程 QR code")]
scenario = os.environ.get("PAYSKILLS_SCENARIO", "")
if scenario not in ("basic", "advanced"):
    raise ValueError("unsupported BookCars evaluation scenario: %r" % scenario)
if scenario == "advanced":
    defs = SAFETY_INTEGRATION if phase == "integration" else SAFETY_E2E
    msg = "INFRA: backend not running" if phase == "integration" else "INFRA: frontend not running"
else:
    defs = BASIC_INTEGRATION if phase == "integration" else BASIC_E2E
    msg = "INFRA: services not running"
rubrics = [{"id": rid, "name": name, "dimension": "quality", "type": "deterministic", "passed": False, "score": 0.0, "max_score": 1.0, "message": msg, "evidence": ["services_start.log"], "test_infra_failure": True} for rid, name in defs]
out.write_text(json.dumps({"rubrics": rubrics, "metadata": {"phase": phase, "fallback": msg}}, ensure_ascii=False, indent=2), encoding="utf-8")
