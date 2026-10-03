"""Deployment boundaries, admission races, and per-account usage visibility."""
from concurrent.futures import ThreadPoolExecutor
from dataclasses import replace
from threading import Event
from types import SimpleNamespace

import httpx
import pytest
from fastapi.testclient import TestClient

from researchpilot.app import create_app
from researchpilot.config import Settings
from researchpilot.db import now
from researchpilot.ops import preflight, check_url
from test_accounts import encoded, secured
from test_imports import submit, wait_import


@pytest.mark.parametrize('origin', ['http://research.example.com', 'https://user:pass@example.com',
                                   'https://example.com/path', 'https://*.example.com',
                                   'https://example.com?key=secret', 'https://example.com:99999'])
def test_public_origin_rejects_unsafe_config(tmp_path, origin):
    with pytest.raises(ValueError):
        Settings(data_dir=tmp_path, auth_mode='accounts', cookie_secure=True, public_origin=origin)


def test_public_origin_requires_accounts_and_secure_cookies(tmp_path):
    for options in [{}, {'auth_mode':'accounts'}]:
        with pytest.raises(ValueError):
            Settings(data_dir=tmp_path, public_origin='https://research.example.com', **options)


def test_https_host_and_scheme_enforced_without_trusting_client_forwarded_headers(tmp_path):
    app = create_app(Settings(data_dir=tmp_path, auth_mode='accounts', cookie_secure=True,
                              public_origin='https://research.example.com'))
    with TestClient(app, base_url='https://research.example.com') as client:
        assert client.get('/api/auth/status').status_code == 200
        assert client.get('/api/ready').status_code == 503
        app.state.db.execute('INSERT INTO users VALUES (?,?,?,?,1,?)', ('admin','admin','unused','admin',now()))
        assert client.get('/api/ready').json() == {'status':'ready'}
        assert client.get('https://evil.example/').status_code == 400
        assert client.get('http://research.example.com/', headers={'X-Forwarded-Proto':'https'}).status_code == 400
        assert client.get('/api/resources').status_code == 401
        assert preflight(app.state.settings)['ok']


def test_local_preflight_does_not_claim_deployable_or_create_database(tmp_path):
    assert not preflight(Settings(data_dir=tmp_path))['ok']
    assert not (tmp_path/'researchpilot.sqlite3').exists()


def test_project_limit_is_atomic_under_concurrent_requests(client, app, monkeypatch):
    monkeypatch.setattr(app.state.quotas, 'settings', replace(app.state.settings, max_projects=1))
    with ThreadPoolExecutor(max_workers=2) as workers:
        statuses = list(workers.map(lambda n:client.post('/api/workspaces',json={'name':str(n)}).status_code, range(2)))
    assert sorted(statuses) == [201,429]
    assert len(client.get('/api/workspaces').json()) == 1


def test_source_limit_dedup_and_delete_release(client, app, workspace, monkeypatch):
    monkeypatch.setattr(app.state.quotas, 'settings', replace(app.state.settings, max_sources=1))
    monkeypatch.setattr(app.state.library, 'settings', app.state.quotas.settings)
    url = f'/api/workspaces/{workspace}/upload'
    first = client.post(url, files={'file':('one.txt',b'first evidence')})
    assert first.status_code == 201
    assert client.post(url, files={'file':('one.txt',b'first evidence')}).json()['duplicate']
    assert client.post(url, files={'file':('two.txt',b'second evidence')}).status_code == 429
    assert client.delete('/api/sources/'+first.json()['id']).status_code == 204
    assert client.post(url, files={'file':('two.txt',b'second evidence')}).status_code == 201


def test_import_reservations_and_cancel_do_not_release_running_work_early(client, app, workspace, monkeypatch):
    monkeypatch.setattr(app.state.quotas, 'settings', replace(app.state.settings, max_storage_mb=1))
    monkeypatch.setattr(app.state.imports.pool, 'submit', lambda *args:None)
    payload = b'a' * 600_000
    identifier = submit(client, workspace, payload, 'one.txt')
    usage = client.get('/api/resources').json()
    assert usage['reserved_bytes'] == len(payload) and usage['active_imports'] == 1
    url = f'/api/workspaces/{workspace}/imports'
    assert client.post(url,files={'file':('two.txt',payload)}).json()['code'] == 'storage_quota'
    client.post(f'/api/imports/{identifier}/cancel')
    assert client.get('/api/resources').json()['reserved_bytes'] == len(payload)
    assert client.get('/api/maintenance/backup').status_code == 409
    app.state.imports.run(identifier)
    assert client.get('/api/resources').json()['reserved_bytes'] == 0
    assert not app.state.imports.path(identifier).exists()
    accepted = submit(client, workspace, b'valid evidence', 'small.txt')
    app.state.imports.run(accepted)
    assert client.get('/api/resources').json()['storage_bytes'] == len(b'valid evidence')
    assert client.get('/api/resources').json()['reserved_bytes'] == 0


