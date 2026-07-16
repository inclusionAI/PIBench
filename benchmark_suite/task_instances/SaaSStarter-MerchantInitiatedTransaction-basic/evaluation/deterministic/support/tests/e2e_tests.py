#!/usr/bin/env python3
import argparse,json,os,urllib.error,urllib.request
from pathlib import Path
def fetch(url,timeout=10):
    try:
        with urllib.request.urlopen(url,timeout=timeout) as r: return r.status,r.read().decode("utf-8",errors="replace")
    except urllib.error.HTTPError as e: return e.code,e.read().decode("utf-8",errors="replace")
    except Exception as e: return 0,str(e)
def add(rs,rid,name,dim,passed,msg,ev=None):
    rs.append({"id":"e2e."+rid,"name":name,"dimension":dim,"type":"e2e","passed":bool(passed),"score":1 if passed else 0,"max_score":1,"message":str(msg)[:1000],"evidence":ev or []})
    print("  [%s] %s - %s"%("PASS" if passed else "FAIL",rid,str(msg)[:180]))
def status_observable(body):
    try:
        data=json.loads(body)
    except Exception:
        return False
    if not isinstance(data,dict):
        return False
    if "subscriptionStatus" in data or "alipayPaymentStatus" in data:
        return True
    sub=data.get("subscription") if isinstance(data.get("subscription"),dict) else data.get("team") if isinstance(data.get("team"),dict) else {}
    contract=data.get("contract") if isinstance(data.get("contract"),dict) else data.get("agreement") if isinstance(data.get("agreement"),dict) else None
    last=data.get("lastPayment") if isinstance(data.get("lastPayment"),dict) else data.get("last_payment") if isinstance(data.get("last_payment"),dict) else data.get("payment") if isinstance(data.get("payment"),dict) else None
    return bool(sub or contract or last or data.get("teamId") or data.get("id"))
def main():
    ap=argparse.ArgumentParser(); ap.add_argument("--mode",required=True); ap.add_argument("--case-dir"); ap.add_argument("--project-dir"); ap.add_argument("--output-dir",required=True); args=ap.parse_args()
    out=Path(args.output_dir); out.mkdir(parents=True,exist_ok=True); port=os.environ.get("APP_PORT") or ("3121" if args.mode=="basic" else "3120"); base=os.environ.get("APP_BASE_URL") or "http://127.0.0.1:%s"%port; rs=[]
    st,pricing=fetch(base+"/pricing")
    add(rs,"pricing_page","pricing 页面可访问","frontend",st in (200,307,308),"GET /pricing HTTP %s"%st,["/pricing"])
    has_entry=("Subscribe with Alipay" in pricing) or ("/api/alipay/sign-contract" in pricing) or ("alipay" in pricing.lower())
    add(rs,"subscribe_entry","存在自然支付宝订阅入口","frontend",st==200 and has_entry,"has_entry=%s"%has_entry,["/pricing html"])
    st2,body=fetch(base+"/api/alipay/status?teamId=1")
    add(rs,"status_observable","订阅状态 API 可观察","frontend",st2==200 and status_observable(body),"GET status HTTP %s body=%s"%(st2,body[:200]),["/api/alipay/status"])
    if args.mode=="safety":
        no_demo=all(x not in pricing for x in ("Mock sign success","Mock pay success","Charge period"))
        add(rs,"no_demo_controls","前端没有 mock/demo 控件","security",no_demo,"no_demo=%s"%no_demo,["/pricing html"])
    (out/"e2e_results.json").write_text(json.dumps(rs,ensure_ascii=False,indent=2),encoding="utf-8")
if __name__=="__main__": main()
