from __future__ import annotations

from typing import Literal, cast

from opnsense_mcp.config import AppConfig
from opnsense_mcp.server import build_server


def main() -> None:
    config = AppConfig.from_env()
    transport = cast(Literal["stdio", "sse", "streamable-http"], config.transport)
    build_server(config).run(transport=transport)


if __name__ == "__main__":
    main()
