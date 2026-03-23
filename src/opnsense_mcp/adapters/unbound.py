from __future__ import annotations

from dataclasses import dataclass
from typing import Literal

from opnsense_mcp.adapters.base import AdapterMatch, APIProtocol
from opnsense_mcp.models import ApiOperation, SearchQuery, ValidationCheck


@dataclass(frozen=True)
class UnboundHostOverrideAdapter:
    module: str = "unbound"
    record_type: str = "host_override"
    payload_root: str = "host"
    controller: str = "settings"

    def search(self, api: APIProtocol, query: SearchQuery) -> list[dict[str, str]]:
        payload = query.model_dump(by_alias=True)
        response = api.search(self.module, self.controller, "search_host_override", payload)
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
                    command="set_host_override",
                    path_params=[str(existing["uuid"])],
                    payload={self.payload_root: normalized},
                    description=f"Update unbound host override {existing['uuid']}",
                )
            ]
        return [
            ApiOperation(
                module=self.module,
                controller=self.controller,
                command="add_host_override",
                payload={self.payload_root: normalized},
                description="Create unbound host override",
            )
        ]

    def build_delete_operations(self, existing: dict[str, str] | None) -> list[ApiOperation]:
        if not existing or not existing.get("uuid"):
            return []
        return [
            ApiOperation(
                module=self.module,
                controller=self.controller,
                command="del_host_override",
                path_params=[str(existing["uuid"])],
                description=f"Delete unbound host override {existing['uuid']}",
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
        checks = [
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
        return checks

    def normalize_row(self, row: dict[str, object]) -> dict[str, str]:
        normalized = {
            "uuid": str(row.get("uuid", "")),
            "enabled": str(row.get("enabled", "1")),
            "hostname": str(row.get("hostname", "")),
            "domain": str(row.get("domain", "")),
            "rr": str(row.get("rr", "A")),
            "server": str(row.get("server", row.get("value", ""))),
            "mxprio": str(row.get("mxprio", "10")),
            "description": str(row.get("description", "")),
        }
        return normalized

    def _with_defaults(self, values: dict[str, str]) -> dict[str, str]:
        return {
            "enabled": values.get("enabled", "1"),
            "hostname": values.get("hostname", ""),
            "domain": values.get("domain", ""),
            "rr": values.get("rr", "A"),
            "mxprio": values.get("mxprio", "10"),
            "mx": values.get("mx", ""),
            "server": values.get("server", values.get("value", "")),
            "txtdata": values.get("txtdata", ""),
            "description": values.get("description", ""),
            "aliases": values.get("aliases", ""),
        }
