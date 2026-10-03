import io
import time

from pypdf import PdfWriter
from pypdf.generic import DecodedStreamObject, DictionaryObject, NameObject


def wait_task(client, task_id):
    for _ in range(100):
        result = client.get(f"/api/tasks/{task_id}").json()
        if result["status"] not in {"queued", "running"}:
            return result
        time.sleep(.02)
    raise AssertionError("Task failed to finish")


def make_pdf(text=None):
    writer = PdfWriter()
    page = writer.add_blank_page(width=600, height=800)
    if text:
        font = DictionaryObject({NameObject("/Type"):NameObject("/Font"), NameObject("/Subtype"):NameObject("/Type1"), NameObject("/BaseFont"):NameObject("/Helvetica")})
        page[NameObject("/Resources")] = DictionaryObject({NameObject("/Font"):DictionaryObject({NameObject("/F1"):writer._add_object(font)})})
        stream = DecodedStreamObject()
        stream.set_data(f"BT /F1 12 Tf 50 700 Td ({text}) Tj ET".encode())
        page[NameObject("/Contents")] = writer._add_object(stream)
    buffer = io.BytesIO()
    writer.write(buffer)
    return buffer.getvalue()


def test_full_offline_journey_and_report(client, demo):
    sources = client.get(f"/api/workspaces/{demo}/sources").json()
    assert len(sources) == 6
    for intent, prompt in [("qa", "方法 训练目标"), ("plan", "制定复现计划"), ("diagnose", "分析错误日志")]:
        created = client.post(f"/api/workspaces/{demo}/tasks", json={"prompt":prompt,"intent":intent})
        assert created.status_code == 202
        task = wait_task(client, created.json()["id"])
        assert task["status"] == "completed", task
        assert task["citations"]
        assert "离线演示" in task["answer"]
        assert task["usage"]["tool_calls"] <= 8
        assert task["usage"]["tool_success"] == task["usage"]["tool_calls"]
        assert "total_tokens" not in task["usage"]
        report = client.get(f"/api/tasks/{task['id']}/report")
        assert report.status_code == 200 and "引用原文" in report.text
        assert "attachment" in report.headers["content-disposition"]
    tasks = client.get(f"/api/workspaces/{demo}/tasks").json()
    assert len(tasks) == 3


def test_pdf_has_page_grounded_evidence(client, workspace):
    result = client.post(f"/api/workspaces/{workspace}/upload", files={"file":("paper.pdf",make_pdf("Denoising uses residual prediction and MSE loss."),"application/pdf")})
    assert result.status_code == 201, result.text
    results = client.post(f"/api/workspaces/{workspace}/search", json={"query":"residual prediction"}).json()
    assert results[0]["page"] == 1
    assert results[0]["locator"] == "第 1 页"
    assert "MSE" in results[0]["text"]


def test_invalid_and_scanned_pdf_are_rejected(client, workspace):
    for payload in [b"not a pdf", make_pdf()]:
        result = client.post(f"/api/workspaces/{workspace}/upload", files={"file":("paper.pdf",payload,"application/pdf")})
        assert result.status_code == 422
    assert client.get(f"/api/workspaces/{workspace}/sources").json() == []


def test_dedup_and_project_isolation(client, demo):
    result = client.post(f"/api/workspaces/{demo}/demo").json()
    assert all(s["duplicate"] for s in result["sources"])
    assert len(client.get(f"/api/workspaces/{demo}/sources").json()) == 6
    second = client.post("/api/workspaces",json={"name":"other"}).json()["id"]
    assert client.post(f"/api/workspaces/{second}/search",json={"query":"TinyRestore"}).json() == []
    assert client.get(f"/api/workspaces/{second}/tasks").json() == []


def test_delete_source_preserves_report_snapshot(client, demo):
    created = client.post(f"/api/workspaces/{demo}/tasks",json={"prompt":"方法 训练目标"}).json()
    task = wait_task(client, created["id"])
    source = task["citations"][0]["source_id"]
    assert client.delete(f"/api/sources/{source}").status_code == 204
    assert client.get(f"/api/sources/{source}").status_code == 404
    assert client.get(f"/api/tasks/{task['id']}").json()["citations"] == task["citations"]


def test_missing_evidence_does_not_invent_answer(client, workspace):
    created = client.post(f"/api/workspaces/{workspace}/tasks",json={"prompt":"未知的理论"}).json()
    task = wait_task(client, created["id"])
    assert task["status"] == "insufficient_evidence"
    assert task["citations"] == []


def test_validation_and_local_request_boundary(client, workspace, app):
    assert client.post("/api/workspaces",json={"name":"   "}).status_code == 422
    assert client.post(f"/api/workspaces/{workspace}/tasks",json={"prompt":"hi","intent":"shell"}).status_code == 422
    assert client.post(f"/api/workspaces/{workspace}/search",json={"query":"hi","k":1000}).status_code == 422
    assert client.post("/api/workspaces",json={"name":"x"},headers={"Origin":"https://evil.example"}).status_code == 403
    assert client.get("/api/health",headers={"Host":"evil.example"}).status_code == 400
    assert client.post("/api/workspaces",json={"name":"x"},headers={"Content-Length":str(app.state.settings.max_upload_bytes + 100_001)}).status_code == 413
    assert client.get("/api/workspaces/missing/sources").status_code == 404
    assert client.get("/api/tasks/missing").status_code == 404


def test_static_ui_and_no_secrets_in_health(client):
    assert client.get("/").status_code == 200
    assert "frame-ancestors 'none'" in client.get("/").headers["content-security-policy"]
    assert client.get("/static/app.js").status_code == 200
    health = client.get("/api/health").json()
    assert health["mode"] == "offline" and health["retrieval"] == "BM25"
    assert "api_key" not in health and "github_token" not in health
