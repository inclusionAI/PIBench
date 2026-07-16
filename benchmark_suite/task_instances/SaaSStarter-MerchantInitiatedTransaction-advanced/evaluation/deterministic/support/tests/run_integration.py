#!/usr/bin/env python3
import argparse,json,os,subprocess,sys,time,urllib.error,urllib.parse,urllib.request
from pathlib import Path
def post_json(url,obj,timeout=20):
    data=json.dumps(obj).encode(); req=urllib.request.Request(url,data=data,headers={"content-type":"application/json"},method="POST")
    try:
        with urllib.request.urlopen(req,timeout=timeout) as r: return r.status,json.loads(r.read().decode() or "{}")
    except urllib.error.HTTPError as e:
        body=e.read().decode()
        try: return e.code,json.loads(body or "{}")
        except Exception: return e.code,{"body":body}
    except Exception as e: return 0,{"error":str(e)}
def post_form_json(url,obj,timeout=20):
    clean={k:str(v) for k,v in obj.items() if v is not None}
    data=urllib.parse.urlencode(clean).encode(); req=urllib.request.Request(url,data=data,headers={"content-type":"application/x-www-form-urlencoded"},method="POST")
    try:
        with urllib.request.urlopen(req,timeout=timeout) as r: return r.status,json.loads(r.read().decode() or "{}")
    except urllib.error.HTTPError as e:
        body=e.read().decode()
        try: return e.code,json.loads(body or "{}")
        except Exception: return e.code,{"body":body}
    except Exception as e: return 0,{"error":str(e)}
def get_json(url,timeout=20):
    with urllib.request.urlopen(url,timeout=timeout) as r: return json.loads(r.read().decode() or "{}")
def add(cs,rid,name,dim,passed,msg,ev=None):
    cs.append({"id":"integ."+rid,"name":name,"dimension":dim,"type":"integration","passed":bool(passed),"score":1 if passed else 0,"max_score":1,"message":str(msg)[:1200],"evidence":ev or []})
    print("  [%s] %s - %s"%("PASS" if passed else "FAIL",rid,str(msg)[:200]))
def run(cmd,cwd=None,env=None): return subprocess.run(cmd,cwd=str(cwd) if cwd else None,env=env,universal_newlines=True,stdout=subprocess.PIPE,stderr=subprocess.STDOUT,check=False)
def wait_url(url,timeout=30):
    end=time.time()+timeout
    while time.time()<end:
        try: urllib.request.urlopen(url,timeout=2).read(); return True
        except Exception: time.sleep(.5)
    return False

def status_view(status):
    if not isinstance(status, dict):
        return {}
    team=status.get("team") if isinstance(status.get("team"),dict) else {}
    sub=status.get("subscription") if isinstance(status.get("subscription"),dict) else team
    contract=status.get("contract") if isinstance(status.get("contract"),dict) else status.get("agreement") if isinstance(status.get("agreement"),dict) else {}
    last=latest_payment_record(status)
    view=dict(status)
    def put(key, *values):
        if view.get(key) not in (None, ""):
            return
        for value in values:
            if value not in (None, ""):
                view[key]=value
                return
    put("id", status.get("teamId"), team.get("id"), team.get("teamId"))
    put("teamId", status.get("id"), team.get("teamId"), team.get("id"))
    put("planName", sub.get("planName"), sub.get("plan_name"), team.get("planName"), team.get("plan_name"))
    put("subscriptionStatus", sub.get("status"), sub.get("subscriptionStatus"), team.get("subscriptionStatus"), team.get("status"))
    put("alipayAgreementNo", contract.get("agreementNo"), contract.get("agreement_no"), contract.get("alipayAgreementNo"), contract.get("alipay_agreement_no"))
    put("alipayExternalAgreementNo", contract.get("externalAgreementNo"), contract.get("external_agreement_no"), contract.get("alipayExternalAgreementNo"), contract.get("alipay_external_agreement_no"))
    put("alipayBuyerUserId", contract.get("buyerUserId"), contract.get("buyer_user_id"), contract.get("alipayUserId"), contract.get("alipay_user_id"))
    put("alipayLastOutTradeNo", last.get("outTradeNo"), last.get("out_trade_no"))
    put("alipayLastTradeNo", last.get("tradeNo"), last.get("trade_no"), last.get("alipayTradeNo"), last.get("alipay_trade_no"))
    put("alipayLastAmount", last.get("amount"), last.get("totalAmount"), last.get("total_amount"))
    put("alipayPaymentStatus", last.get("tradeStatus"), last.get("trade_status"), last.get("status"))
    return view
