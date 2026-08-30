#!/usr/bin/env bash
# Re-deploy the DGX Spark Flash-Next (ds4 SSD-PLE) stack via the Portainer API.
#
#   bash deploy_spark.sh
#
# Re-creates stack "qwen38-flashnext-dgxsparx" (endpoint 4 / DGX-Spark) from
# qwen38-flashnext-dgxsparx-v3-ds4ssdple.yaml (the source of truth: the ds4:spark
# image, bind-mounted models, the /slots shim). Keeps the name so the router +
# Grafana keep working. Safe to re-run: deletes any existing stack of that name
# first, then creates. After a ds4:spark image rebuild, just re-run this.
set -Eeuo pipefail
cd "$(dirname "$0")/.."

STACK_NAME="qwen38-flashnext-dgxsparx"
EP=4
YAML="qwen38-flashnext-dgxsparx-v3-ds4ssdple.yaml"

# 1) stage the YAML + request body on the databricks box (where Portainer's API runs)
scp -q "$YAML" databricks:/tmp/spark_stack.yaml
ssh databricks '
  python3 -c "import json;json.dump({\"Name\":\"'"$STACK_NAME"'\",\"EntryPoint\":\"docker-compose.yml\",\"Prune\":True,\"StackFileContent\":open(\"/tmp/spark_stack.yaml\").read()},open(\"/tmp/spark_body.json\",\"w\"))"
'

# 2) login, delete existing, create
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
code=\$(curl -sk -X POST -H \"Authorization: Bearer \$TOK\" -H 'Content-Type: application/json' -d @/tmp/spark_body.json \"http://127.0.0.1:9000/api/stacks/create/standalone/string?endpointId=$EP\" -o /tmp/r.json -w '%{http_code}')
echo \"create: [\$code]\"
cat /tmp/r.json; echo
"
echo
echo "Re-deployed $STACK_NAME (ep $EP). Track the engine on the Spark:"
echo "  ssh dgxspark 'docker logs -f qwen3.8-flashnext-dgxsparx'"
