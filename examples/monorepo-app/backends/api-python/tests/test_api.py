import pytest
from fastapi.testclient import TestClient
from app.main import app


@pytest.fixture
def client():
    return TestClient(app)


def test_health(client):
    r = client.get("/health")
    assert r.status_code == 200
    assert r.json()["status"] == "healthy"


def test_create_and_list_items(client):
    r = client.post("/api/v1/items", json={"name": "Test", "price": 9.99})
    assert r.status_code == 201
    item = r.json()
    assert item["name"] == "Test"

    r = client.get("/api/v1/items")
    assert r.status_code == 200
    assert len(r.json()) >= 1
