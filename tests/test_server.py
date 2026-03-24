from dataclasses import replace

from opnsense_mcp.server import build_server


def test_build_server_uses_http_runtime_settings(config) -> None:
    http_config = replace(
        config,
        transport="streamable-http",
        http_host="0.0.0.0",
        http_port=8080,
        http_path="/mcp",
    )

    server = build_server(http_config)

    assert server.settings.host == "0.0.0.0"
    assert server.settings.port == 8080
    assert server.settings.streamable_http_path == "/mcp"
    assert server.settings.stateless_http is False
    assert server.settings.lifespan is None


def test_build_server_can_enable_stateless_http(config) -> None:
    http_config = replace(
        config,
        transport="streamable-http",
        http_host="0.0.0.0",
        http_port=8080,
        http_path="/mcp",
        stateless_http=True,
    )

    server = build_server(http_config)

    assert server.settings.stateless_http is True
