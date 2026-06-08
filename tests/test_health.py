from fastapi.testclient import TestClient

from analisador_videos.main import app


def test_health():
    client = TestClient(app)
    r = client.get("/health")
    assert r.status_code == 200
    data = r.json()
    assert data["status"] == "ok"
    assert data["backend"] in ("cpu", "cuda")
    assert data["mode"] in ("cpu", "gpu")
    assert data["mode_label"] in ("CPU", "CPU + GPU")
    assert "detection_summary" in data
    assert "sample_fps" in data
