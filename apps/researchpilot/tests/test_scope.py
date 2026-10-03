import json

from researchpilot.agent import Agent
from researchpilot.config import Settings
from researchpilot.db import dump
from test_agent import ScriptedProvider, call, create_task
from test_api import wait_task


def test_search_and_offline_task_only_use_selected_paper(client, app, workspace):
    first = app.state.library.ingest(workspace, "first.txt", "paper", [(1, "Denoising uses residual prediction and MSE loss.")])
    second = app.state.library.ingest(workspace, "second.txt", "paper", [(1, "Denoising uses an unrelated diffusion objective.")])
    result = client.post(f"/api/workspaces/{workspace}/search", json={"query": "denoising", "source_ids": [first["id"]]}).json()
    assert result and {r["source_id"] for r in result} == {first["id"]}
    assert client.post(f"/api/workspaces/{workspace}/search", json={"query": "diffusion", "source_ids": [first["id"]]}).json() == []
    task_id = client.post(f"/api/workspaces/{workspace}/tasks", json={"prompt": "denoising", "source_ids": [second["id"], second["id"]]}).json()["id"]
    task = wait_task(client, task_id)
    assert task["source_ids"] == [second["id"]]
    assert task["citations"] and {e["source_id"] for e in task["citations"]} == {second["id"]}


def test_invalid_and_other_project_scope_are_rejected(client, app, workspace):
    other = client.post("/api/workspaces", json={"name": "other"}).json()["id"]
    source = app.state.library.ingest(other, "private.txt", "paper", [(1, "Outside the chosen workspace")])
    for ids in [[source["id"]], ["missing"], ["missing"] * 51]:
        assert client.post(f"/api/workspaces/{workspace}/search", json={"query": "outside", "source_ids": ids}).status_code == 422
        assert client.post(f"/api/workspaces/{workspace}/tasks", json={"prompt": "outside", "source_ids": ids}).status_code == 422


def test_model_cannot_read_outside_scope_or_inherit_other_scope_history(client, app, demo, settings):
    sources = app.state.library.list(demo)
    paper = next(s for s in sources if s["kind"] == "paper")
    repo = next(s for s in sources if s["kind"] == "repository")
    unrelated = create_task(app.state.db, demo)
    app.state.db.execute("UPDATE tasks SET status='completed',answer='UNRELATED_HISTORY_SECRET' WHERE id=?", (unrelated,))
    task_id = create_task(app.state.db, demo)
    app.state.db.execute("UPDATE tasks SET source_ids=? WHERE id=?", (dump([paper["id"]]), task_id))
    provider = ScriptedProvider([call("read_source", {"source_id": repo["id"]}), call("inspect_repository", {}), call("diagnose_logs", {}), {"content": "仅有选定论文可用。"}])
    live = Settings(data_dir=settings.data_dir, mode="llm", model="test")
    Agent(app.state.db, app.state.library, live, provider).run(task_id)
    assert "error" in json.loads(provider.messages[1][-1]["content"])
    assert json.loads(provider.messages[2][-1]["content"])["files"] == []
    assert not app.state.db.task(task_id)["citations"]
    assert "UNRELATED_HISTORY_SECRET" not in json.dumps(provider.messages)
    assert repo["id"] not in provider.messages[0][0]["content"]
