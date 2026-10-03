import io
import time
from threading import Event

import pytest
from fastapi.testclient import TestClient
from pypdf import PdfReader, PdfWriter

from researchpilot.app import create_app
from researchpilot.config import Settings
from researchpilot.db import now, uid
from test_api import make_pdf


def wait_import(client, identifier):
    for _ in range(200):
        job = client.get(f"/api/imports/{identifier}").json()
        if job["status"] in {"completed", "failed", "cancelled"}:
            return job
        time.sleep(.01)
    raise AssertionError("Import did not finish")


def submit(client, workspace, data, name="paper.pdf"):
    response = client.post(f"/api/workspaces/{workspace}/imports", files={"file": (name, data)})
    assert response.status_code == 202, response.text
    return response.json()["id"]


def test_original_range_download_dedup_and_delete(client, app, workspace):
    data = make_pdf("Residual prediction uses MSE loss.")
    first = wait_import(client, submit(client, workspace, data))
    assert first["status"] == "completed", first
    assert first["current_page"] == first["total_pages"] == 1
    source_id = first["result"]["id"]
    source = client.get(f"/api/sources/{source_id}").json()
    assert source["has_original"]
    assert source["metadata"]["text_pages"] == 1
    path = f"/api/sources/{source_id}/original"
    response = client.get(path)
    assert response.content == data and "inline" in response.headers["content-disposition"]
    part = client.get(path, headers={"Range": "bytes=0-4"})
    assert part.status_code == 206 and part.content == b"%PDF-"
    assert "attachment" in client.get(path + "?download=true").headers["content-disposition"]
    second = wait_import(client, submit(client, workspace, data))
    assert second["result"]["id"] == source_id and second["result"]["duplicate"]
    assert second["result"]["metadata"]["original_id"] == first["id"]
    app.state.imports.close()  # Wait for staging-file cleanup after the commit.
    assert list(app.state.imports.directory.glob("*.bin")) == [app.state.imports.path(first["id"])]
    assert len(client.get(f"/api/workspaces/{workspace}/imports").json()) == 2
    assert client.delete(f"/api/sources/{source_id}").status_code == 204
    assert client.get(path).status_code == 404
    assert not app.state.imports.path(first["id"]).exists()


def test_old_source_reupload_attaches_original(client, workspace):
    data = make_pdf("Text imported before originals were supported.")
    old = client.post(f"/api/workspaces/{workspace}/upload", files={"file": ("paper.pdf", data)}).json()
    assert client.get(f"/api/sources/{old['id']}/original").status_code == 404
    job = wait_import(client, submit(client, workspace, data))
    assert job["result"]["duplicate"] and job["result"]["id"] == old["id"]
    assert client.get(f"/api/sources/{old['id']}/original").content == data
    assert len(client.get(f"/api/workspaces/{workspace}/sources").json()) == 1


@pytest.mark.parametrize("data,reason", [(b"not pdf", "PDF"), (make_pdf(), "OCR")])
def test_failed_import_has_durable_reason_and_no_source(client, app, workspace, data, reason):
    job = wait_import(client, submit(client, workspace, data))
    assert job["status"] == "failed" and reason in job["error"]
    app.state.imports.close()
    assert not app.state.imports.path(job["id"]).exists()
    assert not client.get(f"/api/workspaces/{workspace}/sources").json()
    assert reason in client.get(f"/api/workspaces/{workspace}/imports").json()[0]["error"]


def test_cancel_during_indexing_rolls_back_source_and_chunks(client, app, workspace, monkeypatch):
    arrived, release = Event(), Event()
    original_progress = app.state.imports.progress

    def progress(identifier, phase, *args):
        original_progress(identifier, phase, *args)
        if phase == "indexing":
            arrived.set()
            assert release.wait(5)

    monkeypatch.setattr(app.state.imports, "progress", progress)
    identifier = submit(client, workspace, make_pdf("Cancel before committing this source."))
    try:
        assert arrived.wait(5)
        result = client.post(f"/api/imports/{identifier}/cancel").json()
        assert result["status"] == "cancelled"
    finally:
        release.set()
    app.state.imports.close()
    assert not client.get(f"/api/workspaces/{workspace}/sources").json()
    assert app.state.db.one("SELECT COUNT(*) AS n FROM chunks")["n"] == 0
    assert not app.state.imports.path(identifier).exists()
    assert client.get(f"/api/imports/{identifier}").json()["status"] == "cancelled"


