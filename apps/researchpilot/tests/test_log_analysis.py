import json

import pytest
from fastapi.testclient import TestClient

from researchpilot.app import create_app
from researchpilot.log_analysis import digest, parse_log
from test_experiments import create, path, update_body
from test_imports import submit, wait_import


def analyze(client, workspace, source):
    return client.post(f"/api/workspaces/{workspace}/logs/{source}/analysis")


def series(result, name, split=""):
    return next(s for s in result["series"] if s["name"] == name and s["split"] == split)


def selected_metric(result, name="psnr", split="val"):
    s = series(result, name, split)
    point = s["points"][-1]
    return {"name": name, "value": point["value"], "unit": s["unit"], "split": split, "protocol": "test protocol",
            "origin": {"source_id": result["source_id"], "checksum": result["checksum"], "point_id": point["id"]}}


def test_key_values_scientific_notation_context_and_lines():
    text = "# intro\n[train] epoch=1 step=10 loss: 1.2e-2 lr=3E-4\n[2026-09-27] epoch=2 step=20 val/psnr=28.4dB test/accuracy=91.2%\n"
    result = parse_log(text, digest(text))
    loss = series(result, "loss", "train")
    assert loss["points"][0]["value"] == .012 and loss["points"][0]["line"] == 2
    assert loss["axis"] == "step" and loss["points"][0]["epoch"] == 1
    assert series(result, "psnr", "val")["unit"] == "dB"
    assert series(result, "accuracy", "test")["unit"] == "%"
    assert result["point_count"] == 4 and result["lines"]["3"].startswith("[2026")


def test_json_flat_nested_and_invalid_objects_are_not_regex_parsed():
    text = '\n'.join(['{"epoch":1,"split":"validation","loss":0.2}',
                      '{"epoch":2,"val":{"loss":0.1,"psnr":"29dB"},"message":"loss=999"}',
                      '{"loss":0.9,"loss":0.8}', '{invalid loss=100}', '{"loss":true}'])
    result = parse_log(text, digest(text))
    assert [p["value"] for p in series(result, "loss", "val")["points"]] == [.2, .1]
    assert result["point_count"] == 3
    assert any("JSON" in w for w in result["warnings"]) and any("无法解析" in w for w in result["warnings"])


def test_no_cross_line_phase_or_coordinate_inference():
    text = "[train] epoch=1 loss=0.4\nloss=0.3\nepoch=2 loss=0.2"
    result = parse_log(text, digest(text))
    assert series(result, "loss", "train")["count"] == 1
    unknown = series(result, "loss")
    assert unknown["axis"] == "line" and unknown["points"][0]["epoch"] is None


def test_units_are_separate_and_duplicate_names_are_ambiguous():
    text = "step=1 accuracy=90%\nstep=2 accuracy=0.91\nstep=3 loss=0.1 loss=0.2\nstep=4 psnr=28dB psnr=29"
    result = parse_log(text, digest(text))
    assert len(result["series"]) == 2 and result["point_count"] == 2
    assert {s["unit"] for s in result["series"]} == {"%", ""}
    assert any("重复指标" in w for w in result["warnings"])


def test_nonfinite_overflow_and_numeric_fragments_are_not_valid_measurements():
    text = "loss=nan\nloss=inf\nloss=-Infinity\nloss=1e309\nloss=1e101\nloss=1.2.3\nloss=1e\nloss=1/10\nloss=12oops\nloss=0"
    result = parse_log(text, digest(text))
    assert result["point_count"] == 1 and result["series"][0]["points"][0]["value"] == 0
    assert result["warnings"]


def test_repeated_and_reset_steps_are_preserved_without_averaging():
    text = "step=1 loss=1\nstep=2 loss=0.5\nstep=2 loss=0.4\nstep=1 loss=0.8"
    result = parse_log(text, digest(text))
    s = series(result, "loss")
    assert s["count"] == 4 and s["breaks"] == 2
    assert s["last"] != s["minimum"] and s["maximum"] == s["points"][0]["id"]
    assert len({p["id"] for p in s["points"]}) == 4
    assert result["warnings"]


def test_partial_last_line_at_point_limit_does_not_create_empty_series(monkeypatch):
    monkeypatch.setattr("researchpilot.log_analysis.MAX_POINTS", 3)
    text = "epoch=1 loss=0.4\nepoch=2 loss=0.3 psnr=20 ssim=0.7"
    result = parse_log(text, digest(text))
    assert result["point_count"] == 3 and result["limited"]
    assert len(result["series"]) == 2 and all(s["points"] for s in result["series"])


def test_line_series_and_long_line_limits_are_reported(monkeypatch):
    monkeypatch.setattr("researchpilot.log_analysis.MAX_LINES", 3)
    monkeypatch.setattr("researchpilot.log_analysis.MAX_SERIES", 1)
    text = "loss=0.3 psnr=20\n" + "x" * 4097 + " loss=0.5\nloss=0.2\nloss=0.1"
    result = parse_log(text, digest(text))
    assert result["point_count"] == 2 and result["scanned_lines"] == 3 and result["limited"]
    assert len(result["warnings"]) == 3


def test_diagnostics_line_numbers_and_ansi_preserve_raw_evidence():
    text = "# demo\n\x1b[32mstep=1 loss=0.2\x1b[0m\nRuntimeError: CUDA out of memory\n"
    result = parse_log(text, digest(text))
    assert result["point_count"] == 1 and result["lines"]["2"].startswith("\x1b")
    assert result["findings"][0]["line"] == 3


