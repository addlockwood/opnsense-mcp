from __future__ import annotations

from pathlib import Path

import pytest

from opnsense_mcp.config import AppConfig


def test_validate_runtime_allows_https_by_default(tmp_path: Path) -> None:
    config = AppConfig(
        base_url="https://router.example",
        api_key="key",
        api_secret="secret",
        verify_tls=True,
        allow_insecure_http=False,
        workspace_path=tmp_path,
        snapshot_host="this",
        git_author_name="Test User",
        git_author_email="test@example.com",
        transport="stdio",
        http_host="127.0.0.1",
        http_port=8000,
        http_path="/mcp",
        image_ref="",
    )

    config.validate_runtime()


def test_validate_runtime_rejects_plain_http_without_opt_in(tmp_path: Path) -> None:
    config = AppConfig(
        base_url="http://opnsense.internal",
        api_key="key",
        api_secret="secret",
        verify_tls=False,
        allow_insecure_http=False,
        workspace_path=tmp_path,
        snapshot_host="this",
        git_author_name="Test User",
        git_author_email="test@example.com",
        transport="stdio",
        http_host="127.0.0.1",
        http_port=8000,
        http_path="/mcp",
        image_ref="",
    )

    with pytest.raises(ValueError, match="OPNSENSE_ALLOW_INSECURE_HTTP=true"):
        config.validate_runtime()


def test_validate_runtime_allows_plain_http_with_explicit_opt_in(tmp_path: Path) -> None:
    config = AppConfig(
        base_url="http://opnsense.internal",
        api_key="key",
        api_secret="secret",
        verify_tls=False,
        allow_insecure_http=True,
        workspace_path=tmp_path,
        snapshot_host="this",
        git_author_name="Test User",
        git_author_email="test@example.com",
        transport="stdio",
        http_host="127.0.0.1",
        http_port=8000,
        http_path="/mcp",
        image_ref="",
    )

    config.validate_runtime()


def test_validate_runtime_rejects_invalid_transport(tmp_path: Path) -> None:
    config = AppConfig(
        base_url="https://router.example",
        api_key="key",
        api_secret="secret",
        verify_tls=True,
        allow_insecure_http=False,
        workspace_path=tmp_path,
        snapshot_host="this",
        git_author_name="Test User",
        git_author_email="test@example.com",
        transport="http",
        http_host="127.0.0.1",
        http_port=8000,
        http_path="/mcp",
        image_ref="",
    )

    with pytest.raises(ValueError, match="OPNSENSE_MCP_TRANSPORT"):
        config.validate_runtime()
