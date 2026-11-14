"""Phase 7 Hardening & Edge-Case Verification Tests.

Verifies:
- All Section 10 error and edge cases
- File and content size limits (Text 20k chars, HTML 400KB, Image 8MB)
- Unsupported image format rejection
- DEMO_REPLAY safety net fallback
- OCR availability handling
- Completely offline zero-CDN self-contained validation
"""

import io
import os
import pytest
from PIL import Image

os.environ["CHEEK_MOCK"] = "1"

import config
from app import app, engine_adapter


@pytest.fixture(scope="module", autouse=True)
def warmup():
    engine_adapter._do_warmup()


@pytest.fixture
def client():
    app.config["TESTING"] = True
    with app.test_client() as client:
        yield client


class TestInputSizeLimits:
    def test_empty_content_rejected(self, client):
        res = client.post("/api/analyze", json={"mode": "text", "content": "   "})
        assert res.status_code == 400
        data = res.get_json()
        assert data["error"]["code"] == "bad_input"

    def test_text_over_20k_chars_rejected(self, client):
        long_text = "A" * (config.MAX_TEXT_CHARS + 10)
        res = client.post("/api/analyze", json={"mode": "text", "content": long_text})
        assert res.status_code == 400
        data = res.get_json()
        assert data["error"]["code"] == "too_large"
        assert "20,000" in data["error"]["message"]

    def test_html_over_400kb_rejected(self, client):
        huge_html = "<div>" + ("hello world " * 400_000) + "</div>"
        assert len(huge_html.encode("utf-8")) > config.MAX_HTML_BYTES
        res = client.post("/api/analyze", json={"mode": "html", "content": huge_html})
        assert res.status_code == 400
        data = res.get_json()
        assert data["error"]["code"] == "too_large"
        assert f"{config.MAX_HTML_BYTES // 1024} KB" in data["error"]["message"]

    def test_image_over_8mb_rejected(self, client):
        fake_huge_bytes = b"\x89PNG\r\n\x1a\n" + (b"\x00" * (config.MAX_IMAGE_BYTES + 100))
        buf = io.BytesIO(fake_huge_bytes)
        res = client.post("/api/analyze", data={
            "mode": "screenshot",
            "file": (buf, "huge.png")
        }, content_type="multipart/form-data")
        assert res.status_code == 400
        data = res.get_json()
        assert data["error"]["code"] == "too_large"
        assert "8 MB" in data["error"]["message"]


class TestImageTypeValidation:
    def test_fake_text_file_as_image_rejected(self, client):
        buf = io.BytesIO(b"This is just a plain text file pretending to be an image.")
        res = client.post("/api/analyze", data={
            "mode": "screenshot",
            "file": (buf, "fake.png")
        }, content_type="multipart/form-data")
        assert res.status_code == 400
        data = res.get_json()
        assert data["error"]["code"] == "unsupported_type"
        assert "PNG, JPEG or WEBP" in data["error"]["message"]

    def test_gif_file_rejected(self, client):
        img = Image.new("RGB", (50, 50), color=(255, 0, 0))
        buf = io.BytesIO()
        img.save(buf, format="GIF")
        buf.seek(0)
        res = client.post("/api/analyze", data={
            "mode": "screenshot",
            "file": (buf, "test.gif")
        }, content_type="multipart/form-data")
        assert res.status_code == 400
        data = res.get_json()
        assert data["error"]["code"] == "unsupported_type"
        assert "PNG, JPEG or WEBP" in data["error"]["message"]


class TestOcrUnavailable:
    def test_ocr_unavailable_returns_503(self, client, monkeypatch):
        # Force ocr_ready to False
        monkeypatch.setattr(engine_adapter, "_ocr_ready", False)
        img = Image.new("RGB", (50, 50), color=(255, 255, 255))
        buf = io.BytesIO()
        img.save(buf, format="PNG")
        buf.seek(0)

        res = client.post("/api/analyze", data={
            "mode": "screenshot",
            "file": (buf, "test.png")
        }, content_type="multipart/form-data")
        assert res.status_code == 503
        data = res.get_json()
        assert data["error"]["code"] == "ocr_unavailable"

        # Verify text still works even when OCR is unavailable
        res_text = client.post("/api/analyze", json={"mode": "text", "content": "Free shipping"})
        assert res_text.status_code == 200


class TestDemoReplaySafetyNet:
    def test_demo_replay_returns_saved_result_on_failure(self, client, monkeypatch):
        monkeypatch.setattr(config, "DEMO_REPLAY", True)
        
        # Simulate engine failure
        def mock_failing_analyze(*args, **kwargs):
            raise RuntimeError("Engine model missing during demo")
        
        monkeypatch.setattr(engine_adapter, "analyze", mock_failing_analyze)

        res = client.post("/api/analyze", json={
            "mode": "text",
            "content": "Hurry! Only 2 left in stock."
        })
        assert res.status_code == 200
        data = res.get_json()
        assert data["_isSavedResult"] is True
        assert data["summary"]["status"] == "flagged"


class TestOfflineZeroCdnIntegrity:
    def test_index_html_has_no_cdn_or_external_urls(self):
        index_path = os.path.join(config.BASE_DIR, "static", "index.html")
        with open(index_path, "r", encoding="utf-8") as f:
            html = f.read()

        # Check for external script or stylesheet links
        assert "https://" not in html.replace("https://www.w3.org/2000/svg", "")
        assert "http://" not in html.replace("http://www.w3.org/2000/svg", "")
        assert "cdn." not in html.lower()
        assert "unpkg.com" not in html.lower()
        assert "cdnjs.cloudflare.com" not in html.lower()
