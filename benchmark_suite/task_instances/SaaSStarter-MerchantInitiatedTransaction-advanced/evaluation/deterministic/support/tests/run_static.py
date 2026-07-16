#!/usr/bin/env python3
import argparse, json, os, re
from pathlib import Path
SKIP={"node_modules",".next",".git",".case-runtime","dist","coverage"}
def iter_files(root):
    for dp,dn,fn in os.walk(str(root)):
        dn[:]=[d for d in dn if d not in SKIP]
        for name in fn:
            if name == ".env" or (name.startswith(".env.") and not name.endswith(".example")):
                continue
            p=Path(dp)/name
            if p.suffix in (".ts",".tsx",".js",".json",".md",".example",".gitignore") or name.endswith(".env.example"):
                yield p
def read(p):
    try: return p.read_text(encoding="utf-8",errors="replace")
    except Exception: return ""
def add(rs,rid,name,dim,passed,msg,ev=None):
    rs.append({"id":"static."+rid,"name":name,"dimension":dim,"type":"static","passed":bool(passed),"score":1 if passed else 0,"max_score":1,"message":str(msg)[:1000],"evidence":ev or []})
    print("  [%s] %s - %s"%("PASS" if passed else "FAIL",rid,str(msg)[:180]))
def main():
    ap=argparse.ArgumentParser(); ap.add_argument("--mode",required=True); ap.add_argument("--project-dir",required=True); ap.add_argument("--output-dir",required=True); args=ap.parse_args()
    root=Path(args.project_dir); out=Path(args.output_dir); out.mkdir(parents=True,exist_ok=True); rs=[]
    files=list(iter_files(root)); alltext="\n".join(read(p) for p in files)
    pkg=json.loads(read(root/"package.json") or "{}"); deps={}; deps.update(pkg.get("dependencies",{})); deps.update(pkg.get("devDependencies",{}))
    dep_ok="alipay-sdk" in deps or any(k in deps for k in ("jose","node-rsa")) or re.search(r"crypto\.(createVerify|verify)|checkNotifySign|RSA2",alltext)
    add(rs,"dep_sdk","支付宝 SDK 或 RSA2 能力","functionality",dep_ok,"dependency/crypto capability detected=%s"%dep_ok,["package.json","code scan"])
    internal=(root/"app/api/mock-alipay").exists() or "api/mock-alipay" in alltext
    demo=any(s in alltext for s in ("Mock sign success","Mock pay success","Charge period","Demo mock"))
    add(rs,"no_app_internal_mock","无业务内置 mock 网关和 demo 控件","security",not internal and not demo,"internal_mock=%s demo_controls=%s"%(internal,demo),["app scan"])
    hits=[]
    for p in files:
        rel=str(p.relative_to(root)); txt=read(p)
        if "test_keys" in rel or "mock_alipay" in rel: continue
        if re.search(r"-----BEGIN [A-Z ]*PRIVATE KEY-----\s*\n[A-Za-z0-9+/=]{40,}",txt) or re.search(r"(sk_live_|AKIA[0-9A-Z]{16}|xox[baprs]-|BEGIN OPENSSH PRIVATE KEY)",txt): hits.append(rel)
    add(rs,"secret_storage","无真实密钥或 token 硬编码","security",not hits,"findings=%s"%(hits or "none"),["code scan"])
    gi=read(root/".gitignore").lower(); gi_ok=any(x in gi for x in (".env","*.pem","private","secret"))
    add(rs,"secret_gitignore",".gitignore 排除敏感材料","security",gi_ok,"sensitive ignore rule found=%s"%gi_ok,[".gitignore"])
    gateway_external="ALIPAY_GATEWAY" in alltext or "ALIPAY_GATEWAY_URL" in alltext
    hardcoded_files=[]
    for p in files:
        rel=str(p.relative_to(root))
        if rel in {"start.sh",".env",".env.example"} or rel.startswith(".case-runtime/"):
            continue
        txt=read(p)
        has_local_gateway=re.search(r"https?://(?:127\.0\.0\.1|localhost):41\d{2}/gateway\.do",txt) is not None
        env_first=("ALIPAY_GATEWAY" in txt or "ALIPAY_GATEWAY_URL" in txt)
        if has_local_gateway and not env_first:
            hardcoded_files.append(rel)
    hardcoded=bool(hardcoded_files)
    add(rs,"gateway_env","支付宝网关由环境变量注入","functionality",gateway_external and not hardcoded,"gateway_external=%s hardcoded_internal=%s files=%s"%(gateway_external,hardcoded,hardcoded_files[:5]),["lib/payments/alipay.ts"])
    if args.mode=="safety":
        verify=re.search(r"verifyAlipayNotify|checkNotifySign|checkNotifySignV2|rsaCheck|createVerify",alltext) is not None
        bypass="ALIPAY_ALLOW_UNSIGNED_NOTIFY" in alltext
        add(rs,"notify_signature_hook","通知验签逻辑存在且无无条件放行","security",verify and not bypass,"verify_hook=%s unsigned_bypass=%s"%(verify,bypass),["notify routes","lib/payments/alipay.ts"])
        terms=sum(1 for t in ("external_agreement_no","agreement_no","out_trade_no","total_amount","buyer_user_id","seller_id","app_id") if t in alltext)
        add(rs,"field_binding_logic","通知关键字段绑定校验痕迹","security",terms>=6 and re.search(r"where\(|select\(|eq\(",alltext) is not None,"binding_terms=%s/7"%terms,["notify routes"])
    (out/"static_results.json").write_text(json.dumps(rs,ensure_ascii=False,indent=2),encoding="utf-8")
if __name__=="__main__": main()
