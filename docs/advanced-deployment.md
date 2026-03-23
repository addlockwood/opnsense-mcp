# Advanced Deployment

Stage 2 is the advanced deployment path for private remote hosting after local Docker UAT succeeds.

## Intended shape

- run the same MCP server over Streamable HTTP
- host the server privately behind HTTPS
- keep the same workspace contract used in local UAT
- deploy to a homelab or similar always-on environment such as k3s

## Default remote target

The first supported remote target is:

- private hostname `opnsense-mcp.lab.lockwd.io`
- Traefik ingress with TLS
- private network access only
- pinned-node `hostPath` mounted private state repo at `/workspace`
- Kubernetes secret-backed OPNsense credentials

## Cluster assumptions

- label exactly one state-owning node with `opnsense-mcp-state=true`
- create or populate the host path `/srv/opnsense-mcp/router-state` on that node
- replace placeholder values in the `opnsense-mcp-env` Secret before sync
- keep the deployment private behind your existing Traefik and wildcard TLS setup

## Manifest layout

The reference k3s manifests live in your GitOps repo under:

- `apps/opnsense-mcp-app.yaml`
- `apps/opnsense-mcp/`

That deployment:

- runs `OPNSENSE_MCP_TRANSPORT=streamable-http`
- exposes `/mcp` on port `8000`
- mounts the writable private router-state repo
- uses a Traefik `IngressRoute` on `websecure`

Use the local Docker stdio flow first, then move to this private HTTPS deployment when you want a shared remote MCP endpoint.
