# Atomic release runbook — flashbot production (immutable bundle + blue/green swap)

New, documented deploy procedure for a **directory-swap** host (the server is not a git repo;
the old code-delivery command was never recovered — see `docs/loop/` forensics). This replaces
the unknown legacy delivery with an explicit, reviewable, atomic one.

**Executable form:** `scripts/atomic_release.sh [REF] [--dry-run]` (REF defaults to `fa654ba`).
`--dry-run` prints every remote command and changes nothing. **Run only after owner sign-off.**
Validated locally: `bash -n` clean · `shellcheck -S style` clean · `--dry-run` renders the full chain.

## Hard gates (each exits non-zero — no `|| echo WARN` masking anywhere)
1. **Config drift** — live `Dockerfile`, `docker-compose.yml`, `docker-compose.prod.yml`, `Caddyfile`
   are `diff -u`'d against the bundle (the `.env` is **never** read). Any difference → **ABORT (exit
   20)** with a safe diff. Manual server-side edits are NOT overwritten; they must be migrated into
   Git and re-bundled first.
2. **Disk ≥ 7 GB, checked twice** — once before the frontend build (exit 21) and again right before
   the docker build/swap (exit 23). **No `prune`/cleanup is ever run on production.**
3. **Verification** — alembic must reach `0044` (exit 30); the 4 new indexes must exist AND be
   `indisvalid` (exit 31); no container `health=unhealthy` and api/bot/worker/beat must be `running`
   (exit 32); `scripts/smoke_test.sh` must pass (exit 33).
4. **Scoped compose ops** — only the app services `migrate api bot worker beat` are `build`+`up -d`,
   and `caddy` is a **separate** `up -d --force-recreate`. **postgres, redis, minio, backup are NOT
   recreated.**

## Verified facts this design relies on
- `migrate` compose service runs `alembic upgrade head && seed_ai_models`; **bot/api/worker/beat
  `depends_on: migrate (service_completed_successfully)`** → migrations are fail-closed (app never
  serves against a behind-head schema). Source: `docker-compose.yml`.
- App code is **baked into the image** (Dockerfile `COPY . .`), NOT bind-mounted → swapping the dir
  does not disturb running app containers until rebuild+recreate.
- **caddy bind-mounts** `./miniapp/dist`, `./admin/dist`, `./Caddyfile` (ro) → after a swap caddy
  must be `--force-recreate`d to serve the new SPA/Caddyfile. Source: `docker-compose.prod.yml`.
- Prod is at `alembic 0042_search_model`; target head after deploy is `0044_missing_model_indexes`
  (additive `CREATE INDEX CONCURRENTLY`). Source: read-only inventory + `migration-runbook.md`.

## Exact command chain (what the script does)
```
# ---- LOCAL (immutable artifact) ----
git archive --format=tar.gz -o release-<short>.tar.gz <REF>     # exactly the committed tree; no .git/.env/untracked
sha256sum release-<short>.tar.gz > release-<short>.tar.gz.sha256

# ---- DELIVER ----
ssh flashbot 'mkdir -p /home/ubuntu/releases/incoming'
scp release-<short>.tar.gz{,.sha256} flashbot:/home/ubuntu/releases/incoming/

# ---- READ-ONLY QUOTING PREFLIGHT (exercises the exact psql/shell quoting the later gates use) ----
ssh flashbot: docker exec ...postgres... psql -tAc "select 1"   # must return 1, else ABORT exit 12 (no writes)

# ---- STAGE (same filesystem as the live dir → atomic mv later) ----
ssh flashbot: (cd releases/incoming && sha256sum -c release-<short>.tar.gz.sha256)   # integrity, checked IN incoming/
              mkdir -p /home/ubuntu/releases/<short>-<ts>
              tar xzf incoming/release-<short>.tar.gz -C /home/ubuntu/releases/<short>-<ts>

# ---- CONFIG DRIFT HARD-GATE (live vs bundle by sha256; file CONTENTS never printed — may hold secrets) ----
ssh flashbot: for f in Dockerfile docker-compose.yml docker-compose.prod.yml Caddyfile;
                do cmp -s CHATGPTFLASHBOT/$f <stage>/$f || echo "DRIFT: $f (sha live vs bundle)"; done
              # any differing file → ABORT exit 20; only NAMES + truncated sha256 fingerprints are logged

# ---- ENV (copy only; never printed) ----
ssh flashbot: test -s CHATGPTFLASHBOT/.env && cp -p CHATGPTFLASHBOT/.env <stage>/.env   # size-checked, contents never shown

# ---- DISK HARD-STOP #1 (before frontend build) ----
ssh flashbot: avail=$(df -BG --output=avail /); [ avail >= 7 GB ] || ABORT exit 21  (no prune, nothing swapped)

# ---- BUILD + VALIDATE IN STAGING ----
ssh flashbot: (cd <stage>/miniapp && npm ci && npm run build)
              (cd <stage>/admin   && npm ci && npm run build)
              (cd <stage> && docker compose -f docker-compose.yml -f docker-compose.prod.yml config -q)

# ---- PRE-SWAP SAFETY ----
ssh flashbot: assert prod alembic_current == 0042_search_model  (else ABORT exit 22)

# ---- DISK HARD-STOP #2 (right before swap + docker build) ----
ssh flashbot: avail=$(df -BG --output=avail /); [ avail >= 7 GB ] || ABORT exit 23  (no prune, nothing swapped)

# ---- ATOMIC SWAP (preserve previous; auto-recover on 2nd-mv failure) ----
ssh flashbot: mv CHATGPTFLASHBOT           CHATGPTFLASHBOT.prev.<ts>     # rename (atomic)
              mv releases/<short>-<ts>      CHATGPTFLASHBOT || {         # rename (atomic)
                mv CHATGPTFLASHBOT.prev.<ts> CHATGPTFLASHBOT             # RECOVERY: restore original current
                exit 40; }                                              #           then ABORT (nothing rebuilt)
              printf '%s\n' <full-sha> > CHATGPTFLASHBOT/.DEPLOYED_SHA

# ---- REBUILD + RECREATE + MIGRATE (app services ONLY; DB/redis/minio/backup untouched) ----
ssh flashbot: cd CHATGPTFLASHBOT
              docker compose -f ... -f ... build migrate api bot worker beat        # build new app images (old containers keep running)
              docker compose -f ... -f ... up -d migrate api bot worker beat        # migrate runs 0043/0044, THEN app services start
              docker compose -f ... -f ... up -d --force-recreate caddy             # serve new dist/Caddyfile (separate)

# ---- VERIFY (each check exits non-zero on failure — no masking) ----
ssh flashbot: alembic_current == 0044_missing_model_indexes                        (else exit 30)
              4 indexes ix_users_bot_id / ix_gifts_buyer_id / ix_gifts_redeemed_by /
                ix_contest_entries_user_id present + indisvalid = t                 (else exit 31)
              no health=unhealthy container AND api/bot/worker/beat == running      (else exit 32)
              bash scripts/smoke_test.sh                                            (else exit 33)
              docker compose logs --tail=30 api bot worker                          (informational)
```

