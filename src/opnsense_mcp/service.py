from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

from opnsense_mcp.api import OPNsenseAPIClient
from opnsense_mcp.config import AppConfig
from opnsense_mcp.errors import PlanApprovalError, UnsupportedModuleError, ValidationFailedError
from opnsense_mcp.models import (
    ApiOperation,
    ChangeApproval,
    ChangePlan,
    ChangeRecordMetadata,
    InspectResult,
    ManagedState,
    OperationExecution,
    RollbackBasis,
    SearchQuery,
    SearchResult,
    ServiceAction,
    ValidationCheck,
    ValidationResult,
)
from opnsense_mcp.registry import CoreModuleRegistry
from opnsense_mcp.workspace import WorkspaceManager


class OPNsenseMCPService:
    def __init__(
        self,
        config: AppConfig,
        *,
        api_client: OPNsenseAPIClient | None = None,
        registry: CoreModuleRegistry | None = None,
        workspace: WorkspaceManager | None = None,
    ) -> None:
        self._config = config
        self._registry = registry or CoreModuleRegistry()
        self._workspace = workspace or WorkspaceManager(config)
        self._api = api_client or OPNsenseAPIClient(config)

    def list_core_modules(self) -> list[dict[str, Any]]:
        return [item.model_dump(mode="json") for item in self._registry.list_modules()]

    def inspect_runtime(self) -> dict[str, Any]:
        self._workspace.ensure_layout()
        history_files = sorted(path.name for path in self._workspace.paths.history_dir.glob("*.md"))
        snapshot_exists = self._workspace.paths.current_snapshot.exists()
        return {
            "workspace_path": str(self._workspace.paths.root),
            "history_dir": str(self._workspace.paths.history_dir),
            "snapshots_dir": str(self._workspace.paths.snapshots_dir),
            "current_snapshot_path": str(self._workspace.paths.current_snapshot),
            "current_snapshot_exists": snapshot_exists,
            "history_files": history_files,
            "workspace_head": self._workspace.current_head(),
        }

    def inspect_state(self, module: str) -> dict[str, Any]:
        descriptor = self._registry.get_module(module)
        notes: list[str] = []
        state: dict[str, Any] = {
            "supported_record_types": descriptor.metadata.supported_record_types
        }
        if not descriptor.adapters:
            notes.append("Module is discoverable but has no implemented live-state adapter yet.")
        else:
            adapter_state: dict[str, list[dict[str, str]]] = {}
            for record_type, adapter in descriptor.adapters.items():
                rows = adapter.search(self._api, SearchQuery())
                adapter_state[record_type] = rows
            state["records"] = adapter_state
        return InspectResult(
            module=module,
            inspectable=True,
            mutable=descriptor.metadata.mutable,
            state=state,
            notes=notes,
        ).model_dump(mode="json")

    def search_records(self, module: str, record_type: str, phrase: str = "") -> dict[str, Any]:
        adapter = self._registry.get_adapter(module, record_type)
        rows = adapter.search(self._api, SearchQuery(phrase=phrase))
        return SearchResult(module=module, record_type=record_type, rows=rows).model_dump(
            mode="json"
        )

    def plan_change(
        self,
        *,
        summary: str,
        requested_change: str,
        module: str,
        record_type: str,
        intent: str,
        match_fields: dict[str, str],
        values: dict[str, str] | None = None,
    ) -> dict[str, Any]:
        adapter = self._registry.get_adapter(module, record_type)
        values = values or {}
        match = adapter.find_match(self._api, match_fields)
        if intent == "upsert":
            operations = adapter.build_upsert_operations(match.existing, {**match_fields, **values})
        elif intent == "delete":
            operations = adapter.build_delete_operations(match.existing)
        else:
            raise UnsupportedModuleError(f"Unsupported intent '{intent}'")

        plan = ChangePlan(
            summary=summary,
            requested_change=requested_change,
            module=module,
            record_type=record_type,
            intent="upsert" if intent == "upsert" else "delete",
            match_fields=match_fields,
            values=values,
            affected_modules=[module],
            operations=operations,
            services=[ServiceAction(module=module, description=f"Reconfigure {module}")],
            validation_checks=adapter.build_validation_checks(
                intent, match_fields, {**match_fields, **values}
            ),
            rollback=RollbackBasis(workspace_head=self._workspace.current_head()),
        )
        return plan.model_dump(mode="json")

    def apply_change(self, plan: ChangePlan, approval: ChangeApproval) -> dict[str, Any]:
        if not approval.approved:
            raise PlanApprovalError("Mutating changes require explicit approval")
        operation_results = [self._execute_operation(operation) for operation in plan.operations]
        return {
            "plan_id": plan.plan_id,
            "approved_by": approval.approved_by,
            "operation_results": [result.model_dump(mode="json") for result in operation_results],
        }

    def reconfigure_services(self, services: list[ServiceAction]) -> dict[str, Any]:
        results = [self._execute_service(service) for service in services]
        return {"service_results": [result.model_dump(mode="json") for result in results]}

    def validate_change(self, plan: ChangePlan) -> dict[str, Any]:
        results = [self._run_validation(check) for check in plan.validation_checks]
        overall = all(result.ok for result in results)
        return {
            "ok": overall,
            "results": [result.model_dump(mode="json") for result in results],
        }

    def capture_snapshot(self) -> dict[str, Any]:
        xml_text = self._api.fetch_snapshot_xml(self._config.snapshot_host)
        snapshot = self._workspace.capture_snapshot(xml_text)
        return snapshot.model_dump(mode="json")

    def finalize_change(
        self,
        *,
        plan: ChangePlan,
        approval: ChangeApproval,
        operation_results: list[OperationExecution],
        service_results: list[OperationExecution],
        validation_results: list[ValidationResult],
    ) -> dict[str, Any]:
        if not all(result.ok for result in validation_results):
            raise ValidationFailedError("Refusing to record a change that failed validation")
        snapshot = self.capture_snapshot()
        managed_state = self._capture_managed_state()
        metadata = ChangeRecordMetadata(
            summary=plan.summary,
            requested_change=plan.requested_change,
            approved_by=approval.approved_by,
            approval_reason=approval.reason,
            plan=plan,
            applied_at=datetime.now(UTC).isoformat(),
            operation_results=operation_results,
            service_results=service_results,
            validation_results=validation_results,
            snapshot_path=snapshot["path"],
            rollback_target=plan.rollback.workspace_head,
            managed_state=managed_state,
        )
        history_path = self._workspace.write_history_record(metadata)
        commit_sha = self._workspace.commit_files(
            [history_path, self._workspace.paths.current_snapshot],
            message=f"opnsense-mcp: {plan.summary}",
        )
        return {
            "history_path": str(history_path),
            "snapshot_path": snapshot["path"],
            "commit_sha": commit_sha,
        }

    def rollback_change(self, target_ref: str, approved_by: str, reason: str) -> dict[str, Any]:
        target_record = self._workspace.read_latest_record_from_ref(target_ref)
        current_state = self._capture_managed_state()
        plan = self._build_rollback_plan(
            target_ref, current_state.records, target_record.managed_state.records
        )
        approval = ChangeApproval(approved=True, approved_by=approved_by, reason=reason)
        apply_payload = self.apply_change(plan, approval)
        service_payload = self.reconfigure_services(plan.services)
        validation_payload = self.validate_change(plan)
        validation_results = [
            ValidationResult.model_validate(result) for result in validation_payload["results"]
        ]
        finalize_payload = self.finalize_change(
            plan=plan,
            approval=approval,
            operation_results=[
                OperationExecution.model_validate(result)
                for result in apply_payload["operation_results"]
            ],
            service_results=[
                OperationExecution.model_validate(result)
                for result in service_payload["service_results"]
            ],
            validation_results=validation_results,
        )
        return {
            "plan": plan.model_dump(mode="json"),
            "apply": apply_payload,
            "services": service_payload,
            "validation": validation_payload,
            "finalize": finalize_payload,
        }

    def close(self) -> None:
        self._api.close()

    def _execute_operation(self, operation: ApiOperation) -> OperationExecution:
        response = self._api.execute(
            operation.method,
            operation.module,
            operation.controller,
            operation.command,
            path_params=operation.path_params,
            payload=operation.payload,
        )
        return OperationExecution(operation=operation, ok=True, response=response)

    def _execute_service(self, service: ServiceAction) -> OperationExecution:
        response = self._api.execute(
            service.method,
            service.module,
            service.controller,
            service.command,
        )
        operation = ApiOperation(
            module=service.module,
            controller=service.controller,
            command=service.command,
            method=service.method,
            description=service.description,
        )
        return OperationExecution(operation=operation, ok=True, response=response)

    def _run_validation(self, check: ValidationCheck) -> ValidationResult:
        if check.kind == "service_status":
            details = self._api.service_status(check.module)
            message = f"Service status read back for {check.module}"
            return ValidationResult(check=check, ok=True, message=message, details=details)

        if check.record_type is None:
            raise UnsupportedModuleError("Record validation requires a record_type")

        adapter = self._registry.get_adapter(check.module, check.record_type)
        rows = adapter.search(self._api, SearchQuery())
        matches = [
            row
            for row in rows
            if all(row.get(key, "") == value for key, value in check.match_fields.items())
        ]
        if check.kind == "record_exists":
            ok = any(
                all(match.get(key, "") == value for key, value in check.expected_fields.items())
                for match in matches
            )
            message = f"Validated expected {check.module}.{check.record_type} record exists"
        else:
            ok = len(matches) == 0
            message = f"Validated {check.module}.{check.record_type} record is absent"
        return ValidationResult(
            check=check,
            ok=ok,
            message=message,
            details={"matches": matches},
        )

    def _capture_managed_state(self) -> ManagedState:
        records: dict[str, dict[str, list[dict[str, str]]]] = {}
        for module_meta in self._registry.list_modules():
            if not module_meta.supported_record_types:
                continue
            module_records: dict[str, list[dict[str, str]]] = {}
            for record_type in module_meta.supported_record_types:
                adapter = self._registry.get_adapter(module_meta.name, record_type)
                module_records[record_type] = adapter.search(self._api, SearchQuery())
            records[module_meta.name] = module_records
        return self._workspace.collect_managed_state(records)

    def _build_rollback_plan(
        self,
        target_ref: str,
        current_state: dict[str, dict[str, list[dict[str, str]]]],
        target_state: dict[str, dict[str, list[dict[str, str]]]],
    ) -> ChangePlan:
        operations: list[ApiOperation] = []
        services: dict[str, ServiceAction] = {}
        validation_checks: list[ValidationCheck] = []

        for module, record_map in target_state.items():
            for record_type, target_rows in record_map.items():
                adapter = self._registry.get_adapter(module, record_type)
                current_rows = current_state.get(module, {}).get(record_type, [])
                current_index = {
                    tuple(sorted(self._default_match_fields(row).items())): row
                    for row in current_rows
                }
                target_index = {
                    tuple(sorted(self._default_match_fields(row).items())): row
                    for row in target_rows
                }
                for target_key, target_row in target_index.items():
                    current_row = current_index.get(target_key)
                    operations.extend(adapter.build_upsert_operations(current_row, target_row))
                    validation_checks.extend(
                        adapter.build_validation_checks(
                            "upsert", self._default_match_fields(target_row), target_row
                        )
                    )
                for current_key, current_row in current_index.items():
                    if current_key in target_index:
                        continue
                    operations.extend(adapter.build_delete_operations(current_row))
                    validation_checks.extend(
                        adapter.build_validation_checks(
                            "delete",
                            self._default_match_fields(current_row),
                            current_row,
                        )
                    )
                services[module] = ServiceAction(module=module, description=f"Reconfigure {module}")

        return ChangePlan(
            summary=f"rollback to {target_ref}",
            requested_change=f"Rollback managed state to git ref {target_ref}",
            module="core",
            record_type="managed_state",
            intent="rollback",
            match_fields={},
            values={},
            affected_modules=sorted(services),
            operations=operations,
            services=list(services.values()),
            validation_checks=validation_checks,
            rollback=RollbackBasis(
                workspace_head=self._workspace.current_head(),
                target_ref=target_ref,
            ),
        )

    def _default_match_fields(self, row: dict[str, str]) -> dict[str, str]:
        for candidate_keys in (
            ("hostname", "domain"),
            ("option", "interface", "tag"),
        ):
            match_fields = {key: row[key] for key in candidate_keys if key in row and row[key]}
            if match_fields:
                return match_fields
        return {key: value for key, value in row.items() if key != "uuid" and value}
