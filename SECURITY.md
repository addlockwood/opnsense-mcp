# Security Notes

`opnsense-mcp` is designed to be published as a public container image and public source repo.

## Trust model

- The MCP server code and container image are public.
- Router-specific state is expected to live in a separate private mounted workspace.
- OPNsense credentials must be provided at runtime through environment variables or secret files.
- Secrets must never be committed into this repo or baked into container images.

## Recommended operator practices

- Prefer `https://` OPNsense endpoints with trusted certificates.
- Leave `OPNSENSE_VERIFY_TLS=true` whenever possible.
- Use `OPNSENSE_ALLOW_INSECURE_HTTP=true` only for trusted local lab environments.
- Use a dedicated OPNsense API account for this MCP instead of a shared admin credential.
- Scope the API key to the smallest practical permission set.
- Keep the mounted workspace private because it contains change history and live config snapshots.
- Rotate credentials immediately if they are ever pasted into chat, logs, shell history, or committed by mistake.

## Image hardening

- The published runtime image excludes local `.env` files and test fixtures.
- The runtime image runs as a non-root user by default.
- The generated local launcher runs the container as the calling host user so mounted private repos stay writable without granting the container root access.

## Reporting

If you discover a security issue, please avoid filing a public issue with live credentials or router details attached.
