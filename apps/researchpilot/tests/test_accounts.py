"""Real password/session checks and cross-account access regression tests."""
from contextlib import closing
from dataclasses import replace
import sqlite3
import time

import pytest
from fastapi.testclient import TestClient

from researchpilot.accounts import Accounts, COOKIE, csrf, digest, password_hash, check_password
from researchpilot.app import create_app
from researchpilot.config import Settings
from researchpilot.db import Database, now
from researchpilot.maintenance import create_backup, restore_backup, verify_backup, doctor, AUTH_TABLES
from test_api import make_pdf, wait_task
from test_imports import submit, wait_import

PASSWORD = 'test-only long passphrase 2026'
NEW_PASSWORD = 'another test-only passphrase 2026'


def login(client, name='admin', password=PASSWORD):
    result = client.post('/api/auth/login', json={'username':name,'password':password})
    assert result.status_code == 200, result.text
    client.headers['X-CSRF-Token'] = result.json()['csrf_token']
    return result


@pytest.fixture(scope='module')
def encoded():
    return password_hash(PASSWORD)


@pytest.fixture
def secured(tmp_path, encoded):
    settings = Settings(data_dir=tmp_path, auth_mode='accounts')
    app = create_app(settings)
    for name, role in [('admin','admin'),('member','member')]:
        app.state.db.execute('INSERT INTO users VALUES (?,?,?,?,1,?)',(name,name,encoded,role,now()))
    with TestClient(app) as owner, TestClient(app) as member, TestClient(app) as anon:
        login(owner)
        login(member,'member')
        yield app, owner, member, anon


def test_passwords_are_salted_and_checked_without_trimming(encoded):
    other = password_hash(PASSWORD)
    assert other != encoded and PASSWORD not in encoded
    assert check_password(PASSWORD, encoded)
    assert not check_password(PASSWORD+' ', encoded)
    assert not check_password(PASSWORD, None)
    with pytest.raises(ValueError): password_hash('too-short')


def test_claim_legacy_data_and_fail_closed_even_in_running_local_app(tmp_path):
    settings = Settings(data_dir=tmp_path)
    app = create_app(settings)
    with TestClient(app) as client:
        workspace = client.post('/api/workspaces',json={'name':'legacy'}).json()['id']
        app.state.accounts.create_admin('Owner',PASSWORD)
        assert client.get('/api/workspaces').status_code == 503
        assert client.get('/api/auth/status').json()['configuration_error']
        assert not doctor(tmp_path)['ok']
        assert doctor(tmp_path, auth_mode='accounts')['ok']
        with pytest.raises(ValueError): app.state.accounts.create_admin('second',PASSWORD)
    secured_app = create_app(replace(settings, auth_mode='accounts'))
    with TestClient(secured_app) as client:
        assert client.get('/api/workspaces').status_code == 401
        login(client,'owner')
        assert client.get('/api/workspaces').json()[0]['id'] == workspace


def test_no_web_admin_bootstrap_and_no_open_registration(tmp_path):
    app = create_app(Settings(data_dir=tmp_path, auth_mode='accounts'))
    with TestClient(app) as client:
        assert client.get('/api/auth/status').json()['setup_required']
        assert client.post('/api/auth/register',json={'username':'admin','password':PASSWORD,'invitation':'fake'}).status_code == 400
        assert client.get('/api/workspaces').status_code == 401
        assert app.state.db.all('SELECT * FROM users') == []


def test_login_cookie_rotation_expiry_and_logout(secured):
    app, owner, member, anon = secured
    old = owner.cookies[COOKIE]
    assert app.state.db.one('SELECT * FROM sessions WHERE token_hash=?',(digest(old),))
    assert not app.state.db.one('SELECT * FROM sessions WHERE token_hash=?',(old,))
    result = login(owner)
    cookie = result.headers['set-cookie'].lower()
    assert 'httponly' in cookie and 'samesite=strict' in cookie and 'max-age=43200' in cookie
    assert owner.cookies[COOKIE] != old
    assert anon.get('/api/workspaces',headers={'Cookie':f'{COOKIE}={old}'}).status_code == 401
    assert owner.post('/api/auth/logout').status_code == 204
    assert owner.get('/api/workspaces').status_code == 401
    login(owner)
    app.state.db.execute('UPDATE sessions SET expires_at=0 WHERE token_hash=?',(digest(owner.cookies[COOKIE]),))
    assert owner.get('/api/workspaces').status_code == 401
    assert set(anon.get('/api/health').json()) == {'status','version','auth_mode'}


