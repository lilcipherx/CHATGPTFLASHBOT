#!/usr/bin/env bash
# Atomic release to the flashbot production host — immutable bundle + blue/green dir swap.
#
# Runs from the LOCAL machine (git-bash) and orchestrates the server over `ssh flashbot`.
# It NEVER prints the server .env or any secret. It preserves the previous release and
# prints exact rollback commands.
#
#   Usage:  bash scripts/atomic_release.sh [REF] [--dry-run]
#   REF defaults to the merged SHA fa654ba. --dry-run prints every remote command
#   without executing it (nothing is changed on the server).
#
# Design (why atomic + safe):
#   - Immutable artifact: `git archive REF` = exactly the committed tree (no .git, no
#     untracked/.env, reproducible), verified by sha256 on the server.
#   - Same-filesystem staging under ~/releases so the final `mv` is a rename (atomic).
#   - Prod app keeps running on its baked images during staging/build; only the two
#     back-to-back `mv` renames + `up -d` recreate cause the (accepted) brief downtime.
#   - Migrations (0043/0044) run via the one-off `migrate` compose service before
#     api/bot/worker/beat start; they are additive CONCURRENT indexes (see migration-runbook).
set -euo pipefail

REF="${1:-fa654ba}"
DRY=0; [[ "${2:-}" == "--dry-run" || "${1:-}" == "--dry-run" ]] && DRY=1
[[ "${1:-}" == "--dry-run" ]] && REF="fa654ba"

SSH_HOST="flashbot"
APP_DIR="/home/ubuntu/CHATGPTFLASHBOT"
REL_ROOT="/home/ubuntu/releases"
COMPOSE="docker compose -f docker-compose.yml -f docker-compose.prod.yml"
MIN_FREE_GB=4                 # hard-stop threshold (build + node_modules + layers headroom)
EXPECT_CUR="0042_search_model"  # prod alembic must be here before deploy
EXPECT_HEAD="0044_missing_model_indexes"

TS="$(date +%Y%m%d-%H%M%S)"
SHORT="$(git rev-parse --short "$REF")"
FULL="$(git rev-parse "$REF")"
BUNDLE="release-${SHORT}.tar.gz"
STAGE="${REL_ROOT}/${SHORT}-${TS}"

say(){ printf '\n=== %s ===\n' "$*"; }
run_remote(){ # run_remote "<description>" "<remote command>"
  echo "  [remote] $1"
  if [[ $DRY -eq 1 ]]; then echo "    DRY: ssh $SSH_HOST '$2'"; else ssh -o ConnectTimeout=30 "$SSH_HOST" "$2"; fi
}

say "0. Preflight (local)"
git rev-parse --verify "$REF^{commit}" >/dev/null
echo "  REF=$REF  short=$SHORT  full=$FULL  ts=$TS  dry_run=$DRY"

say "1. Build immutable bundle (local git archive — no .git/.env/untracked)"
if [[ $DRY -eq 1 ]]; then echo "  DRY: git archive --format=tar.gz -o $BUNDLE $REF"; else
  git archive --format=tar.gz -o "$BUNDLE" "$REF"
  sha256sum "$BUNDLE" | tee "${BUNDLE}.sha256"
fi

say "2. Deliver bundle to server staging area (scp)"
run_remote "ensure releases dir" "mkdir -p '$REL_ROOT/incoming'"
if [[ $DRY -eq 1 ]]; then echo "  DRY: scp $BUNDLE ${BUNDLE}.sha256 $SSH_HOST:$REL_ROOT/incoming/"; else
  scp "$BUNDLE" "${BUNDLE}.sha256" "$SSH_HOST:$REL_ROOT/incoming/"
fi

say "3. Stage: extract into SAME-FS dir + verify checksum"
run_remote "create staging + extract + verify" "
  set -e
  cd '$REL_ROOT/incoming'
  ( cd '$REL_ROOT' && sha256sum -c 'incoming/${BUNDLE}.sha256' ) || { echo 'CHECKSUM FAIL'; exit 1; }
  mkdir -p '$STAGE'
  tar xzf '$REL_ROOT/incoming/$BUNDLE' -C '$STAGE'
  test -f '$STAGE/Dockerfile' && test -f '$STAGE/docker-compose.prod.yml' && echo 'staging tree OK'
"

say "4. Carry over the existing .env (copy only — NEVER printed)"
run_remote "copy .env, verify non-empty by SIZE only" "
  set -e
  test -s '$APP_DIR/.env' || { echo 'ERROR: current .env missing/empty'; exit 1; }
  cp -p '$APP_DIR/.env' '$STAGE/.env'
  test -s '$STAGE/.env' && echo \".env carried (size=\$(stat -c%s '$STAGE/.env') bytes, contents not shown)\"
"

