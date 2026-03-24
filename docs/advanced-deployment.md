# Advanced Deployment

This guide is for users who want to host `opnsense-mcp` as a private remote MCP server instead of running it as a local stdio server.

For most users, the default path is still the local quick start in [`docs/end-user-quickstart.md`](./end-user-quickstart.md).
Move to remote hosting only when you want an always-on endpoint or a shared MCP server.

## Deployment Model

The remote deployment keeps the same core contract as the local quick start:

- the MCP server runs from the published Docker image
- a writable private workspace is mounted at `/workspace`
- OPNsense credentials are injected through environment variables or a secret manager
- the server writes history and snapshots into the mounted workspace
- the remote transport is Streamable HTTP at `/mcp`

The main difference is that the workspace is now remote too. It lives on the host or shared storage attached to the deployment environment, not on your laptop.

## Generic Defaults

If you run the container directly on a single Docker host, the simplest remote shape is:

- container listens on `0.0.0.0:8000`
- MCP path is `/mcp`
- host port is published as `8000`
- local test URL is `http://localhost:8000/mcp`

Those are transport defaults, not a recommendation to expose the server publicly over plain HTTP.
For real remote use, put the container behind a private HTTPS endpoint such as:

- `https://opnsense-mcp.example.internal/mcp`

## Single-Host Docker Example

This is the simplest advanced deployment and a good stepping stone before Kubernetes:

```bash
mkdir -p /srv/opnsense-mcp/router-state/history
mkdir -p /srv/opnsense-mcp/router-state/snapshots

docker run -d \
  --name opnsense-mcp \
  --restart unless-stopped \
  -p 8000:8000 \
  -e OPNSENSE_BASE_URL=https://opnsense.internal \
  -e OPNSENSE_API_KEY=replace-me \
  -e OPNSENSE_API_SECRET=replace-me \
  -e OPNSENSE_VERIFY_TLS=true \
  -e OPNSENSE_WORKSPACE_PATH=/workspace \
  -e OPNSENSE_MCP_TRANSPORT=streamable-http \
  -e OPNSENSE_MCP_HTTP_HOST=0.0.0.0 \
  -e OPNSENSE_MCP_HTTP_PORT=8000 \
  -e OPNSENSE_MCP_HTTP_PATH=/mcp \
  -v /srv/opnsense-mcp/router-state:/workspace \
  ghcr.io/addlockwood/opnsense-mcp:latest
```

Then verify it locally:

```bash
curl -i http://localhost:8000/mcp
```

A `405` or `406` response is fine here. It confirms the MCP HTTP route exists.

## HTTPS Hosting

For a more realistic remote deployment:

- keep `opnsense-mcp` on a private network
- terminate TLS at a reverse proxy such as Traefik, Caddy, or NGINX
- expose only the `/mcp` endpoint
- prefer a private hostname rather than a raw IP

Example client URL:

- `https://opnsense-mcp.example.internal/mcp`

The container itself can still serve plain HTTP on port `8000` behind the proxy.

## Workspace Persistence

Your mounted workspace should be durable and writable by the container runtime.

Minimum expected layout:

```text
router-state/
  history/
  snapshots/
```

The server will write:

- `history/<timestamp>-<slug>.md`
- `snapshots/current-config.xml`

If you deploy with Docker on a single host, a normal bind mount is fine.
If you deploy in Kubernetes, use either:

- a node-pinned host path
- or shared persistent storage

Choose one location that is treated as the source of truth for the remote workspace.

## Secrets

Do not bake router credentials into the image or commit them into the workspace repo.

Use one of:

- environment variables provided by your deployment platform
- Docker secrets
- Kubernetes secrets
- an external secret manager such as Vault plus External Secrets Operator

Required runtime values:

- `OPNSENSE_BASE_URL`
- `OPNSENSE_API_KEY`
- `OPNSENSE_API_SECRET`

Common optional values:

- `OPNSENSE_VERIFY_TLS`
- `OPNSENSE_WORKSPACE_PATH`
- `OPNSENSE_MCP_TRANSPORT`
- `OPNSENSE_MCP_HTTP_HOST`
- `OPNSENSE_MCP_HTTP_PORT`
- `OPNSENSE_MCP_HTTP_PATH`
- `OPNSENSE_MCP_IMAGE_REF`

## Kubernetes Notes

Kubernetes is supported, but it should be treated as an advanced deployment rather than the default setup.

A typical cluster deployment includes:

- one `Deployment`
- one `Service`
- one ingress or route exposing `/mcp`
- a mounted persistent workspace
- secrets injected from your cluster secret flow

If you use node-local storage, pin the workload so it always lands on the node that owns the workspace path.

## Client Connection

Once the remote endpoint is live, connect your MCP client to the hosted URL rather than a local stdio launcher.

Example:

- `https://opnsense-mcp.example.internal/mcp`

The tool surface and workflow stay the same:

- `connectivity_preflight`
- `inspect_runtime`
- `inspect_dhcp`
- `inspect_dns_topology`
- `explain_resolution_path`
- `plan_change`
- `apply_change`
- `validate_change`
- `rollback_change`

## Recommended Rollout Sequence

1. Validate the workflow locally with the stdio quick start.
2. Stand up the single-host Docker HTTP deployment and confirm `http://localhost:8000/mcp` responds.
3. Add a private HTTPS reverse proxy in front of it.
4. Move to Kubernetes only if you actually want cluster-managed hosting.

That sequence keeps the advanced deployment understandable and avoids turning “host the MCP remotely” into a mandatory cluster project.