def start_mock(case_dir,out,port):
    existing=os.environ.get("ALIPAY_MOCK_BASE_URL")
    if existing:
        if not wait_url(existing+"/__mock/state",20): raise RuntimeError("existing mock server failed")
        return None
    subprocess.run(["bash","-lc","fuser -k %s/tcp 2>/dev/null || true"%port],check=False)
    log=open(str(out/"mock_alipay.log"),"w")
    p=subprocess.Popen([sys.executable,str(case_dir/"tests/mock_alipay_server.py"),"--host","127.0.0.1","--port",str(port)],stdout=log,stderr=subprocess.STDOUT,universal_newlines=True)
    (out/"mock_alipay.pid").write_text(str(p.pid))
    if not wait_url("http://127.0.0.1:%s/__mock/state"%port,20): raise RuntimeError("mock server failed")
    return p
_PNPM_CMD=None
def pnpm_cmd():
    global _PNPM_CMD
    if _PNPM_CMD is not None:
        return _PNPM_CMD
    try:
        ver=subprocess.run(['pnpm','--version'],text=True,stdout=subprocess.PIPE,stderr=subprocess.STDOUT,check=False).stdout.strip()
        if ver and int(ver.split('.')[0]) <= 9:
            _PNPM_CMD=['pnpm']
            return _PNPM_CMD
    except Exception:
        pass
    _PNPM_CMD=['npx','-y','pnpm@9.15.9']
    return _PNPM_CMD
def reset_app(project):
    env=os.environ.copy()
    env.update({
        "POSTGRES_URL": env.get("POSTGRES_URL") or "postgres://postgres:postgres@127.0.0.1:5432/postgres",
        "SKIP_STRIPE_SEED": "true",
        "ALIPAY_CASE_LOCAL_PLANS": "true",
    })
    script = r"""
import postgres from 'postgres';
const sql = postgres(process.env.POSTGRES_URL || 'postgres://postgres:postgres@127.0.0.1:5432/postgres');
const quoteIdent = (s) => '"' + String(s).replaceAll('"', '""') + '"';
const literal = (v) => v === null ? 'NULL' : "'" + String(v).replaceAll("'", "''") + "'";
try {
  const rows = await sql`
    select table_name
    from information_schema.tables
    where table_schema = 'public' and table_name like 'alipay_%'
  `;
  if (rows.length) {
    await sql.unsafe(`TRUNCATE TABLE ${rows.map(r => quoteIdent(r.table_name)).join(', ')} RESTART IDENTITY CASCADE`);
  }
  const cols = await sql`
    select column_name
    from information_schema.columns
    where table_schema = 'public' and table_name = 'teams'
  `;
  const existing = new Set(cols.map(c => c.column_name));
  const values = {
    plan_name: 'Base',
    subscription_status: 'mock_ready',
    alipay_external_agreement_no: null,
    alipay_agreement_no: null,
    alipay_buyer_user_id: null,
    alipay_last_out_trade_no: null,
    alipay_last_trade_no: null,
    alipay_last_amount: null,
    alipay_payment_status: 'READY',
    alipay_next_deduct_time: null,
    updated_at: new Date().toISOString(),
  };
  const assignments = Object.entries(values)
    .filter(([key]) => existing.has(key))
    .map(([key, value]) => `${quoteIdent(key)} = ${literal(value)}`);
  if (assignments.length) {
    await sql.unsafe(`UPDATE "teams" SET ${assignments.join(', ')} WHERE id = 1`);
  }
} finally {
  await sql.end();
}
"""
    p=run(['node','--input-type=module','-e',script],cwd=project,env=env)
    if p.returncode:
        raise RuntimeError("app db reset failed: %s"%p.stdout[-2000:])
def reset(mock,project):
    st,res=post_json(mock+"/__mock/reset",{})
    if st >= 400 or st == 0:
        raise RuntimeError("mock reset failed: status=%s body=%s"%(st,res))
    reset_app(project)
    time.sleep(.2)
def latest_deduction_status(status):
    deductions=status.get("deductions") if isinstance(status,dict) else None
    if isinstance(deductions,list) and deductions and isinstance(deductions[0],dict):
        return deductions[0].get("status") or deductions[0].get("tradeStatus") or deductions[0].get("trade_status")
    return None
def first_value(obj,*keys):
    if not isinstance(obj,dict):
        return None
    for key in keys:
        value=obj.get(key)
        if value not in (None,""):
            return value
    return None