say "5. Free-space HARD-STOP (need >= ${MIN_FREE_GB} GB on /)"
run_remote "disk hard-stop" "
  avail=\$(df -BG --output=avail / | tail -1 | tr -dc 0-9)
  echo \"free_GB=\$avail (min=${MIN_FREE_GB})\"
  [ \"\$avail\" -ge ${MIN_FREE_GB} ] || { echo 'HARD-STOP: insufficient disk — aborting BEFORE any swap/build'; exit 2; }
"

say "6. Build SPAs in staging (Caddy serves miniapp/dist + admin/dist)"
run_remote "npm ci + build (miniapp, admin) in staging" "
  set -e
  ( cd '$STAGE/miniapp' && npm ci && npm run build )
  ( cd '$STAGE/admin'   && npm ci && npm run build )
  test -d '$STAGE/miniapp/dist' && test -d '$STAGE/admin/dist' && echo 'SPA dist built'
"

say "7. Validate merged compose in staging (config -q — no secret output)"
run_remote "compose config -q" "
  cd '$STAGE' && $COMPOSE config -q && echo 'compose config valid (exit 0)'
"

say "8. Prod safety: confirm current alembic == ${EXPECT_CUR} BEFORE swap"
run_remote "check prod alembic current" "
  cur=\$(docker exec chatgptflashbot-postgres-1 sh -lc 'psql -U \$POSTGRES_USER -d \$POSTGRES_DB -tAc \"select version_num from alembic_version\"' | tr -d '[:space:]')
  echo \"alembic_current=\$cur\"
  [ \"\$cur\" = '${EXPECT_CUR}' ] || { echo \"HARD-STOP: expected ${EXPECT_CUR}, got \$cur\"; exit 3; }
"

say "9. ATOMIC SWAP (preserve previous release) + write provenance marker"
run_remote "swap current<->staging" "
  set -e
  mv '$APP_DIR' '${APP_DIR}.prev.${TS}'      # preserve previous (rename, atomic)
  mv '$STAGE'   '$APP_DIR'                    # activate new release (rename, atomic)
  printf '%s\n' '$FULL' > '$APP_DIR/.DEPLOYED_SHA'
  echo \"swapped: prev=${APP_DIR}.prev.${TS}  active=$APP_DIR  .DEPLOYED_SHA=$FULL\"
"

say "10. Rebuild images, recreate, run migrations (migrate service applies 0043/0044)"
run_remote "build" "cd '$APP_DIR' && $COMPOSE build"
run_remote "up -d (migrate runs alembic upgrade head BEFORE app services start)" "cd '$APP_DIR' && $COMPOSE up -d"
run_remote "force-recreate caddy to serve new dist (caddy-reload-gotcha)" "cd '$APP_DIR' && $COMPOSE up -d --force-recreate caddy"

say "11. Post-deploy verification"
run_remote "alembic head == ${EXPECT_HEAD}" "
  cur=\$(docker exec chatgptflashbot-postgres-1 sh -lc 'psql -U \$POSTGRES_USER -d \$POSTGRES_DB -tAc \"select version_num from alembic_version\"' | tr -d '[:space:]')
  echo \"alembic_current=\$cur\"; [ \"\$cur\" = '${EXPECT_HEAD}' ] && echo 'MIGRATIONS OK' || echo 'WARN: not at head'
"
run_remote "new indexes present + VALID (0043/0044)" "
  docker exec chatgptflashbot-postgres-1 sh -lc \"psql -U \\\$POSTGRES_USER -d \\\$POSTGRES_DB -c \\\"SELECT c.relname AS index, i.indisvalid AS valid FROM pg_class c JOIN pg_index i ON i.indexrelid=c.oid WHERE c.relname IN ('ix_users_bot_id','ix_gifts_buyer_id','ix_gifts_redeemed_by','ix_contest_entries_user_id') ORDER BY 1;\\\"\"
  echo 'expect 4 rows, all valid=t'
"
run_remote "container health" "$COMPOSE ps"
run_remote "smoke test" "cd '$APP_DIR' && bash scripts/smoke_test.sh || echo 'SMOKE FAILED — see rollback'"
run_remote "recent app logs (tail)" "cd '$APP_DIR' && $COMPOSE logs --tail=40 api bot worker"

cat <<ROLLBACK

===========================  ROLLBACK (run on the server if needed)  ===========================
# APP rollback (0043/0044 are additive → old code runs fine on the indexed schema; no DB
# downgrade needed). Swap back to the preserved previous release, then rebuild+recreate:
  mv $APP_DIR ${APP_DIR}.failed.${TS}
  mv ${APP_DIR}.prev.${TS} $APP_DIR
  cd $APP_DIR && $COMPOSE up -d --build --force-recreate

# MIGRATION rollback (only if you must revert the schema; both are reversible DROP INDEX
# CONCURRENTLY downgrades):
  cd $APP_DIR && $COMPOSE run --rm migrate alembic downgrade $EXPECT_CUR

# DB restore (LAST RESORT — only on data corruption; our change is additive indexes):
  # gunzip -c ~/predeploy-backup-fa654ba-*.sql.gz | docker exec -i chatgptflashbot-postgres-1 \\
  #   sh -lc 'psql -U \$POSTGRES_USER -d \$POSTGRES_DB'
===============================================================================================
ROLLBACK
