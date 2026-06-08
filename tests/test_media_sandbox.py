import pytest
from fastapi import HTTPException
from fastapi.testclient import TestClient

from analisador_videos.config import settings
from analisador_videos.main import _resolve_media_path, app


@pytest.fixture
def client(tmp_path, monkeypatch):
    monkeypatch.setattr(settings, "data_dir", tmp_path)
    return TestClient(app)


def test_serve_valid_file_in_data_dir(client, tmp_path):
    media_file = tmp_path / "snapshots" / "test.jpg"
    media_file.parent.mkdir(parents=True)
    media_file.write_bytes(b"fake-jpg")

    response = client.get("/media/snapshots/test.jpg")

    assert response.status_code == 200
    assert response.content == b"fake-jpg"


def test_serve_file_with_data_prefix(client, tmp_path):
    media_file = tmp_path / "snapshots" / "test.jpg"
    media_file.parent.mkdir(parents=True)
    media_file.write_bytes(b"fake-jpg")

    response = client.get("/media/data/snapshots/test.jpg")

    assert response.status_code == 200
    assert response.content == b"fake-jpg"


def test_serve_absolute_path_inside_data_dir(client, tmp_path):
    media_file = tmp_path / "snapshots" / "test.jpg"
    media_file.parent.mkdir(parents=True)
    media_file.write_bytes(b"fake-jpg")

    response = client.get(f"/media/{media_file.as_posix()}")

    assert response.status_code == 200
    assert response.content == b"fake-jpg"


def test_block_path_traversal(tmp_path, monkeypatch):
    monkeypatch.setattr(settings, "data_dir", tmp_path)
    secret = tmp_path.parent / "secret.txt"
    secret.write_text("secret")

    with pytest.raises(HTTPException) as exc_info:
        _resolve_media_path("snapshots/../../secret.txt")

    assert exc_info.value.status_code == 403


def test_block_file_outside_data_dir(client, tmp_path):
    outside = tmp_path.parent / "outside.txt"
    outside.write_text("outside")

    response = client.get(f"/media/{outside.as_posix()}")

    assert response.status_code == 403


def test_missing_file_returns_404(client, tmp_path):
    response = client.get("/media/snapshots/missing.jpg")

    assert response.status_code == 404