def looks_like_payment_record(value):
    if not isinstance(value,dict) or not value:
        return False
    order=first_value(value,"outTradeNo","out_trade_no","alipayLastOutTradeNo","alipay_last_out_trade_no")
    trade=first_value(value,"tradeNo","trade_no","alipayTradeNo","alipay_trade_no","alipayLastTradeNo","alipay_last_trade_no")
    status=first_value(value,"tradeStatus","trade_status","rawTradeStatus","raw_trade_status","status","paymentStatus","payment_status","alipayPaymentStatus","alipay_payment_status")
    amount=first_value(value,"amount","totalAmount","total_amount","alipayLastAmount","alipay_last_amount")
    period=first_value(value,"periodIndex","period_index","billingPeriod","billing_period")
    source=first_value(value,"confirmedSource","confirmed_source","confirmedAt","confirmed_at","paidAt","paid_at","finishedAt","finished_at","successAt","success_at")
    return bool(order or trade or (status and amount) or (status and period) or (source and status))
def payment_records(status):
    if not isinstance(status,dict):
        return []
    records=[]
    seen=set()
    def add(value):
        if isinstance(value,dict) and looks_like_payment_record(value):
            marker=id(value)
            if marker not in seen:
                seen.add(marker)
                records.append(value)
    def walk(value):
        if isinstance(value,dict):
            add(value)
            for child in value.values():
                walk(child)
        elif isinstance(value,list):
            for child in value:
                walk(child)
    walk(status)
    return records
def payment_record_score(rec):
    score=0
    if out_trade_no(rec): score+=4
    if payment_trade_no_from_record(rec): score+=3
    if payment_raw_status_from_record(rec): score+=2
    if first_value(rec,"amount","totalAmount","total_amount","alipayLastAmount","alipay_last_amount"): score+=1
    if first_value(rec,"confirmedSource","confirmed_source","confirmedAt","confirmed_at","paidAt","paid_at","finishedAt","finished_at","successAt","success_at"): score+=1
    return score
def latest_payment_record(status, expected_out_trade_no=None):
    records=payment_records(status)
    if expected_out_trade_no:
        matches=[rec for rec in records if out_trade_no(rec) == expected_out_trade_no]
        if matches:
            return max(matches,key=payment_record_score)
    if records:
        return max(records,key=payment_record_score)
    return {}
def canonical_status(value):
    return str(value or "").strip().upper()
def payment_trade_no_from_record(rec):
    return first_value(rec,"tradeNo","trade_no","alipayTradeNo","alipay_trade_no","alipayLastTradeNo","alipay_last_trade_no")
def payment_raw_status_from_record(rec):
    return canonical_status(first_value(rec,"tradeStatus","trade_status","rawTradeStatus","raw_trade_status","status","paymentStatus","payment_status","alipayPaymentStatus","alipay_payment_status"))
def payment_amount(status, expected_out_trade_no=None):
    rec=latest_payment_record(status, expected_out_trade_no)
    return first_value(rec,"amount","totalAmount","total_amount") or first_value(status,"alipayLastAmount","alipay_last_amount","amount","totalAmount","total_amount")
def payment_trade_no(status, expected_out_trade_no=None):
    rec=latest_payment_record(status, expected_out_trade_no)
    return payment_trade_no_from_record(rec) or first_value(status,"alipayLastTradeNo","alipay_last_trade_no")
def payment_confirmed_at(status, expected_out_trade_no=None):
    rec=latest_payment_record(status, expected_out_trade_no)
    return first_value(rec,"confirmedAt","confirmed_at","paidAt","paid_at","finishedAt","finished_at","successAt","success_at")
def payment_raw_status(status, expected_out_trade_no=None):
    rec=latest_payment_record(status, expected_out_trade_no)
    return payment_raw_status_from_record(rec) or canonical_status(first_value(status,"alipayPaymentStatus","alipay_payment_status"))
def payment_success(status, expected_out_trade_no=None, expected_amount="8.00", verified_event=False):
    if not isinstance(status,dict):
        return False
    rec=latest_payment_record(status, expected_out_trade_no)
    out_no=out_trade_no(rec) or out_trade_no(status)
    if expected_out_trade_no and out_no != expected_out_trade_no:
        return False
    amount=payment_amount(status, expected_out_trade_no)
    if expected_amount is not None and amount not in (None,"") and str(amount) != str(expected_amount):
        return False
    raw=payment_raw_status(status, expected_out_trade_no)
    if raw in {"WAIT_BUYER_PAY","TRADE_CLOSED","PENDING","PROCESSING","UNKNOWN","FAILED","CLOSED","10000","10003","20000","40004"}:
        return False
    if raw in {"TRADE_SUCCESS","TRADE_FINISHED"}:
        return bool(out_no and payment_trade_no(status, expected_out_trade_no))
    if verified_event:
        return bool(out_no and payment_trade_no(status, expected_out_trade_no))
    return bool(out_no and payment_trade_no(status, expected_out_trade_no) and payment_confirmed_at(status, expected_out_trade_no))
def payment_not_success(status, expected_out_trade_no=None):
    return not payment_success(status, expected_out_trade_no)
