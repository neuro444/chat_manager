#!/usr/bin/env bash
# LIVE — start the API, drive it with curl, prove sessions persist over HTTP.
set -e
cd "$(dirname "$0")/../.."
export SQLITE_PATH=./curl_test.db
rm -f "$SQLITE_PATH"

./.venv/bin/uvicorn api:app --host 127.0.0.1 --port 8111 --log-level warning &
PID=$!
trap "kill $PID 2>/dev/null" EXIT
for i in $(seq 1 40); do curl -sf localhost:8111/health >/dev/null && break; sleep 0.25; done

echo "=== 1. GET /health ==="
curl -s localhost:8111/health | python3 -m json.tool

echo -e "\n=== 2. POST /chat  (turn 1, states a fact) ==="
R1=$(curl -s -X POST localhost:8111/chat -H 'Content-Type: application/json' \
  -d '{"user_id":"sree","message":"My name is Sree and my favourite database is MongoDB."}')
echo "$R1" | python3 -m json.tool
SID=$(echo "$R1" | python3 -c 'import sys,json;print(json.load(sys.stdin)["session_id"])')

echo -e "\n=== 3. POST /chat  (turn 2, same session, tests memory) ==="
curl -s -X POST localhost:8111/chat -H 'Content-Type: application/json' \
  -d "{\"user_id\":\"sree\",\"session_id\":\"$SID\",\"message\":\"What is my favourite database?\"}" \
  | python3 -m json.tool

echo -e "\n=== 4. GET /sessions ==="
curl -s "localhost:8111/sessions?user_id=sree" | python3 -m json.tool

echo -e "\n=== 5. GET /sessions/{id}/messages ==="
curl -s "localhost:8111/sessions/$SID/messages" | python3 -m json.tool

echo -e "\n=== 6. Scoping: bob must NOT see sree's sessions ==="
curl -s "localhost:8111/sessions?user_id=bob" | python3 -m json.tool

echo -e "\n=== 7. DELETE /sessions/{id} ==="
curl -s -X DELETE "localhost:8111/sessions/$SID" | python3 -m json.tool
echo "messages after delete:"
curl -s "localhost:8111/sessions/$SID/messages" | python3 -m json.tool
