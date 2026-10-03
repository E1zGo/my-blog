import pytest
from fastapi.testclient import TestClient

from researchpilot.app import create_app
from researchpilot.experiments import ExperimentFields
from test_api import wait_task


def path(workspace):
    return f"/api/workspaces/{workspace}/experiments"


def create(client, workspace, **fields):
    result = client.post(path(workspace), json={"name": "baseline", **fields})
    assert result.status_code == 201, result.text
    return result.json()


def update_body(record, **changes):
    return {**{k: record[k] for k in ExperimentFields.model_fields}, "revision": record["revision"], **changes}


def metric(value=28.4, **changes):
    return {"name": "PSNR", "value": value, "unit": "dB", "split": "test", "protocol": "RGB; crop=4; eval@abc", **changes}


def test_plan_conversion_and_snapshot_survive_source_deletion(client, app, demo):
    task = client.post(f"/api/workspaces/{demo}/tasks", json={"prompt": "制定复现计划", "intent": "plan"}).json()
    task = wait_task(client, task["id"])
    record = create(client, demo, name="计划转实验", plan_task_id=task["id"])
    assert record["plan"]["answer"] == task["answer"]
    assert record["plan"]["citations"] == task["citations"]
    assert record["status"] == "planned" and record["metrics"] == []
    assert not any(c["done"] for c in record["checklist"])
    for source in app.state.library.list(demo):
        client.delete("/api/sources/" + source["id"])
    assert client.get(path(demo) + "/" + record["id"]).json()["plan"] == record["plan"]
    assert "引用证据" in client.get(path(demo) + "/" + record["id"] + "/export").text


def test_cross_workspace_access_and_plan_validation(client, app, demo):
    other = client.post("/api/workspaces", json={"name": "other"}).json()["id"]
    record = create(client, demo)
    target = path(other) + "/" + record["id"]
    assert client.get(target).status_code == 404
    assert client.patch(target, json=update_body(record)).status_code == 404
    for suffix in ("clone", "trash", "restore"):
        assert client.post(target + "/" + suffix, json={"revision": 1}).status_code == 404
    assert client.get(target + "/export").status_code == 404
    other_record = create(client, other)
    assert client.post(path(other) + "/compare", json={"baseline_id": record["id"], "candidate_id": other_record["id"]}).status_code == 404
    task = client.post(f"/api/workspaces/{demo}/tasks", json={"prompt": "方法", "intent": "qa"}).json()
    wait_task(client, task["id"])
    assert client.post(path(demo), json={"name": "invalid", "plan_task_id": task["id"]}).status_code == 422
    assert client.post(path(other), json={"name": "invalid", "plan_task_id": task["id"]}).status_code == 404
    app.state.db.execute("UPDATE tasks SET intent='plan',status='running' WHERE id=?", (task["id"],))
    assert client.post(path(demo), json={"name": "pending", "plan_task_id": task["id"]}).status_code == 422
    app.state.db.execute("UPDATE tasks SET status='completed',citations='[]' WHERE id=?", (task["id"],))
    assert client.post(path(demo), json={"name": "empty", "plan_task_id": task["id"]}).status_code == 422


def test_log_snapshot_validation_and_retention(client, app, demo):
    sources = app.state.library.list(demo)
    log = next(s for s in sources if s["kind"] == "log")
    paper = next(s for s in sources if s["kind"] == "paper")
    assert client.post(path(demo), json={"name": "wrong kind", "log_source_ids": [paper["id"]]}).status_code == 422
    other = client.post("/api/workspaces", json={"name": "other"}).json()["id"]
    assert client.post(path(other), json={"name": "wrong scope", "log_source_ids": [log["id"]]}).status_code == 422
    record = create(client, demo, log_source_ids=[log["id"]])
    assert "CUDA" in record["logs"][0]["text"]
    client.delete("/api/sources/" + log["id"])
    saved = client.patch(path(demo) + "/" + record["id"], json=update_body(record, conclusion="retained")).json()
    assert saved["logs"] == record["logs"]
    assert client.post(path(demo), json={"name": "deleted", "log_source_ids": [log["id"]]}).status_code == 422
    no_log = client.patch(path(demo) + "/" + record["id"], json=update_body(saved, log_source_ids=[])).json()
    assert no_log["logs"] == []


def test_large_log_snapshot_marks_truncation(client, app, workspace):
    log = app.state.library.ingest(workspace, "large.log", "log", [(None, "loss=0.1\n" * 4000)])
    record = create(client, workspace, log_source_ids=[log["id"]])
    assert record["logs"][0]["truncated"]
    assert len(record["logs"][0]["text"]) == 20000
    assert "快照仅保留前 20000 字符" in client.get(path(workspace) + "/" + record["id"] + "/export").text


