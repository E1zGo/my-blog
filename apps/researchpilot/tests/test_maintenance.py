from contextlib import closing
import io
import json
from pathlib import Path
import sqlite3
import stat
import zipfile

import pytest
from fastapi.testclient import TestClient

from researchpilot.app import create_app
from researchpilot.config import Settings
from researchpilot.db import now, uid
from researchpilot import maintenance as m
from test_api import wait_task
from test_imports import submit, wait_import


@pytest.fixture
def saved(client, workspace):
    content = b'Method: a denoising model optimizes reconstruction loss.'
    source = wait_import(client, submit(client, workspace, content, 'reading.txt'))['result']
    note = client.post(f'/api/workspaces/{workspace}/notes', json={'title':'Reading note','body':'Verify assumptions','source_id':source['id'],'source_page':1}).json()
    task = wait_task(client, client.post(f'/api/workspaces/{workspace}/tasks', json={'prompt':'denoising','source_ids':[source['id']]}).json()['id'])
    assert task['status'] == 'completed'
    return {'source':source,'note':note,'task':task,'content':content}


def test_backup_roundtrip_preserves_data_and_excludes_unrelated_files(client, app, settings, workspace, saved, tmp_path):
    (settings.data_dir / '.env').write_text('SECRET=not-in-backup')
    (settings.data_dir / 'private.txt').write_text('unrelated')
    (settings.data_dir / 'originals' / ('f'*32+'.bin')).write_bytes(b'staging-file')
    archive = tmp_path / 'exports' / 'backup.zip'
    manifest = m.create_backup(settings.data_dir, archive)
    assert manifest['inventory']['counts']['notes'] == 1
    assert manifest == m.verify_backup(archive)
    with zipfile.ZipFile(archive) as bundle:
        assert set(bundle.namelist()) == {'manifest.json',m.DATABASE,*manifest['inventory']['originals']}
    restored = tmp_path / 'restored'
    assert m.restore_backup(archive, restored) == manifest
    with closing(sqlite3.connect(restored / m.DATABASE)) as con, app.state.db.connect() as original:
        for table in m.TABLES:
            assert con.execute(f'SELECT * FROM {table} ORDER BY 1').fetchall() == [tuple(row) for row in original.execute(f'SELECT * FROM {table} ORDER BY 1')]
    with TestClient(create_app(Settings(data_dir=restored))) as recovered:
        assert recovered.get(f"/api/sources/{saved['source']['id']}/original").content == saved['content']
        assert recovered.get(f"/api/tasks/{saved['task']['id']}").json()['answer'] == saved['task']['answer']
        assert recovered.get(f"/api/workspaces/{workspace}/notes").json()[0]['source_page'] == 1
        assert recovered.post(f'/api/workspaces/{workspace}/search',json={'query':'denoising'}).json()


def test_backup_is_a_snapshot_even_when_database_changes_during_packaging(app, settings, saved, tmp_path, monkeypatch):
    copy_hash = m._copy_hash
    changed = False
    def concurrent_change(*args):
        nonlocal changed
        if not changed:
            changed = True
            app.state.db.execute("UPDATE notes SET body='new body after snapshot' WHERE id=?",(saved['note']['id'],))
        return copy_hash(*args)
    monkeypatch.setattr(m,'_copy_hash',concurrent_change)
    archive = tmp_path / 'snapshot.zip'
    m.create_backup(settings.data_dir, archive)
    restored = tmp_path / 'snapshot-restore'
    m.restore_backup(archive, restored)
    with closing(sqlite3.connect(restored / m.DATABASE)) as con:
        assert con.execute('SELECT body FROM notes').fetchone()[0] == 'Verify assumptions'
    assert app.state.db.one('SELECT body FROM notes')['body'] == 'new body after snapshot'


def test_missing_original_or_active_job_cannot_produce_complete_backup(client,app,settings,workspace,saved,tmp_path):
    path = settings.data_dir / 'originals' / (saved['source']['metadata']['original_id']+'.bin')
    path.unlink()
    destination = tmp_path / 'missing.zip'
    with pytest.raises(m.MaintenanceError,match='原文件'):
        m.create_backup(settings.data_dir,destination)
    assert not destination.exists()
    assert not m.doctor(settings.data_dir)['ok']
    path.write_bytes(saved['content'])
    app.state.db.execute("INSERT INTO tasks(id,workspace_id,prompt,intent,mode,status,created_at) VALUES (?,?,?,'qa','offline','queued',?)",(uid(),workspace,'pending',now()))
    with pytest.raises(m.MaintenanceError,match='未结束'):
        m.create_backup(settings.data_dir,destination)
    assert client.get('/api/maintenance/backup').status_code == 409
    assert not destination.exists()


