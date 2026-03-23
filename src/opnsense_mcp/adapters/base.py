from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol

from opnsense_mcp.models import ApiOperation, SearchQuery, ValidationCheck


class APIProtocol(Protocol):
    def search(
        self,
        module: str,
        controller: str,
        command: str,
        payload: dict[str, object],
    ) -> dict[str, object]: ...


@dataclass(frozen=True)
class AdapterMatch:
    existing: dict[str, str] | None
    search_rows: list[dict[str, str]]


class RecordAdapter(Protocol):
    @property
    def module(self) -> str: ...

    @property
    def record_type(self) -> str: ...

    @property
    def payload_root(self) -> str: ...

    def search(self, api: APIProtocol, query: SearchQuery) -> list[dict[str, str]]: ...

    def find_match(
        self,
        api: APIProtocol,
        match_fields: dict[str, str],
    ) -> AdapterMatch: ...

    def build_upsert_operations(
        self,
        existing: dict[str, str] | None,
        values: dict[str, str],
    ) -> list[ApiOperation]: ...

    def build_delete_operations(self, existing: dict[str, str] | None) -> list[ApiOperation]: ...

    def build_validation_checks(
        self,
        intent: str,
        match_fields: dict[str, str],
        values: dict[str, str],
    ) -> list[ValidationCheck]: ...

    def normalize_row(self, row: dict[str, object]) -> dict[str, str]: ...
