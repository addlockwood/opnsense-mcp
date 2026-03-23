from pathlib import Path

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
