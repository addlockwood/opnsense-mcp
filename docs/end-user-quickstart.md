# End-User Quick Start

This guide is for users who want to use `opnsense-mcp` without building the project from source.

## What You Need

- Docker installed locally
- Codex or Cursor installed locally
- an OPNsense API key and secret
- a private local folder or repo for writable state

## 1. Pull The Image

Once published, pull the latest release image:

```bash
docker pull ghcr.io/addlockwood/opnsense-mcp:latest
```

If you prefer a pinned release, replace `latest` with a version tag.

## 2. Bootstrap The Local State Repo

Download the bootstrap script from the latest GitHub release and run it locally:

```bash
curl -fsSL -o setup-local.sh \
  https://github.com/addlockwood/opnsense-mcp/releases/latest/download/setup-local.sh
chmod +x setup-local.sh
./setup-local.sh
```

The script only prepares your private router-state repo and local launcher; it does not build the image.

Recommended normal defaults:

- repo path: `~/dev/opnsense`
- Codex MCP server name: `opnsense`

For isolated testing, override those to something like:

- repo path: `~/dev/opnsense-uat`
- Codex MCP server name: `opnsense-uat`

The script will create:

- `history/`
- `snapshots/`
- `.env.local.example`
- `.env.local`
- `run-opnsense-mcp.sh`

It can also register the MCP server in Codex for you.

## 3. Fill In OPNsense Credentials

Edit the generated `.env.local` and set:

- `OPNSENSE_BASE_URL`
- `OPNSENSE_API_KEY`
- `OPNSENSE_API_SECRET`

Default example:

```env
OPNSENSE_BASE_URL=http://opnsense.internal
OPNSENSE_API_KEY=replace-me
OPNSENSE_API_SECRET=replace-me
OPNSENSE_VERIFY_TLS=false
```

## 4. Confirm The Launcher Image

The generated launcher defaults to:

```bash
ghcr.io/addlockwood/opnsense-mcp:latest
```

If you want to pin a specific release, edit `run-opnsense-mcp.sh` and replace `latest` with a version tag.

## 5. Verify Codex MCP Registration

```bash
codex mcp list
```

You should see the configured server name, such as `opnsense`.

## 6. Start UAT Safely

In a fresh Codex session, begin with:

```text
Use only the opnsense MCP server. First run inspect_runtime, then inspect_state for unbound and dnsmasq. Do not inspect local repos or files outside the MCP workspace.
```

If you used a custom server name like `opnsense-uat`, replace the server name in that prompt.

## 7. What Good UAT Looks Like

- `inspect_runtime` reports `/workspace`
- `inspect_state` returns live OPNsense data
- `snapshots/current-config.xml` appears in your private repo
- `history/` stays empty until you actually finalize a validated change

## Build From Source Instead

If you want to build the image locally rather than pull it, go back to the main [`README.md`](../README.md) and use the `Build From Source` section.
