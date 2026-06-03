from fastapi.testclient import TestClient

from analisador_videos.main import app


def test_health():
    client = TestClient(app)
    r = client.get("/health")
    assert r.status_code == 200
    data = r.json()
    assert data["status"] == "ok"
    assert "backend" in data
    assert "sample_fps" in data