def invalid_notify_rejected(result):
    notify=result.get("notify")
    body=json.dumps(notify,ensure_ascii=False).lower()
    if "unknown url type" in body or "no host supplied" in body:
        return False
    if isinstance(notify,dict) and "error" in notify and not notify.get("ok"):
        return False
    app_status=notify.get("status") if isinstance(notify,dict) else result.get("notify_status")
    app_body=str(notify.get("body") if isinstance(notify,dict) else notify).lower()
    if result.get("notify_status") in (500,502,503,504) and not (app_status in (400,403)):
        return False
    if not (app_status in (400,403) or "fail" in app_body or "mismatch" in app_body or "invalid" in app_body or "rejected" in app_body or "not found" in app_body):
        return False
    before=result.get("before_notify") or {}
    after=result.get("status") or {}
    before_out=out_trade_no(before)
    after_out=out_trade_no(after)
    if before_out and after_out and before_out != after_out:
        return False
    if payment_success(after, after_out, verified_event=True) and not payment_success(before, before_out, verified_event=True):
        return False
    return True
def out_trade_no(obj):
    return first_value(obj,"outTradeNo","out_trade_no","alipayLastOutTradeNo","alipay_last_out_trade_no")
def normalize_field_name(key):
    return "".join(ch for ch in str(key).lower() if ch.isalnum())
def find_out_trade_no(obj):
    seen=set()
    def walk(value):
        if isinstance(value,dict):
            marker=id(value)
            if marker in seen:
                return None
            seen.add(marker)
            direct=out_trade_no(value)
            if direct:
                return direct
            for key, child in value.items():
                if normalize_field_name(key)=="outtradeno" and child not in (None,""):
                    return child
            for child in value.values():
                found=walk(child)
                if found:
                    return found
        elif isinstance(value,list):
            marker=id(value)
            if marker in seen:
                return None
            seen.add(marker)
            for child in value:
                found=walk(child)
                if found:
                    return found
        return None
    return walk(obj)
def resolved_out_trade_no(*objs):
    for obj in objs:
        value=out_trade_no(obj)
        if value:
            return value
    for obj in objs:
        if isinstance(obj,dict):
            value=out_trade_no(latest_payment_record(obj))
            if value:
                return value
    for obj in objs:
        value=find_out_trade_no(obj)
        if value:
            return value
    return None
def external_agreement_no(obj):
    return first_value(obj,"externalAgreementNo","external_agreement_no","alipayExternalAgreementNo","alipay_external_agreement_no","agreementId","agreement_id")
def require_seed_data(app):
    try:
        status=get_json(app+"/api/alipay/status?teamId=1")
    except Exception as e:
        return False, {"error": str(e)}
    view=status_view(status)
    return isinstance(status,dict) and (view.get("id")==1 or view.get("teamId")==1 or status.get("teamName")), view
def iter_order_strings(obj):
    if isinstance(obj,dict):
        for key,value in obj.items():
            if key in ("orderStr","orderString","order_string","order_str","payUrl","pay_url","appPayParams") and isinstance(value,str) and value.strip():
                yield value
            elif isinstance(value,(dict,list)):
                for found in iter_order_strings(value):
                    yield found
    elif isinstance(obj,list):
        for value in obj:
            for found in iter_order_strings(value):
                yield found
def parse_order_params(order):
    if not isinstance(order,str) or not order.strip():
        return None, "empty order string"
    raw=order.strip()
    parsed=urllib.parse.urlparse(raw)
    query=parsed.query if parsed.query else raw
    params={k:v[-1] for k,v in urllib.parse.parse_qs(query,keep_blank_values=True).items()}
    nested=first_value(params,"orderStr","orderString","order_string","order_str")
    if nested and not params.get("method"):
        return parse_order_params(nested)
    return params, ""
def parse_biz_content(params):
    raw=params.get("biz_content") or params.get("bizContent")
    if isinstance(raw,dict):
        return raw, ""
    if not raw:
        return {}, "missing biz_content"
    try:
        return json.loads(raw), ""
    except Exception as e:
        return {}, "invalid biz_content: %s"%e
def has_withholding_pay_request(mock_state):
    requests=mock_state.get("pay_requests",{}) if isinstance(mock_state,dict) else {}
    if not isinstance(requests,dict):
        return False
    for req in requests.values():
        if isinstance(req,dict) and first_value(req,"product_code","productCode")=="GENERAL_WITHHOLDING":
            return True
    return False
def mock_has_sign_request(mock, external=None):
    try:
        requests=state(mock).get("sign_requests",{})
    except Exception:
        return False
    if external:
        return external in requests
    return bool(requests)
