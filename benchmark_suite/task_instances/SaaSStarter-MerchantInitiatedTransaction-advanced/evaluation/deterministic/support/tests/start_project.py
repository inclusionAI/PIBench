#!/usr/bin/env python3
import os, subprocess, sys, time, urllib.request
from pathlib import Path

def run(cmd, cwd=None, env=None, check=True, stdout=None):
    return subprocess.run(cmd, cwd=cwd, env=env, check=check, universal_newlines=True, stdout=stdout or subprocess.PIPE, stderr=subprocess.STDOUT)

def wait_url(url, timeout=90):
    end=time.time()+timeout
    last=''
    while time.time()<end:
        try:
            with urllib.request.urlopen(url, timeout=2) as r:
                if r.status < 500:
                    return True
        except Exception as e:
            last=str(e)
        time.sleep(1)
    raise RuntimeError(f'{url} not ready: {last}')

def ensure_postgres():
    if subprocess.run(["bash", "-lc", "command -v pg_ctlcluster >/dev/null 2>&1"], check=False).returncode == 0:
        subprocess.run(["bash", "-lc", "pg_ctlcluster 16 main start 2>/dev/null || pg_ctlcluster 15 main start 2>/dev/null || service postgresql start"], check=False)
        subprocess.run(["bash", "-lc", "id postgres >/dev/null 2>&1 && su postgres -c \"psql -c \\\"ALTER USER postgres PASSWORD 'postgres';\\\"\""], check=False)
        return
    if subprocess.run(["bash", "-lc", "command -v docker >/dev/null 2>&1"], check=False).returncode == 0:
        subprocess.run(["docker", "rm", "-f", "payskills_sub_postgres"], check=False, stdout=subprocess.PIPE, stderr=subprocess.STDOUT)
        subprocess.run(["docker", "run", "-d", "--name", "payskills_sub_postgres", "-e", "POSTGRES_DB=postgres", "-e", "POSTGRES_USER=postgres", "-e", "POSTGRES_PASSWORD=postgres", "-p", "127.0.0.1:5432:5432", "postgres:16.4-alpine"], check=True)
        for _ in range(60):
            if subprocess.run(["docker", "exec", "payskills_sub_postgres", "pg_isready", "-U", "postgres"], check=False, stdout=subprocess.PIPE, stderr=subprocess.STDOUT).returncode == 0:
                return
            time.sleep(1)
    raise RuntimeError("Postgres is unavailable: install postgresql in Dockerfile or provide docker on host")

