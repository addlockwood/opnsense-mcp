from __future__ import annotations

from dataclasses import dataclass

from opnsense_mcp.adapters.base import RecordAdapter
from opnsense_mcp.adapters.dnsmasq import DnsmasqOptionAdapter
from opnsense_mcp.adapters.unbound import UnboundHostOverrideAdapter
from opnsense_mcp.errors import UnsupportedModuleError
from opnsense_mcp.models import ModuleMetadata

CORE_MODULES: tuple[tuple[str, str], ...] = (
    ("auth", "Authentication and authorization"),
    ("captiveportal", "Captive portal"),
    ("core", "Core system APIs"),
    ("cron", "Cron jobs"),
    ("dhcrelay", "DHCP relay"),
    ("diagnostics", "Diagnostics"),
    ("dnsmasq", "Dnsmasq DNS and DHCP"),
    ("firewall", "Firewall"),
    ("firmware", "Firmware"),
    ("hostdiscovery", "Host discovery"),
    ("ids", "Intrusion detection"),
    ("interfaces", "Interface management"),
    ("ipsec", "IPsec"),
    ("kea", "Kea DHCP"),
    ("monit", "Monit"),
    ("ntpd", "NTP daemon"),
    ("openvpn", "OpenVPN"),
    ("radvd", "Router advertisements"),
    ("routes", "Routes"),
    ("routing", "Routing"),
    ("syslog", "Syslog"),
    ("trafficshaper", "Traffic shaper"),
    ("trust", "Trust and certificates"),
    ("unbound", "Unbound DNS"),
    ("wireguard", "WireGuard"),
)


@dataclass(frozen=True)
class ModuleDescriptor:
    metadata: ModuleMetadata
    adapters: dict[str, RecordAdapter]


class CoreModuleRegistry:
    def __init__(self) -> None:
        descriptors: dict[str, ModuleDescriptor] = {}
        for name, description in CORE_MODULES:
            descriptors[name] = ModuleDescriptor(
                metadata=ModuleMetadata(
                    name=name,
                    docs_slug=name,
                    description=description,
                    inspectable=True,
                    mutable=False,
                    supported_record_types=[],
                ),
                adapters={},
            )

        self._descriptors = descriptors
        self._register_adapter(UnboundHostOverrideAdapter())
        self._register_adapter(DnsmasqOptionAdapter())

    def _register_adapter(self, adapter: RecordAdapter) -> None:
        descriptor = self._descriptors[adapter.module]
        adapters = dict(descriptor.adapters)
        adapters[adapter.record_type] = adapter
        self._descriptors[adapter.module] = ModuleDescriptor(
            metadata=ModuleMetadata(
                name=descriptor.metadata.name,
                docs_slug=descriptor.metadata.docs_slug,
                description=descriptor.metadata.description,
                inspectable=descriptor.metadata.inspectable,
                mutable=True,
                supported_record_types=sorted(adapters),
            ),
            adapters=adapters,
        )

    def list_modules(self) -> list[ModuleMetadata]:
        return [self._descriptors[name].metadata for name, _ in CORE_MODULES]

    def get_module(self, module: str) -> ModuleDescriptor:
        try:
            return self._descriptors[module]
        except KeyError as exc:
            raise UnsupportedModuleError(f"Unsupported Core API module: {module}") from exc

    def get_adapter(self, module: str, record_type: str) -> RecordAdapter:
        descriptor = self.get_module(module)
        try:
            return descriptor.adapters[record_type]
        except KeyError as exc:
            raise UnsupportedModuleError(
                f"Unsupported record type '{record_type}' for module '{module}'"
            ) from exc
