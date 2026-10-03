import io

from PIL import Image
from pypdf import PdfReader, PdfWriter

from test_api import make_pdf
from test_imports import submit, wait_import


def test_original_page_preview_renders_text_and_respects_page_and_size(client, workspace):
    writer = PdfWriter(clone_from=PdfReader(io.BytesIO(make_pdf("Visible scientific evidence on page one."))))
    writer.add_blank_page(width=600, height=800)
    buffer = io.BytesIO()
    writer.write(buffer)
    job = wait_import(client, submit(client, workspace, buffer.getvalue()))
    source = job["result"]["id"]
    path = f"/api/sources/{source}/pages"
    response = client.get(path + "/1?width=600")
    assert response.status_code == 200 and response.headers["content-type"] == "image/png"
    assert response.headers["cache-control"] == "no-store"
    with Image.open(io.BytesIO(response.content)) as first:
        assert first.size == (600, 800)
        low, high = first.convert("L").getextrema()
        assert low < 100 and high == 255  # Visible ink; not an empty placeholder.
    second = client.get(path + "/2?width=600")
    with Image.open(io.BytesIO(second.content)) as blank:
        assert blank.convert("L").getextrema() == (255, 255)
    enlarged = client.get(path + "/1?width=2200")
    with Image.open(io.BytesIO(enlarged.content)) as image:
        assert max(image.size) <= 2400
    for suffix in ["/0", "/3", "/1?width=10000", "/1?width=1"]:
        assert client.get(path + suffix).status_code == 422
    assert client.get("/api/sources/missing/pages/1").status_code == 404


def test_preview_of_text_and_legacy_sources_is_explicit(client, workspace):
    legacy = client.post(f"/api/workspaces/{workspace}/upload", files={"file": ("old.pdf", make_pdf("Legacy source"))}).json()
    assert client.get(f"/api/sources/{legacy['id']}/pages/1").status_code == 404
    job = wait_import(client, submit(client, workspace, b"Plain text evidence", "notes.txt"))
    assert client.get(f"/api/sources/{job['result']['id']}/pages/1").status_code == 422