def ensure_app_pay_observed(mock, sign_body):
    external=external_agreement_no(sign_body)
    out_no=first_value(sign_body,"outTradeNo","out_trade_no","signOutTradeNo","sign_out_trade_no")
    if mock_has_sign_request(mock,external):
        return {"ok":True,"source":"server_gateway","external_agreement_no":external}
    errors=[]
    for order in iter_order_strings(sign_body):
        params,err=parse_order_params(order)
        if err:
            errors.append(err); continue
        if params.get("method")!="alipay.trade.app.pay":
            errors.append("method=%s"%params.get("method")); continue
        biz,err=parse_biz_content(params)
        if err:
            errors.append(err); continue
        agreement=biz.get("agreement_sign_params") if isinstance(biz.get("agreement_sign_params"),dict) else {}
        parsed_external=first_value(agreement,"external_agreement_no","externalAgreementNo")
        parsed_out=first_value(biz,"out_trade_no","outTradeNo")
        sign_notify=first_value(agreement,"sign_notify_url","signNotifyUrl")
        if not parsed_external or not parsed_out or not sign_notify:
            errors.append("missing out_trade_no/external_agreement_no/sign_notify_url"); continue
        if external and parsed_external!=external:
            errors.append("external mismatch %s != %s"%(parsed_external,external)); continue
        if out_no and parsed_out!=out_no:
            errors.append("out_trade_no mismatch %s != %s"%(parsed_out,out_no)); continue
        st,res=post_form_json(mock+"/gateway.do",params)
        if st==200 and mock_has_sign_request(mock,parsed_external):
            return {"ok":True,"source":"client_orderstr","external_agreement_no":parsed_external,"out_trade_no":parsed_out}
        errors.append("mock gateway status=%s body=%s"%(st,json.dumps(res,ensure_ascii=False)[:300]))
    return {"ok":False,"source":"none","external_agreement_no":external,"error":"; ".join(errors[-3:])}
def sign(app,mock,scenario="success"):
    st,res=post_json(app+"/api/alipay/sign-contract",{"teamId":1,"amount":"8.00","planName":"Base"})
    if st!=200: return {"error":"sign_contract_failed","status_code":st,"res":res,"status":{}}
    observed=ensure_app_pay_observed(mock,res)
    external=external_agreement_no(res) or observed.get("external_agreement_no")
    nst,nres=post_json(mock+"/__mock/notify/sign",{"external_agreement_no":external,"scenario":scenario})
    return {"sign":res,"notify_status":nst,"notify":nres,"order_observed":observed,"status":status_view(get_json(app+"/api/alipay/status?teamId=1"))}
def deduct(app,mock,scenario="success",amount="8.00",notify=True):
    st,res=post_json(app+"/api/alipay/withhold",{"teamId":1,"amount":amount})
    cur={}
    try: cur=status_view(get_json(app+"/api/alipay/status?teamId=1"))
    except Exception: pass
    resolved=resolved_out_trade_no(res,cur)
    accepted=st in (200,201,202)
    if not accepted or not resolved: return {"error":"withhold_failed","status_code":st,"res":res,"status":cur,"resolvedOutTradeNo":resolved}
    nst=nres=None
    if notify: nst,nres=post_json(mock+"/__mock/notify/pay",{"out_trade_no":resolved,"scenario":scenario})
    status_after=status_view(get_json(app+"/api/alipay/status?teamId=1"))
    resolved=resolved or resolved_out_trade_no(res,cur,status_after)
    return {"withhold":res,"before_notify":cur,"notify_status":nst,"notify":nres,"status":status_after,"resolvedOutTradeNo":resolved}
def set_scenario(mock,key,scenario): return post_json(mock+"/__mock/scenario",{"key":key,"scenario":scenario})
def state(mock): return get_json(mock+"/__mock/state")
def fail_fill(cs,mode):
    items_basic=[("sign_entry","签约入口可调用"),("method_app_pay","调用 alipay.trade.app.pay"),("sign_notify_accept","有效签约通知通过"),("agreement_persisted","协议号落库"),("method_trade_pay","调用 alipay.trade.pay"),("pay_notify_success","扣款成功终态")]
    items_safety=[("success_accept","有效签约和扣款通知通过"),("wrong_amount_reject","错误金额拒绝"),("wrong_agreement_reject","错误协议拒绝"),("wrong_user_reject","错误用户拒绝"),("unsigned_notify_reject","无签名拒绝"),("bad_signature_reject","坏签名拒绝"),("duplicate_notify_idempotent","重复通知幂等"),("pending_not_final","pending 不作为成功"),("gateway_error_fail_closed","网关错误 fail-closed"),("query_methods_available","未知扣款状态触发权威查询补偿"),("async_acceptance_not_final","扣款受理不等于成功"),("sync_success_not_final","同步成功码不作为最终成功"),("terminal_not_overwritten","终态不被旧通知覆盖"),("no_repeat_pay_before_confirm","未确认前不重复扣款"),("deduct_limit","扣款金额限制"),("request_idempotency_keys","请求号和业务单据绑定")]
    for rid,name in (items_basic if mode=="basic" else items_safety): add(cs,rid,name,"security" if mode=="safety" else "functionality",False,"应用未启动，无法执行该集成检查")
