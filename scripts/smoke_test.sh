#!/usr/bin/env bash
# Post-deploy smoke test — fast assertions that a deployment is actually serving.
# Run after `up -d` (CI deploy step or manually):
#
#   BASE_URL=http://localhost:8001 scripts/smoke_test.sh
#
# Exits non-zero on the first failed check so a bad deploy is caught immediately.
set -euo pipefail

BASE_URL="${BASE_URL:-http://localhost:8001}"
fail=0

check() {  # check <name> <expected-code> <url>
  local name="$1" want="$2" url="$3"
  local code
  code="$(curl -s -o /dev/null -w '%{http_code}' -m 10 "$url" || echo 000)"
  if [ "$code" = "$want" ]; then
    echo "  ✓ ${name} (${code})"
  else
    echo "  ✗ ${name}: expected ${want}, got ${code}  [${url}]"; fail=1
  fi
}

echo "Smoke testing ${BASE_URL}"
check "liveness"          200 "${BASE_URL}/health"
check "readiness"         200 "${BASE_URL}/health/ready"
check "provider health"   200 "${BASE_URL}/health/providers"
check "metrics"           200 "${BASE_URL}/metrics"
check "admin redirect"    307 "${BASE_URL}/admin"
check "miniapp API auth"  401 "${BASE_URL}/api/profile"   # unauthenticated -> 401 (good)
check "admin API auth"    401 "${BASE_URL}/api/admin/dashboard"

if [ "$fail" -ne 0 ]; then
  echo "SMOKE TEST FAILED"; exit 1
fi
echo "SMOKE TEST PASSED"
