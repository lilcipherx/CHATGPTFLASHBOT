#!/usr/bin/env bash
# Atomic release to the flashbot production host — immutable bundle + blue/green dir swap.
#
# Runs from the LOCAL machine (git-bash) and orchestrates the server over `ssh flashbot`.
# It NEVER prints the server .env or any secret. It hard-ABORTs on config drift, low disk,
# or any failed verification, preserves the previous release, and prints exact rollback.
#
#   Usage:  bash scripts/atomic_release.sh [REF] [--dry-run]
#   REF defaults to fa654ba. --dry-run prints every remote command and changes NOTHING.
#
# Hard gates (each exits non-zero, no masking):
#   * config drift  — live Dockerfile/compose/Caddyfile must match the bundle (else ABORT + diff)
#   * disk >= 7 GB   — checked before the frontend build AND again right before the docker build
#   * alembic == 0042 before swap; == 0044 after; 4 new indexes VALID; all app containers healthy;
#     smoke test passes — any failure exits non-zero.
# No prune / cleanup is ever run on production.
set -euo pipefail

# ---- args -------------------------------------------------------------------------------
REF="fa654ba"; DRY=0
for a in "$@"; do
  case "$a" in
    --dry-run) DRY=1 ;;
    -*) echo "unknown flag: $a" >&2; exit 64 ;;
    *) REF="$a" ;;
  esac
done

SSH_HOST="flashbot"
APP_DIR="/home/ubuntu/CHATGPTFLASHBOT"
REL_ROOT="/home/ubuntu/releases"
COMPOSE="docker compose -f docker-compose.yml -f docker-compose.prod.yml"
APP_SERVICES="migrate api bot worker beat"   # ONLY these are (re)built/recreated; caddy separate
DRIFT_FILES="Dockerfile docker-compose.yml docker-compose.prod.yml Caddyfile"
MIN_FREE_GB=7
EXPECT_CUR="0042_search_model"
EXPECT_HEAD="0044_missing_model_indexes"

TS="$(date +%Y%m%d-%H%M%S)"
SHORT="$(git rev-parse --short "$REF")"
FULL="$(git rev-parse "$REF")"
BUNDLE="release-${SHORT}.tar.gz"
STAGE="${REL_ROOT}/${SHORT}-${TS}"

say(){ printf '\n=== %s ===\n' "$*"; }

# ssh_do <description> <remote-command>: returns the remote exit code (0 in dry-run).
ssh_do(){
  echo "  [remote] $1"
  if [[ "$DRY" -eq 1 ]]; then
    printf '    DRY: ssh %s <<CMD\n%s\nCMD\n' "$SSH_HOST" "$2"
    return 0
  fi
  ssh -o ConnectTimeout=30 "$SSH_HOST" "$2"
}

# --- these SQL/psql snippets run on the server; server-side $VARs are escaped as \$ ---
# SELECT1_Q / ALEMBIC_Q share the EXACT same shell+psql quoting path, so the read-only
# SELECT-1 preflight actually exercises the quoting the later gates depend on.
PSQL='docker exec chatgptflashbot-postgres-1 sh -lc'
ALEMBIC_Q="\"psql -U \\\$POSTGRES_USER -d \\\$POSTGRES_DB -tAc \\\"select version_num from alembic_version\\\"\""
SELECT1_Q="\"psql -U \\\$POSTGRES_USER -d \\\$POSTGRES_DB -tAc \\\"select 1\\\"\""

say "0. Preflight (local)"
git rev-parse --verify "${REF}^{commit}" >/dev/null
echo "  REF=$REF short=$SHORT full=$FULL ts=$TS dry_run=$DRY min_free=${MIN_FREE_GB}GB"

say "0.5 Read-only quoting preflight — SELECT 1 via the EXACT PSQL/quoting path (no writes)"
if ! ssh_do "psql shell-quoting check (SELECT 1)" "
  out=\$($PSQL $SELECT1_Q | tr -d '[:space:]')
  echo \"select1=\$out\"; [ \"\$out\" = '1' ]
"; then
  echo '>>> ABORT: psql/shell quoting preflight failed (SELECT 1 did not return 1).'
  echo '>>> Later alembic/index gates use the same quoting — fix quoting before any deploy.'
  exit 12
fi

say "1. Build immutable bundle (local git archive — no .git/.env/untracked)"
if [[ "$DRY" -eq 1 ]]; then
  echo "  DRY: git archive --format=tar.gz -o $BUNDLE $REF && sha256sum $BUNDLE"
else
  git archive --format=tar.gz -o "$BUNDLE" "$REF"
  sha256sum "$BUNDLE" | tee "${BUNDLE}.sha256"
fi