def test_exact_text_avoids_chunk_overlap_and_duplicate_reupload_backfills(client, app, workspace):
    text = "\n".join(f"epoch={i} train/loss={1/(i+1)}" for i in range(100))
    source = app.state.library.ingest(workspace, "training.log", "log", [(1, text)])
    assert len(app.state.library.chunks(workspace)) > 1
    result = analyze(client, workspace, source["id"]).json()
    assert result["point_count"] == 100 and result["total_lines"] == 100
    app.state.db.execute("DELETE FROM log_documents WHERE source_id=?", (source["id"],))
    assert analyze(client, workspace, source["id"]).status_code == 422
    duplicate = app.state.library.ingest(workspace, "training.log", "log", [(1, text)])
    assert duplicate["duplicate"] and duplicate["id"] == source["id"]
    assert analyze(client, workspace, source["id"]).json()["point_count"] == 100


def test_original_fallback_scoping_and_deletion(client, app, workspace):
    job = wait_import(client, submit(client, workspace, b"epoch=1 val/psnr=28dB\n", name="training.log"))
    source = job["result"]["id"]
    app.state.db.execute("DELETE FROM log_documents WHERE source_id=?", (source,))
    assert analyze(client, workspace, source).json()["point_count"] == 1
    other = client.post("/api/workspaces", json={"name": "other"}).json()["id"]
    assert analyze(client, other, source).status_code == 404
    paper = app.state.library.ingest(workspace, "paper.txt", "paper", [(1, "loss=1")])
    assert analyze(client, workspace, paper["id"]).status_code == 422
    client.delete("/api/sources/" + source)
    assert analyze(client, workspace, source).status_code == 404


def test_confirm_metric_server_snapshot_retention_and_manual_conversion(client, app, workspace):
    source = app.state.library.ingest(workspace, "run.log", "log", [(1, "epoch=1 val/psnr=28dB\nepoch=2 val/psnr=29dB")])
    result = analyze(client, workspace, source["id"]).json()
    metric = selected_metric(result)
    record = create(client, workspace, metrics=[metric])
    evidence = record["metric_evidence"]["psnr"]
    assert evidence["line"] == 2 and evidence["value"] == 29 and evidence["text"] == "epoch=2 val/psnr=29dB"
    client.delete("/api/sources/" + source["id"])
    assert app.state.db.one("SELECT * FROM log_documents WHERE source_id=?", (source["id"],)) is None
    saved = client.patch(path(workspace) + "/" + record["id"], json=update_body(record, conclusion="keep")).json()
    assert saved["metric_evidence"] == record["metric_evidence"]
    exported = client.get(path(workspace) + "/" + record["id"] + "/export").text
    assert "run.log:L2" in exported and result["checksum"] in exported
    changed = {**metric, "value": 30}
    assert client.patch(path(workspace) + "/" + record["id"], json=update_body(saved, metrics=[changed])).status_code == 422
    manual = {**changed, "origin": None}
    updated = client.patch(path(workspace) + "/" + record["id"], json=update_body(saved, metrics=[manual])).json()
    assert updated["metric_evidence"] == {} and updated["metrics"][0]["value"] == 30


@pytest.mark.parametrize("change", ["value", "checksum", "point_id", "source_id", "evidence"])
def test_forged_metric_rejected_without_partial_record(client, app, workspace, change):
    source = app.state.library.ingest(workspace, "run.log", "log", [(1, "val/psnr=28dB")])
    m = selected_metric(analyze(client, workspace, source["id"]).json())
    if change == "value":
        m["value"] = 999
    elif change == "evidence":
        m["origin"]["text"] = "made up"
    else:
        m["origin"][change] = "0" * {"checksum": 64, "point_id": 24, "source_id": 32}[change]
    response = client.post(path(workspace), json={"name": "forged", "metrics": [m]})
    assert response.status_code in {404, 409, 422}
    assert client.get(path(workspace)).json() == []


def test_cross_workspace_metric_and_old_revision_cannot_override(client, app, workspace):
    source = app.state.library.ingest(workspace, "run.log", "log", [(1, "val/psnr=28dB")])
    m = selected_metric(analyze(client, workspace, source["id"]).json())
    other = client.post("/api/workspaces", json={"name": "other"}).json()["id"]
    assert client.post(path(other), json={"name": "wrong", "metrics": [m]}).status_code == 404
    record = create(client, workspace, metrics=[m])
    client.patch(path(workspace) + "/" + record["id"], json=update_body(record, conclusion="keep"))
    assert client.patch(path(workspace) + "/" + record["id"], json=update_body(record)).status_code == 409
    clone = client.post(path(workspace) + "/" + record["id"] + "/clone", json={"revision": 2}).json()
    assert clone["metrics"] == [] and clone["metric_evidence"] == {}


def test_log_and_metric_snapshots_survive_restart(settings):
    with TestClient(create_app(settings)) as client:
        workspace = client.post("/api/workspaces", json={"name": "persist"}).json()["id"]
        source = client.post(f"/api/workspaces/{workspace}/logs/demo").json()
        analysis = analyze(client, workspace, source["id"]).json()
        record = create(client, workspace, metrics=[selected_metric(analysis)])
    with TestClient(create_app(settings)) as client:
        assert analyze(client, workspace, source["id"]).json()["series"] == analysis["series"]
        restored = client.get(path(workspace) + "/" + record["id"]).json()
        assert restored["metric_evidence"] == record["metric_evidence"]
        duplicate = client.post(f"/api/workspaces/{workspace}/logs/demo").json()
        assert duplicate["id"] == source["id"] and duplicate["duplicate"]
