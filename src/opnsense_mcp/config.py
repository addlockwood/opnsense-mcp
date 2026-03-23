from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path


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
    workspace_path: Path
    snapshot_host: str
    git_author_name: str
    git_author_email: str
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
        verify_tls = _bool_from_env(os.environ.get("OPNSENSE_VERIFY_TLS"), default=False)

        return cls(
            base_url=base_url,
            api_key=api_key,
            api_secret=api_secret,
            verify_tls=verify_tls,
            workspace_path=workspace_path,
            snapshot_host=snapshot_host,
            git_author_name=git_author_name,
            git_author_email=git_author_email,
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