def test_page_progress_and_partial_scan_warning(client, app, workspace, monkeypatch):
    writer = PdfWriter(clone_from=PdfReader(io.BytesIO(make_pdf("Page one has searchable evidence."))))
    writer.add_blank_page(width=600, height=800)
    stream = io.BytesIO()
    writer.write(stream)
    updates = []
    original_progress = app.state.imports.progress

    def progress(identifier, phase, current, total, message):
        updates.append((phase, current, total))
        original_progress(identifier, phase, current, total, message)

    monkeypatch.setattr(app.state.imports, "progress", progress)
    job = wait_import(client, submit(client, workspace, stream.getvalue()))
    assert job["status"] == "completed"
    assert ("parsing", 0, 2) in updates and ("parsing", 1, 2) in updates and ("parsing", 2, 2) in updates
    assert job["result"]["metadata"]["text_pages"] == 1
    assert "第 2 页" in job["result"]["metadata"]["warnings"][0]


def test_queue_capacity_and_queued_cancel(client, app, workspace, monkeypatch):
    from dataclasses import replace
    monkeypatch.setattr(app.state.quotas, "settings", replace(app.state.settings, max_active_imports=8))
    # Keep queued jobs pending without allocating workers or relying on timing.
    monkeypatch.setattr(app.state.imports.pool, "submit", lambda *args: None)
    ids = [submit(client, workspace, b"Queued text", f"paper{i}.txt") for i in range(8)]
    response = client.post(f"/api/workspaces/{workspace}/imports", files={"file": ("ninth.txt", b"content")})
    assert response.status_code == 429
    assert client.post(f"/api/imports/{ids[0]}/cancel").json()["status"] == "cancelled"
    app.state.imports.run(ids[0])
    assert not app.state.imports.path(ids[0]).exists()
    assert submit(client, workspace, b"Next text", "next.txt")
    assert client.get("/api/imports/missing").status_code == 404
    assert client.post("/api/imports/missing/cancel").status_code == 404


def test_restart_keeps_completed_original_and_cleans_interrupted_files(tmp_path):
    settings = Settings(data_dir=tmp_path)
    app = create_app(settings)
    with TestClient(app) as client:
        workspace = client.post("/api/workspaces", json={"name": "restart"}).json()["id"]
        complete = wait_import(client, submit(client, workspace, make_pdf("Keep this original across restarts.")))
        interrupted = []
        for status in ["queued", "parsing", "cancelled"]:
            identifier = uid()
            interrupted.append(identifier)
            app.state.db.execute("INSERT INTO imports(id,workspace_id,name,kind,status,created_at) VALUES (?,?,?,'paper',?,?)",
                                 (identifier, workspace, "interrupted.pdf", status, now()))
            app.state.imports.path(identifier).write_bytes(b"temporary")
    restarted = create_app(settings)
    with TestClient(restarted) as client:
        for identifier in interrupted:
            job = client.get(f"/api/imports/{identifier}").json()
            assert job["status"] in {"failed", "cancelled"}
            assert not restarted.state.imports.path(identifier).exists()
        assert "重启" in client.get(f"/api/imports/{interrupted[0]}").json()["error"]
        assert client.get(f"/api/sources/{complete['result']['id']}/original").content.startswith(b"%PDF-")


def test_import_size_limit_and_stream_memory(tmp_path):
    # Real multipart goes through the async route, including its per-file byte check.
    settings = Settings(data_dir=tmp_path, max_upload_mb=1)
    app = create_app(settings)
    with TestClient(app) as client:
        workspace = client.post("/api/workspaces", json={"name": "limits"}).json()["id"]
        response = client.post(f"/api/workspaces/{workspace}/imports", files={"file": ("big.pdf", b"x" * (settings.max_upload_bytes + 1))})
        assert response.status_code == 413
        assert not list(app.state.imports.directory.glob("*.bin"))

        class BoundedStream(io.BytesIO):
            def read(self, size=-1):
                assert 0 <= size <= 1024 * 1024, "Originals must be copied in bounded blocks"
                return super().read(size)

        result = app.state.imports.submit(workspace, "text.txt", BoundedStream(b"bounded transfer"), "paper")
        assert wait_import(client, result["id"])["status"] == "completed"
