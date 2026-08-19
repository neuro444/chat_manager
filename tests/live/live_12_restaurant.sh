#!/usr/bin/env bash
# LIVE — a realistic phone order, then a returning caller.
set -e
cd "$(dirname "$0")/../.."
export SQLITE_PATH=./restaurant_demo.db
rm -f "$SQLITE_PATH"
./.venv/bin/uvicorn api:app --host 127.0.0.1 --port 8112 --log-level warning &
PID=$!; trap "kill $PID 2>/dev/null" EXIT
for i in $(seq 1 40); do curl -sf localhost:8112/health >/dev/null && break; sleep 0.25; done

PHONE="+919876543210"
say() {
  BODY=$(python3 -c "import json,sys;print(json.dumps({'user_id':sys.argv[1],'session_id':sys.argv[2] or None,'message':sys.argv[3]}))" "$PHONE" "$SID" "$1")
  R=$(curl -s -X POST localhost:8112/chat -H 'Content-Type: application/json' -d "$BODY")
  SID=$(echo "$R" | python3 -c 'import sys,json;print(json.load(sys.stdin)["session_id"])')
  echo "caller> $1"
  echo "agent > $(echo "$R" | python3 -c 'import sys,json;print(json.load(sys.stdin)["answer"])')"
  echo
}

SID=""
echo "═══ CALL 1 ═══"
say "Hi, I'd like to order two chicken biryani and one garlic naan."
say "Make the biryani medium spicy please."
say "Pickup, in about thirty minutes. Can you read back my order?"

echo "═══ CALL 2 — same number, NEW session (tests cross-session memory) ═══"
SID=""
say "Hi, it's me again. What did I order last time?"

echo "═══ DASHBOARD ═══"
echo "--- /callers ---"
curl -s localhost:8112/callers | python3 -m json.tool
echo "--- /sessions ---"
curl -s "localhost:8112/sessions?user_id=$PHONE" | python3 -m json.tool
echo "--- / (dashboard page) ---"
curl -s -o /dev/null -w "HTTP %{http_code}, %{size_download} bytes\n" localhost:8112/
