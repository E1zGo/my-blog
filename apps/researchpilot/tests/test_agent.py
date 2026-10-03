import json
from contextlib import contextmanager
import pytest

from researchpilot.agent import Agent
from researchpilot.config import Settings
from researchpilot.db import now, uid
from researchpilot.library import Library


@pytest.mark.parametrize('failed', [False, True])
def test_terminal_state_is_committed_with_final_metrics_and_event(app, demo, settings, monkeypatch, failed):
    db = app.state.db
    task_id = create_task(db, demo, mode='offline')
    agent = Agent(db, app.state.library, settings)
    if failed:
        def fail(task):
            raise ValueError('controlled failure')
        monkeypatch.setattr(agent, 'offline', fail)
    original_connect, observations = db.connect, []

    @contextmanager
    def observe_commits():
        with original_connect() as con:
            yield con
        # Use a separate connection to observe only externally committed data.
        with original_connect() as con:
            row = con.execute('SELECT * FROM tasks WHERE id=?', (task_id,)).fetchone()
            if row['status'] in {'completed', 'failed', 'insufficient_evidence', 'needs_review'}:
                events = con.execute('SELECT * FROM events WHERE task_id=? ORDER BY id', (task_id,)).fetchall()
                observations.append((tuple(row), [tuple(event) for event in events]))
                assert json.loads(row['usage'])['elapsed_ms'] >= 0
                assert events[-1]['phase'] == ('error' if failed else 'done')
    monkeypatch.setattr(db, 'connect', observe_commits)
    agent.run(task_id)
    assert observations and all(observation == observations[0] for observation in observations)


def create_task(db, workspace, mode="llm"):
    identifier = uid()
    db.execute("INSERT INTO tasks(id,workspace_id,prompt,intent,mode,status,created_at) VALUES (?,?,?,'qa',?,'queued',?)",
               (identifier, workspace, "解释训练目标", mode, now()))
    return identifier


def call(name, args, identifier="call_1"):
    return {"role":"assistant", "content":None,"tool_calls":[{"id":identifier,"type":"function","function":{"name":name,"arguments":json.dumps(args)}}]}


class ScriptedProvider:
    def __init__(self, outputs):
        self.outputs = iter(outputs)
        self.messages = []

    def chat(self, messages, tools, allow_tools=True):
        self.messages.append(list(messages))
        return next(self.outputs), {"prompt_tokens":10,"completion_tokens":5,"total_tokens":15}


def test_real_protocol_with_mocked_model(client, app, demo, settings):
    provider = ScriptedProvider([call("search_evidence",{"query":"训练目标", "kind":"paper"}), {"content":"训练使用 MSE 损失。[E1]"}])
    live = Settings(data_dir=settings.data_dir,mode="llm",model="test")
    task_id = create_task(app.state.db, demo)
    Agent(app.state.db, app.state.library, live, provider).run(task_id)
    result = app.state.db.task(task_id)
    assert result["status"] == "completed"
    assert result["usage"]["total_tokens"] == 30
    assert result["citations"][0]["label"] == "E1"
    assert provider.messages[1][-1]["role"] == "tool"
    assert provider.messages[1][-1]["tool_call_id"] == "call_1"


def test_unknown_tool_and_invalid_citation_are_not_trusted(client, app, demo, settings):
    provider = ScriptedProvider([call("run_shell",{"cmd":"rm anything"}), {"content":"已经完成 [E999]"}])
    live = Settings(data_dir=settings.data_dir,mode="llm",model="test")
    task_id = create_task(app.state.db, demo)
    Agent(app.state.db, app.state.library, live, provider).run(task_id)
    result = app.state.db.task(task_id)
    assert result["status"] == "needs_review"
    assert "[引用无效]" in result["answer"] and not result["citations"]
    assert result["usage"]["tool_success"] == 0
    assert "error" in json.loads(provider.messages[1][-1]["content"])


def test_cross_project_read_tool_is_rejected(client, app, demo, settings):
    other = client.post("/api/workspaces",json={"name":"other"}).json()["id"]
    source_id = app.state.library.list(demo)[0]["id"]
    task_id = create_task(app.state.db,other)
    provider = ScriptedProvider([call("read_source",{"source_id":source_id}), {"content":"当前项目没有此资料。"}])
    live = Settings(data_dir=settings.data_dir,mode="llm",model="test")
    Agent(app.state.db,app.state.library,live,provider).run(task_id)
    assert app.state.db.task(task_id)["citations"] == []
    assert "error" in json.loads(provider.messages[1][-1]["content"])


def test_tool_budget_is_bounded(client, app, demo, settings):
    provider = ScriptedProvider([call("search_evidence",{"query":"训练目标"}),call("search_evidence",{"query":"环境"})])
    live = Settings(data_dir=settings.data_dir,mode="llm",model="test",max_tool_calls=1)
    task_id = create_task(app.state.db,demo)
    Agent(app.state.db,app.state.library,live,provider).run(task_id)
    result = app.state.db.task(task_id)
    assert result["usage"]["tool_calls"] == 1
    assert "预算" in result["answer"]


def test_cancelled_task_does_not_call_provider(client, app, demo, settings):
    task_id = create_task(app.state.db,demo)
    client.post(f"/api/tasks/{task_id}/cancel")
    provider = ScriptedProvider([])
    Agent(app.state.db,app.state.library,settings,provider).run(task_id)
    assert app.state.db.task(task_id)["status"] == "cancelled"
    assert provider.messages == []
