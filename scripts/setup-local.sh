#!/bin/zsh
set -euo pipefail

default_repo_path="${HOME}/dev/opnsense"
default_server_name="opnsense"
default_image="ghcr.io/addlockwood/opnsense-mcp:latest"

repo_path="${1:-}"
server_name="${2:-}"
image_name="${3:-$default_image}"

prompt_with_default() {
  local prompt="$1"
  local default_value="$2"
  local response=""
  printf "%s [%s]: " "${prompt}" "${default_value}" >&2
  read -r response
  if [[ -z "${response}" ]]; then
    printf "%s" "${default_value}"
  else
    printf "%s" "${response}"
  fi
}

yes_no_default() {
  local prompt="$1"
  local default_value="$2"
  local response=""
  printf "%s [%s]: " "${prompt}" "${default_value}" >&2
  read -r response
  response="${response:l}"
  if [[ -z "${response}" ]]; then
    response="${default_value:l}"
  fi
  [[ "${response}" == "y" || "${response}" == "yes" ]]
}

if [[ -z "${repo_path}" ]]; then
  repo_path="$(prompt_with_default "Private router state repo path" "${default_repo_path}")"
fi

if [[ -z "${server_name}" ]]; then
  server_name="$(prompt_with_default "Codex MCP server name" "${default_server_name}")"
fi

repo_path="${repo_path:A}"

mkdir -p "${repo_path}/history" "${repo_path}/snapshots"

if [[ ! -d "${repo_path}/.git" ]]; then
  git -C "${repo_path}" init >/dev/null
fi

cat > "${repo_path}/.gitignore" <<'EOF'
.env.local
EOF

cat > "${repo_path}/README.md" <<EOF
# ${server_name}

Private local state repo for \`opnsense-mcp\`.

Expected writable paths:

- \`history/\`
- \`snapshots/current-config.xml\`

This repo is mounted into the Dockerized MCP server at \`/workspace\`.
EOF

cat > "${repo_path}/.env.local.example" <<'EOF'
OPNSENSE_BASE_URL=http://opnsense.internal
OPNSENSE_API_KEY=replace-me
OPNSENSE_API_SECRET=replace-me
OPNSENSE_VERIFY_TLS=false
EOF

if [[ ! -f "${repo_path}/.env.local" ]]; then
  cp "${repo_path}/.env.local.example" "${repo_path}/.env.local"
fi

cat > "${repo_path}/run-opnsense-mcp.sh" <<EOF
#!/bin/zsh
set -euo pipefail

SCRIPT_DIR="\${0:A:h}"
ENV_FILE="\${SCRIPT_DIR}/.env.local"

if [[ ! -f "\${ENV_FILE}" ]]; then
  echo "Missing \${ENV_FILE}. Copy .env.local.example to .env.local and fill in your OPNsense API values." >&2
  exit 1
fi

set -a
source "\${ENV_FILE}"
set +a

exec docker run --rm -i \\
  -e OPNSENSE_BASE_URL \\
  -e OPNSENSE_API_KEY \\
  -e OPNSENSE_API_SECRET \\
  -e OPNSENSE_VERIFY_TLS \\
  -e OPNSENSE_WORKSPACE_PATH=/workspace \\
  -v "\${SCRIPT_DIR}:/workspace" \\
  ${image_name}
EOF

chmod +x "${repo_path}/run-opnsense-mcp.sh"

if command -v codex >/dev/null 2>&1; then
  if yes_no_default "Register '${server_name}' in Codex MCP now?" "Y"; then
    codex mcp remove "${server_name}" >/dev/null 2>&1 || true
    codex mcp add "${server_name}" -- "${repo_path}/run-opnsense-mcp.sh"
  fi
fi

cat <<EOF

Local router-state repo ready:
  repo: ${repo_path}
  launcher: ${repo_path}/run-opnsense-mcp.sh
  env file: ${repo_path}/.env.local
  image: ${image_name}

Next steps:
  1. Fill in ${repo_path}/.env.local with your OPNsense API values.
  2. Build the image if needed:
       docker build --target runtime -t ${image_name} /Users/addom/dev/opnsense-mcp
  3. In Codex, start with:
       Use only the ${server_name} MCP server. First run inspect_runtime.
EOF
