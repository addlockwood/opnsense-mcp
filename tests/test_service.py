from pathlib import Path

import httpx

from opnsense_mcp.models import ChangeApproval, ChangePlan, OperationExecution, ValidationResult
from opnsense_mcp.workspace import parse_history_record


def test_plan_change_builds_upsert_plan(service) -> None:
    payload = service.plan_change(
        summary="add vault override",
        requested_change="Create vault.lab.lockwd.io",
        module="unbound",
        record_type="host_override",
        intent="upsert",
        match_fields={"hostname": "vault", "domain": "lab.lockwd.io"},
        values={"server": "172.19.10.54", "description": "Vault DNS"},
    )
    plan = ChangePlan.model_validate(payload)
    assert plan.module == "unbound"
    assert plan.operations[0].command == "add_host_override"
    assert plan.services[0].module == "unbound"


def test_plan_change_accepts_create_alias_and_string_values(service) -> None:
    payload = service.plan_change(
        summary="add eap720 override",
        requested_change="Create eap720.core.lockwd.io",
        module="unbound",
        record_type="host_override",
        intent="create",
        match_fields={"hostname": "eap720", "domain": "core.lockwd.io"},
        values='server=172.19.10.120 description="EAP720 AP management DNS"',
    )
    plan = ChangePlan.model_validate(payload)
    assert plan.intent == "upsert"
    assert plan.values["server"] == "172.19.10.120"
    assert plan.values["description"] == "EAP720 AP management DNS"
    assert plan.operations[0].command == "add_host_override"


def test_plan_change_builds_dnsmasq_host_plan(service) -> None:
    payload = service.plan_change(
        summary="reserve ap ip",
        requested_change="Create static reservation for EAP720",
        module="dnsmasq",
        record_type="host",
        intent="add",
        match_fields={"host": "eap720", "domain": "core.lockwd.io"},
        values='ip=172.19.10.120 hwaddr=AA:BB:CC:DD:EE:FF descr="EAP720 static reservation"',
    )
    plan = ChangePlan.model_validate(payload)
    assert plan.module == "dnsmasq"
    assert plan.record_type == "host"
    assert plan.operations[0].command == "add_host"
    assert plan.values["ip"] == "172.19.10.120"
    assert plan.values["hwaddr"] == "AA:BB:CC:DD:EE:FF"


def test_connectivity_preflight_reports_ready(service) -> None:
    payload = service.connectivity_preflight()
    assert payload["ok"] is True
    names = [check["name"] for check in payload["checks"]]
    assert names == [
        "workspace_writable",
        "router_reachable",
        "auth_valid",
        "snapshot_endpoint",
    ]


def test_inspect_dns_topology_gracefully_handles_missing_service_status(service) -> None:
    request = httpx.Request("GET", "https://router.example/api/unbound/service/status")
    response = httpx.Response(400, request=request)

    def failing_status(module: str) -> dict[str, object]:
        raise httpx.HTTPStatusError("bad request", request=request, response=response)

    service._api.service_status = failing_status  # type: ignore[method-assign]

    payload = service.inspect_dns_topology()

    assert payload["unbound"]["status"] == "unavailable"
    assert payload["dnsmasq"]["status"] == "unavailable"


def test_inspect_dhcp_reports_option_6_and_warning(service) -> None:
    payload = service.inspect_dhcp()
    assert payload["advertised_dns_servers"] == ["172.19.10.241"]
    assert payload["dhcp_option_6_records"][0]["option"] == "6"
    assert payload["warnings"]


def test_inspect_dns_topology_reports_split_horizon_warning(service) -> None:
    payload = service.inspect_dns_topology()
    assert payload["unbound"]["host_overrides"]
    assert payload["dnsmasq"]["dhcp"]["advertised_dns_servers"] == ["172.19.10.241"]
    assert any("local host overrides" in warning for warning in payload["warnings"])


def test_explain_resolution_path_reports_local_override(service) -> None:
    payload = service.explain_resolution_path("vault.lab.lockwd.io")
    assert payload["local_matches"][0]["hostname"] == "vault"
    assert "local host override" in payload["summary"]


