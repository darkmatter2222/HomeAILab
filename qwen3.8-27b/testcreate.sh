#!/usr/bin/env bash
# PORTAINER_USERNAME / PORTAINER_PASSWORD come from the repo .env (gitignored).
TOK=$(curl -sk -X POST http://127.0.0.1:9000/api/auth -H "Content-Type: application/json" -d "{\"username\":\"$PORTAINER_USERNAME\",\"password\":\"$PORTAINER_PASSWORD\"}" | python3 -c "import json,sys;print(json.load(sys.stdin)[\"jwt\"])")
B=/home/darkmatter2222/qwen38-opt/body.json
echo "=== POST /stacks/create/standalone/string?endpointId=3 ==="
code=$(curl -sk -X POST -H "Authorization: Bearer $TOK" -H "Content-Type: application/json" -d @$B "http://127.0.0.1:9000/api/stacks/create/standalone/string?endpointId=3" -o /tmp/r.json -w "%{http_code}")
echo "[$code]"
cat /tmp/r.json; echo
echo "=== list stacks to confirm creation ==="
curl -sk -H "Authorization: Bearer $TOK" http://127.0.0.1:9000/api/stacks | python3 -c "import json,sys
for s in json.load(sys.stdin):
    print('#%s %s ep=%s status=%s' % (s['Id'],s['Name'],s['EndpointId'],s['Status']))"
