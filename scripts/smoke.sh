#!/usr/bin/env bash
set -euo pipefail

BASE_URL="${SEARCHARVESTER_URL:-http://localhost:8000}"
AUTH_HEADER=()
if [ -n "${RESEARCH_API_TOKEN:-}" ]; then
  AUTH_HEADER=(-H "Authorization: Bearer ${RESEARCH_API_TOKEN}")
fi

echo "[1/3] health"
curl -fsS "$BASE_URL/health" | python3 -m json.tool >/dev/null

echo "[2/3] search"
curl -fsS -X POST "$BASE_URL/search" \
  -H 'Content-Type: application/json' \
  -d '{"query":"trafilatura python", "max_results": 3}' \
  | python3 -c 'import json,sys; obj=json.load(sys.stdin); assert "results" in obj and isinstance(obj["results"], list), obj; print("search OK:", len(obj["results"]), "results")'

echo "[3/3] extract"
curl -fsS -X POST "$BASE_URL/extract" \
  -H 'Content-Type: application/json' \
  -d '{"url":"https://example.com", "size":"s"}' \
  | python3 -c 'import json,sys; obj=json.load(sys.stdin); assert "content" in obj and obj["content"].strip(), obj; print("extract OK:", len(obj["content"]), "chars")'

if [ "${RUN_RESEARCH_SMOKE:-0}" = "1" ]; then
  echo "[optional] research"
  job_id=$(curl -fsS -X POST "$BASE_URL/research" \
    "${AUTH_HEADER[@]}" \
    -H 'Content-Type: application/json' \
    -d '{"query":"What is example.com? Answer in one sentence with source."}' \
    | python3 -c 'import json,sys; print(json.load(sys.stdin)["job_id"])')
  echo "research queued: $job_id"
fi

echo "Smoke OK"
