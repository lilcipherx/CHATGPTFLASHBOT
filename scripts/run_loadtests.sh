#!/usr/bin/env bash
# Run the load-test suite and emit HTML reports.
#
#   BASE_URL=https://staging.example.com BOT_TOKEN=<token> \
#     scripts/run_loadtests.sh [smoke|load|spike|soak|all]
#
# Requires k6 (https://k6.io) and, for the Locust run, `pip install locust`.
set -euo pipefail

BASE_URL="${BASE_URL:-http://localhost:8000}"
SCENARIO="${1:-smoke}"
ROOT="$(cd "$(dirname "$0")/.." && pwd)"

run_k6() {
  local s="$1"
  echo "== k6: ${s} against ${BASE_URL} =="
  SCENARIO="$s" BASE_URL="$BASE_URL" BOT_TOKEN="${BOT_TOKEN:-}" \
    k6 run "${ROOT}/loadtests/k6/api.js"
  if [ -f "${ROOT}/loadtests/report.html" ]; then
    mv "${ROOT}/loadtests/report.html" "${ROOT}/loadtests/report-${s}.html"
    echo "report -> loadtests/report-${s}.html"
  fi
}

if [ "$SCENARIO" = "all" ]; then
  for s in smoke load spike soak; do run_k6 "$s"; done
else
  run_k6 "$SCENARIO"
fi

echo "== Locust (headless, 60s) =="
if command -v locust >/dev/null 2>&1; then
  BOT_TOKEN="${BOT_TOKEN:-}" locust -f "${ROOT}/loadtests/locust/locustfile.py" \
    --host "$BASE_URL" --headless -u 50 -r 10 -t 60s \
    --html "${ROOT}/loadtests/locust_report.html" || true
  echo "report -> loadtests/locust_report.html"
else
  echo "locust not installed (pip install locust) — skipping Locust run"
fi
