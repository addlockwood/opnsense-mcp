from __future__ import annotations

import re
import xml.etree.ElementTree as ET
from dataclasses import dataclass
from typing import cast
from urllib.parse import urlparse


@dataclass(frozen=True)
class SnapshotDnsState:
    system_hostname: str
    system_domain: str
    system_dns_servers: list[str]
    dns_allow_override: bool
    dnsmasq_settings: dict[str, str]
    dnsmasq_dhcp_ranges: list[dict[str, str]]
    dnsmasq_dhcp_options: list[dict[str, str]]
    unbound_general: dict[str, str]
    unbound_forwarding: dict[str, str]
    unbound_host_overrides: list[dict[str, str]]
    unbound_domain_overrides: list[dict[str, str]]


def parse_snapshot_dns_state(xml_text: str) -> SnapshotDnsState:
    root = ET.fromstring(xml_text)

    return SnapshotDnsState(
        system_hostname=_text(root.find("./system/hostname")),
        system_domain=_text(root.find("./system/domain")),
        system_dns_servers=[
            _text(elem) for elem in root.findall("./system/dnsserver") if _text(elem)
        ],
        dns_allow_override=_text(root.find("./system/dnsallowoverride")) == "1",
        dnsmasq_settings=_child_map(root.find("./dnsmasq")),
        dnsmasq_dhcp_ranges=_collection(root.find("./dnsmasq/dhcp_ranges")),
        dnsmasq_dhcp_options=_collection(root.find("./dnsmasq/dhcp_options")),
        unbound_general=_child_map(root.find("./OPNsense/unboundplus/general")),
        unbound_forwarding=_child_map(root.find("./OPNsense/unboundplus/forwarding")),
        unbound_host_overrides=_collection(root.find("./OPNsense/unboundplus/hosts")),
        unbound_domain_overrides=_collection(
            root.find("./OPNsense/unboundplus/forwarding/domainoverrides")
        ),
    )


def split_dns_servers(value: str) -> list[str]:
    parts = [piece.strip() for piece in re.split(r"[\s,;]+", value) if piece.strip()]
    return parts


def router_host(base_url: str) -> str:
    return urlparse(base_url).hostname or ""


def fqdn_for_snapshot(state: SnapshotDnsState) -> str:
    if state.system_hostname and state.system_domain:
        return f"{state.system_hostname}.{state.system_domain}"
    return state.system_hostname or state.system_domain


def summarize_dhcp(
    *,
    state: SnapshotDnsState,
    option_rows: list[dict[str, str]],
    dnsmasq_status: str,
) -> dict[str, object]:
    option6_rows = [row for row in option_rows if row.get("option") == "6"]
    advertised_dns_servers: list[str] = []
    for row in option6_rows:
        raw_value = row.get("value", "") or row.get("option6", "")
        advertised_dns_servers.extend(split_dns_servers(raw_value))
    advertised_dns_servers = list(dict.fromkeys(advertised_dns_servers))

    dhcp_enabled = _boolish(state.dnsmasq_settings.get("dhcp")) or bool(state.dnsmasq_dhcp_ranges)
    summary = (
        "LAN clients are explicitly advertised these DNS resolvers via DHCP option 6: "
        + ", ".join(advertised_dns_servers)
        if advertised_dns_servers
        else (
            "No explicit DHCP option 6 is configured; clients may fall back to the interface "
            "default."
        )
    )

    warnings: list[str] = []
    if advertised_dns_servers and state.unbound_host_overrides:
        warnings.append(
            "Clients use DHCP-advertised DNS servers while OPNsense Unbound owns local "
            "host overrides."
        )
    if not dhcp_enabled:
        warnings.append(
            "Dnsmasq DHCP does not appear to have active ranges in the current snapshot."
        )

    return {
        "dnsmasq_status": dnsmasq_status,
        "dnsmasq_enabled": _boolish(state.dnsmasq_settings.get("enable")),
        "dhcp_enabled": dhcp_enabled,
        "dhcp_ranges": state.dnsmasq_dhcp_ranges,
        "dhcp_option_6_records": option6_rows,
        "advertised_dns_servers": advertised_dns_servers,
        "summary": summary,
        "warnings": warnings,
    }


