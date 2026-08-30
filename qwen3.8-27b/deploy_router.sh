#!/usr/bin/env bash
# Re-deploy the GPU router stack (qwen38-gpu-router, endpoint 3 / Databricks).
#
#   bash deploy_router.sh
#
# Re-creates stack "qwen38-gpu-router" (endpoint 3) from qwen38-router-v1.yaml.
# The router source is bind-mounted from /home/darkmatter2222/qwen38-router/router.py
# (the live copy is what the container runs). This script re-syncs the local
# qwen3.8-27b/router/router.py -> that live path, then re-creates the stack.
#
# Caps/priorities match the live deployment: 5090 prio1 cap1 (vllm), 3090 prio2
# cap1 (llama), DGX Spark prio3 cap3 (llama, the ds4 /slots shim). Vision image
# requests are pinned to the Spark (VISION_BACKEND=dgxsparx).
set -Eeuo pipefail
cd "$(dirname "$0")/.."

STACK_NAME="qwen38-gpu-router"
EP=3
YAML="qwen38-router-v1.yaml"
ROUTER_SRC_LOCAL="qwen3.8-27b/router/router.py"
ROUTER_SRC_LIVE="/home/darkmatter2222/qwen38-router/router.py"

# 1) sync the router source to the live bind-mount path (backup first)
ssh databricks "cp $ROUTER_SRC_LIVE ${ROUTER_SRC_LIVE}.bak-\$(date +%s)"
scp -q "$ROUTER_SRC_LOCAL" databricks:"$ROUTER_SRC_LIVE"
echo "synced router.py -> $ROUTER_SRC_LIVE"

# 2) stage the YAML + body on databricks
scp -q "$YAML" databricks:/tmp/router_stack.yaml
ssh databricks '
  python3 -c "import json;json.dump({\"Name\":\"'"$STACK_NAME"'\",\"EntryPoint\":\"docker-compose.yml\",\"Prune\":True,\"StackFileContent\":open(\"/tmp/router_stack.yaml\").read()},open(\"/tmp/router_body.json\",\"w\"))"
'

# 3) login, delete existing, create
# PORTAINER_USERNAME / PORTAINER_PASSWORD come from the repo .env (gitignored).
ssh databricks "
set -e
PORTAINER_USERNAME='"$PORTAINER_USERNAME"':PORTAINER_PASSWORD='"$PORTAINER_PASSWORD"'
TOK=\$(curl -sk -X POST http://127.0.0.1:9000/api/auth -H 'Content-Type: application/json' -d '{\"username\":\"\${PORTAINER_USERNAME}\",\"password\":\"\${PORTAINER_PASSWORD}\"}' | python3 -c 'import json,sys;print(json.load(sys.stdin)[\"jwt\"])')
echo '=== delete existing '"$STACK_NAME"' if present ==='
for id in \$(curl -sk -H \"Authorization: Bearer \$TOK\" http://127.0.0.1:9000/api/stacks | python3 -c 'import json,sys
[print(s[\"Id\"]) for s in json.load(sys.stdin) if s[\"Name\"]==\"'"$STACK_NAME"'\"']
  ); do
  echo \"removing stack \$id\"
  curl -sk -X DELETE -H \"Authorization: Bearer \$TOK\" \"http://127.0.0.1:9000/api/stacks/\$id?endpointId=$EP\" -o /tmp/d.json -w 'delete: %{http_code}\n'
done
echo '=== create stack ==='
code=\$(curl -sk -X POST -H \"Authorization: Bearer \$TOK\" -H 'Content-Type: application/json' -d @/tmp/router_body.json \"http://127.0.0.1:9000/api/stacks/create/standalone/string?endpointId=$EP\" -o /tmp/r.json -w '%{http_code}')
echo \"create: [\$code]\"
cat /tmp/r.json; echo
"
echo
echo "Re-deployed $STACK_NAME (ep $EP). Check it is up:"
echo "  curl -s http://192.168.86.48:8010/health"
