from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path
from urllib.parse import urlparse


def _bool_from_env(value: str | None, *, default: bool) -> bool:
    if value is None:
        return default
    return value.strip().lower() in {"1", "true", "yes", "on"}


@dataclass(frozen=True)
class AppConfig:
    base_url: str
    api_key: str
    api_secret: str
    verify_tls: bool
    allow_insecure_http: bool
    workspace_path: Path
    snapshot_host: str
    git_author_name: str
    git_author_email: str
    transport: str = "stdio"
    http_host: str = "127.0.0.1"
    http_port: int = 8000
    http_path: str = "/mcp"
    image_ref: str = ""
    request_timeout_seconds: float = 30.0

    @classmethod
    def from_env(cls) -> AppConfig:
        base_url = os.environ.get("OPNSENSE_BASE_URL", "").rstrip("/")
        api_key = os.environ.get("OPNSENSE_API_KEY", "")
        api_secret = os.environ.get("OPNSENSE_API_SECRET", "")
        workspace_path = Path(os.environ.get("OPNSENSE_WORKSPACE_PATH", "/workspace"))
        snapshot_host = os.environ.get("OPNSENSE_SNAPSHOT_HOST", "this")
        git_author_name = os.environ.get("OPNSENSE_GIT_AUTHOR_NAME", "OPNsense MCP")
        git_author_email = os.environ.get(
            "OPNSENSE_GIT_AUTHOR_EMAIL",
            "opnsense-mcp@example.invalid",
        )
        verify_tls = _bool_from_env(os.environ.get("OPNSENSE_VERIFY_TLS"), default=True)
        allow_insecure_http = _bool_from_env(
            os.environ.get("OPNSENSE_ALLOW_INSECURE_HTTP"),
            default=False,
        )
        transport = os.environ.get("OPNSENSE_MCP_TRANSPORT", "stdio").strip().lower() or "stdio"
        http_host = os.environ.get("OPNSENSE_MCP_HTTP_HOST", "127.0.0.1").strip() or "127.0.0.1"
        http_port = int(os.environ.get("OPNSENSE_MCP_HTTP_PORT", "8000"))
        http_path = os.environ.get("OPNSENSE_MCP_HTTP_PATH", "/mcp").strip() or "/mcp"
        image_ref = os.environ.get("OPNSENSE_MCP_IMAGE_REF", "").strip()

        return cls(
            base_url=base_url,
            api_key=api_key,
            api_secret=api_secret,
            verify_tls=verify_tls,
            allow_insecure_http=allow_insecure_http,
            workspace_path=workspace_path,
            snapshot_host=snapshot_host,
            git_author_name=git_author_name,
            git_author_email=git_author_email,
            transport=transport,
            http_host=http_host,
            http_port=http_port,
            http_path=http_path,
            image_ref=image_ref,
        )

    def validate_runtime(self) -> None:
        missing = []
        if not self.base_url:
            missing.append("OPNSENSE_BASE_URL")
        if not self.api_key:
            missing.append("OPNSENSE_API_KEY")
        if not self.api_secret:
            missing.append("OPNSENSE_API_SECRET")
        if missing:
            joined = ", ".join(missing)
            raise ValueError(f"Missing required environment variables: {joined}")

        parsed = urlparse(self.base_url)
        if parsed.scheme not in {"http", "https"}:
            raise ValueError("OPNSENSE_BASE_URL must start with http:// or https://")
        if parsed.scheme == "http" and not self.allow_insecure_http:
            raise ValueError(
                "Refusing insecure HTTP OPNsense connection. "
                "Set OPNSENSE_ALLOW_INSECURE_HTTP=true only for trusted local lab use."
            )
        if self.transport not in {"stdio", "streamable-http"}:
            raise ValueError("OPNSENSE_MCP_TRANSPORT must be stdio or streamable-http")
        if not self.http_path.startswith("/"):
            raise ValueError("OPNSENSE_MCP_HTTP_PATH must start with /")