def test_existing_backup_and_restore_targets_are_never_overwritten(settings,saved,tmp_path):
    archive = tmp_path / 'backup.zip'
    m.create_backup(settings.data_dir,archive)
    previous=archive.read_bytes()
    with pytest.raises(m.MaintenanceError,match='已存在'):
        m.create_backup(settings.data_dir,archive)
    assert archive.read_bytes()==previous
    target=tmp_path/'existing'
    target.mkdir()
    (target/'keep.txt').write_text('keep')
    with pytest.raises(m.MaintenanceError,match='新目录'):
        m.restore_backup(archive,target)
    assert (target/'keep.txt').read_text()=='keep'


@pytest.mark.parametrize('mutation',['tampered','missing','extra','traversal','absolute','backslash','duplicate','symlink','future','bad-manifest','wrong-inventory'])
def test_invalid_backups_fail_before_destination_creation(settings,saved,tmp_path,mutation):
    source=tmp_path/'valid.zip'
    m.create_backup(settings.data_dir,source)
    with zipfile.ZipFile(source) as bundle:
        members={n:bundle.read(n) for n in bundle.namelist()}
    original=next(n for n in members if n.startswith('originals/'))
    if mutation=='tampered': members[original]=b'X'*len(members[original])
    if mutation=='missing': members.pop(original)
    if mutation in {'extra','traversal','absolute','backslash'}:
        name={'extra':'config.env','traversal':'../escape.txt','absolute':'/escape.txt','backslash':'originals\\escape.txt'}[mutation]
        members[name]=b'no'
    if mutation=='bad-manifest': members['manifest.json']=b'{}'
    if mutation in {'future','wrong-inventory'}:
        manifest=json.loads(members['manifest.json'])
        if mutation=='future': manifest['app_version']='999.0.0'
        else: manifest['inventory']['counts']['notes']=100
        members['manifest.json']=json.dumps(manifest).encode()
    damaged=tmp_path/'damaged.zip'
    with zipfile.ZipFile(damaged,'w') as bundle:
        for name,data in members.items():
            entry=zipfile.ZipInfo(name)
            if mutation=='symlink' and name==original: entry.external_attr=(stat.S_IFLNK|0o777)<<16
            bundle.writestr(entry,data)
        if mutation=='duplicate':
            with pytest.warns(UserWarning): bundle.writestr(original,b'no')
    target=tmp_path/'recovered'
    with pytest.raises(m.MaintenanceError): m.restore_backup(damaged,target)
    assert not target.exists()
    assert not (tmp_path/'escape.txt').exists()


def test_restore_size_limit_and_invalid_original_reference(settings,saved,app,tmp_path,monkeypatch):
    archive=tmp_path/'valid.zip'
    m.create_backup(settings.data_dir,archive)
    monkeypatch.setattr(m,'MAX_BYTES',10)
    with pytest.raises(m.MaintenanceError,match='上限'): m.verify_backup(archive)
    app.state.db.execute('UPDATE sources SET metadata=?',(json.dumps({'original_id':'../../config'}),))
    assert not m.doctor(settings.data_dir)['ok']


def test_web_status_and_backup_keep_configuration_private(client,settings,saved,tmp_path,monkeypatch):
    monkeypatch.setenv('RP_API_KEY','PRIVATE_KEY_NOT_FOR_BROWSER')
    status=client.get('/api/maintenance/status')
    assert status.status_code==200 and status.json()['ok'] and status.json()['backup_ready']
    assert 'PRIVATE_KEY_NOT_FOR_BROWSER' not in status.text and str(settings.data_dir) not in status.text
    assert client.get('/api/maintenance/backup',headers={'Sec-Fetch-Site':'cross-site'}).status_code==403
    response=client.get('/api/maintenance/backup')
    assert response.status_code==200 and response.headers['content-type']=='application/zip'
    archive=tmp_path/'download.zip'
    archive.write_bytes(response.content)
    assert m.verify_backup(archive)['inventory']['counts']['notes']==1
    # FileResponse has run its cleanup; a second backup still works.
    assert client.get('/api/maintenance/backup').status_code==200


def test_doctor_and_cli_do_not_initialize_or_leak_configuration(tmp_path,capsys,monkeypatch):
    data=tmp_path/'unused'
    monkeypatch.setenv('RP_API_KEY','PRIVATE_KEY_NOT_FOR_CLI')
    assert m.main(['doctor','--data-dir',str(data)])==0
    assert not data.exists()
    assert 'PRIVATE_KEY_NOT_FOR_CLI' not in capsys.readouterr().out
    assert m.main(['verify',str(tmp_path/'missing.zip')])==1
    assert '操作失败' in capsys.readouterr().err


def test_relative_config_data_directory_does_not_follow_launch_directory(tmp_path,monkeypatch):
    from researchpilot.config import ROOT
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv('RP_DATA_DIR','data-restored')
    assert Settings.from_env().data_dir == (ROOT/'data-restored').resolve()