def test_clone_resets_actual_results_and_checklist(client, workspace):
    record = create(client, workspace, status="completed", metrics=[metric()], parameters={"seed": "42", "lr": "0.001"},
                    dataset="v1", code_ref="abc", environment="GPU A", conclusion="measured", checklist=[{"label": "test", "done": True}])
    cloned = client.post(path(workspace) + "/" + record["id"] + "/clone", json={"revision": 1})
    assert cloned.status_code == 201
    cloned = cloned.json()
    assert cloned["parameters"] == record["parameters"] and cloned["dataset"] == record["dataset"]
    assert cloned["status"] == "planned" and cloned["metrics"] == [] and cloned["logs"] == [] and cloned["conclusion"] == ""
    assert not cloned["checklist"][0]["done"]
    assert cloned["id"] != record["id"]


def test_revision_conflicts_trash_and_restore(client, workspace):
    record = create(client, workspace)
    target = path(workspace) + "/" + record["id"]
    saved = client.patch(target, json=update_body(record, conclusion="keep my result")).json()
    assert saved["revision"] == 2
    assert client.patch(target, json=update_body(record, conclusion="stale")).status_code == 409
    for action in ("clone", "trash", "restore"):
        assert client.post(target + "/" + action, json={"revision": 1}).status_code == 409
    trashed = client.post(target + "/trash", json={"revision": 2}).json()
    assert trashed["archived"] and client.get(path(workspace)).json() == []
    assert len(client.get(path(workspace) + "?archived=true").json()) == 1
    assert client.patch(target, json=update_body(trashed)).status_code == 409
    assert client.post(target + "/clone", json={"revision": 3}).status_code == 409
    restored = client.post(target + "/restore", json={"revision": 3}).json()
    assert not restored["archived"] and restored["conclusion"] == "keep my result"


def test_compare_delta_changes_missing_metrics_and_same_record(client, workspace):
    left = create(client, workspace, dataset="D@v1", parameters={"lr": "0.01", "seed": "42"}, metrics=[metric(), metric(name="SSIM", value=0.8, unit="")])
    right = create(client, workspace, dataset="D@v1", parameters={"lr": "0.001", "batch": "8"}, metrics=[metric(29.0)])
    result = client.post(path(workspace) + "/compare", json={"baseline_id": left["id"], "candidate_id": right["id"]}).json()
    assert result["metrics"][0]["comparable"] and result["metrics"][0]["delta"] == pytest.approx(.6)
    assert result["metrics"][1]["delta"] is None and "仅一侧" in result["metrics"][1]["reason"]
    assert {c["field"] for c in result["changes"]} == {"参数 · lr", "参数 · seed", "参数 · batch"}
    assert client.post(path(workspace) + "/compare", json={"baseline_id": left["id"], "candidate_id": left["id"]}).status_code == 422


@pytest.mark.parametrize("field,value", [("dataset", "D@v2"), ("dataset", ""), ("unit", "%"), ("split", "val"), ("split", ""), ("protocol", "gray"), ("protocol", "")])
def test_incompatible_comparison_does_not_compute_delta(client, workspace, field, value):
    left = create(client, workspace, dataset="D@v1", metrics=[metric()])
    right = create(client, workspace, dataset=value if field == "dataset" else "D@v1", metrics=[metric(29, **({field: value} if field != "dataset" else {}))])
    result = client.post(path(workspace) + "/compare", json={"baseline_id": left["id"], "candidate_id": right["id"]}).json()["metrics"][0]
    assert not result["comparable"] and result["delta"] is None and result["reason"]


@pytest.mark.parametrize("bad", [
    {"metrics": [metric(value="NaN")]}, {"metrics": [metric(value="Infinity")]}, {"metrics": [metric(value=1e101)]},
    {"metrics": [metric(), metric(name="psnr")]}, {"parameters": {"": "bad"}}, {"name": "   "},
    {"status": "succeeded"}, {"plan": {"answer": "forged"}}, {"logs": [{"text": "forged"}]}])
def test_validation_rejects_invalid_or_forged_data(client, workspace, bad):
    assert client.post(path(workspace), json={"name": "bad data", **bad}).status_code == 422


@pytest.mark.parametrize("parameters", [{"lr": "1", " lr ": "2"}, {"a=b": "c"}, {"config": "first\nsecond"}])
def test_parameters_roundtrip_without_silent_loss(client, workspace, parameters):
    assert client.post(path(workspace), json={"name": "bad parameters", "parameters": parameters}).status_code == 422


def test_export_escaping_and_restart_preserves_manual_status(settings):
    with TestClient(create_app(settings)) as client:
        workspace = client.post("/api/workspaces", json={"name": "persist"}).json()["id"]
        record = create(client, workspace, name="<script>unsafe</script>", status="running", conclusion="[click](javascript:evil)", metrics=[metric()], parameters={"seed": "42"})
        exported = client.get(path(workspace) + "/" + record["id"] + "/export")
        assert exported.status_code == 200 and "attachment" in exported.headers["content-disposition"]
        assert "人工实验记录" in exported.text and "PSNR" in exported.text and "seed" in exported.text
        assert "<script>" not in exported.text and r"\[click\]" in exported.text
    with TestClient(create_app(settings)) as client:
        restored = client.get(path(workspace) + "/" + record["id"]).json()
        assert restored["status"] == "running" and restored["metrics"] == record["metrics"]