def test_all_resource_families_enforce_ownership_before_read_or_write(secured):
    app, owner, member, anon = secured
    workspace = owner.post('/api/workspaces',json={'name':'private'}).json()['id']
    mine = member.post('/api/workspaces',json={'name':'member-private'}).json()['id']
    assert [r['id'] for r in owner.get('/api/workspaces').json()] == [workspace]
    assert [r['id'] for r in member.get('/api/workspaces').json()] == [mine]
    assert owner.get(f'/api/workspaces/{mine}/sources').status_code == 404  # Admins have no project bypass.
    imported = wait_import(owner, submit(owner, workspace, make_pdf('Residual model training uses reconstruction loss.')))
    source = imported['result']['id']
    task = wait_task(owner, owner.post(f'/api/workspaces/{workspace}/tasks',json={'prompt':'training loss'}).json()['id'])['id']
    note = owner.post(f'/api/workspaces/{workspace}/notes',json={'title':'Private note','body':'secret'}).json()['id']
    experiment = owner.post(f'/api/workspaces/{workspace}/experiments',json={'name':'Private experiment'}).json()['id']
    root = f'/api/workspaces/{workspace}'
    reads = [root+'/sources',root+'/imports',root+'/tasks',root+'/notes',root+'/notes/export',root+'/notes/'+note,
             root+'/experiments',root+'/experiments/'+experiment,root+'/experiments/'+experiment+'/export',
             f'/api/sources/{source}',f'/api/sources/{source}/original',f'/api/sources/{source}/pages/1',
             f'/api/tasks/{task}',f'/api/tasks/{task}/report',f'/api/imports/{imported["id"]}']
    for path in reads:
        assert owner.get(path).status_code == 200, path
        assert member.get(path).status_code == 404, path
        assert anon.get(path).status_code == 401, path
    assert owner.get(f'/api/sources/{source}/original',headers={'Range':'bytes=0-4'}).content == b'%PDF-'
    assert member.get(f'/api/sources/{source}/original?download=true',headers={'Range':'bytes=0-4'}).status_code == 404
    writes = [root+'/demo',root+'/repository',root+'/search',root+'/tasks',root+'/upload',root+'/imports',root+'/notes',root+'/experiments',root+'/experiments/compare',root+'/logs/demo',root+f'/logs/{source}/analysis',f'/api/sources/{source}/reindex',f'/api/tasks/{task}/cancel',f'/api/imports/{imported["id"]}/cancel',root+f'/notes/{note}/trash',root+f'/notes/{note}/restore',root+f'/experiments/{experiment}/trash',root+f'/experiments/{experiment}/restore',root+f'/experiments/{experiment}/clone']
    for path in writes:
        # Invalid payload would be 422 if authorization waited until after body parsing.
        assert member.post(path, content=b'invalid').status_code == 404, path
        assert anon.post(path, content=b'invalid').status_code == 401, path
    assert member.delete(f'/api/sources/{source}').status_code == 404
    assert member.patch(root+'/notes/'+note,json={}).status_code == 404
    assert member.patch(root+'/experiments/'+experiment,json={}).status_code == 404
    # Swapping only nested IDs must also fail within an otherwise owned workspace.
    assert member.get(f'/api/workspaces/{mine}/notes/{note}').status_code == 404
    assert member.get(f'/api/workspaces/{mine}/experiments/{experiment}').status_code == 404
    assert member.post(f'/api/workspaces/{mine}/tasks',json={'prompt':'read','source_ids':[source]}).status_code == 422
    assert member.post(f'/api/workspaces/{mine}/notes',json={'title':'stolen','source_id':source}).status_code == 404
    assert member.post(f'/api/workspaces/{mine}/experiments',json={'name':'stolen','plan_task_id':task}).status_code in {404,422}
    assert member.post(f'/api/workspaces/{mine}/logs/{source}/analysis').status_code in {404,422}
    assert owner.get(root+'/notes/'+note).json()['body'] == 'secret'
    for path in ['/api/maintenance/status','/api/maintenance/backup','/api/admin/users']:
        assert member.get(path).status_code == 403
        assert anon.get(path).status_code == 401
    for path in ['/docs','/openapi.json','/api/query-terms?query=loss']:
        assert anon.get(path).status_code == 401
        assert owner.get(path).status_code == 200