def summarize_dns_topology(
    *,
    state: SnapshotDnsState,
    option_rows: list[dict[str, str]],
    unbound_rows: list[dict[str, str]],
    unbound_status: str,
    dnsmasq_status: str,
    base_url: str,
) -> dict[str, object]:
    dhcp = summarize_dhcp(state=state, option_rows=option_rows, dnsmasq_status=dnsmasq_status)
    dhcp_warnings = cast(list[str], dhcp["warnings"])
    advertised_dns_servers = cast(list[str], dhcp["advertised_dns_servers"])
    router_fqdn = fqdn_for_snapshot(state)
    firewall_dns_summary = (
        "The firewall is configured with explicit upstream resolvers: "
        + ", ".join(state.system_dns_servers)
        if state.system_dns_servers
        else "The firewall does not list explicit upstream DNS servers in the current snapshot."
    )

    warnings = list(dhcp_warnings)
    if state.system_dns_servers and unbound_rows:
        warnings.append(
            "The firewall has explicit system DNS servers configured while Unbound also owns "
            "local records."
        )
    if _boolish(state.unbound_forwarding.get("enabled")) and unbound_rows:
        warnings.append(
            "Unbound forwarding is enabled while local overrides are present; verify ownership "
            "for affected zones."
        )
    if advertised_dns_servers and router_host(base_url) not in advertised_dns_servers:
        warnings.append(
            "Clients are not being pointed at the same resolver endpoint used for OPNsense "
            "API access."
        )

    summary = (
        "OPNsense Unbound owns local DNS records, while DHCP is advertising external DNS servers."
        if advertised_dns_servers and unbound_rows
        else "Resolver ownership looks aligned from the current snapshot and managed API records."
    )

    return {
        "firewall_identity": {
            "hostname": state.system_hostname,
            "domain": state.system_domain,
            "fqdn": router_fqdn,
        },
        "firewall_resolution": {
            "system_dns_servers": state.system_dns_servers,
            "dns_allow_override": state.dns_allow_override,
            "summary": firewall_dns_summary,
        },
        "unbound": {
            "status": unbound_status,
            "enabled": _boolish(state.unbound_general.get("enabled", "1")),
            "forwarding_enabled": _boolish(state.unbound_forwarding.get("enabled")),
            "host_overrides": unbound_rows,
            "domain_overrides": state.unbound_domain_overrides,
            "settings": state.unbound_general,
        },
        "dnsmasq": {
            "status": dnsmasq_status,
            "enabled": _boolish(state.dnsmasq_settings.get("enable")),
            "settings": state.dnsmasq_settings,
            "dhcp": dhcp,
        },
        "summary": summary,
        "warnings": list(dict.fromkeys(warnings)),
    }


def explain_resolution_path(
    hostname: str,
    *,
    state: SnapshotDnsState,
    option_rows: list[dict[str, str]],
    unbound_rows: list[dict[str, str]],
    base_url: str,
) -> dict[str, object]:
    requested = hostname.rstrip(".")
    host_label, domain = _split_hostname(requested)
    local_matches = [
        row
        for row in unbound_rows
        if row.get("hostname", "") == host_label and row.get("domain", "") == domain
    ]
    forwarding_matches = [
        row for row in state.unbound_domain_overrides if domain.endswith(row.get("domain", ""))
    ]
    dhcp = summarize_dhcp(
        state=state,
        option_rows=option_rows,
        dnsmasq_status=state.dnsmasq_settings.get("enable", "0"),
    )
    advertised_dns_servers = cast(list[str], dhcp["advertised_dns_servers"])
    client_path = (
        "Clients will send this query to the DHCP-advertised resolvers: "
        + ", ".join(advertised_dns_servers)
        if advertised_dns_servers
        else (
            "Clients likely query the default router resolver path because no explicit DHCP "
            "option 6 was found."
        )
    )
    if local_matches:
        resolver_summary = "OPNsense Unbound answers this hostname from a local host override."
    elif forwarding_matches:
        resolver_summary = "OPNsense Unbound forwards this hostname's domain to an override target."
    else:
        resolver_summary = (
            "No local Unbound ownership was found; this hostname is expected to resolve via "
            "the configured upstream path."
        )

    warnings: list[str] = []
    if local_matches and advertised_dns_servers:
        warnings.append(
            "Clients may bypass the local Unbound override if their DHCP-advertised DNS does "
            "not point back to OPNsense."
        )
    if not local_matches and not forwarding_matches and state.system_dns_servers:
        warnings.append(
            "Resolution depends on upstream/system DNS because no local ownership was detected."
        )

    return {
        "hostname": requested,
        "client_resolution_path": client_path,
        "firewall_resolution_path": resolver_summary,
        "local_matches": local_matches,
        "forwarding_matches": forwarding_matches,
        "advertised_dns_servers": advertised_dns_servers,
        "router_api_host": router_host(base_url),
        "summary": resolver_summary,
        "warnings": warnings,
    }


def _text(elem: ET.Element | None) -> str:
    if elem is None or elem.text is None:
        return ""
    return elem.text.strip()


def _child_map(elem: ET.Element | None) -> dict[str, str]:
    if elem is None:
        return {}
    return {child.tag: _text(child) for child in list(elem)}


def _collection(elem: ET.Element | None) -> list[dict[str, str]]:
    if elem is None:
        return []
    children = list(elem)
    if not children:
        value = _text(elem)
        return [{"value": value}] if value else []

    rows: list[dict[str, str]] = []
    for child in children:
        if list(child):
            rows.append({grandchild.tag: _text(grandchild) for grandchild in list(child)})
            continue
        value = _text(child)
        if value:
            rows.append({child.tag: value})
    return rows


def _boolish(value: str | None) -> bool:
    return (value or "").strip().lower() in {"1", "true", "yes", "on"}


def _split_hostname(hostname: str) -> tuple[str, str]:
    if "." not in hostname:
        return hostname, ""
    host, domain = hostname.split(".", 1)
    return host, domain