def test_per_account_concurrency_and_rolling_daily_tasks(client, app, workspace, monkeypatch):
    entered, release = Event(), Event()
    monkeypatch.setattr(app.state.quotas, 'settings', replace(app.state.settings, max_active_tasks=1, max_tasks_daily=1))
    def slow_run(self, identifier):
        entered.set()
        assert release.wait(10)
    monkeypatch.setattr('researchpilot.app.Agent.run', slow_run)
    url = f'/api/workspaces/{workspace}/tasks'
    try:
        first = client.post(url,json={'prompt':'test'})
        assert first.status_code == 202 and entered.wait(5)
        identifier = first.json()['id']
        client.post(f'/api/tasks/{identifier}/cancel')
        assert client.post(url,json={'prompt':'next'}).json()['code'] == 'active_tasks'
    finally:
        release.set()
    # Use the shared lock to inspect the lease independently of the cancelled DB status.
    import time
    for _ in range(100):
        if client.get('/api/resources').json()['active_tasks'] == 0: break
        time.sleep(.01)
    assert client.post(url,json={'prompt':'next'}).json()['code'] == 'daily_tasks'
    app.state.db.execute("UPDATE tasks SET created_at='2000-01-01T00:00:00+00:00'")
    assert client.post(url,json={'prompt':'next'}).status_code == 202


def test_usage_is_private_and_runtime_is_admin_only(secured):
    app, owner, member, anon = secured
    owner.post('/api/workspaces',json={'name':'admin private project'})
    member.post('/api/workspaces',json={'name':'member project'})
    usage = member.get('/api/resources')
    assert [p['name'] for p in usage.json()['projects']] == ['member project']
    assert 'admin private project' not in usage.text
    assert anon.get('/api/resources').status_code == 401
    assert member.get('/api/maintenance/runtime').status_code == 403
    response = owner.get('/api/maintenance/runtime')
    assert response.status_code == 200 and response.json()['ready']
    assert response.headers['cache-control'] == 'no-store'
    assert len(response.headers['x-request-id']) == 32


def test_legacy_and_repository_routes_share_import_limit(client, app, workspace, monkeypatch):
    monkeypatch.setattr(app.state.quotas, 'settings', replace(app.state.settings, max_active_imports=1))
    root = f'/api/workspaces/{workspace}'
    with app.state.quotas.synchronous_import(workspace):
        assert client.post(root+'/upload',files={'file':('test.txt',b'evidence')}).status_code == 429
        assert client.post(root+'/repository',json={'url':'https://github.com/example/project'}).status_code == 429
        assert client.post(root+'/imports',files={'file':('test.txt',b'evidence')}).status_code == 429
    assert client.get('/api/resources').json()['active_imports'] == 0
    assert client.post(root+'/upload',files={'file':('test.txt',b'evidence')}).status_code == 201


def test_low_disk_rejects_new_work_and_readiness_but_keeps_reads(client, app, workspace, monkeypatch):
    monkeypatch.setattr('shutil.disk_usage',lambda path:SimpleNamespace(free=0))
    assert client.get('/api/ready').status_code == 503
    assert client.get('/api/workspaces').status_code == 200
    response = client.post('/api/workspaces',json={'name':'no room'})
    assert response.status_code == 507 and response.json()['code'] == 'disk_low'
    assert client.post(f'/api/workspaces/{workspace}/imports',files={'file':('file.txt',b'text')}).status_code == 507
    assert not app.state.imports.list(workspace)


@pytest.mark.parametrize('headers', [{}, {'Content-Length':'1'}])
def test_streaming_json_limit_does_not_trust_content_length(client, app, headers):
    response = client.post('/api/workspaces', content=iter([b'{"name":"',b'x' * (1024**2),b'"}']),
                           headers={'Content-Type':'application/json',**headers})
    assert response.status_code == 413 and response.json()['code'] == 'request_too_large'
    assert not client.get('/api/workspaces').json()
    assert app.state.runtime.active == 0


def test_streaming_multipart_limit_before_import_commit(tmp_path):
    app = create_app(Settings(data_dir=tmp_path, max_upload_mb=1))
    with TestClient(app) as client:
        workspace = client.post('/api/workspaces',json={'name':'multipart'}).json()['id']
        body = [b'--boundary\r\nContent-Disposition: form-data; name="file"; filename="large.txt"\r\n\r\n',
                b'x' * 1_150_000, b'\r\n--boundary--\r\n']
        response = client.post(f'/api/workspaces/{workspace}/imports',content=iter(body),
                               headers={'Content-Type':'multipart/form-data; boundary=boundary'})
        assert response.status_code == 413
        assert not app.state.imports.list(workspace)
        assert not list(app.state.imports.directory.iterdir())


def test_runtime_overload_recovers_and_keeps_probe_available(client, app):
    app.state.runtime.active = 32
    try:
        response = client.get('/api/workspaces')
        assert response.status_code == 503 and response.headers['retry-after'] == '5'
        assert client.get('/api/ready').status_code == 200
    finally:
        app.state.runtime.active = 0
    assert client.get('/api/workspaces').status_code == 200


def test_deployment_probe_rejects_redirects_and_plain_remote_http(monkeypatch):
    with pytest.raises(ValueError): check_url('http://example.com')
    factory = httpx.Client
    for status, payload, expected in [(200,{'status':'ready'},True),(503,{'status':'not_ready'},False),(302,{},False)]:
        transport = httpx.MockTransport(lambda request:httpx.Response(status,json=payload))
        monkeypatch.setattr(httpx,'Client',lambda **kw:factory(transport=transport,**kw))
        assert check_url('https://research.example.com')['ok'] is expected
