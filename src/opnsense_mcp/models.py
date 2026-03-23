from __future__ import annotations

from datetime import UTC, datetime
from typing import Any, Literal
from uuid import uuid4

from pydantic import BaseModel, Field


class SearchQuery(BaseModel):
    phrase: str = ""
    current: int = 1
    row_count: int = Field(default=100, alias="rowCount")

    model_config = {"populate_by_name": True}


class ApiOperation(BaseModel):
    module: str
    controller: str
    command: str
    method: Literal["GET", "POST"] = "POST"
    path_params: list[str] = Field(default_factory=list)
    payload: dict[str, Any] = Field(default_factory=dict)
    description: str


class OperationExecution(BaseModel):
    operation: ApiOperation
    ok: bool
    response: dict[str, Any] | str


class ServiceAction(BaseModel):
    module: str
    controller: str = "service"
    command: str = "reconfigure"
    method: Literal["GET", "POST"] = "POST"
    description: str


class ValidationCheck(BaseModel):
    kind: Literal["record_exists", "record_absent", "service_status"]
    module: str
    record_type: str | None = None
    match_fields: dict[str, str] = Field(default_factory=dict)
    expected_fields: dict[str, str] = Field(default_factory=dict)
    service_command: str | None = None


class ValidationResult(BaseModel):
    check: ValidationCheck
    ok: bool
    message: str
    details: dict[str, Any] = Field(default_factory=dict)


class RollbackBasis(BaseModel):
    workspace_head: str | None = None
    target_ref: str | None = None
    strategy: Literal["api_reverse", "snapshot_restore"] = "api_reverse"


class ChangePlan(BaseModel):
    plan_id: str = Field(default_factory=lambda: f"plan-{uuid4()}")
    summary: str
    requested_change: str
    module: str
    record_type: str
    intent: Literal["upsert", "delete", "rollback"]
    match_fields: dict[str, str] = Field(default_factory=dict)
    values: dict[str, str] = Field(default_factory=dict)
    affected_modules: list[str]
    operations: list[ApiOperation]
    services: list[ServiceAction]
    validation_checks: list[ValidationCheck]
    rollback: RollbackBasis
    requires_confirmation: bool = True
    created_at: str = Field(default_factory=lambda: datetime.now(UTC).isoformat())


class ChangeApproval(BaseModel):
    approved: bool
    approved_by: str
    reason: str = ""


class ModuleMetadata(BaseModel):
    name: str
    docs_slug: str
    description: str
    inspectable: bool
    mutable: bool
    supported_record_types: list[str] = Field(default_factory=list)


class SearchResult(BaseModel):
    module: str
    record_type: str
    rows: list[dict[str, Any]]


class ManagedState(BaseModel):
    captured_at: str = Field(default_factory=lambda: datetime.now(UTC).isoformat())
    records: dict[str, dict[str, list[dict[str, Any]]]]


class SnapshotResult(BaseModel):
    path: str
    valid_xml: bool
    bytes_written: int


class ChangeRecordMetadata(BaseModel):
    summary: str
    requested_change: str
    approved_by: str
    approval_reason: str
    plan: ChangePlan
    applied_at: str
    operation_results: list[OperationExecution]
    service_results: list[OperationExecution]
    validation_results: list[ValidationResult]
    snapshot_path: str
    rollback_target: str | None
    managed_state: ManagedState


class InspectResult(BaseModel):
    module: str
    inspectable: bool
    mutable: bool
    state: dict[str, Any] = Field(default_factory=dict)
    notes: list[str] = Field(default_factory=list)
