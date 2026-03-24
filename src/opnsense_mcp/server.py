from __future__ import annotations

from typing import Any

from mcp.server.fastmcp import FastMCP

from opnsense_mcp.config import AppConfig
from opnsense_mcp.models import ChangeApproval, ChangePlan
from opnsense_mcp.service import OPNsenseMCPService


def build_server(config: AppConfig | None = None) -> FastMCP:
    app_config = config or AppConfig.from_env()
    app_config.validate_runtime()
    service = OPNsenseMCPService(app_config)

    mcp = FastMCP(
        "OPNsense MCP",
        json_response=True,
        stateless_http=app_config.stateless_http,
        host=app_config.http_host,
        port=app_config.http_port,
        streamable_http_path=app_config.http_path,
    )

    @mcp.tool()
    def list_core_modules() -> list[dict[str, Any]]:
        """List documented OPNsense Core API modules and local support level."""
        return service.list_core_modules()

    @mcp.tool()
    def inspect_runtime() -> dict[str, Any]:
        """Report the active mounted workspace and current local UAT state files."""
        return service.inspect_runtime()

    @mcp.tool()
    def inspect_state(module: str) -> dict[str, Any]:
        """Inspect live state for a supported module."""
        return service.inspect_state(module)

    @mcp.tool()
    def connectivity_preflight() -> dict[str, Any]:
        """Check router reachability, auth, workspace writability, and snapshot access."""
        return service.connectivity_preflight()

    @mcp.tool()
    def inspect_dhcp() -> dict[str, Any]:
        """Inspect DHCP state, option 6, and the DNS resolvers clients are being told to use."""
        return service.inspect_dhcp()

    @mcp.tool()
    def inspect_dns_topology() -> dict[str, Any]:
        """Inspect DNS ownership, forwarding, DHCP-advertised resolvers, and topology risks."""
        return service.inspect_dns_topology()

    @mcp.tool()
    def explain_resolution_path(hostname: str) -> dict[str, Any]:
        """Explain how a specific hostname is expected to resolve for clients and the firewall."""
        return service.explain_resolution_path(hostname)

    @mcp.tool()
    def capture_dns_diagnosis() -> dict[str, Any]:
        """Capture a live snapshot and return a normalized DNS/DHCP diagnosis bundle."""
        return service.capture_dns_diagnosis()

    @mcp.tool()
    def search_records(module: str, record_type: str, phrase: str = "") -> dict[str, Any]:
        """Search supported records within a module."""
        return service.search_records(module, record_type, phrase)

    @mcp.tool()
    def plan_change(
        summary: str,
        requested_change: str,
        module: str,
        record_type: str,
        intent: str,
        match_fields: dict[str, str],
        values: dict[str, str] | None = None,
    ) -> dict[str, Any]:
        """Create a structured change plan for a supported record type."""
        return service.plan_change(
            summary=summary,
            requested_change=requested_change,
            module=module,
            record_type=record_type,
            intent=intent,
            match_fields=match_fields,
            values=values,
        )

    @mcp.tool()
    def apply_change(plan: ChangePlan, approval: ChangeApproval) -> dict[str, Any]:
        """Apply a previously generated plan after explicit approval."""
        return service.apply_change(plan, approval)

    @mcp.tool()
    def reconfigure_services(plan: ChangePlan) -> dict[str, Any]:
        """Run service reconfigure actions required by a plan."""
        return service.reconfigure_services(plan.services)

    @mcp.tool()
    def validate_change(plan: ChangePlan) -> dict[str, Any]:
        """Validate that plan effects are visible through API readback."""
        return service.validate_change(plan)

    @mcp.tool()
    def capture_snapshot() -> dict[str, Any]:
        """Capture the live full config XML into the mounted workspace."""
        return service.capture_snapshot()

    @mcp.tool()
    def rollback_change(target_ref: str, approved_by: str, reason: str) -> dict[str, Any]:
        """Rollback managed state to a previous git ref."""
        return service.rollback_change(target_ref, approved_by, reason)

    return mcp
