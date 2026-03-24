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
                "host": [],
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
                ],
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
        if command == "search_host":
            return {"rows": deepcopy(self.state["dnsmasq"]["host"])}
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
            payload_root = "host" if command.endswith("_host") else "option"
            record_type = "host" if command.endswith("_host") else "option"
            return self._apply_mutation(
                records=self.state["dnsmasq"][record_type],
                command=command,
                payload_root=payload_root,
                path_params=path_params,
                payload=payload,
            )
        raise AssertionError(f"unexpected execute module: {module}")

    def service_status(self, module: str) -> dict[str, object]:
        return {"status": self.services[module]}

    def fetch_snapshot_xml(self, host: str) -> str:
        del host
        return """<?xml version='1.0'?>
<opnsense>
  <system>
    <hostname>opnsense</hostname>
    <domain>lab.lockwd.io</domain>
    <dnsallowoverride>0</dnsallowoverride>
    <dnsserver>1.1.1.1</dnsserver>
    <dnsserver>1.0.0.1</dnsserver>
  </system>
  <dnsmasq>
    <enable>1</enable>
    <interface>lan</interface>
    <port>53053</port>
    <dhcp>1</dhcp>
    <dhcp_ranges>
      <range>
        <interface>lan</interface>
        <from>172.19.10.100</from>
        <to>172.19.10.199</to>
      </range>
    </dhcp_ranges>
    <dhcp_options />
  </dnsmasq>
  <OPNsense>
    <unboundplus>
      <general>
        <enabled>1</enabled>
        <local_zone_type>transparent</local_zone_type>
      </general>
      <forwarding>
        <enabled>0</enabled>
      </forwarding>
      <hosts>
        <host>
          <enabled>1</enabled>
          <hostname>kube</hostname>
          <domain>lab.lockwd.io</domain>
          <rr>A</rr>
          <mxprio>10</mxprio>
          <mx></mx>
          <server>172.19.10.54</server>
          <txtdata></txtdata>
          <description>Bootstrap k3s API DNS</description>
          <aliases></aliases>
        </host>
        <host>
          <enabled>1</enabled>
          <hostname>vault</hostname>
          <domain>lab.lockwd.io</domain>
          <rr>A</rr>
          <mxprio>10</mxprio>
          <mx></mx>
          <server>172.19.10.54</server>
          <txtdata></txtdata>
          <description>Bootstrap Vault host DNS</description>
          <aliases></aliases>
        </host>
      </hosts>
      <aliases />
    </unboundplus>
  </OPNsense>
</opnsense>"""

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
        transport="stdio",
        http_host="127.0.0.1",
        http_port=8000,
        http_path="/mcp",
        image_ref="ghcr.io/addlockwood/opnsense-mcp:test",
        stateless_http=False,
    )


@pytest.fixture()
def fake_api() -> FakeAPIClient:
    return FakeAPIClient()


@pytest.fixture()
def service(config: AppConfig, fake_api: FakeAPIClient) -> OPNsenseMCPService:
    workspace = WorkspaceManager(config)
    return OPNsenseMCPService(config, api_client=fake_api, workspace=workspace)