def main():
    ap=argparse.ArgumentParser(); ap.add_argument("--mode",required=True); ap.add_argument("--case-dir",required=True); ap.add_argument("--project-dir",required=True); ap.add_argument("--output-dir",required=True); args=ap.parse_args()
    case_dir=Path(args.case_dir); project=Path(args.project_dir); out=Path(args.output_dir); out.mkdir(parents=True,exist_ok=True)
    mock_port=4100 if args.mode=="basic" else 4101; app_port=os.environ.get("APP_PORT") or ("3121" if args.mode=="basic" else "3120"); app=os.environ.get("APP_BASE_URL") or "http://127.0.0.1:%s"%app_port; mock=os.environ.get("ALIPAY_MOCK_BASE_URL") or "http://127.0.0.1:%s"%mock_port
    cs=[]; mock_proc=None
    try:
        mock_proc=start_mock(case_dir,out,mock_port)
        if os.environ.get("PAYSKILLS_TOP_LEVEL_START")=="1":
            start_ok=bool(os.environ.get("APP_BASE_URL")) and wait_url(app+"/api/alipay/status?teamId=1",30)
            setup_rc=0 if start_ok else 1
        else:
            setup=subprocess.run([sys.executable,str(case_dir/"tests/start_project.py"),str(project),str(out),app_port,mock+"/gateway.do"],universal_newlines=True,stdout=open(str(out/"start_project.log"),"w"),stderr=subprocess.STDOUT,timeout=420)
            setup_rc=setup.returncode
            start_ok=(out/".start_ok").exists() and (out/".start_ok").read_text().strip()=="1"
        add(cs,"dep_build","项目可构建并启动","functionality",setup_rc==0 and start_ok,"build/start returncode=%s start_ok=%s app=%s"%(setup_rc,start_ok,app),["start_project.log","app_setup.log","app_server.log"])
        if setup_rc!=0 or not start_ok:
            fail_fill(cs,args.mode); (out/"integration_results.json").write_text(json.dumps(cs,ensure_ascii=False,indent=2),encoding="utf-8"); return
        if args.mode=="basic":
            reset(mock,project); seed_ok, seed_status=require_seed_data(app)
            hp=sign(app,mock); st=hp.get("status",{})
            sign_body=hp.get("sign",{})
            sign_entry_ok=not hp.get("error") and bool(sign_body.get("externalAgreementNo") or sign_body.get("external_agreement_no") or sign_body.get("agreementId") or sign_body.get("gatewayResponse"))
            add(cs,"sign_entry","签约入口可调用","functionality",sign_entry_ok,"seed=%s sign result=%s notify_status=%s"%(json.dumps(seed_status,ensure_ascii=False)[:300],json.dumps(sign_body,ensure_ascii=False)[:500],hp.get("notify_status")),["/api/alipay/sign-contract"])
            ms=state(mock); add(cs,"method_app_pay","使用 alipay.trade.app.pay 发起签约","functionality",len(ms.get("sign_requests",{}))>=1,"sign_requests=%s order_observed=%s"%(list(ms.get("sign_requests",{}).keys())[:3],hp.get("order_observed")),["mock state"])
            add(cs,"sign_notify_accept","有效签约通知推进签约状态","functionality",st.get("subscriptionStatus")=="active" and bool(st.get("alipayAgreementNo")),"status=%s"%json.dumps(st,ensure_ascii=False),["status API"])
            add(cs,"agreement_persisted","协议号和 external_agreement_no 可观察落库","functionality",bool(st.get("alipayAgreementNo")) and bool(st.get("alipayExternalAgreementNo")),"agreement=%s external=%s"%(st.get("alipayAgreementNo"),st.get("alipayExternalAgreementNo")),["status API"])
            hd=deduct(app,mock); ds=hd.get("status",{}); ms=state(mock)
            response_product=hd.get("withhold",{}).get("result",{}).get("product_code")
            pay_product_ok=has_withholding_pay_request(ms) or response_product=="GENERAL_WITHHOLDING"
            add(cs,"method_trade_pay","使用 alipay.trade.pay 发起周期扣款","functionality",len(ms.get("pay_requests",{}))>=1 and pay_product_ok,"pay_requests=%s product_ok=%s"%(list(ms.get("pay_requests",{}).keys())[:3],pay_product_ok),["mock state"])
            add(cs,"pay_notify_success","有效支付通知形成 active + TRADE_SUCCESS","functionality",ds.get("subscriptionStatus")=="active" and ds.get("alipayPaymentStatus")=="TRADE_SUCCESS","status=%s"%json.dumps(ds,ensure_ascii=False),["status API"])
        else:
            reset(mock,project); hp=sign(app,mock); hd=deduct(app,mock); ds=hd.get("status",{}); hs=hp.get("status",{}); happy_out=resolved_out_trade_no(hd.get("withhold",{}),ds,hd)
            add(cs,"success_accept","有效签约和扣款通知通过","functionality",bool(hs.get("alipayAgreementNo") or hs.get("alipayExternalAgreementNo")) and payment_success(ds,happy_out,verified_event=True),"sign=%s final=%s"%(json.dumps(hs,ensure_ascii=False)[:500],json.dumps(ds,ensure_ascii=False)[:800]),["happy path"])
            reset(mock,project); sign(app,mock); wa=deduct(app,mock,"wrong_amount"); add(cs,"wrong_amount_reject","错误金额通知不得成功","security",invalid_notify_rejected(wa) and str(payment_amount(wa["status"]) or "")!="0.01","before=%s after=%s notify=%s"%(json.dumps(wa.get("before_notify",{}),ensure_ascii=False)[:500],json.dumps(wa["status"],ensure_ascii=False)[:500],json.dumps(wa.get("notify"),ensure_ascii=False)[:300]),["wrong_amount"])
            reset(mock,project); sign(app,mock); wg=deduct(app,mock,"wrong_agreement"); add(cs,"wrong_agreement_reject","错误协议号通知不得成功","security",invalid_notify_rejected(wg),"before=%s after=%s notify=%s"%(json.dumps(wg.get("before_notify",{}),ensure_ascii=False)[:500],json.dumps(wg["status"],ensure_ascii=False)[:500],json.dumps(wg.get("notify"),ensure_ascii=False)[:300]),["wrong_agreement"])
            reset(mock,project); sign(app,mock); wu=deduct(app,mock,"wrong_user"); add(cs,"wrong_user_reject","错误用户通知不得成功","security",invalid_notify_rejected(wu),"before=%s after=%s notify=%s"%(json.dumps(wu.get("before_notify",{}),ensure_ascii=False)[:500],json.dumps(wu["status"],ensure_ascii=False)[:500],json.dumps(wu.get("notify"),ensure_ascii=False)[:300]),["wrong_user"])
            reset(mock,project); us=sign(app,mock,"unsigned"); add(cs,"unsigned_notify_reject","无签名签约通知不得激活","security",us["status"].get("subscriptionStatus")!="active","status=%s"%json.dumps(us["status"],ensure_ascii=False),["unsigned sign"])
            reset(mock,project); bs=sign(app,mock,"bad_signature"); add(cs,"bad_signature_reject","错误签名签约通知不得激活","security",bs["status"].get("subscriptionStatus")!="active","status=%s"%json.dumps(bs["status"],ensure_ascii=False),["bad signature"])
            reset(mock,project); sign(app,mock); first=deduct(app,mock); before=first["status"]; first_out=resolved_out_trade_no(first.get("withhold",{}),before,first); post_json(mock+"/__mock/notify/pay",{"out_trade_no":first_out,"scenario":"success","notify_id":"duplicate-notify"}); after=status_view(get_json(app+"/api/alipay/status?teamId=1")); add(cs,"duplicate_notify_idempotent","重复扣款通知幂等","correctness",bool(first_out and before.get("alipayLastOutTradeNo")==first_out and after.get("alipayLastOutTradeNo")==first_out and payment_success(after,first_out,verified_event=True)),"first_out=%s before=%s after=%s"%(first_out,json.dumps(before,ensure_ascii=False)[:500],json.dumps(after,ensure_ascii=False)[:500]),["duplicate notify"])
            reset(mock,project); sign(app,mock); set_scenario(mock,"deduct","pending"); pend=deduct(app,mock,notify=False); pend_out=resolved_out_trade_no(pend.get("withhold",{}),pend.get("status",{}),pend); add(cs,"pending_not_final","pending/10003 不得作为最终成功","security",payment_not_success(pend["status"],pend_out),"status=%s"%json.dumps(pend["status"],ensure_ascii=False),["pending"])
            reset(mock,project); sign(app,mock); set_scenario(mock,"deduct","gateway_error"); ge=deduct(app,mock,notify=False); ge_out=resolved_out_trade_no(ge.get("withhold",{}),ge.get("status",{}),ge); add(cs,"gateway_error_fail_closed","网关错误 fail-closed","security",payment_not_success(ge["status"],ge_out),"status=%s"%json.dumps(ge["status"],ensure_ascii=False),["gateway_error"])
            reset(mock,project); sign(app,mock); set_scenario(mock,"deduct","pending"); pending=deduct(app,mock,notify=False); pending_out=resolved_out_trade_no(pending.get("withhold",{}),pending.get("res",{}),pending.get("status",{}),pending); second=deduct(app,mock,notify=False); ms=state(mock); trade_queries=ms.get("trade_query_requests",{}); agreement_queries=ms.get("agreement_query_requests",{}); add(cs,"query_methods_available","未知扣款状态触发权威查询补偿","functionality",bool(pending_out and pending_out in trade_queries),"pending_out=%s trade_queries=%s agreement_queries=%s second=%s"%(pending_out,list(trade_queries.keys())[:5],list(agreement_queries.keys())[:5],json.dumps(second,ensure_ascii=False)[:500]),["mock state","pending compensation"])
            add(cs,"async_acceptance_not_final","扣款接口受理不等于最终扣款成功","security",payment_not_success(pend["status"],pend_out),"pending status=%s"%json.dumps(pend["status"],ensure_ascii=False),["10003"])
            reset(mock,project); sign(app,mock); set_scenario(mock,"deduct","sync_success_pending"); sync=deduct(app,mock,notify=False); sync_out=resolved_out_trade_no(sync.get("withhold",{}),sync.get("status",{}),sync); add(cs,"sync_success_not_final","同步 code=10000 不得作为最终扣款成功","security",payment_not_success(sync["status"],sync_out),"sync_out=%s status=%s"%(sync_out,json.dumps(sync["status"],ensure_ascii=False)[:700]),["code10000_without_final_confirmation"])
            reset(mock,project); sign(app,mock); ok=deduct(app,mock); ok_out=resolved_out_trade_no(ok.get("withhold",{}),ok.get("status",{}),ok); old=ok["status"].get("alipayLastOutTradeNo"); 
            if ok_out: post_json(mock+"/__mock/notify/pay",{"out_trade_no":ok_out,"scenario":"pending","notify_id":"old-pending"})
            term=status_view(get_json(app+"/api/alipay/status?teamId=1")); add(cs,"terminal_not_overwritten","终态不被旧通知覆盖","security",bool(ok_out and payment_success(term,ok_out,verified_event=True) and term.get("alipayLastOutTradeNo")==old),"ok_out=%s terminal=%s"%(ok_out,json.dumps(term,ensure_ascii=False)[:900]),["old notify"])
            reset(mock,project); sign(app,mock); set_scenario(mock,"deduct","pending"); fp=deduct(app,mock,notify=False); second=deduct(app,mock,notify=False); add(cs,"no_repeat_pay_before_confirm","上一笔未确认前不得重复扣款","security",second.get("status_code") in (400,409) or second.get("error")=="withhold_failed","first=%s second=%s"%(json.dumps(fp.get("status",{}),ensure_ascii=False),json.dumps(second,ensure_ascii=False)[:500]),["double pending"])
            reset(mock,project); sign(app,mock); over=deduct(app,mock,"success",amount="999.00"); add(cs,"deduct_limit","扣款金额不得超过协议约定","security",over.get("status_code") in (400,409) or payment_not_success(over["status"]),"over=%s"%json.dumps(over.get("status",over),ensure_ascii=False)[:700],["over limit"])
            reset(mock,project); sign(app,mock); a=deduct(app,mock,notify=False); mid_state=state(mock); b=deduct(app,mock,notify=False); end_state=state(mock); a_out=resolved_out_trade_no(a.get("withhold",{}),a.get("status",{}),a); b_out=resolved_out_trade_no(b.get("withhold",{}),b.get("status",{}),b); mid_pay=mid_state.get("pay_requests",{}) if isinstance(mid_state,dict) else {}; end_pay=end_state.get("pay_requests",{}) if isinstance(end_state,dict) else {}; rejected=b.get("status_code") in (400,409) or b.get("error")=="withhold_failed"; same_idempotent=bool(a_out and b_out==a_out and len(end_pay)==len(mid_pay)); no_new_order=not b_out or b_out==a_out; add(cs,"request_idempotency_keys","扣款请求号与业务单据绑定且避免同周期混用","correctness",bool(a_out and no_new_order and (rejected or same_idempotent)),"a=%s b=%s b_status=%s pay_count_before=%s pay_count_after=%s"%(a_out,b_out,b.get("status_code"),len(mid_pay),len(end_pay)),["out_trade_no"])
    finally:
        if mock_proc:
            try: mock_proc.terminate()
            except Exception: pass
    (out/"integration_results.json").write_text(json.dumps(cs,ensure_ascii=False,indent=2),encoding="utf-8")
if __name__=="__main__": main()
