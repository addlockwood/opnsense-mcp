from __future__ import annotations

from opnsense_mcp.server import build_server


def main() -> None:
    build_server().run()


if __name__ == "__main__":
    main()
