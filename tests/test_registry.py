from opnsense_mcp.registry import CoreModuleRegistry


def test_registry_lists_core_modules() -> None:
    registry = CoreModuleRegistry()
    modules = registry.list_modules()
    names = [module.name for module in modules]
    assert "unbound" in names
    assert "dnsmasq" in names
    assert "wireguard" in names


def test_registry_marks_mutable_modules_with_supported_record_types() -> None:
    registry = CoreModuleRegistry()
    unbound = registry.get_module("unbound").metadata
    dnsmasq = registry.get_module("dnsmasq").metadata
    assert unbound.mutable is True
    assert unbound.supported_record_types == ["host_override"]
    assert dnsmasq.mutable is True
    assert dnsmasq.supported_record_types == ["host", "option"]
