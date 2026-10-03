import io

import pytest
from fastapi.testclient import TestClient
from pypdf import PdfReader, PdfWriter

from researchpilot.app import create_app
from researchpilot.config import Settings
from test_api import make_pdf


def test_default_accepts_pdf_larger_than_old_15mb_limit(client, workspace):
    writer = PdfWriter(clone_from=PdfReader(io.BytesIO(make_pdf("A large paper with extractable scientific text."))))
    # A large non-text stream simulates a figure-heavy paper without inflating extracted text.
    writer.add_attachment("large-figure.bin", b"\x00" * (16 * 1024 * 1024))
    buffer = io.BytesIO()
    writer.write(buffer)
    data = buffer.getvalue()
    assert len(data) > 15 * 1024 * 1024
    limits = client.get("/api/health").json()["limits"]
    assert limits["max_upload_mb"] == 200
    assert limits["max_upload_bytes"] == 200 * 1024 * 1024
    response = client.post(f"/api/workspaces/{workspace}/upload", files={"file": ("large.pdf", data, "application/pdf")})
    assert response.status_code == 201, response.text
    assert response.json()["chunk_count"] == 1


def test_configurable_exact_boundary_and_both_rejection_layers(tmp_path):
    settings = Settings(data_dir=tmp_path, max_upload_mb=1)
    with TestClient(create_app(settings)) as client:
        workspace = client.post("/api/workspaces", json={"name": "small-limit"}).json()["id"]
        path = f"/api/workspaces/{workspace}/upload"
        # Invalid content exactly at the limit reaches validation (422), rather than a size rejection (413).
        response = client.post(path, files={"file": ("invalid.pdf", b"x" * settings.max_upload_bytes)})
        assert response.status_code == 422 and "PDF" in response.json()["detail"]
        # 1 byte over: multipart envelope still fits; per-file validation must reject it.
        response = client.post(path, files={"file": ("oversized.pdf", b"x" * (settings.max_upload_bytes + 1))})
        assert response.status_code == 413
        assert response.json()["code"] == "upload_too_large"
        assert response.json()["limit_bytes"] == settings.max_upload_bytes
        assert "1 MB" in response.json()["detail"]
        # Much larger: middleware rejects before multipart parsing.
        response = client.post(path, content=b"", headers={"Content-Length": str(settings.max_upload_bytes + 100_001)})
        assert response.status_code == 413 and "1 MB" in response.json()["detail"]
        assert client.get("/api/health").json()["limits"]["max_upload_mb"] == 1
        assert client.get(f"/api/workspaces/{workspace}/sources").json() == []


def test_unreadable_pdf_error_remains_specific(client, workspace, caplog):
    response = client.post(f"/api/workspaces/{workspace}/upload", files={"file": ("scan.pdf", make_pdf())})
    assert response.status_code == 422
    assert "OCR" in response.json()["detail"]
    assert "Upload rejected" in caplog.text and "OCR" in caplog.text
    assert "scan.pdf" not in caplog.text


def test_upload_limit_environment(monkeypatch):
    monkeypatch.setenv("RP_MAX_UPLOAD_MB", "100")
    assert Settings.from_env().max_upload_bytes == 100 * 1024 * 1024


@pytest.mark.parametrize("value", [0, -1, 513])
def test_invalid_upload_limit_fails_at_startup(value):
    with pytest.raises(ValueError, match="RP_MAX_UPLOAD_MB"):
        Settings(max_upload_mb=value)
