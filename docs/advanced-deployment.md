# Advanced Deployment

Stage 2 is the advanced deployment path for private remote hosting after local Docker UAT succeeds.

## Intended shape

- add remote MCP HTTP transport to the server
- host the server privately behind HTTPS
- keep the same workspace contract used in local UAT
- deploy to a homelab or similar always-on environment such as k3s

## Example future target

For the lab described during planning, the likely target is:

- private hostname such as `opnsense-mcp.lab.lockwd.io`
- Traefik ingress with TLS
- private network access only
- mounted private state repo
- Kubernetes secret-backed OPNsense credentials

## Not in stage 1

The following are intentionally deferred until after local UAT:

- remote MCP transport
- cluster manifests
- ingress configuration
- private HTTP/TLS exposure
- homelab GitOps rollout

Use the local Docker stdio flow first.