def test_capture_dns_diagnosis_writes_snapshot_and_returns_summary(
    service, temp_workspace: Path
) -> None:
    payload = service.capture_dns_diagnosis()
    snapshot_path = Path(payload["snapshot"]["path"])
    assert snapshot_path.exists()
    assert payload["topology"]["summary"]
    assert payload["warnings"]


def test_apply_reconfigure_validate_finalize_writes_history_and_snapshot(
    service, temp_workspace: Path
) -> None:
    plan = ChangePlan.model_validate(
        service.plan_change(
            summary="update dnsmasq option 6",
            requested_change="Advertise Pi-hole as LAN DNS",
            module="dnsmasq",
            record_type="option",
            intent="upsert",
            match_fields={"option": "6"},
            values={"value": "172.19.10.242", "description": "Use new Pi-hole IP"},
        )
    )
    approval = ChangeApproval(approved=True, approved_by="tester", reason="unit test")
    apply_payload = service.apply_change(plan, approval)
    service_payload = service.reconfigure_services(plan.services)
    validation_payload = service.validate_change(plan)

    operation_results = [
        OperationExecution.model_validate(row) for row in apply_payload["operation_results"]
    ]
    service_results = [
        OperationExecution.model_validate(row) for row in service_payload["service_results"]
    ]
    validation_results = [
        ValidationResult.model_validate(row) for row in validation_payload["results"]
    ]

    finalize = service.finalize_change(
        plan=plan,
        approval=approval,
        operation_results=operation_results,
        service_results=service_results,
        validation_results=validation_results,
    )

    history_path = Path(finalize["history_path"])
    snapshot_path = Path(finalize["snapshot_path"])
    assert history_path.exists()
    assert snapshot_path.exists()
    parsed = parse_history_record(history_path.read_text(encoding="utf-8"))
    assert parsed.summary == "update dnsmasq option 6"
    assert parsed.validation_results[0].ok is True


def test_rollback_change_uses_previous_commit_state(service) -> None:
    first_plan = ChangePlan.model_validate(
        service.plan_change(
            summary="add vault override",
            requested_change="Create vault.lab.lockwd.io",
            module="unbound",
            record_type="host_override",
            intent="upsert",
            match_fields={"hostname": "vault", "domain": "lab.lockwd.io"},
            values={"server": "172.19.10.54", "description": "Vault DNS"},
        )
    )
    approval = ChangeApproval(approved=True, approved_by="tester", reason="seed")
    first_apply = service.apply_change(first_plan, approval)
    first_services = service.reconfigure_services(first_plan.services)
    first_validation = service.validate_change(first_plan)
    first_finalize = service.finalize_change(
        plan=first_plan,
        approval=approval,
        operation_results=[
            OperationExecution.model_validate(row) for row in first_apply["operation_results"]
        ],
        service_results=[
            OperationExecution.model_validate(row) for row in first_services["service_results"]
        ],
        validation_results=[
            ValidationResult.model_validate(row) for row in first_validation["results"]
        ],
    )

    second_plan = ChangePlan.model_validate(
        service.plan_change(
            summary="remove kube override",
            requested_change="Delete kube.lab.lockwd.io",
            module="unbound",
            record_type="host_override",
            intent="delete",
            match_fields={"hostname": "kube", "domain": "lab.lockwd.io"},
            values={},
        )
    )
    second_apply = service.apply_change(second_plan, approval)
    second_services = service.reconfigure_services(second_plan.services)
    second_validation = service.validate_change(second_plan)
    service.finalize_change(
        plan=second_plan,
        approval=approval,
        operation_results=[
            OperationExecution.model_validate(row) for row in second_apply["operation_results"]
        ],
        service_results=[
            OperationExecution.model_validate(row) for row in second_services["service_results"]
        ],
        validation_results=[
            ValidationResult.model_validate(row) for row in second_validation["results"]
        ],
    )

    rollback = service.rollback_change(
        first_finalize["commit_sha"], approved_by="tester", reason="restore"
    )
    assert rollback["plan"]["rollback"]["target_ref"] == first_finalize["commit_sha"]
    assert rollback["validation"]["ok"] is True
