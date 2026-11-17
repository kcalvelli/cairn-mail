"""SPA fallback: client-side routes get the shell, real 404s stay 404s."""

from fastapi import FastAPI
from fastapi.testclient import TestClient

from cairn_mail.api.main import CachedStaticFiles


def _client(tmp_path):
    (tmp_path / "index.html").write_text("<html>shell</html>")
    (tmp_path / "assets").mkdir()
    (tmp_path / "assets" / "app-abc123.js").write_text("console.log(1)")
    app = FastAPI()
    app.mount("/", CachedStaticFiles(directory=str(tmp_path), html=True), name="static")
    return TestClient(app)


def test_deep_link_gets_shell_uncached(tmp_path):
    r = _client(tmp_path).get("/messages/companies:INBOX:44699")
    assert r.status_code == 200
    assert "shell" in r.text
    assert r.headers["cache-control"] == "no-cache"
    assert "etag" not in r.headers


def test_compose_with_query_gets_shell(tmp_path):
    r = _client(tmp_path).get("/compose?reply_to=abc&subject=Re%3A+hi")
    assert r.status_code == 200 and "shell" in r.text


def test_real_assets_still_served(tmp_path):
    r = _client(tmp_path).get("/assets/app-abc123.js")
    assert r.status_code == 200
    assert "immutable" in r.headers["cache-control"]


def test_missing_asset_is_a_real_404(tmp_path):
    assert _client(tmp_path).get("/assets/gone-deadbeef.js").status_code == 404


def test_unknown_api_path_is_a_real_404(tmp_path):
    assert _client(tmp_path).get("/api/nope").status_code == 404
