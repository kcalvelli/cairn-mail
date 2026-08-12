"""Tests for API bearer-token authentication.

Covers the pure helpers in cairn_mail.api.auth and the middleware wiring via
auth.install_security on a minimal app (so we exercise the real security code
path without main.py's config/database/IDLE startup). The websocket tests mount
the real /ws endpoint.
"""

import pytest
from fastapi import FastAPI, HTTPException
from fastapi.testclient import TestClient
from starlette.websockets import WebSocketDisconnect

from cairn_mail.api import auth
from cairn_mail.api.websocket import router as websocket_router

TOKEN = "s3cr3t-token"


# --- Pure helpers -----------------------------------------------------------


def test_load_token_missing_env(monkeypatch):
    monkeypatch.delenv(auth.TOKEN_FILE_ENV, raising=False)
    with pytest.raises(RuntimeError):
        auth.load_token()


def test_load_token_empty_file(monkeypatch, tmp_path):
    f = tmp_path / "token"
    f.write_text("   \n")
    monkeypatch.setenv(auth.TOKEN_FILE_ENV, str(f))
    with pytest.raises(RuntimeError):
        auth.load_token()


def test_load_token_reads_and_strips(monkeypatch, tmp_path):
    f = tmp_path / "token"
    f.write_text(f"  {TOKEN}\n")
    monkeypatch.setenv(auth.TOKEN_FILE_ENV, str(f))
    assert auth.load_token() == TOKEN


@pytest.mark.parametrize(
    "header,expected",
    [
        (f"Bearer {TOKEN}", True),
        (f"bearer {TOKEN}", True),
        ("Bearer wrong", False),
        (TOKEN, False),  # no scheme
        ("", False),
        (None, False),
        ("Bearer ", False),
    ],
)
def test_token_matches(header, expected):
    assert auth.token_matches(header, TOKEN) is expected


@pytest.mark.parametrize(
    "path,needs",
    [
        ("/api/messages", True),
        ("/api/messages/abc", True),
        ("/api/health", False),
        ("/api/version", False),
        ("/api/clear-sw", False),
        ("/", False),
        ("/assets/app.js", False),
        ("/messages/123", False),  # SPA route served by static files
    ],
)
def test_path_requires_auth(path, needs):
    assert auth.path_requires_auth(path) is needs


def test_resolve_allowed_hosts_unset_is_permissive(monkeypatch):
    monkeypatch.delenv(auth.ALLOWED_HOSTS_ENV, raising=False)
    assert list(auth.resolve_allowed_hosts()) == ["*"]


def test_resolve_allowed_hosts_configured_includes_loopback(monkeypatch):
    monkeypatch.setenv(auth.ALLOWED_HOSTS_ENV, "edge.ts.net, other.host")
    hosts = list(auth.resolve_allowed_hosts())
    assert "localhost" in hosts and "127.0.0.1" in hosts
    assert "edge.ts.net" in hosts and "other.host" in hosts


# --- Middleware wiring ------------------------------------------------------


def _build_app(monkeypatch, allowed_hosts_env=None):
    if allowed_hosts_env is None:
        monkeypatch.delenv(auth.ALLOWED_HOSTS_ENV, raising=False)
    else:
        monkeypatch.setenv(auth.ALLOWED_HOSTS_ENV, allowed_hosts_env)
    app = FastAPI()
    auth.install_security(app, cors_origins=["http://localhost:5173"])
    app.state.api_token = TOKEN

    @app.get("/api/secret")
    async def secret():
        return {"ok": True}

    @app.get("/api/health")
    async def health():
        return {"status": "healthy"}

    @app.get("/api/boom")
    async def boom():
        raise ValueError("leak me: /secret/path and stack")

    app.include_router(websocket_router)
    return app


def _auth_headers(token=TOKEN):
    return {"Authorization": f"Bearer {token}"}


def test_valid_token_passes(monkeypatch):
    client = TestClient(_build_app(monkeypatch))
    r = client.get("/api/secret", headers=_auth_headers())
    assert r.status_code == 200 and r.json() == {"ok": True}


def test_missing_token_rejected(monkeypatch):
    client = TestClient(_build_app(monkeypatch))
    r = client.get("/api/secret")
    assert r.status_code == 401
    assert r.headers.get("www-authenticate") == "Bearer"


def test_incorrect_token_rejected(monkeypatch):
    client = TestClient(_build_app(monkeypatch))
    r = client.get("/api/secret", headers=_auth_headers("nope"))
    assert r.status_code == 401


def test_health_exempt(monkeypatch):
    client = TestClient(_build_app(monkeypatch))
    assert client.get("/api/health").status_code == 200


def test_trusted_host_allows_configured(monkeypatch):
    client = TestClient(_build_app(monkeypatch, allowed_hosts_env="edge.ts.net"))
    r = client.get("/api/health", headers={"host": "edge.ts.net"})
    assert r.status_code == 200


def test_trusted_host_rejects_unexpected(monkeypatch):
    client = TestClient(_build_app(monkeypatch, allowed_hosts_env="edge.ts.net"))
    r = client.get("/api/health", headers={"host": "evil.example.com"})
    assert r.status_code == 400  # TrustedHostMiddleware


def test_generic_500_no_exception_text(monkeypatch):
    client = TestClient(_build_app(monkeypatch), raise_server_exceptions=False)
    r = client.get("/api/boom", headers=_auth_headers())
    assert r.status_code == 500
    assert r.json() == {"detail": "Internal server error"}
    assert "leak me" not in r.text


# --- WebSocket handshake ----------------------------------------------------


def test_ws_valid_token_connects(monkeypatch):
    client = TestClient(_build_app(monkeypatch))
    with client.websocket_connect(f"/ws?token={TOKEN}") as ws:
        msg = ws.receive_json()
        assert msg["type"] == "connected"


def test_ws_missing_token_rejected(monkeypatch):
    client = TestClient(_build_app(monkeypatch))
    with pytest.raises(WebSocketDisconnect):
        with client.websocket_connect("/ws") as ws:
            ws.receive_json()


def test_ws_incorrect_token_rejected(monkeypatch):
    client = TestClient(_build_app(monkeypatch))
    with pytest.raises(WebSocketDisconnect):
        with client.websocket_connect("/ws?token=wrong") as ws:
            ws.receive_json()
