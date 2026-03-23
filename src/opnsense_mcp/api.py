from __future__ import annotations

from collections.abc import Callable
from typing import Any

import httpx

from opnsense_mcp.config import AppConfig


class OPNsenseAPIClient:
    def __init__(
        self,
        config: AppConfig,
        *,
        client_factory: Callable[..., httpx.Client] = httpx.Client,
    ) -> None:
        self._config = config
        self._client = client_factory(
            base_url=config.base_url,
            auth=(config.api_key, config.api_secret),
            follow_redirects=True,
            timeout=config.request_timeout_seconds,
            verify=config.verify_tls,
        )

    def close(self) -> None:
        self._client.close()

    def _build_path(
        self,
        module: str,
        controller: str,
        command: str,
        path_params: list[str] | None = None,
    ) -> str:
        suffix = ""
        if path_params:
            suffix = "/" + "/".join(path_params)
        return f"/api/{module}/{controller}/{command}{suffix}"

    def request_json(
        self,
        method: str,
        module: str,
        controller: str,
        command: str,
        *,
        path_params: list[str] | None = None,
        payload: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        response = self._client.request(
            method,
            self._build_path(module, controller, command, path_params),
            json=payload or {},
        )
        response.raise_for_status()
        data = response.json()
        if not isinstance(data, dict):
            raise TypeError("Expected JSON object response from OPNsense API")
        return data

    def search(
        self,
        module: str,
        controller: str,
        command: str,
        payload: dict[str, object],
    ) -> dict[str, object]:
        return self.request_json("POST", module, controller, command, payload=dict(payload))

    def execute(
        self,
        method: str,
        module: str,
        controller: str,
        command: str,
        *,
        path_params: list[str] | None = None,
        payload: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        return self.request_json(
            method,
            module,
            controller,
            command,
            path_params=path_params,
            payload=payload,
        )

    def service_status(self, module: str) -> dict[str, Any]:
        return self.request_json("GET", module, "service", "status")

    def fetch_snapshot_xml(self, host: str) -> str:
        response = self._client.get(f"/api/core/backup/download/{host}")
        response.raise_for_status()
        return response.text
