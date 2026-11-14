"""Integration tests for all Flask API endpoints."""

import io
import os
import pytest
from PIL import Image

os.environ["CHEEK_MOCK"] = "1"

from app import app, engine_adapter


@pytest.fixture(scope="module", autouse=True)
def warmup():
    engine_adapter._do_warmup()


@pytest.fixture
def client():
    app.config["TESTING"] = True
    with app.test_client() as client:
        yield client


def test_health(client):
    res = client.get("/api/health")
    assert res.status_code == 200
    data = res.get_json()
    assert data["status"] == "ready"
    assert data["model_loaded"] is True
    assert data["engine"] == "mock"
    assert data["api_version"] == "1"


def test_model(client):
    res = client.get("/api/model")
    assert res.status_code == 200
    data = res.get_json()
    assert data["name"] == "DistilBERT"
    assert "classes" in data
    assert "macro_f1" in data
    assert "limitations" in data


def test_samples(client):
    res = client.get("/api/samples")
    assert res.status_code == 200
    samples = res.get_json()
    assert len(samples) >= 2


def test_analyze_deceptive_text(client):
    res = client.post("/api/analyze", json={
        "mode": "text",
        "content": "Hurry! Only 2 left in stock.\n8 people are viewing this right now."
    })
    assert res.status_code == 200
    data = res.get_json()
    assert data["mode"] == "text"
    assert data["summary"]["status"] == "flagged"
    assert data["summary"]["flagged_items"] > 0
    assert data["exposure"]["percent"] > 0
    assert len(data["findings"]) > 0


def test_analyze_clean_text(client):
    res = client.post("/api/analyze", json={
        "mode": "text",
        "content": "Ships in 2 business days.\nFree returns within 30 days."
    })
    assert res.status_code == 200
    data = res.get_json()
    assert data["summary"]["status"] == "clean"
    assert data["summary"]["flagged_items"] == 0
    assert data["exposure"]["percent"] == 0
    assert data["exposure"]["band"] == "fresh"


def test_analyze_html(client):
    res = client.post("/api/analyze", json={
        "mode": "html",
        "content": "<input type='checkbox' checked> Add Rs 199 order protection"
    })
    assert res.status_code == 200
    data = res.get_json()
    assert data["mode"] == "html"
    assert data["summary"]["status"] == "flagged"


def test_analyze_screenshot(client):
    img = Image.new("RGB", (200, 200), color=(255, 255, 255))
    buf = io.BytesIO()
    img.save(buf, format="PNG")
    buf.seek(0)

    res = client.post("/api/analyze", data={
        "mode": "screenshot",
        "file": (buf, "test.png")
    }, content_type="multipart/form-data")
    assert res.status_code == 200
    data = res.get_json()
    assert data["mode"] == "screenshot"
    assert "screenshot" in data
    assert data["screenshot"]["width"] == 200
    assert data["screenshot"]["height"] == 200
    assert data["screenshot"]["annotated"].startswith("data:image/jpeg;base64,")


def test_security_headers(client):
    res = client.get("/")
    assert "Content-Security-Policy" in res.headers
    assert res.headers["X-Content-Type-Options"] == "nosniff"
    assert res.headers["Referrer-Policy"] == "no-referrer"
    assert res.headers["X-Frame-Options"] == "DENY"


@pytest.mark.real_model
def test_real_model_inference():
    """Verify that real model tests skip with clear reason when outputs/model/ is empty."""
    from adapter import engine_adapter
    assert engine_adapter.get_health()["engine"] == "real"
