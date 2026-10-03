"""Deployment preflight and an unauthenticated, minimal readiness probe."""
import argparse
from contextlib import closing
import json
from pathlib import Path
import sqlite3
import sys
import tempfile
from urllib.parse import urlsplit

from .config import Settings
from .maintenance import doctor


def preflight(settings):
    report = doctor(settings.data_dir, settings.mode, settings.auth_mode)
    checks = list(report['checks'])
    def add(name, valid, message):
        checks.append({'name':name,'status':'ok' if valid else 'error','message':message})
    add('HTTPS 站点', bool(settings.public_origin), settings.public_origin or '请配置 RP_PUBLIC_ORIGIN。')
    add('登录与 Cookie',settings.auth_mode=='accounts' and settings.cookie_secure,'需要账号模式和 Secure Cookie。')
    configured = False
    path = settings.data_dir/'researchpilot.sqlite3'
    if path.is_file():
        try:
            with closing(sqlite3.connect(path.resolve().as_uri()+'?mode=ro',uri=True)) as con:
                configured = bool(con.execute("SELECT 1 FROM users WHERE role='admin' AND active=1").fetchone())
        except sqlite3.Error:
            pass
    add('管理员',configured,'部署前必须在目标数据目录创建管理员。')
    writable = False
    if settings.data_dir.is_dir():
        try:
            with tempfile.TemporaryFile(dir=settings.data_dir) as probe:
                probe.write(b'preflight');probe.flush()
            writable=True
        except OSError:
            pass
    add('持久目录可写',writable,'数据目录必须可写，并在升级和重启后保留。')
    return {'ok':all(c['status']!='error' for c in checks),'checks':checks,
            'unverified':['DNS 与证书','可信反向代理与防火墙','外部备份恢复','持续负载与隔离解析']}


def check_url(url):
    import httpx
    parsed = urlsplit(url)
    if (parsed.scheme not in {'http','https'} or not parsed.hostname or parsed.username or parsed.password
            or parsed.query or parsed.fragment or parsed.path not in {'','/'}):
        raise ValueError('请输入不带路径、凭据或查询参数的站点地址。')
    if parsed.scheme != 'https' and parsed.hostname not in {'127.0.0.1','localhost','::1'}:
        raise ValueError('远程站点只允许 HTTPS；HTTP 仅用于本机探针。')
    with httpx.Client(timeout=10,follow_redirects=False) as client:
        response=client.get(url.rstrip('/')+'/api/ready')
        ok=response.status_code==200 and response.json()=={'status':'ready'}
    return {'ok':ok,'status_code':response.status_code}


def main(argv=None):
    parser=argparse.ArgumentParser(description='ResearchPilot 部署检查，不修改配置或发布站点。')
    sub=parser.add_subparsers(dest='command',required=True)
    sub.add_parser('preflight')
    check=sub.add_parser('check');check.add_argument('--url',default='http://127.0.0.1:8765')
    args=parser.parse_args(argv)
    for stream in (sys.stdout,sys.stderr):
        if hasattr(stream,'reconfigure') and not stream.isatty():stream.reconfigure(encoding='utf-8')
    try:
        report=preflight(Settings.from_env()) if args.command=='preflight' else check_url(args.url)
    except Exception:
        report={'ok':False,'error':'检查失败，请核对配置、连接或 HTTPS 证书；没有修改站点。'}
    print(json.dumps(report,ensure_ascii=False,indent=2))
    return 0 if report['ok'] else 1


if __name__=='__main__':
    raise SystemExit(main())
