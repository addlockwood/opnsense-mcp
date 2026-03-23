# Private Router State Repo

This directory documents the expected shape of the private mounted workspace.

Do not use the public `opnsense-mcp` source repo itself as the writable state repo.

Recommended local setup:

```bash
mkdir -p ~/dev/opnsense/history
mkdir -p ~/dev/opnsense/snapshots
cd ~/dev/opnsense
git init
```

Expected structure after UAT begins:

```text
opnsense/
  history/
  snapshots/
    current-config.xml
```

The MCP server writes:

- history markdown records
- the current XML snapshot
- known-good commits after validation
