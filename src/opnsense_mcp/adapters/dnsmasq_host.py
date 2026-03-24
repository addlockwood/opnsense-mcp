from __future__ import annotations

from dataclasses import dataclass
from typing import Literal

from opnsense_mcp.adapters.base import AdapterMatch, APIProtocol
from opnsense_mcp.models import ApiOperation, SearchQuery, ValidationCheck


@dataclass(frozen=True)
class DnsmasqHostAdapter:
    module: str = "dnsmasq"
    record_type: str = "host"
    payload_root: str = "host"
    controller: str = "settings"

    def search(self, api: APIProtocol, query: SearchQuery) -> list[dict[str, str]]:
        payload = query.model_dump(by_alias=True)
        response = api.search(self.module, self.controller, "search_host", payload)
        rows_object = response.get("rows", [])
        if not isinstance(rows_object, list):
            return []
        rows: list[dict[str, str]] = []
        for row in rows_object:
            if isinstance(row, dict):
                rows.append(self.normalize_row(row))
        return rows

    def find_match(
        self,
        api: APIProtocol,
        match_fields: dict[str, str],
    ) -> AdapterMatch:
        rows = self.search(api, SearchQuery())
        existing = None
        for row in rows:
            if all(row.get(key, "") == value for key, value in match_fields.items()):
                existing = row
                break
        return AdapterMatch(existing=existing, search_rows=rows)

    def build_upsert_operations(
        self,
        existing: dict[str, str] | None,
        values: dict[str, str],
    ) -> list[ApiOperation]:
        normalized = self._with_defaults(values)
        if existing and existing.get("uuid"):
            return [
                ApiOperation(
                    module=self.module,
                    controller=self.controller,
                    command="set_host",
                    path_params=[str(existing["uuid"])],
                    payload={self.payload_root: normalized},
                    description=f"Update dnsmasq host {existing['uuid']}",
                )
            ]
        return [
            ApiOperation(
                module=self.module,
                controller=self.controller,
                command="add_host",
                payload={self.payload_root: normalized},
                description="Create dnsmasq host",
            )
        ]

    def build_delete_operations(self, existing: dict[str, str] | None) -> list[ApiOperation]:
        if not existing or not existing.get("uuid"):
            return []
        return [
            ApiOperation(
                module=self.module,
                controller=self.controller,
                command="del_host",
                path_params=[str(existing["uuid"])],
                description=f"Delete dnsmasq host {existing['uuid']}",
            )
        ]

    def build_validation_checks(
        self,
        intent: str,
        match_fields: dict[str, str],
        values: dict[str, str],
    ) -> list[ValidationCheck]:
        kind: Literal["record_exists", "record_absent"] = (
            "record_exists" if intent == "upsert" else "record_absent"
        )
        return [
            ValidationCheck(
                kind=kind,
                module=self.module,
                record_type=self.record_type,
                match_fields=match_fields,
                expected_fields=self._with_defaults(values),
            ),
            ValidationCheck(
                kind="service_status",
                module=self.module,
                service_command="status",
            ),
        ]

    def normalize_row(self, row: dict[str, object]) -> dict[str, str]:
        return {
            "uuid": str(row.get("uuid", "")),
            "host": str(row.get("host", "")),
            "domain": str(row.get("domain", "")),
            "local": str(row.get("local", "0")),
            "ip": str(row.get("ip", "")),
            "cnames": str(row.get("cnames", "")),
            "client_id": str(row.get("client_id", "")),
            "hwaddr": str(row.get("hwaddr", row.get("macaddr", row.get("mac", "")))),
            "lease_time": str(row.get("lease_time", "")),
            "ignore": str(row.get("ignore", "0")),
            "set_tag": str(row.get("set_tag", "")),
            "descr": str(row.get("descr", row.get("description", ""))),
            "comments": str(row.get("comments", "")),
            "aliases": str(row.get("aliases", "")),
        }

    def _with_defaults(self, values: dict[str, str]) -> dict[str, str]:
        return {
            "host": values.get("host", values.get("hostname", "")),
            "domain": values.get("domain", ""),
            "local": values.get("local", "0"),
            "ip": values.get("ip", values.get("address", values.get("server", ""))),
            "cnames": values.get("cnames", ""),
            "client_id": values.get("client_id", ""),
            "hwaddr": values.get("hwaddr", values.get("macaddr", values.get("mac", ""))),
            "lease_time": values.get("lease_time", ""),
            "ignore": values.get("ignore", "0"),
            "set_tag": values.get("set_tag", ""),
            "descr": values.get("descr", values.get("description", "")),
            "comments": values.get("comments", ""),
            "aliases": values.get("aliases", ""),
        }