def test_csrf_cross_site_and_protected_upload_body(secured):
    app, owner, member, anon = secured
    for token in ['', 'wrong']:
        assert owner.post('/api/workspaces',json={'name':'bad'},headers={'X-CSRF-Token':token}).status_code == 403
    assert owner.post('/api/workspaces',json={'name':'bad'},headers={'Origin':'https://evil.example'}).status_code == 403
    assert owner.post('/api/auth/login',json={'username':'admin','password':PASSWORD},headers={'Sec-Fetch-Site':'cross-site'}).status_code == 403
    assert owner.post('/api/auth/login',content=b'x'*16385).status_code == 413
    response = owner.post('/api/auth/password',json={'current_password':PASSWORD,'new_password':'secret-short'})
    assert response.status_code == 422 and 'secret-short' not in response.text and PASSWORD not in response.text
    assert anon.post('/api/workspaces/any/imports',content=b'not multipart').status_code == 401
    assert owner.post('/api/workspaces',json={'name':'okay'},headers={'Origin':'http://testserver'}).status_code == 201


def test_invitations_are_single_use_expire_and_cannot_grant_admin(secured):
    app, owner, member, anon = secured
    assert member.post('/api/admin/invitations').status_code == 403
    invite = owner.post('/api/admin/invitations').json()['invitation']
    body = {'username':'new_member','password':PASSWORD,'invitation':invite}
    assert anon.post('/api/auth/register',json={**body,'role':'admin'}).status_code == 422
    response = anon.post('/api/auth/register',json=body)
    assert response.status_code == 201 and response.json()['user']['role'] == 'member'
    assert 'password_hash' not in response.text
    assert anon.get('/api/workspaces').json() == []
    assert anon.post('/api/auth/register',json={**body,'username':'reused'}).status_code == 400
    invitation = owner.post('/api/admin/invitations').json()['invitation']
    app.state.db.execute('UPDATE invitations SET expires_at=0')
    assert anon.post('/api/auth/register',json={**body,'username':'expired','invitation':invitation}).status_code == 400
    assert 'password_hash' not in owner.get('/api/admin/users').text


def test_disable_member_revokes_sessions_and_does_not_destroy_projects(secured):
    app, owner, member, anon = secured
    workspace = member.post('/api/workspaces',json={'name':'retained'}).json()['id']
    assert owner.patch('/api/admin/users/admin',json={'active':False}).status_code == 422
    assert owner.patch('/api/admin/users/member',json={'active':False}).status_code == 200
    assert member.get('/api/workspaces').status_code == 401
    assert member.post('/api/auth/login',json={'username':'member','password':PASSWORD}).status_code == 401
    assert owner.patch('/api/admin/users/member',json={'active':True}).status_code == 200
    assert member.get('/api/workspaces').status_code == 401  # Re-enable never resurrects old sessions.
    login(member,'member')
    assert member.get('/api/workspaces').json()[0]['id'] == workspace


def test_password_change_and_cli_reset_revoke_old_sessions(secured):
    app, owner, member, anon = secured
    login(anon)
    previous = owner.cookies[COOKIE]
    response = owner.post('/api/auth/password',json={'current_password':PASSWORD,'new_password':NEW_PASSWORD})
    assert response.status_code == 200, response.text
    assert response.json()['csrf_token'] != csrf(previous)
    assert anon.get('/api/workspaces').status_code == 401
    assert owner.get('/api/workspaces').status_code == 200
    assert owner.post('/api/workspaces',json={'name':'old csrf'}).status_code == 403
    owner.headers['X-CSRF-Token'] = response.json()['csrf_token']
    assert owner.post('/api/workspaces',json={'name':'new csrf'}).status_code == 201
    app.state.accounts.reset_password('admin', PASSWORD)
    assert owner.get('/api/workspaces').status_code == 401
    login(owner)


