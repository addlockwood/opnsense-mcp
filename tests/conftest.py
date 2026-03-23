from __future__ import annotations

import subprocess
from collections.abc import Iterator
from copy import deepcopy
from pathlib import Path

import pytest

from opnsense_mcp.config import AppConfig
from opnsense_mcp.service import OPNsenseMCPService
from opnsense_mcp.workspace import WorkspaceManager


class FakeAPIClient:
    def __init__(self) -> None:
        self.state = {
            "unbound": {
                "host_override": [
                    {
                        "uuid": "uuid-kube",
                        "enabled": "1",
                        "hostname": "kube",
                        "domain": "lab.lockwd.io",
                        "rr": "A",
                        "server": "172.19.10.54",
                        "mxprio": "10",
                        "description": "Bootstrap k3s API DNS",
                    }
                ]
            },
            "dnsmasq": {
                "option": [
                    {
                        "uuid": "uuid-option-6",
                        "type": "set",
                        "option": "6",
                        "option6": "",
                        "interface": "",
                        "tag": "",
                        "set_tag": "",
                        "value": "172.19.10.241",
                        "force": "0",
                        "description": "Advertise Pi-hole as LAN DNS",
                    }
                ]
            },
        }
        self.services = {"unbound": "running", "dnsmasq": "running"}

    def close(self) -> None:
        return None

    def search(
        self,
        module: str,
        controller: str,
        command: str,
        payload: dict[str, object],
    ) -> dict[str, object]:
        del controller, payload
        if command == "search_host_override":
            return {"rows": deepcopy(self.state["unbound"]["host_override"])}
        if command == "search_option":
            return {"rows": deepcopy(self.state["dnsmasq"]["option"])}
        raise AssertionError(f"unexpected search command: {command}")

    def execute(
        self,
        method: str,
        module: str,
        controller: str,
        command: str,
        *,
        path_params: list[str] | None = None,
        payload: dict[str, object] | None = None,
    ) -> dict[str, object]:
        del method, controller
        payload = payload or {}
        if module == "unbound":
            return self._apply_mutation(
                records=self.state["unbound"]["host_override"],
                command=command,
                payload_root="host",
                path_params=path_params,
                payload=payload,
            )
        if module == "dnsmasq":
            return self._apply_mutation(
                records=self.state["dnsmasq"]["option"],
                command=command,
                payload_root="option",
                path_params=path_params,
                payload=payload,
            )
        raise AssertionError(f"unexpected execute module: {module}")

    def service_status(self, module: str) -> dict[str, object]:
        return {"status": self.services[module]}

    def fetch_snapshot_xml(self, host: str) -> str:
        return f"<?xml version='1.0'?><opnsense><host>{host}</host></opnsense>"

    def _apply_mutation(
        self,
        *,
        records: list[dict[str, str]],
        command: str,
        payload_root: str,
        path_params: list[str] | None,
        payload: dict[str, object],
    ) -> dict[str, object]:
        if command == "reconfigure":
            return {"status": "ok"}
        if command.startswith("add_"):
            new_record = deepcopy(payload[payload_root])
            new_record["uuid"] = f"generated-{len(records) + 1}"
            records.append(new_record)
            return {"status": "saved", "uuid": new_record["uuid"]}
        if command.startswith("set_"):
            target_uuid = (path_params or [""])[0]
            for record in records:
                if record["uuid"] == target_uuid:
                    record.update(deepcopy(payload[payload_root]))
                    return {"status": "saved", "uuid": target_uuid}
            raise AssertionError(f"missing uuid for update: {target_uuid}")
        if command.startswith("del_"):
            target_uuid = (path_params or [""])[0]
            records[:] = [record for record in records if record["uuid"] != target_uuid]
            return {"status": "deleted", "uuid": target_uuid}
        raise AssertionError(f"unexpected mutation command: {command}")


@pytest.fixture()
def temp_workspace(tmp_path: Path) -> Iterator[Path]:
    subprocess.run(["git", "init"], cwd=tmp_path, check=True, capture_output=True)
    yield tmp_path


@pytest.fixture()
def config(temp_workspace: Path) -> AppConfig:
    return AppConfig(
        base_url="https://router.example",
        api_key="key",
        api_secret="secret",
        verify_tls=False,
        allow_insecure_http=False,
        workspace_path=temp_workspace,
        snapshot_host="this",
        git_author_name="Test User",
        git_author_email="test@example.com",
    )


@pytest.fixture()
def fake_api() -> FakeAPIClient:
    return FakeAPIClient()


@pytest.fixture()
def service(config: AppConfig, fake_api: FakeAPIClient) -> OPNsenseMCPService:
    workspace = WorkspaceManager(config)
    return OPNsenseMCPService(config, api_client=fake_api, workspace=workspace)
