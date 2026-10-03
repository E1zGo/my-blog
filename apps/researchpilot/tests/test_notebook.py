from concurrent.futures import ThreadPoolExecutor

from fastapi.testclient import TestClient

from researchpilot.app import create_app
from researchpilot.notebook import NoteCreate
from test_api import wait_task


def notebook_path(workspace):
    return f"/api/workspaces/{workspace}/notes"


def test_bookmark_is_canonical_deduplicated_and_survives_source_deletion(client, app, demo):
    chunk = app.state.library.chunks(demo, kind="paper")[0]
    path = notebook_path(demo)
    note = client.post(path, json={"chunk_id": chunk["id"]}).json()
    assert note["evidence"]["text"] == chunk["text"]
    assert note["evidence"]["page"] == chunk["page"]
    assert note["source_name"] == chunk["name"]
    changed = client.patch(path + "/" + note["id"], json={"title": "创新点分析", "body": "我的理解：需要验证残差假设。", "category": "method", "revision": 1}).json()
    duplicate = client.post(path, json={"chunk_id": chunk["id"], "body": "Must not replace existing analysis"}).json()
    assert duplicate["duplicate"] and duplicate["id"] == note["id"]
    assert duplicate["body"] == changed["body"] and duplicate["revision"] == 2
    assert len(client.get(path).json()) == 1
    assert client.delete(f"/api/sources/{chunk['source_id']}").status_code == 204
    saved = client.get(path + "/" + note["id"]).json()
    assert saved["evidence"] == note["evidence"] and saved["body"] == changed["body"]


def test_citation_snapshot_can_be_saved_after_source_removed(client, app, demo):
    task_id = client.post(f"/api/workspaces/{demo}/tasks", json={"prompt": "训练目标"}).json()["id"]
    task = wait_task(client, task_id)
    evidence = task["citations"][0]
    path = notebook_path(demo)
    before = client.post(path, json={"chunk_id": evidence["id"]}).json()
    client.delete(f"/api/sources/{evidence['source_id']}")
    result = client.post(path, json={"task_id": task_id, "citation_label": evidence["label"]})
    assert result.status_code == 201
    assert result.json()["id"] == before["id"] and result.json()["duplicate"]
    assert result.json()["evidence"]["text"] == evidence["text"]


def test_notes_cannot_spoof_evidence_or_cross_workspace(client, app, demo):
    other = client.post("/api/workspaces", json={"name": "other"}).json()["id"]
    chunk = app.state.library.chunks(demo)[0]
    note = client.post(notebook_path(demo), json={"chunk_id": chunk["id"]}).json()
    assert client.get(notebook_path(other)).json() == []
    assert client.post(notebook_path(other), json={"chunk_id": chunk["id"]}).status_code == 404
    assert client.post(notebook_path(other), json={"title": "wrong source", "source_id": chunk["source_id"]}).status_code == 404
    assert client.get(notebook_path(other) + "/" + note["id"]).status_code == 404
    assert client.patch(notebook_path(other) + "/" + note["id"], json={"title": "changed", "revision": 1}).status_code == 404
    assert client.post(notebook_path(demo), json={"title": "spoof", "evidence": {"text": "invented"}}).status_code == 422
    assert client.patch(notebook_path(demo) + "/" + note["id"], json={"title": "spoof", "revision": 1, "evidence": {}}).status_code == 422
    assert client.post(notebook_path(other) + "/" + note["id"] + "/trash", json={"revision": 1}).status_code == 404


def test_note_validation_and_stale_edit_conflict(client, workspace):
    path = notebook_path(workspace)
    for body in [{}, {"title": " "}, {"title": "x", "category": "invented"}, {"title": "x", "body": "x" * 12001}, {"task_id": "x"}, {"chunk_id": "a", "source_id": "b"}]:
        assert client.post(path, json=body).status_code == 422
    note = client.post(path, json={"title": "before", "body": "old"}).json()
    new = client.patch(path + "/" + note["id"], json={"title": "first tab", "body": "keep me", "revision": 1})
    assert new.status_code == 200
    stale = client.patch(path + "/" + note["id"], json={"title": "second tab", "body": "stale", "revision": 1})
    assert stale.status_code == 409
    assert client.get(path + "/" + note["id"]).json()["body"] == "keep me"


def test_trash_and_restore_preserve_note_and_export_excludes_trash(client, workspace):
    path = notebook_path(workspace)
    note = client.post(path, json={"title": "保留的分析", "body": "不可丢失的实验假设", "category": "question"}).json()
    trashed = client.post(path + "/" + note["id"] + "/trash", json={"revision": 1}).json()
    assert trashed["archived"] and trashed["revision"] == 2
    assert client.get(path).json() == []
    assert client.get(path + "?archived=true").json()[0]["body"] == note["body"]
    assert note["title"] not in client.get(path + "/export").text
    assert client.patch(path + "/" + note["id"], json={"title": "oops", "revision": 2}).status_code == 409
    assert client.post(path + "/" + note["id"] + "/restore", json={"revision": 1}).status_code == 409
    restored = client.post(path + "/" + note["id"] + "/restore", json={"revision": 2}).json()
    assert not restored["archived"] and restored["body"] == note["body"]
    assert len(client.get(path).json()) == 1


def test_rebookmark_restores_without_overwriting_analysis(client, app, demo):
    chunk = app.state.library.chunks(demo)[0]
    path = notebook_path(demo)
    note = client.post(path, json={"chunk_id": chunk["id"], "body": "my analysis"}).json()
    client.post(path + "/" + note["id"] + "/trash", json={"revision": 1})
    restored = client.post(path, json={"chunk_id": chunk["id"]}).json()
    assert restored["restored"] and restored["duplicate"]
    assert restored["body"] == "my analysis" and restored["revision"] == 3


def test_export_contains_origin_and_analysis_as_separate_sections(client, app, workspace):
    source = app.state.library.ingest(workspace, "paper.md", "paper", [(1, "<script>alert(1)</script> canonical [evidence](javascript:evil)")])
    chunk = app.state.library.chunks(workspace)[0]
    path = notebook_path(workspace)
    client.post(path, json={"chunk_id": chunk["id"], "title": "My <analysis>", "body": "A personal hypothesis", "category": "method"})
    report = client.get(path + "/export")
    assert report.status_code == 200 and "attachment" in report.headers["content-disposition"]
    assert "### 原文证据" in report.text and "### 个人分析 / 待办" in report.text
    assert "第 1 页" in report.text and "paper.md" in report.text
    assert "A personal hypothesis" in report.text and "<script>" not in report.text
    assert "&lt;script&gt;" in report.text and r"\[evidence\]" in report.text


def test_concurrent_bookmarks_have_one_snapshot(client, app, demo):
    chunk = app.state.library.chunks(demo)[0]
    with ThreadPoolExecutor(max_workers=4) as pool:
        results = list(pool.map(lambda _: app.state.notebook.create(demo, NoteCreate(chunk_id=chunk["id"])), range(4)))
    assert len({n["id"] for n in results}) == 1
    assert sum(not n["duplicate"] for n in results) == 1


def test_notes_persist_across_restart(settings):
    with TestClient(create_app(settings)) as client:
        workspace = client.post("/api/workspaces", json={"name": "persistent notes"}).json()["id"]
        note = client.post(notebook_path(workspace), json={"title": "Persist", "body": "Retain my reasoning"}).json()
    with TestClient(create_app(settings)) as client:
        assert client.get(notebook_path(workspace) + "/" + note["id"]).json()["body"] == "Retain my reasoning"
