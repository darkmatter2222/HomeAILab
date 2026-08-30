#!/usr/bin/env bash
# Deploy the router via the Portainer API (endpoint 3 = Databrick local Docker),
# so the stack is visible/manageable in the Portainer UI.
# Usage: ./scripts/portainer-deploy.sh
set -euo pipefail

# Real values live in the repo .env (gitignored). Source it or export them:
#   source .env   (sets PORTAINER_API, PORTAINER_USER, PORTAINER_PASS)
PORTAINER_API="${PORTAINER_API:?PORTAINER_API not set (see .env)}"
PORTAINER_USER="${PORTAINER_USER:?PORTAINER_USER not set (see .env)}"
PORTAINER_PASS="${PORTAINER_PASS:?PORTAINER_PASS not set (see .env)}"
ENDPOINT_ID="${ENDPOINT_ID:-3}"
STACK_NAME="${STACK_NAME:-llm-router}"
REPO_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
STACK_YAML="${REPO_DIR}/llm-router-stack.yaml"

echo ">> Logging in to Portainer"
LOGIN=$(curl -s -X POST "${PORTAINER_API}/auth/interactive/login" \
  -H 'Content-Type: application/json' \
  -d "{\"username\":\"${PORTAINER_USER}\",\"password\":\"${PORTAINER_PASS}\"}")
JWT=$(echo "$LOGIN" | sed -n 's/.*"jwt":"\([^"]*\)".*/\1/p')
if [ -z "$JWT" ]; then
  echo ">> login failed:"; echo "$LOGIN"; exit 1
fi

echo ">> Deploying stack '${STACK_NAME}' on endpoint ${ENDPOINT_ID}"
# jq to embed the YAML string as a JSON value.
PAYLOAD=$(jq -n --arg name "${STACK_NAME}" --arg y "$(cat "${STACK_YAML}")" \
  '{name: $name, stackFile: $y, prune: false}')
RESP=$(curl -s -X POST \
  "${PORTAINER_API}/endpoint/${ENDPOINT_ID}/stacks/create/standalone/string" \
  -H "Authorization: Bearer ${JWT}" \
  -H 'Content-Type: application/json' \
  -d "${PAYLOAD}")
echo ">> response: ${RESP}"
echo ">> stack deployed. Verify:  ssh databricks 'docker ps --filter name=llm-router'"