## Risks (and mitigations)
| Risk | Impact | Mitigation |
|------|--------|------------|
| **Downtime on recreate** | api/bot/worker/beat restart during `up -d` (seconds–low minutes) | expected + accepted; build happens BEFORE recreate so a build failure never touches running containers |
| **Swap window** | ~ms gap where the live dir is briefly renamed | two back-to-back `mv` renames; running app containers use baked images; caddy is force-recreated afterwards |
| **Migration `CONCURRENTLY` interrupted** | an INVALID index left behind | `migration-runbook.md`: `DROP INDEX CONCURRENTLY IF EXISTS <name>` then re-run `alembic upgrade head` (idempotent) |
| **Disk pressure** (9.3 GB free, build on prod host) | a build could fill the disk shared with prod | HARD-STOP at **7 GB** free, checked **twice** (before frontend build AND right before docker build); build reuses the ~12 GB cache; **no prune** performed |
| **Config drift** (manual server edits to Dockerfile/compose/Caddyfile) | a blind deploy would silently overwrite un-Git'd prod config | **drift hard-gate**: `diff -u` live vs bundle for all 4 files → ABORT + safe diff if any differ; `.env` is never read |
| **Image build not pre-verified** | Docker unavailable locally (residual limitation) — bumped deps unverified in an actual build | deps are manylinux/pure wheels for python:3.12-slim; build step (app services only) will surface any failure BEFORE recreate (containers keep old image) |
| **Migrate fails** | app services won't start (fail-closed depends_on) → app down | roll back the dir swap + rebuild/recreate **app services only** (old code, additive schema is compatible) |
| **Unintended service churn** | a blanket `up -d` could recreate postgres/redis/minio/backup | compose ops are **scoped** to `migrate api bot worker beat`; caddy is a separate `--force-recreate`; stateful services are never named |
| **.env drift** | staging uses the current server `.env` (copied) | fa654ba adds no new config vars, so the existing `.env` is compatible |

## Rollback (exact)
```
# APP rollback — 0043/0044 are additive; the OLD code (2c6d678) runs fine on the indexed
# schema, so NO DB downgrade is needed. Swap back to the preserved release:
mv /home/ubuntu/CHATGPTFLASHBOT              /home/ubuntu/CHATGPTFLASHBOT.failed.<ts>
mv /home/ubuntu/CHATGPTFLASHBOT.prev.<ts>    /home/ubuntu/CHATGPTFLASHBOT
cd /home/ubuntu/CHATGPTFLASHBOT && docker compose -f docker-compose.yml -f docker-compose.prod.yml build migrate api bot worker beat \
  && docker compose -f docker-compose.yml -f docker-compose.prod.yml up -d migrate api bot worker beat \
  && docker compose -f docker-compose.yml -f docker-compose.prod.yml up -d --force-recreate caddy

# MIGRATION rollback (only if the schema must be reverted; both migrations are reversible):
cd /home/ubuntu/CHATGPTFLASHBOT && docker compose -f docker-compose.yml -f docker-compose.prod.yml run --rm migrate alembic downgrade 0042_search_model

# DB restore (LAST RESORT — data corruption only; our change is additive indexes):
gunzip -c ~/predeploy-backup-fa654ba-20260713-195247.sql.gz | docker exec -i chatgptflashbot-postgres-1 sh -lc 'psql -U $POSTGRES_USER -d $POSTGRES_DB'
```

## Prerequisites before running (owner)
- Confirm this exact procedure.
- Ensure a fresh, verified DB backup exists (already created: `~/predeploy-backup-fa654ba-20260713-195247.sql.gz`).
- Accept the brief downtime window on container recreate.
- Nothing runs on AWS until you separately confirm.