def main():
    project=Path(sys.argv[1]).resolve(); out=Path(sys.argv[2]).resolve(); port=sys.argv[3]; mock_url=sys.argv[4]
    out.mkdir(parents=True, exist_ok=True)
    ensure_postgres()
    safe_port = ''.join(ch if ch.isalnum() else '_' for ch in str(port))[:40]
    db_name = f"payskills_saas_{safe_port}"
    admin_url = 'postgres://postgres:postgres@127.0.0.1:5432/postgres'
    postgres_url = f'postgres://postgres:postgres@127.0.0.1:5432/{db_name}'
    reset_sql = (
        f"PGPASSWORD=postgres psql {admin_url!r} -v ON_ERROR_STOP=1 "
        f"-c \"SELECT pg_terminate_backend(pid) FROM pg_stat_activity WHERE datname = '{db_name}' AND pid <> pg_backend_pid();\" "
        f"-c 'DROP DATABASE IF EXISTS \"{db_name}\";' "
        f"-c 'CREATE DATABASE \"{db_name}\";'"
    )
    subprocess.run(['bash', '-lc', reset_sql], check=True)
    case_dir=Path(__file__).resolve().parents[1]
    public_key=(case_dir/"tests/test_keys/mock_alipay_public_key.pem").read_text()
    private_key=(case_dir/"tests/test_keys/mock_alipay_private_key.pem").read_text()
    env=os.environ.copy()
    env.update({
      'POSTGRES_URL':postgres_url,
      'STRIPE_SECRET_KEY':'sk_test_case_placeholder',
      'STRIPE_WEBHOOK_SECRET':'whsec_case_placeholder',
      'BASE_URL':f'http://127.0.0.1:{port}',
      'AUTH_SECRET':'case-auth-secret-at-least-32-bytes-long',
      'SKIP_STRIPE_SEED':'true','ALIPAY_CASE_LOCAL_PLANS':'true',
      'ALIPAY_MOCK_MODE':'true','ALIPAY_ALLOW_UNSIGNED_NOTIFY':'false',
      'ALIPAY_GATEWAY':mock_url,'ALIPAY_GATEWAY_URL':mock_url,'ALIPAY_APP_ID':'case_mock_app','ALIPAY_PID':'case_mock_pid','ALIPAY_SELLER_ID':'case_mock_pid',
      'ALIPAY_SIGN_SCENE':'INDUSTRY|DIGITAL_MEDIA',
      'ALIPAY_PUBLIC_KEY': public_key,
      'ALIPAY_PRIVATE_KEY': private_key,
      'ALIPAY_APP_PRIVATE_KEY': private_key,
      'ALIPAY_APP_PRIVATE_PKCS_KEY': private_key,
      'ALIPAY_PUBLIC_KEY_PATH': str(case_dir/"tests/test_keys/mock_alipay_public_key.pem"),
      'ALIPAY_PRIVATE_KEY_PATH': str(case_dir/"tests/test_keys/mock_alipay_private_key.pem"),
    })

    ws = project / 'pnpm-workspace.yaml'
    if ws.exists() and 'packages:' not in ws.read_text(errors='replace'):
        ws.unlink()
    env_file_keys=['POSTGRES_URL','STRIPE_SECRET_KEY','STRIPE_WEBHOOK_SECRET','BASE_URL','AUTH_SECRET','SKIP_STRIPE_SEED','ALIPAY_CASE_LOCAL_PLANS','ALIPAY_MOCK_MODE','ALIPAY_ALLOW_UNSIGNED_NOTIFY','ALIPAY_GATEWAY','ALIPAY_GATEWAY_URL','ALIPAY_APP_ID','ALIPAY_PID','ALIPAY_SELLER_ID','ALIPAY_SIGN_SCENE','ALIPAY_PUBLIC_KEY','ALIPAY_PRIVATE_KEY','ALIPAY_APP_PRIVATE_KEY','ALIPAY_APP_PRIVATE_PKCS_KEY','ALIPAY_PUBLIC_KEY_PATH','ALIPAY_PRIVATE_KEY_PATH']
    def env_line(key):
        return f"{key}={str(env[key]).replace(chr(10), chr(92) + 'n')}"
    (project/'.env').write_text('\n'.join(env_line(k) for k in env_file_keys if k in env)+'\n')
    log=open(out/'app_setup.log','w')
    pnpm_cmd=['pnpm']
    try:
        ver=subprocess.run(['pnpm','--version'],text=True,stdout=subprocess.PIPE,stderr=subprocess.STDOUT).stdout.strip()
        if ver and int(ver.split('.')[0]) > 9:
            pnpm_cmd=['npx','-y','pnpm@9.15.9']
    except Exception:
        pnpm_cmd=['npx','-y','pnpm@9.15.9']
    for cmd in [pnpm_cmd+['install','--frozen-lockfile'], pnpm_cmd+['db:migrate'], pnpm_cmd+['db:seed'], pnpm_cmd+['build']]:
        try:
            p=subprocess.run(cmd,cwd=project,env=env,universal_newlines=True,stdout=log,stderr=subprocess.STDOUT,timeout=180)
            if p.returncode:
                (out/'.build_ok').write_text('0')
                raise SystemExit(p.returncode)
        except Exception:
            (out/'.build_ok').write_text('0')
            raise
    (out/'.build_ok').write_text('1')
    subprocess.run(['bash','-lc',f"fuser -k {port}/tcp 2>/dev/null || true"], check=False)
    app_log=open(out/'app_server.log','w')
    proc=subprocess.Popen((pnpm_cmd+['start']),cwd=project,env={**env,'PORT':port,'HOSTNAME':'127.0.0.1'},stdout=app_log,stderr=subprocess.STDOUT,universal_newlines=True)
    (out/'app.pid').write_text(str(proc.pid))
    try:
        wait_url(f'http://127.0.0.1:{port}/api/alipay/status?teamId=1')
        (out/'.start_ok').write_text('1')
    except Exception as e:
        (out/'.start_ok').write_text('0')
        raise
if __name__=='__main__': main()
