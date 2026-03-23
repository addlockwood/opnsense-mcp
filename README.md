# opnsense-mcp

Standalone MCP server for managing OPNsense Core API workflows from any MCP client.

## Quick Start

Stage 1 is the default path for most users:

- pull a released Docker image
- bootstrap a private local state repo
- run the MCP as a local Dockerized stdio server
- mount a private local state repo into `/workspace`
- connect from Codex or Cursor on the same machine
- validate the OPNsense workflow locally before considering any remote deployment

Advanced private remote hosting is intentionally deferred to stage 2.

For most users, start with the end-user quick start:

```bash
docs/end-user-quickstart.md
```

Default bootstrap values:

- repo path: `~/dev/opnsense`
- Codex MCP server name: `opnsense`
- base URL example: `http://opnsense.internal`

If you are testing or want an isolated workspace, override these to something like `opnsense-uat`.

## What it does

- exposes structured MCP tools for discovery, planning, apply, validation, snapshot, and rollback
- uses the official OPNsense Core API directly
- writes history and XML snapshots into a mounted private state repo
- creates git commits only after validation succeeds

## Stage 1 Runtime Model

The published server image stays generic. Router-specific state lives in a separate mounted workspace.

- mount your private router-state repo into the container at `/workspace`
- provide OPNsense API credentials through environment variables
- run the server over stdio from your MCP client
- keep the state repo local to your workstation during UAT

## Stage 2 Runtime Model

Stage 2 is an advanced deployment for private remote hosting in a homelab or similar always-on environment.

- add remote MCP HTTP transport later
- host it privately behind HTTPS
- keep the same mounted workspace and history/snapshot contract
- do not treat this as the default onboarding path

## Configuration

Required environment variables:

- `OPNSENSE_BASE_URL`
- `OPNSENSE_API_KEY`
- `OPNSENSE_API_SECRET`

Optional environment variables:

- `OPNSENSE_VERIFY_TLS` default `false`
- `OPNSENSE_WORKSPACE_PATH` default `/workspace`
- `OPNSENSE_SNAPSHOT_HOST` default `this`
- `OPNSENSE_GIT_AUTHOR_NAME`
- `OPNSENSE_GIT_AUTHOR_EMAIL`

## Private State Repo Layout

Your mounted workspace should be a private git repo. The MCP server will create and update:

```text
private-router-state/
  history/
    20260323-120000-update-dnsmasq-option-6.md
  snapshots/
    current-config.xml
```

Recommended setup:

```bash
mkdir -p ~/dev/opnsense/history
mkdir -p ~/dev/opnsense/snapshots
cd ~/dev/opnsense
git init
```

Or let the bootstrap script create this layout and register Codex for you.

## Local development

Contributor and source-build workflow:

```bash
docker build --target dev -t opnsense-mcp:dev .
docker run --rm opnsense-mcp:dev pytest
docker run --rm opnsense-mcp:dev ruff check .
docker run --rm opnsense-mcp:dev ruff format --check .
docker run --rm opnsense-mcp:dev mypy src
```

## Released Image Setup

If you are using a published release, pull the latest image and download the bootstrap script:

```bash
docker pull ghcr.io/addlockwood/opnsense-mcp:latest
curl -fsSL -o setup-local.sh \
  https://github.com/addlockwood/opnsense-mcp/releases/latest/download/setup-local.sh
chmod +x setup-local.sh
./setup-local.sh
```

The bootstrap script will:

- ask where to create the private repo
- ask what Codex MCP server name to use
- scaffold the writable repo layout
- create the local launcher script
- optionally register the stdio MCP server in Codex

By default, the generated launcher points at `ghcr.io/addlockwood/opnsense-mcp:latest`.
After that, edit the generated `.env.local` in your private repo and fill in your OPNsense API values.

## Build From Source

If you want to build locally instead of pulling a release:

```bash
docker build --target runtime -t opnsense-mcp:runtime .
./scripts/setup-local.sh ~/dev/opnsense opnsense opnsense-mcp:runtime
```

For a normal install, accept the defaults.
For testing, choose a different repo and server name such as `opnsense-uat`.

Run it as a local stdio MCP server:

```bash
docker run --rm -i \
  -e OPNSENSE_BASE_URL=https://router.example \
  -e OPNSENSE_API_KEY=... \
  -e OPNSENSE_API_SECRET=... \
  -e OPNSENSE_VERIFY_TLS=false \
  -v /path/to/private-router-repo:/workspace \
  opnsense-mcp:local
```

For a real local UAT run, point `/path/to/private-router-repo` at your private state repo, not this public project repo.

## MCP Client Setup

Example local stdio configuration files live under [`examples/`](./examples):

- Codex: [`examples/codex/config.toml`](./examples/codex/config.toml)
- Cursor: [`examples/cursor/mcp.json`](./examples/cursor/mcp.json)
- Bootstrap script: [`scripts/setup-local.sh`](./scripts/setup-local.sh)
- End-user guide: [`docs/end-user-quickstart.md`](./docs/end-user-quickstart.md)

These examples assume:

- the Docker image is available locally, either from a published registry or a local build
- your local private state repo is mounted from your workstation
- your OPNsense API credentials are provided as environment variables on the host

For most users, the bootstrap script plus the published GHCR image is the easier path because it generates the launcher and local repo automatically without requiring a source checkout.

## UAT Checklist

Use this checklist for stage-1 acceptance:

1. Connect from Codex or Cursor to the local Docker stdio server.
2. Run `inspect_runtime` first and confirm the workspace path is `/workspace` and maps to your private mounted UAT repo, not your source repo.
3. Run `list_core_modules` and `inspect_state` against the live router.
4. Generate a plan for one supported change without applying it yet.
5. Confirm and apply one supported mutation.
6. Reconfigure only the affected OPNsense service.
7. Validate the changed state through API readback.
8. Confirm `snapshots/current-config.xml` is written to the mounted private repo.
9. Confirm a new history entry is written to `history/`.
10. Confirm the mounted private repo receives a known-good git commit.
11. Roll back to the previous commit and validate the restored state.

## Tooling overview

- `list_core_modules`
- `inspect_runtime`
- `inspect_state`
- `search_records`
- `plan_change`
- `apply_change`
- `reconfigure_services`
- `validate_change`
- `capture_snapshot`
- `rollback_change`

## Notes

V1 supports broad Core API discovery, with staged write adapters for supported record types. Today the implemented mutation adapters cover:

- `unbound.settings.host_override`
- `dnsmasq.settings.option`

Other modules remain inspectable and plan-oriented until their write payloads are confirmed.

## Advanced Deployment

Stage 2 deployment guidance lives in [`docs/advanced-deployment.md`](./docs/advanced-deployment.md).

That path is for:

- private remote HTTP MCP hosting
- homelab or cluster deployment
- HTTPS ingress and deployment-specific networking

It is intentionally not required for local UAT.
