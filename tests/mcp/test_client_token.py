"""Tests for MCP client bearer-token propagation."""

import asyncio

import pytest

from cairn_mail.mcp import client as mcp_client
from cairn_mail.mcp.client import APIError, CairnMailClient

TOKEN = "mcp-token"


def test_resolve_prefers_literal(monkeypatch, tmp_path):
    f = tmp_path / "token"
    f.write_text("from-file")
    monkeypatch.setenv(mcp_client.TOKEN_ENV, TOKEN)
    monkeypatch.setenv(mcp_client.TOKEN_FILE_ENV, str(f))
    assert mcp_client._resolve_api_token() == TOKEN


def test_resolve_reads_file(monkeypatch, tmp_path):
    f = tmp_path / "token"
    f.write_text(f"  {TOKEN}\n")
    monkeypatch.delenv(mcp_client.TOKEN_ENV, raising=False)
    monkeypatch.setenv(mcp_client.TOKEN_FILE_ENV, str(f))
    assert mcp_client._resolve_api_token() == TOKEN


def test_resolve_none(monkeypatch):
    monkeypatch.delenv(mcp_client.TOKEN_ENV, raising=False)
    monkeypatch.delenv(mcp_client.TOKEN_FILE_ENV, raising=False)
    assert mcp_client._resolve_api_token() is None


def test_client_attaches_authorization_header(monkeypatch):
    monkeypatch.setenv(mcp_client.TOKEN_ENV, TOKEN)
    client = CairnMailClient()
    try:
        assert client._client.headers.get("authorization") == f"Bearer {TOKEN}"
    finally:
        asyncio.run(client.close())


def test_client_without_token_fails_closed(monkeypatch):
    monkeypatch.delenv(mcp_client.TOKEN_ENV, raising=False)
    monkeypatch.delenv(mcp_client.TOKEN_FILE_ENV, raising=False)
    client = CairnMailClient()
    try:
        with pytest.raises(APIError) as exc:
            asyncio.run(client._request("GET", "/api/accounts"))
        assert "token" in str(exc.value).lower()
    finally:
        asyncio.run(client.close())
