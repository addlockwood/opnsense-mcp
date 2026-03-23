from __future__ import annotations

from dataclasses import dataclass
from typing import Literal

from opnsense_mcp.adapters.base import AdapterMatch, APIProtocol
from opnsense_mcp.models import ApiOperation, SearchQuery, ValidationCheck


@dataclass(frozen=True)
class DnsmasqOptionAdapter:
    module: str = "dnsmasq"
    record_type: str = "option"
    payload_root: str = "option"
    controller: str = "settings"

    def search(self, api: APIProtocol, query: SearchQuery) -> list[dict[str, str]]:
        payload = query.model_dump(by_alias=True)
        response = api.search(self.module, self.controller, "search_option", payload)
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
                    command="set_option",
                    path_params=[str(existing["uuid"])],
                    payload={self.payload_root: normalized},
                    description=f"Update dnsmasq option {existing['uuid']}",
                )
            ]
        return [
            ApiOperation(
                module=self.module,
                controller=self.controller,
                command="add_option",
                payload={self.payload_root: normalized},
                description="Create dnsmasq option",
            )
        ]

    def build_delete_operations(self, existing: dict[str, str] | None) -> list[ApiOperation]:
        if not existing or not existing.get("uuid"):
            return []
        return [
            ApiOperation(
                module=self.module,
                controller=self.controller,
                command="del_option",
                path_params=[str(existing["uuid"])],
                description=f"Delete dnsmasq option {existing['uuid']}",
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
            "type": str(row.get("type", "set")),
            "option": str(row.get("option", "")),
            "option6": str(row.get("option6", "")),
            "interface": str(row.get("interface", "")),
            "tag": str(row.get("tag", "")),
            "set_tag": str(row.get("set_tag", "")),
            "value": str(row.get("value", "")),
            "force": str(row.get("force", "0")),
            "description": str(row.get("description", "")),
        }

    def _with_defaults(self, values: dict[str, str]) -> dict[str, str]:
        return {
            "type": values.get("type", "set"),
            "option": values.get("option", ""),
            "option6": values.get("option6", ""),
            "interface": values.get("interface", ""),
            "tag": values.get("tag", ""),
            "set_tag": values.get("set_tag", ""),
            "value": values.get("value", ""),
            "force": values.get("force", "0"),
            "description": values.get("description", ""),
        }
