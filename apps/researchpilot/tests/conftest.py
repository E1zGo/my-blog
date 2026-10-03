import pytest
from fastapi.testclient import TestClient

from researchpilot.app import create_app
from researchpilot.config import Settings


@pytest.fixture
def settings(tmp_path):
    return Settings(data_dir=tmp_path)


@pytest.fixture
def app(settings):
    return create_app(settings)


@pytest.fixture
def client(app):
    with TestClient(app) as client:
        yield client


@pytest.fixture
def workspace(client):
    return client.post("/api/workspaces", json={"name": "test project"}).json()["id"]


@pytest.fixture
def demo(client, workspace):
    result = client.post(f"/api/workspaces/{workspace}/demo")
    assert result.status_code == 201, result.text
    return workspace
