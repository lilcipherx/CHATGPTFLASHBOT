#!/usr/bin/env bash
# Post-deploy smoke test — fast assertions that a deployment is actually serving.
#
# Contracts (do NOT weaken app protection to make a check pass):
#   * PUBLIC endpoints  (liveness/readiness) MUST return 200.
#   * A specific REDIRECT (/admin) MUST return 307.
#   * PROTECTED endpoints (metrics, provider health, authed APIs) MUST be auth-gated:
#       401/403 = PASS; 200 = FAIL (a 200 anonymously is a protection LEAK, caught here);
#     anything else (000/5xx) = FAIL. Protected endpoints are NOT expected to be public.
#
# Local dev default targets :8001. PRODUCTION callers MUST pass the real port explicitly, e.g.
# atomic_release.sh runs:  BASE_URL=http://127.0.0.1:8000 scripts/smoke_test.sh
# (127.0.0.1, not localhost, to avoid depending on IPv6 resolution of ::1).
#
# Exits non-zero if any check fails, so a bad deploy is caught immediately.
set -euo pipefail

BASE_URL="${BASE_URL:-http://localhost:8001}"   # local-dev default; prod overrides via env
CURL="${CURL:-curl}"                            # overridable for the contract test harness
fail=0

_code() {  # _code <url> -> prints the HTTP status (000 on connect failure)
  "$CURL" -s -o /dev/null -w '%{http_code}' -m 10 "$1" || echo 000
}

check() {  # check <name> <expected-code> <url>   exact-match a PUBLIC/redirect endpoint
  local name="$1" want="$2" url="$3" code
  code="$(_code "$url")"
  if [ "$code" = "$want" ]; then
    echo "  ✓ ${name} (${code})"
  else
    echo "  ✗ ${name}: expected ${want}, got ${code}  [${url}]"; fail=1
  fi
}

check_protected() {  # check_protected <name> <url>   PASS iff 401/403; 200 = LEAK = FAIL
  local name="$1" url="$2" code
  code="$(_code "$url")"
  case "$code" in
    401|403) echo "  ✓ ${name} protected (${code})" ;;
    200)     echo "  ✗ ${name}: PROTECTION LEAK — 200 returned anonymously  [${url}]"; fail=1 ;;
    *)       echo "  ✗ ${name}: expected 401/403 (auth-gated), got ${code}  [${url}]"; fail=1 ;;
  esac
}

echo "Smoke testing ${BASE_URL}"
# --- public: must be open + 200 ---
check           "liveness"          200 "${BASE_URL}/health"
check           "readiness"         200 "${BASE_URL}/health/ready"
# --- specific redirect ---
check           "admin redirect"    307 "${BASE_URL}/admin"
# --- protected: must be auth-gated (401/403), never 200 anonymously ---
check_protected "provider health"       "${BASE_URL}/health/providers"
check_protected "metrics"                "${BASE_URL}/metrics"
check_protected "miniapp API auth"       "${BASE_URL}/api/profile"
check_protected "admin API auth"         "${BASE_URL}/api/admin/dashboard"

if [ "$fail" -ne 0 ]; then
  echo "SMOKE TEST FAILED"; exit 1
fi
echo "SMOKE TEST PASSED"
