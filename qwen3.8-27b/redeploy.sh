#!/usr/bin/env bash
# Create (or re-create) the qwen38-27b-3090 stack on endpoint 3 via Portainer API.
# PORTAINER_USERNAME / PORTAINER_PASSWORD come from the repo .env (gitignored).
TOK=$(curl -sk -X POST http://127.0.0.1:9000/api/auth -H "Content-Type: application/json" -d "{\"username\":\"$PORTAINER_USERNAME\",\"password\":\"$PORTAINER_PASSWORD\"}" | python3 -c "import json,sys;print(json.load(sys.stdin)[\"jwt\"])")
B=/home/darkmatter2222/qwen38-opt/body.json
python3 -c "import json;open('$B','w').write(json.dumps({'Name':'qwen38-27b-3090','EntryPoint':'docker-compose.yml','Prune':True,'StackFileContent':open('/home/darkmatter2222/qwen38-opt/stack.yaml').read()}))"
# remove any existing stack with this name (by id)
EXIST=$(curl -sk -H "Authorization: Bearer $TOK" http://127.0.0.1:9000/api/stacks | python3 -c "import json,sys
for s in json.load(sys.stdin):
    if s['Name']=='qwen38-27b-3090': print(s['Id'])")
for id in $EXIST; do
  echo "removing existing stack id $id"
  curl -sk -X DELETE -H "Authorization: Bearer $TOK" "http://127.0.0.1:9000/api/stacks/$id?endpointId=3" -o /tmp/d.json -w "delete: %{http_code}\n"
  cat /tmp/d.json; echo
done
echo "=== creating stack ==="
code=$(curl -sk -X POST -H "Authorization: Bearer $TOK" -H "Content-Type: application/json" -d @$B "http://127.0.0.1:9000/api/stacks/create/standalone/string?endpointId=3" -o /tmp/r.json -w "%{http_code}")
echo "create: [$code]"
cat /tmp/r.json; echo
echo "=== stacks now ==="
curl -sk -H "Authorization: Bearer $TOK" http://127.0.0.1:9000/api/stacks | python3 -c "import json,sys
for s in json.load(sys.stdin):
    if s['EndpointId']==3: print('#%s %s status=%s' % (s['Id'],s['Name'],s['Status']))"