def test_persistent_login_throttling_and_generic_errors(secured):
    app, owner, member, anon = secured
    error = anon.post('/api/auth/login',json={'username':'unknown','password':'wrong'}).json()
    assert anon.post('/api/auth/login',json={'username':'admin','password':'wrong'}).json() == error
    app.state.db.execute('INSERT OR REPLACE INTO auth_attempts VALUES (?,?,?)',(digest('login-user:admin'),10,int(time.time())))
    assert anon.post('/api/auth/login',json={'username':'admin','password':PASSWORD}).status_code == 429
    other = Accounts(Database(app.state.settings.data_dir), app.state.settings)
    from fastapi import HTTPException
    with pytest.raises(HTTPException) as exc: other.throttle(('login-user:admin',10))
    assert exc.value.status_code == 429
    app.state.db.execute('UPDATE auth_attempts SET window_start=0')
    login(anon)


def test_accounts_backup_keeps_ownership_but_never_sessions_or_invitations(secured, tmp_path):
    app, owner, member, anon = secured
    workspace = member.post('/api/workspaces',json={'name':'restored member project'}).json()['id']
    invite = owner.post('/api/admin/invitations').json()['invitation']
    member_cookie = member.cookies[COOKIE]
    archive = tmp_path/'backup.zip'
    result = create_backup(app.state.settings.data_dir,archive)
    assert result['inventory']['counts']['users'] == 2
    for table in ['sessions','invitations','auth_attempts']:
        assert result['inventory']['counts'][table] == 0
    assert app.state.db.one('SELECT COUNT(*) AS n FROM sessions')['n'] == 2
    restored = tmp_path/'restored'
    restore_backup(archive,restored)
    recovered = create_app(Settings(data_dir=restored,auth_mode='accounts'))
    with TestClient(recovered) as client:
        assert client.get('/api/workspaces',headers={'Cookie':f'{COOKIE}={member_cookie}'}).status_code == 401
        assert client.post('/api/auth/register',json={'username':'late','password':PASSWORD,'invitation':invite}).status_code == 400
        login(client,'member')
        assert client.get('/api/workspaces').json()[0]['id'] == workspace


def test_legacy_v08_backup_without_auth_tables_remains_compatible(tmp_path):
    directory = tmp_path/'legacy'
    db = Database(directory)
    db.execute('INSERT INTO workspaces VALUES (?,?,?)',('legacy','old project',now()))
    with closing(sqlite3.connect(db.path)) as con:
        for table in reversed(AUTH_TABLES): con.execute(f'DROP TABLE {table}')
        con.commit()
    archive = tmp_path/'old.zip'
    manifest = create_backup(directory,archive)
    assert 'users' not in manifest['inventory']['counts']
    assert verify_backup(archive) == manifest
    restored = tmp_path/'restored'
    restore_backup(archive,restored)
    app = create_app(Settings(data_dir=restored))
    with TestClient(app) as client:
        assert client.get('/api/workspaces').json()[0]['id'] == 'legacy'


def test_cookie_can_be_hardened_for_https(tmp_path, encoded):
    app = create_app(Settings(data_dir=tmp_path,auth_mode='accounts',cookie_secure=True))
    app.state.db.execute('INSERT INTO users VALUES (?,?,?,?,1,?)',('admin','admin',encoded,'admin',now()))
    with TestClient(app,base_url='https://localhost') as client:
        assert 'Secure' in login(client).headers['set-cookie']
        assert client.get('/api/workspaces').status_code == 200


def test_old_password_verification_cannot_issue_session_after_reset_or_disable(secured):
    from fastapi import HTTPException, Response
    app, owner, member, anon = secured
    db = app.state.db
    old = db.one("SELECT * FROM users WHERE id='admin'")
    db.execute("UPDATE users SET password_hash='changed-by-concurrent-reset' WHERE id='admin'")
    with pytest.raises(HTTPException) as exc:
        app.state.accounts.issue_session(old, Response())
    assert exc.value.status_code == 401
    old = db.one("SELECT * FROM users WHERE id='member'")
    db.execute("UPDATE users SET active=0 WHERE id='member'")
    with pytest.raises(HTTPException) as exc:
        app.state.accounts.issue_session(old, Response())
    assert exc.value.status_code == 401
