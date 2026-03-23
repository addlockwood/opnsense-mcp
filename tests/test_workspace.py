from pathlib import Path

from opnsense_mcp.models import ChangePlan, ChangeRecordMetadata, ManagedState
from opnsense_mcp.workspace import WorkspaceManager, parse_history_record


def test_history_round_trip(config) -> None:
    workspace = WorkspaceManager(config)
    plan = ChangePlan(
        summary="example change",
        requested_change="Example request",
        module="unbound",
        record_type="host_override",
        intent="upsert",
        affected_modules=["unbound"],
        operations=[],
        services=[],
        validation_checks=[],
        rollback={"workspace_head": "abc123"},
    )
    metadata = ChangeRecordMetadata(
        summary="example change",
        requested_change="Example request",
        approved_by="tester",
        approval_reason="test",
        plan=plan,
        applied_at="2026-03-23T00:00:00+00:00",
        operation_results=[],
        service_results=[],
        validation_results=[],
        snapshot_path="snapshots/current-config.xml",
        rollback_target="abc123",
        managed_state=ManagedState(records={"unbound": {"host_override": []}}),
    )
    path = workspace.write_history_record(metadata)
    parsed = parse_history_record(path.read_text(encoding="utf-8"))
    assert parsed.summary == metadata.summary
    assert parsed.rollback_target == "abc123"


def test_capture_snapshot_writes_valid_xml(config) -> None:
    workspace = WorkspaceManager(config)
    result = workspace.capture_snapshot("<?xml version='1.0'?><opnsense />")
    assert result.valid_xml is True
    assert Path(result.path).exists()
