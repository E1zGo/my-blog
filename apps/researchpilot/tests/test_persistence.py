from fastapi.testclient import TestClient

from researchpilot.app import create_app
from researchpilot.db import now, uid
from researchpilot.config import Settings
from researchpilot.library import Library
from researchpilot.provider import ModelProvider, ProviderError
import pytest


def test_restart_marks_interrupted_tasks_and_keeps_sources(settings):
    first=create_app(settings)
    with TestClient(first) as client:
        workspace=client.post('/api/workspaces',json={'name':'persistent'}).json()['id']
        client.post(f'/api/workspaces/{workspace}/demo')
        identifier=uid()
        first.state.db.execute("INSERT INTO tasks(id,workspace_id,prompt,intent,mode,status,created_at) VALUES (?,?,?,'qa','offline','running',?)",(identifier,workspace,'interrupted',now()))
    second=create_app(settings)
    with TestClient(second) as client:
        task=client.get(f'/api/tasks/{identifier}').json()
        assert task['status']=='failed' and '重启' in task['error']
        assert len(client.get(f'/api/workspaces/{workspace}/sources').json())==6


def test_embedding_failure_is_atomic(client, app, workspace, settings, monkeypatch):
    live=Settings(data_dir=settings.data_dir,mode='llm',embed_model='test')
    library=Library(app.state.db,live)
    def fail(*args):
        raise ProviderError('embedding unavailable')
    monkeypatch.setattr(ModelProvider,'embed',fail)
    with pytest.raises(ProviderError):
        library.ingest(workspace,'paper','paper',[(1,'residual denoising model')])
    assert library.list(workspace)==[]
    assert library.chunks(workspace)==[]


def test_embedding_and_model_switch_do_not_mix_dimensions(client, app, workspace, settings, monkeypatch):
    live=Settings(data_dir=settings.data_dir,mode='llm',embed_model='first')
    calls=[]
    def embed(self,texts):
        calls.append(texts)
        return [[1.0,0.0] for _ in texts]
    monkeypatch.setattr(ModelProvider,'embed',embed)
    library=Library(app.state.db,live)
    library.ingest(workspace,'paper','paper',[(1,'denoising model')])
    result=library.search(workspace,'去噪')
    assert result[0]['retrieval']=='BM25 + vector / RRF'
    switched=Library(app.state.db,Settings(data_dir=settings.data_dir,mode='llm',embed_model='second'))
    before=len(calls)
    # Chinese denoising now has an offline lexical correspondence. An unmapped
    # paraphrase still cannot use vectors from a different embedding model.
    assert switched.search(workspace,'消除噪点')==[]
    assert switched.search(workspace,'去噪')[0]['retrieval']=='BM25 + 中英术语'
    assert len(calls)==before
