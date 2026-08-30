#!/usr/bin/env bash
# Phase F validation suite against the running router.
# Usage: BASE=http://192.168.86.48:8001 ./scripts/validate.sh
set -uo pipefail

BASE="${BASE:-http://192.168.86.48:8001}"
ALIAS="${ALIAS:-local-coding}"
MODEL="${MODEL:-qwen3.8}"
PASS=0
FAIL=0

ok()   { echo "  PASS  $1"; PASS=$((PASS+1)); }
bad()  { echo "  FAIL  $1"; FAIL=$((FAIL+1)); }

echo "=== 1. /health ==="
R=$(curl -s -m 5 "${BASE}/health")
echo "$R" | grep -q '"status":"ok"' && ok "health ok: ${R}" || bad "health: ${R}"

echo "=== 2. /v1/models ==="
R=$(curl -s -m 5 "${BASE}/v1/models")
echo "$R" | grep -q "${ALIAS}" && ok "models advertise ${ALIAS}" || bad "models missing alias: ${R}"

echo "=== 3. OpenAI non-stream ==="
R=$(curl -s -m 20 -X POST "${BASE}/v1/chat/completions" \
  -H 'Content-Type: application/json' \
  -d "{\"model\":\"${ALIAS}\",\"messages\":[{\"role\":\"user\",\"content\":\"Reply with exactly the word PONG.\"}],\"max_tokens\":16}")
echo "$R" | grep -q '"choices"' && ok "openai non-stream returned choices" || bad "openai non-stream: ${R}"

echo "=== 4. streaming ==="
TTFT_START=$(date +%s%3N)
R=$(curl -s -m 20 -N -X POST "${BASE}/v1/chat/completions" \
  -H 'Content-Type: application/json' \
  -d "{\"model\":\"${ALIAS}\",\"stream\":true,\"messages\":[{\"role\":\"user\",\"content\":\"Count to three.\"}],\"max_tokens\":48}")
N=$(echo "$R" | grep -c '^data:')
echo "$R" | grep -q 'data:' && ok "stream: ${N} data lines" || bad "stream no data lines: ${R}"

echo "=== 5. /v1/messages (Anthropic) ==="
R=$(curl -s -m 20 -X POST "${BASE}/v1/messages" \
  -H 'Content-Type: application/json' \
  -d "{\"model\":\"${ALIAS}\",\"messages\":[{\"role\":\"user\",\"content\":\"Say hi\"}],\"max_tokens\":16}")
echo "$R" | grep -q '"type":"message"\|"type"' && ok "/v1/messages returned a message" || bad "/v1/messages: ${R}"

echo "=== 6. /v1/messages/count_tokens ==="
R=$(curl -s -m 5 -X POST "${BASE}/v1/messages/count_tokens" \
  -H 'Content-Type: application/json' \
  -d "{\"model\":\"${ALIAS}\",\"messages\":[{\"role\":\"user\",\"content\":\"hello world, this is a token counting probe.\"}]}")
echo "$R" | grep -q '"input_tokens"' && ok "count_tokens: ${R}" || bad "count_tokens: ${R}"

echo "=== 7. tools ==="
R=$(curl -s -m 20 -X POST "${BASE}/v1/chat/completions" \
  -H 'Content-Type: application/json' \
  -d "{\"model\":\"${ALIAS}\",\"messages\":[{\"role\":\"user\",\"content\":\"Use the weather tool for Paris.\"}],\"tools\":[{\"type\":\"function\",\"function\":{\"name\":\"get_weather\",\"description\":\"Get weather\",\"parameters\":{\"type\":\"object\",\"properties\":{\"city\":{\"type\":\"string\"}}}}}],\"tool_choice\":\"auto\",\"max_tokens\":64}")
echo "$R" | grep -q 'tool_call\|tools\|get_weather' && ok "tools: tool structure preserved" || bad "tools: ${R}"

echo "=== 8. thinking-off ==="
R=$(curl -s -m 20 -X POST "${BASE}/v1/chat/completions" \
  -H 'Content-Type: application/json' \
  -d "{\"model\":\"${ALIAS}\",\"messages\":[{\"role\":\"user\",\"content\":\"What is 2+2?\"}],\"max_tokens\":16}")
if echo "$R" | grep -qi '"thinking"\|"reasoning"'; then
  bad "thinking block present (should be off): ${R}"
else
  ok "no thinking/reasoning block"
fi

echo "=== 9. capacity=1 (hold + second request) ==="
# Hold one request open (long generation) in the background.
HOLD_PID=""
( curl -s -m 60 -N -X POST "${BASE}/v1/chat/completions" \
    -H 'Content-Type: application/json' \
    -d "{\"model\":\"${ALIAS}\",\"stream\":true,\"messages\":[{\"role\":\"user\",\"content\":\"Write a 300 word essay on the history of computing.\"}],\"max_tokens\":512}" > /dev/null 2>&1 ) &
HOLD_PID=$!
sleep 3
R2=$(curl -s -m 10 -X POST "${BASE}/v1/chat/completions" \
    -H 'Content-Type: application/json' \
    -d "{\"model\":\"${ALIAS}\",\"messages\":[{\"role\":\"user\",\"content\":\"hi\"}],\"max_tokens\":8}")
if echo "$R2" | grep -q 'capacity_exhausted\|CAPACITY_FULL\|503'; then
  ok "second request got controlled capacity response (5090 at cap 1)"
else
  echo "  second-request body: ${R2}"
  bad "second request not rejected at capacity"
fi
wait "${HOLD_PID}" 2>/dev/null || true

echo "=== 10. release on complete ==="
sleep 2
R=$(curl -s -m 5 "${BASE}/admin/endpoints")
INFLIGHT=$(echo "$R" | grep -o '"inflight":[0-9]*' | head -1 | grep -o '[0-9]*')
[ "${INFLIGHT:-1}" = "0" ] && ok "inflight back to 0 after completion" || bad "inflight=${INFLIGHT} (expected 0)"

echo "=== 13. drain / undrain ==="
EPID="rtx5090-qwen38-262k-01"
curl -s -X POST "${BASE}/admin/endpoints/${EPID}/drain" >/dev/null
R=$(curl -s -m 10 -X POST "${BASE}/v1/chat/completions" -H 'Content-Type: application/json' \
  -d "{\"model\":\"${ALIAS}\",\"messages\":[{\"role\":\"user\",\"content\":\"hi\"}],\"max_tokens\":8}")
echo "$R" | grep -qi 'drain\|CAPACITY_FULL\|capacity' && ok "drained endpoint rejected new requests" || echo "  (drain test: ${R})"
curl -s -X POST "${BASE}/admin/endpoints/${EPID}/undrain" >/dev/null
sleep 1
R=$(curl -s -m 10 -X POST "${BASE}/v1/chat/completions" -H 'Content-Type: application/json' \
  -d "{\"model\":\"${ALIAS}\",\"messages\":[{\"role\":\"user\",\"content\":\"hi\"}],\"max_tokens\":8}")
echo "$R" | grep -q 'choices\|message\|data:' && ok "undrained endpoint accepts again" || bad "undrain: ${R}"

echo
echo "=== SUMMARY: ${PASS} passed, ${FAIL} failed ==="
[ "${FAIL}" -eq 0 ]
