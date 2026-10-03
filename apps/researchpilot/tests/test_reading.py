import json

import pytest

from researchpilot.agent import Agent
from researchpilot.config import Settings
from researchpilot.db import dump
from test_agent import ScriptedProvider, call, create_task
from test_api import wait_task


@pytest.fixture
def paper(app, workspace):
    return app.state.library.ingest(workspace, 'reading.txt', 'paper', [
        (1, 'Introduction. The denoising model uses a unique firstpageanchor.'),
        (2, 'Method. The degradation model uses a unique secondpageanchor.'),
        (3, 'References. The degradation model citation uses thirdpageanchor.')], {'pages':3})


def test_page_range_retrieval_and_offline_task(client, app, workspace, paper):
    scope = {'source_ids':[paper['id']], 'page_range':{'start':2,'end':2}}
    hits = client.post(f'/api/workspaces/{workspace}/search', json={'query':'退化模型',**scope}).json()
    assert hits and {h['page'] for h in hits} == {2}
    assert client.post(f'/api/workspaces/{workspace}/search',json={'query':'firstpageanchor',**scope}).json() == []
    created = client.post(f'/api/workspaces/{workspace}/tasks',json={'prompt':'退化模型',**scope})
    assert created.status_code == 202
    task = wait_task(client, created.json()['id'])
    assert task['page_range'] == scope['page_range']
    assert {c['page'] for c in task['citations']} == {2}
    assert '第 2 页' in task['answer']
    assert '第 2 页' in client.get(f"/api/tasks/{task['id']}/report").text
    assert client.get(f'/api/workspaces/{workspace}/tasks').json()[0]['page_range'] == scope['page_range']


def test_empty_range_does_not_fall_back_to_whole_paper(client, workspace, paper):
    task_id = client.post(f'/api/workspaces/{workspace}/tasks',json={'prompt':'thirdpageanchor','source_ids':[paper['id']],'page_range':{'start':1,'end':1}}).json()['id']
    task = wait_task(client,task_id)
    assert task['status'] == 'insufficient_evidence' and task['citations'] == []


@pytest.mark.parametrize('page_range', [
    {'start':0,'end':2}, {'start':3,'end':2}, {'start':1,'end':4},
    {'start':1,'end':301}, {'start':True,'end':2}, {'start':1.5,'end':2},
    {'start':1,'end':2,'source_id':'other'}, {'start':1},
])
def test_invalid_page_range_rejected(client, workspace, paper, page_range):
    for endpoint, key in [('search','query'),('tasks','prompt')]:
        response=client.post(f'/api/workspaces/{workspace}/{endpoint}',json={key:'model','source_ids':[paper['id']],'page_range':page_range})
        assert response.status_code == 422


def test_page_range_requires_one_paper_in_project(client, app, workspace, paper):
    repo=app.state.library.ingest(workspace,'code.py','repository',[(None,'value=1')])
    other=client.post('/api/workspaces',json={'name':'Other'}).json()['id']
    for ids in [[],[paper['id'],repo['id']],[repo['id']],['missing']]:
        assert client.post(f'/api/workspaces/{workspace}/search',json={'query':'value','source_ids':ids,'page_range':{'start':1,'end':1}}).status_code == 422
    assert client.post(f'/api/workspaces/{other}/search',json={'query':'model','source_ids':[paper['id']],'page_range':{'start':1,'end':1}}).status_code == 422
    for intent in ['plan','diagnose']:
        assert client.post(f'/api/workspaces/{workspace}/tasks',json={'prompt':'model','intent':intent,'source_ids':[paper['id']],'page_range':{'start':1,'end':1}}).status_code == 422


def test_model_tools_and_history_stay_inside_fixed_pages(client,app,workspace,paper,settings):
    prior=create_task(app.state.db,workspace)
    app.state.db.execute("UPDATE tasks SET status='completed',answer='OUTSIDE_PAGE_SECRET',source_ids=?,page_range=? WHERE id=?",(dump([paper['id']]),dump({'start':1,'end':1}),prior))
    task_id=create_task(app.state.db,workspace)
    app.state.db.execute('UPDATE tasks SET source_ids=?,page_range=? WHERE id=?',(dump([paper['id']]),dump({'start':2,'end':2}),task_id))
    provider=ScriptedProvider([call('search_evidence',{'query':'thirdpageanchor'}),call('read_source',{'source_id':paper['id']}),{'content':'第 2 页的方法证据。[E1]'}])
    Agent(app.state.db,app.state.library,Settings(data_dir=settings.data_dir,mode='llm',model='test'),provider).run(task_id)
    assert json.loads(provider.messages[1][-1]['content'])['evidence'] == []
    assert 'thirdpageanchor' not in json.loads(provider.messages[2][-1]['content'])['evidence'][0]['text']
    assert 'OUTSIDE_PAGE_SECRET' not in json.dumps(provider.messages)
    assert {e['page'] for e in app.state.db.task(task_id)['citations']} == {2}


def test_page_note_origin_export_and_source_removal(client,app,workspace,paper):
    response=client.post(f'/api/workspaces/{workspace}/notes',json={'title':'第二页阅读','source_id':paper['id'],'source_page':2,'body':'待核对方法假设。'})
    assert response.status_code == 201
    note=response.json()
    assert note['source_page'] == 2 and note['evidence'] is None
    assert '第 2 页（页级个人笔记' in client.get(f'/api/workspaces/{workspace}/notes/export').text
    # Personal page notes are not fabricated evidence snapshots, and retain the
    # original anchor after reindexing or source deletion.
    client.delete(f"/api/sources/{paper['id']}")
    updated=client.patch(f"/api/workspaces/{workspace}/notes/{note['id']}",json={'title':'仍可编辑','body':'来源已移除','revision':1}).json()
    assert updated['source_page'] == 2 and updated['source_name'] == 'reading.txt'
    assert client.patch(f"/api/workspaces/{workspace}/notes/{note['id']}",json={'title':'伪造页码','source_page':3,'revision':2}).status_code == 422


@pytest.mark.parametrize('page',[0,4,True,2.5])
def test_invalid_page_note_rejected(client,workspace,paper,page):
    assert client.post(f'/api/workspaces/{workspace}/notes',json={'title':'invalid','source_id':paper['id'],'source_page':page}).status_code == 422


def test_page_note_cannot_claim_foreign_source_or_evidence(client,app,workspace,paper):
    chunk=app.state.library.chunks(workspace,source_id=paper['id'])[0]
    for origin in [{},{'chunk_id':chunk['id']}]:
        assert client.post(f'/api/workspaces/{workspace}/notes',json={'title':'invalid','source_page':2,**origin}).status_code == 422
    other=client.post('/api/workspaces',json={'name':'Other'}).json()['id']
    assert client.post(f'/api/workspaces/{other}/notes',json={'title':'invalid','source_id':paper['id'],'source_page':2}).status_code == 404