say "2. Deliver bundle to server staging area"
ssh_do "ensure releases dir" "mkdir -p '$REL_ROOT/incoming'"
if [[ "$DRY" -eq 1 ]]; then
  echo "  DRY: scp $BUNDLE ${BUNDLE}.sha256 $SSH_HOST:$REL_ROOT/incoming/"
else
  scp "$BUNDLE" "${BUNDLE}.sha256" "$SSH_HOST:$REL_ROOT/incoming/"
fi

say "3. Stage: verify checksum + extract into SAME-filesystem dir"
ssh_do "checksum + extract" "
  set -e
  ( cd '$REL_ROOT/incoming' && sha256sum -c '${BUNDLE}.sha256' )
  mkdir -p '$STAGE'
  tar xzf '$REL_ROOT/incoming/$BUNDLE' -C '$STAGE'
  test -f '$STAGE/Dockerfile' && test -f '$STAGE/docker-compose.prod.yml' && echo 'staging tree OK'
"

say "3.5 CONFIG DRIFT HARD-GATE (live vs bundle by sha256; file CONTENTS never printed — may hold secrets)"
if ! ssh_do "fingerprint prod deploy config vs bundle" "
  drift=0
  for f in $DRIFT_FILES; do
    if [ ! -f '$APP_DIR'/\"\$f\" ]; then echo \"### MISSING on server: \$f\"; drift=1; continue; fi
    if ! cmp -s '$APP_DIR'/\"\$f\" '$STAGE'/\"\$f\"; then
      live=\$(sha256sum < '$APP_DIR'/\"\$f\" | cut -c1-16)
      bund=\$(sha256sum < '$STAGE'/\"\$f\" | cut -c1-16)
      echo \"### DRIFT: \$f (live sha=\$live bundle sha=\$bund) ###\"; drift=1
    fi
  done
  [ \"\$drift\" -eq 0 ] && echo 'no drift — deploy config matches Git' || exit 20
"; then
  echo ">>> ABORT: production Dockerfile/compose/Caddyfile drift from Git (differing files listed above)."
  echo ">>> Contents are NOT shown (possible secrets). Migrate manual server changes into Git first, then re-run."
  exit 20
fi

say "4. Carry over existing .env (copy only — contents NEVER printed)"
ssh_do "copy .env, verify by SIZE only" "
  set -e
  test -s '$APP_DIR/.env'
  cp -p '$APP_DIR/.env' '$STAGE/.env'
  test -s '$STAGE/.env' && echo \".env carried (size=\$(stat -c%s '$STAGE/.env') bytes; contents not shown)\"
"

say "5. DISK HARD-STOP #1 (>= ${MIN_FREE_GB} GB) — before frontend build"
if ! ssh_do "disk check #1" "
  avail=\$(df -BG --output=avail / | tail -1 | tr -dc 0-9)
  echo \"free_GB=\$avail (min=${MIN_FREE_GB})\"
  [ \"\$avail\" -ge ${MIN_FREE_GB} ]
"; then
  echo ">>> ABORT: < ${MIN_FREE_GB} GB free before build. No prune performed. Nothing swapped."
  exit 21
fi

say "6. Build SPAs in staging (Caddy serves miniapp/dist + admin/dist)"
ssh_do "npm ci + build (miniapp, admin)" "
  set -e
  ( cd '$STAGE/miniapp' && npm ci && npm run build )
  ( cd '$STAGE/admin'   && npm ci && npm run build )
  test -d '$STAGE/miniapp/dist' && test -d '$STAGE/admin/dist' && echo 'SPA dist built'
"

say "7. Validate merged compose in staging (config -q — no secret output)"
ssh_do "compose config -q" "cd '$STAGE' && $COMPOSE config -q && echo 'compose config valid'"

say "8. Pre-swap safety: prod alembic MUST be $EXPECT_CUR"
if ! ssh_do "assert alembic == $EXPECT_CUR" "
  cur=\$($PSQL $ALEMBIC_Q | tr -d '[:space:]')
  echo \"alembic_current=\$cur\"
  [ \"\$cur\" = '$EXPECT_CUR' ]
"; then
  echo ">>> ABORT: prod alembic is not $EXPECT_CUR. Nothing swapped."
  exit 22
fi

say "9. DISK HARD-STOP #2 (>= ${MIN_FREE_GB} GB) — right before swap + docker build"
if ! ssh_do "disk check #2" "
  avail=\$(df -BG --output=avail / | tail -1 | tr -dc 0-9)
  echo \"free_GB=\$avail (min=${MIN_FREE_GB})\"
  [ \"\$avail\" -ge ${MIN_FREE_GB} ]
"; then
  echo ">>> ABORT: < ${MIN_FREE_GB} GB free before docker build. No prune. Nothing swapped."
  exit 23
fi

say "10. ATOMIC SWAP (preserve previous) + provenance marker + auto-recovery"
if ! ssh_do "swap current<->staging (recover on failure)" "
  set -e
  mv '$APP_DIR' '${APP_DIR}.prev.${TS}'
  if ! mv '$STAGE' '$APP_DIR'; then
    echo '### SWAP FAILED: second mv failed — restoring previous current dir ###'
    if mv '${APP_DIR}.prev.${TS}' '$APP_DIR'; then
      echo '### RECOVERED: original current dir restored; nothing rebuilt ###'
    else
      echo '### CRITICAL: restore ALSO failed — current is at ${APP_DIR}.prev.${TS}; manual fix required ###'
    fi
    exit 40
  fi
  printf '%s\n' '$FULL' > '$APP_DIR/.DEPLOYED_SHA'
  echo \"swapped: prev=${APP_DIR}.prev.${TS} active=$APP_DIR sha=$FULL\"
"; then
  echo '>>> ABORT: atomic swap failed. Previous release auto-restored (see remote output). Nothing rebuilt.'
  exit 40
fi

say "11. Rebuild + recreate ONLY app services ($APP_SERVICES); caddy separate; DB/cache/minio untouched"
ssh_do "build app images" "cd '$APP_DIR' && $COMPOSE build $APP_SERVICES"
ssh_do "up -d app services (migrate applies 0043/0044 first, fail-closed)" "cd '$APP_DIR' && $COMPOSE up -d $APP_SERVICES"
ssh_do "force-recreate caddy for new dist/Caddyfile" "cd '$APP_DIR' && $COMPOSE up -d --force-recreate caddy"

say "12. VERIFY — any failure exits non-zero (no masking)"
if ! ssh_do "alembic head == $EXPECT_HEAD" "
  cur=\$($PSQL $ALEMBIC_Q | tr -d '[:space:]')
  echo \"alembic_current=\$cur\"; [ \"\$cur\" = '$EXPECT_HEAD' ]
"; then echo ">>> FAIL: migrations not at $EXPECT_HEAD"; exit 30; fi

if ! ssh_do "4 new indexes present + VALID" "
  n=\$($PSQL \"psql -U \\\$POSTGRES_USER -d \\\$POSTGRES_DB -tAc \\\"select count(*) from pg_class c join pg_index i on i.indexrelid=c.oid where c.relname in ('ix_users_bot_id','ix_gifts_buyer_id','ix_gifts_redeemed_by','ix_contest_entries_user_id') and i.indisvalid\\\"\" | tr -d '[:space:]')
  echo \"valid_new_indexes=\$n (expect 4)\"; [ \"\$n\" = '4' ]
"; then echo ">>> FAIL: missing/invalid new index (run DROP INDEX CONCURRENTLY IF EXISTS + re-migrate)"; exit 31; fi

if ! ssh_do "no unhealthy containers + app services running" "
  bad=\$(docker ps --filter 'health=unhealthy' --format '{{.Names}}')
  [ -z \"\$bad\" ] || { echo \"UNHEALTHY: \$bad\"; exit 1; }
  for s in api bot worker beat; do
    st=\$(docker inspect -f '{{.State.Status}}' chatgptflashbot-\$s-1 2>/dev/null)
    echo \"\$s=\$st\"; [ \"\$st\" = 'running' ] || exit 1
  done
"; then echo ">>> FAIL: unhealthy or non-running app container"; exit 32; fi

if ! ssh_do "smoke test (scripts/smoke_test.sh)" "cd '$APP_DIR' && bash scripts/smoke_test.sh"; then
  echo ">>> FAIL: smoke test failed"; exit 33
fi

ssh_do "recent app logs (tail, informational)" "cd '$APP_DIR' && $COMPOSE logs --tail=30 api bot worker" || true

cat <<ROLLBACK

======================  DEPLOY OK  ·  ROLLBACK (run on the server if needed later)  ======================
# APP rollback (0043/0044 additive → old code runs fine on the indexed schema; no DB downgrade):
  mv $APP_DIR ${APP_DIR}.failed.${TS} && mv ${APP_DIR}.prev.${TS} $APP_DIR
  cd $APP_DIR && $COMPOSE build $APP_SERVICES && $COMPOSE up -d $APP_SERVICES && $COMPOSE up -d --force-recreate caddy
# MIGRATION rollback (only if schema must revert; reversible DROP INDEX CONCURRENTLY):
  cd $APP_DIR && $COMPOSE run --rm migrate alembic downgrade $EXPECT_CUR
# DB restore (LAST RESORT — data corruption only):
  gunzip -c ~/predeploy-backup-fa654ba-20260713-195247.sql.gz | docker exec -i chatgptflashbot-postgres-1 sh -lc 'psql -U \$POSTGRES_USER -d \$POSTGRES_DB'
=========================================================================================================
ROLLBACK
