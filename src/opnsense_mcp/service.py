from __future__ import annotations

import shlex
from datetime import UTC, datetime
from importlib.metadata import PackageNotFoundError, version
from typing import Any, Literal, cast
from urllib.parse import urlparse

import httpx

from opnsense_mcp.api import OPNsenseAPIClient
from opnsense_mcp.config import AppConfig
from opnsense_mcp.dns_diagnostics import (
    explain_resolution_path as build_resolution_explanation,
)
from opnsense_mcp.dns_diagnostics import (
    parse_snapshot_dns_state,
    summarize_dhcp,
    summarize_dns_topology,
)
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

UPSERT_INTENTS = {
    "upsert",
    "add",
    "apply",
    "create",
    "ensure",
    "insert",
    "present",
    "set",
    "update",
}
DELETE_INTENTS = {"absent", "del", "delete", "remove"}


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
            "app_version": self._app_version(),
            "image_ref": self._config.image_ref,
            "transport": self._config.transport,
            "http_transport": {
                "host": self._config.http_host,
                "port": self._config.http_port,
                "path": self._config.http_path,
            },
            "router_base_url": self._config.base_url,
            "workspace_path": str(self._workspace.paths.root),
            "history_dir": str(self._workspace.paths.history_dir),
            "snapshots_dir": str(self._workspace.paths.snapshots_dir),
            "current_snapshot_path": str(self._workspace.paths.current_snapshot),
            "current_snapshot_exists": snapshot_exists,
            "history_files": history_files,
            "workspace_head": self._workspace.current_head(),
            "connectivity": self.connectivity_preflight(),
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

    def connectivity_preflight(self) -> dict[str, Any]:
        checks: list[dict[str, Any]] = []
        workspace_ok, workspace_detail = self._check_workspace_writable()
        checks.append(
            {
                "name": "workspace_writable",
                "ok": workspace_ok,
                "detail": workspace_detail,
            }
        )

        api_ok, api_detail, auth_ok = self._check_api_access()
        checks.append({"name": "router_reachable", "ok": api_ok, "detail": api_detail})
        checks.append(
            {
                "name": "auth_valid",
                "ok": auth_ok,
                "detail": api_detail if not auth_ok else "Authenticated API read succeeded.",
            }
        )

        snapshot_ok, snapshot_detail = self._check_snapshot_access()
        checks.append({"name": "snapshot_endpoint", "ok": snapshot_ok, "detail": snapshot_detail})

        return {
            "ok": all(check["ok"] for check in checks),
            "checks": checks,
        }

    def inspect_dhcp(self) -> dict[str, Any]:
        context = self._collect_dns_context()
        return summarize_dhcp(
            state=context["snapshot_state"],
            option_rows=context["dnsmasq_option_rows"],
            dnsmasq_status=context["service_statuses"]["dnsmasq"],
        )

    def inspect_dns_topology(self) -> dict[str, Any]:
        context = self._collect_dns_context()
        return summarize_dns_topology(
            state=context["snapshot_state"],
            option_rows=context["dnsmasq_option_rows"],
            unbound_rows=context["unbound_host_rows"],
            unbound_status=context["service_statuses"]["unbound"],
            dnsmasq_status=context["service_statuses"]["dnsmasq"],
            base_url=self._config.base_url,
        )

    def explain_resolution_path(self, hostname: str) -> dict[str, Any]:
        context = self._collect_dns_context()
        return build_resolution_explanation(
            hostname,
            state=context["snapshot_state"],
            option_rows=context["dnsmasq_option_rows"],
            unbound_rows=context["unbound_host_rows"],
            base_url=self._config.base_url,
        )

    def capture_dns_diagnosis(self) -> dict[str, Any]:
        xml_text = self._api.fetch_snapshot_xml(self._config.snapshot_host)
        snapshot = self._workspace.capture_snapshot(xml_text).model_dump(mode="json")
        snapshot_state = parse_snapshot_dns_state(xml_text)
        dnsmasq_option_rows = self._registry.get_adapter("dnsmasq", "option").search(
            self._api, SearchQuery()
        )
        unbound_host_rows = self._registry.get_adapter("unbound", "host_override").search(
            self._api, SearchQuery()
        )
        service_statuses = self._service_statuses()
        dhcp = summarize_dhcp(
            state=snapshot_state,
            option_rows=dnsmasq_option_rows,
            dnsmasq_status=service_statuses["dnsmasq"],
        )
        topology = summarize_dns_topology(
            state=snapshot_state,
            option_rows=dnsmasq_option_rows,
            unbound_rows=unbound_host_rows,
            unbound_status=service_statuses["unbound"],
            dnsmasq_status=service_statuses["dnsmasq"],
            base_url=self._config.base_url,
        )
        dhcp_warnings = cast(list[str], dhcp["warnings"])
        topology_warnings = cast(list[str], topology["warnings"])
        warnings = list(dict.fromkeys([*dhcp_warnings, *topology_warnings]))
        return {
            "snapshot": snapshot,
            "dhcp": dhcp,
            "topology": topology,
            "summary": topology["summary"],
            "warnings": warnings,
        }

    def plan_change(
        self,
        *,
        summary: str,
        requested_change: str,
        module: str,
        record_type: str,
        intent: str,
        match_fields: dict[str, str] | str,
        values: dict[str, str] | str | None = None,
    ) -> dict[str, Any]:
        adapter = self._registry.get_adapter(module, record_type)
        normalized_intent = self._normalize_intent(intent)
        normalized_match_fields = self._coerce_field_map(match_fields, field_name="match_fields")
        normalized_values = self._coerce_field_map(values, field_name="values")
        match = adapter.find_match(self._api, normalized_match_fields)
        if normalized_intent == "upsert":
            operations = adapter.build_upsert_operations(
                match.existing, {**normalized_match_fields, **normalized_values}
            )
        elif normalized_intent == "delete":
            operations = adapter.build_delete_operations(match.existing)
        else:
            raise UnsupportedModuleError(f"Unsupported intent '{intent}'")

        plan = ChangePlan(
            summary=summary,
            requested_change=requested_change,
            module=module,
            record_type=record_type,
            intent=normalized_intent,
            match_fields=normalized_match_fields,
            values=normalized_values,
            affected_modules=[module],
            operations=operations,
            services=[ServiceAction(module=module, description=f"Reconfigure {module}")],
            validation_checks=adapter.build_validation_checks(
                normalized_intent,
                normalized_match_fields,
                {**normalized_match_fields, **normalized_values},
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
            ("host", "domain"),
            ("option", "interface", "tag"),
            ("hwaddr",),
            ("client_id",),
            ("ip",),
        ):
            match_fields = {key: row[key] for key in candidate_keys if key in row and row[key]}
            if match_fields:
                return match_fields
        return {key: value for key, value in row.items() if key != "uuid" and value}

    def _normalize_intent(self, intent: str) -> Literal["upsert", "delete"]:
        normalized = intent.strip().lower()
        if normalized in UPSERT_INTENTS:
            return "upsert"
        if normalized in DELETE_INTENTS:
            return "delete"
        raise UnsupportedModuleError(
            f"Unsupported intent '{intent}'. Use upsert/create/add/update or delete/remove."
        )

    def _coerce_field_map(
        self,
        value: dict[str, str] | str | None,
        *,
        field_name: str,
    ) -> dict[str, str]:
        if value is None:
            return {}
        if isinstance(value, dict):
            return {str(key): str(item) for key, item in value.items()}
        if not isinstance(value, str):
            raise TypeError(f"{field_name} must be a dictionary or key=value string")

        result: dict[str, str] = {}
        normalized = value.replace(",", " ").replace(";", " ")
        for token in shlex.split(normalized):
            if "=" not in token:
                raise ValueError(
                    f"{field_name} string entries must use key=value syntax; got '{token}'"
                )
            key, raw_item = token.split("=", 1)
            key = key.strip()
            item = raw_item.strip()
            if not key:
                raise ValueError(f"{field_name} contains an empty key in '{token}'")
            result[key] = item
        return result

    def _app_version(self) -> str:
        try:
            return version("opnsense-mcp")
        except PackageNotFoundError:
            return "unknown"

    def _check_workspace_writable(self) -> tuple[bool, str]:
        try:
            self._workspace.ensure_layout()
            probe = self._workspace.paths.root / ".opnsense-mcp-write-check"
            probe.write_text("ok", encoding="utf-8")
            probe.unlink()
            return True, "Workspace layout exists and is writable."
        except OSError as exc:
            return False, f"Workspace is not writable: {exc}"

    def _check_api_access(self) -> tuple[bool, str, bool]:
        try:
            status = self._api.service_status("unbound")
            return True, f"API read succeeded: {status}", True
        except httpx.HTTPStatusError as exc:
            if exc.response.status_code in {401, 403}:
                return True, f"Authentication failed with HTTP {exc.response.status_code}.", False
            return (
                True,
                f"Router responded with HTTP {exc.response.status_code} during API read.",
                True,
            )
        except httpx.HTTPError as exc:
            return False, f"Could not reach router API: {exc}", False

    def _check_snapshot_access(self) -> tuple[bool, str]:
        try:
            xml_text = self._api.fetch_snapshot_xml(self._config.snapshot_host)
            parse_snapshot_dns_state(xml_text)
            return True, "Snapshot endpoint returned parseable XML."
        except httpx.HTTPStatusError as exc:
            return False, f"Snapshot endpoint returned HTTP {exc.response.status_code}."
        except httpx.HTTPError as exc:
            return False, f"Snapshot endpoint could not be reached: {exc}"
        except Exception as exc:
            return False, f"Snapshot endpoint returned unexpected data: {exc}"

    def _service_statuses(self) -> dict[str, str]:
        statuses: dict[str, str] = {}
        for module in ("unbound", "dnsmasq"):
            try:
                details = self._api.service_status(module)
                statuses[module] = str(details.get("status", "unknown"))
            except httpx.HTTPStatusError as exc:
                if exc.response.status_code in {400, 404, 405}:
                    statuses[module] = "unavailable"
                    continue
                statuses[module] = f"http-{exc.response.status_code}"
            except Exception as exc:  # pragma: no cover - surfaced through diagnosis payload
                statuses[module] = f"error: {exc}"
        return statuses

    def _collect_dns_context(self) -> dict[str, Any]:
        xml_text = self._api.fetch_snapshot_xml(self._config.snapshot_host)
        snapshot_state = parse_snapshot_dns_state(xml_text)
        dnsmasq_option_rows = self._registry.get_adapter("dnsmasq", "option").search(
            self._api, SearchQuery()
        )
        live_unbound_host_rows = self._registry.get_adapter("unbound", "host_override").search(
            self._api,
            SearchQuery(),
        )
        snapshot_unbound_host_rows = list(snapshot_state.unbound_host_overrides)
        unbound_host_rows = self._merge_records(
            live_unbound_host_rows,
            snapshot_unbound_host_rows,
            key_fields=("hostname", "domain", "server"),
        )
        return {
            "snapshot_state": snapshot_state,
            "dnsmasq_option_rows": dnsmasq_option_rows,
            "unbound_host_rows": unbound_host_rows,
            "service_statuses": self._service_statuses(),
            "router_host": urlparse(self._config.base_url).hostname or "",
        }

    def _merge_records(
        self,
        primary: list[dict[str, str]],
        secondary: list[dict[str, str]],
        *,
        key_fields: tuple[str, ...],
    ) -> list[dict[str, str]]:
        merged: list[dict[str, str]] = []
        seen: set[tuple[str, ...]] = set()
        for record in [*primary, *secondary]:
            key = tuple(record.get(field, "") for field in key_fields)
            if key in seen:
                continue
            seen.add(key)
            merged.append(record)
        return merged
