"""
Tests for pandoc-api.
Pandoc subprocess is mocked so no real Pandoc binary is needed.
"""
import base64
import io
import json
from unittest.mock import MagicMock, patch

import pytest

import app as app_module
from app import app as flask_app


@pytest.fixture(autouse=True)
def reset_api_key(monkeypatch):
    """Ensure API_KEY is empty by default for each test."""
    monkeypatch.setattr(app_module, "API_KEY", "")
    yield


@pytest.fixture()
def client():
    flask_app.config["TESTING"] = True
    with flask_app.test_client() as c:
        yield c


def _docx_file(name="test.docx"):
    return (io.BytesIO(b"PK fake docx content"), name)


# ---------------------------------------------------------------------------
# Health
# ---------------------------------------------------------------------------


def test_health(client):
    r = client.get("/health")
    assert r.status_code == 200
    assert r.get_json() == {"status": "ok"}


# ---------------------------------------------------------------------------
# Auth — key not set (open)
# ---------------------------------------------------------------------------


def test_no_auth_required_when_key_unset(client):
    with patch("app.subprocess.run") as mock_run, \
         patch("app.tempfile.TemporaryDirectory") as mock_tmp:
        _setup_successful_conversion(mock_run, mock_tmp)
        r = client.post("/convert", data={"file": _docx_file()},
                        content_type="multipart/form-data")
    assert r.status_code == 200


# ---------------------------------------------------------------------------
# Auth — key set
# ---------------------------------------------------------------------------


def test_correct_api_key_accepted(client, monkeypatch):
    monkeypatch.setattr(app_module, "API_KEY", "secret")
    with patch("app.subprocess.run") as mock_run, \
         patch("app.tempfile.TemporaryDirectory") as mock_tmp:
        _setup_successful_conversion(mock_run, mock_tmp)
        r = client.post(
            "/convert",
            data={"file": _docx_file()},
            content_type="multipart/form-data",
            headers={"X-API-Key": "secret"},
        )
    assert r.status_code == 200


def test_wrong_api_key_rejected(client, monkeypatch):
    monkeypatch.setattr(app_module, "API_KEY", "secret")
    r = client.post(
        "/convert",
        data={"file": _docx_file()},
        content_type="multipart/form-data",
        headers={"X-API-Key": "wrong"},
    )
    assert r.status_code == 401
    assert r.get_json() == {"error": "Unauthorized"}


def test_missing_api_key_rejected(client, monkeypatch):
    monkeypatch.setattr(app_module, "API_KEY", "secret")
    r = client.post(
        "/convert",
        data={"file": _docx_file()},
        content_type="multipart/form-data",
    )
    assert r.status_code == 401
    assert r.get_json() == {"error": "Unauthorized"}


# ---------------------------------------------------------------------------
# Input validation
# ---------------------------------------------------------------------------


def test_missing_file_field(client):
    r = client.post("/convert", data={}, content_type="multipart/form-data")
    assert r.status_code == 400
    assert "Missing" in r.get_json()["error"]


def test_wrong_extension_rejected(client):
    r = client.post(
        "/convert",
        data={"file": (io.BytesIO(b"data"), "document.pdf")},
        content_type="multipart/form-data",
    )
    assert r.status_code == 400
    assert "docx" in r.get_json()["error"].lower()


def test_no_filename_rejected(client):
    r = client.post(
        "/convert",
        data={"file": (io.BytesIO(b"data"), "")},
        content_type="multipart/form-data",
    )
    assert r.status_code == 400


# ---------------------------------------------------------------------------
# Successful conversion — no images
# ---------------------------------------------------------------------------


def test_successful_conversion_no_images(client):
    html_output = "<p>Hello world</p>"
    with patch("app.subprocess.run") as mock_run, \
         patch("app.tempfile.TemporaryDirectory") as mock_tmp:
        _setup_successful_conversion(mock_run, mock_tmp, html=html_output)
        r = client.post("/convert", data={"file": _docx_file()},
                        content_type="multipart/form-data")

    assert r.status_code == 200
    body = r.get_json()
    assert body["html"] == html_output
    assert body["images"] == {}


# ---------------------------------------------------------------------------
# Successful conversion — with images
# ---------------------------------------------------------------------------


def test_successful_conversion_with_images(client, tmp_path):
    img_bytes = b"\x89PNG fake"
    html_output = "<p>Doc with image</p>"

    # Build a fake temp dir on disk so rglob works
    media_dir = tmp_path / "media"
    media_dir.mkdir()
    img_file = media_dir / "image1.png"
    img_file.write_bytes(img_bytes)
    (tmp_path / "output.html").write_text(html_output, encoding="utf-8")

    mock_result = MagicMock()
    mock_result.returncode = 0

    ctx = MagicMock()
    ctx.__enter__ = MagicMock(return_value=str(tmp_path))
    ctx.__exit__ = MagicMock(return_value=False)

    with patch("app.subprocess.run", return_value=mock_result), \
         patch("app.tempfile.TemporaryDirectory", return_value=ctx):
        r = client.post("/convert", data={"file": _docx_file()},
                        content_type="multipart/form-data")

    assert r.status_code == 200
    body = r.get_json()
    assert body["html"] == html_output
    assert "media/image1.png" in body["images"]
    assert body["images"]["media/image1.png"] == base64.b64encode(img_bytes).decode()


# ---------------------------------------------------------------------------
# Pandoc failure
# ---------------------------------------------------------------------------


def test_pandoc_failure_returns_500(client, tmp_path):
    mock_result = MagicMock()
    mock_result.returncode = 1
    mock_result.stderr = "unknown format"

    ctx = MagicMock()
    ctx.__enter__ = MagicMock(return_value=str(tmp_path))
    ctx.__exit__ = MagicMock(return_value=False)

    with patch("app.subprocess.run", return_value=mock_result), \
         patch("app.tempfile.TemporaryDirectory", return_value=ctx):
        r = client.post("/convert", data={"file": _docx_file()},
                        content_type="multipart/form-data")

    assert r.status_code == 500
    assert "Pandoc conversion failed" in r.get_json()["error"]


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _setup_successful_conversion(mock_run, mock_tmp, html="<p>ok</p>"):
    """Wire up mocks for a clean Pandoc run with no images."""
    import tempfile as _tmpmod
    from pathlib import Path

    # Use a real temp dir so Path operations work
    real_tmp = _tmpmod.mkdtemp()
    Path(real_tmp, "output.html").write_text(html, encoding="utf-8")

    mock_result = MagicMock()
    mock_result.returncode = 0
    mock_run.return_value = mock_result

    ctx = MagicMock()
    ctx.__enter__ = MagicMock(return_value=real_tmp)
    ctx.__exit__ = MagicMock(return_value=False)
    mock_tmp.return_value = ctx
