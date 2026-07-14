#!/usr/bin/env bash
# Regression harness for scripts/smoke_test.sh + its production wiring in atomic_release.sh.
#
# Proves, without touching any network or server:
#   1. atomic_release.sh runs the smoke test against 127.0.0.1:8000 explicitly (not localhost, not
#      the local-dev :8001 default).
#   2. PUBLIC endpoints require 200; a non-200 fails.
#   3. PROTECTED endpoints pass on 401/403 and are NOT required to return 200.
#   4. A PROTECTED endpoint returning 200 anonymously is a LEAK and MUST fail (protection not weakened).
#
# Uses a fake CURL (injected via $CURL) that returns scripted status codes per URL path.
set -euo pipefail

HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
SMOKE="$HERE/smoke_test.sh"
RELEASE="$HERE/atomic_release.sh"
TMP="$(mktemp -d)"; trap 'rm -rf "$TMP"' EXIT
pass=0; failc=0
ok(){   echo "  PASS: $1"; pass=$((pass+1)); }
bad(){  echo "  FAIL: $1"; failc=$((failc+1)); }

# --- fake curl: prints the status mapped from the URL path via $SMOKE_MAP ("/p=code;/p2=code;...") ---
cat > "$TMP/fakecurl" <<'FAKE'
#!/usr/bin/env bash
url="${*: -1}"                 # smoke_test.sh puts the URL last
path="/${url#*://*/}"          # strip scheme://host -> "/path"
code=000
IFS=';' read -ra pairs <<< "${SMOKE_MAP:-}"
for p in "${pairs[@]}"; do
  [ "${p%%=*}" = "$path" ] && { code="${p##*=}"; break; }
done
printf '%s' "$code"
FAKE
chmod +x "$TMP/fakecurl"

run_smoke(){ # run_smoke <SMOKE_MAP> -> sets RC and OUT (explicit rc capture under set -e)
  set +e
  OUT="$(CURL="$TMP/fakecurl" SMOKE_MAP="$1" BASE_URL="http://smoke.test" bash "$SMOKE" 2>&1)"; RC=$?
  set -e
}

HEALTHY="/health=200;/health/ready=200;/admin=307;/health/providers=401;/metrics=403;/api/profile=401;/api/admin/dashboard=401"

echo "== Test 1: atomic_release.sh targets 127.0.0.1:8000 explicitly =="
if grep -Eq 'BASE_URL=http://127\.0\.0\.1:8000[[:space:]]+bash scripts/smoke_test\.sh' "$RELEASE"; then
  ok "atomic_release.sh runs smoke with BASE_URL=http://127.0.0.1:8000"
else
  bad "atomic_release.sh does NOT run smoke with BASE_URL=http://127.0.0.1:8000"
fi
if grep -n 'smoke_test.sh' "$RELEASE" | grep -q 'localhost'; then
  bad "atomic_release.sh smoke call uses 'localhost' (must be 127.0.0.1 to avoid IPv6)"
else
  ok "atomic_release.sh smoke call does not use 'localhost'"
fi

echo "== Test 2: healthy prod-like responses -> PASS (exit 0) =="
run_smoke "$HEALTHY"
if [ "$RC" -eq 0 ] && printf '%s' "$OUT" | grep -q 'SMOKE TEST PASSED'; then
  ok "healthy prod-like matrix passes"
else
  bad "healthy matrix did not pass (rc=$RC)"; printf '%s\n' "$OUT"
fi

echo "== Test 3: protected endpoint 403/401 must NOT be an error =="
if printf '%s' "$OUT" | grep -q 'metrics protected (403)' && printf '%s' "$OUT" | grep -q 'provider health protected (401)'; then
  ok "protected endpoints accepted at 401/403"
else
  bad "protected endpoints not accepted at 401/403"
fi

echo "== Test 4: protection LEAK (metrics=200 anonymously) -> FAIL =="
run_smoke "${HEALTHY/\/metrics=403/\/metrics=200}"
if [ "$RC" -ne 0 ] && printf '%s' "$OUT" | grep -q 'PROTECTION LEAK'; then
  ok "metrics=200 anonymous is caught as a leak (non-zero)"
else
  bad "leak not caught (rc=$RC)"; printf '%s\n' "$OUT"
fi

echo "== Test 5: readiness down (503) -> FAIL =="
run_smoke "${HEALTHY/\/health\/ready=200/\/health\/ready=503}"
if [ "$RC" -ne 0 ] && printf '%s' "$OUT" | grep -q 'readiness: expected 200'; then
  ok "readiness 503 fails the smoke"
else
  bad "readiness 503 not caught (rc=$RC)"; printf '%s\n' "$OUT"
fi

echo "== Test 6: liveness unreachable (000) -> FAIL =="
run_smoke "${HEALTHY/\/health=200/\/health=000}"
if [ "$RC" -ne 0 ] && printf '%s' "$OUT" | grep -q 'liveness: expected 200'; then
  ok "liveness 000 fails the smoke"
else
  bad "liveness 000 not caught (rc=$RC)"; printf '%s\n' "$OUT"
fi

echo
echo "SUMMARY: pass=$pass fail=$failc"
if [ "$failc" -eq 0 ]; then echo "SMOKE CONTRACT TEST: PASS"; exit 0; else echo "SMOKE CONTRACT TEST: FAIL"; exit 1; fi
