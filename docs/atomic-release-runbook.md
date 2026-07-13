# Atomic release runbook — flashbot production (immutable bundle + blue/green swap)

New, documented deploy procedure for a **directory-swap** host (the server is not a git repo;
the old code-delivery command was never recovered — see `docs/loop/` forensics). This replaces
the unknown legacy delivery with an explicit, reviewable, atomic one.

**Executable form:** `scripts/atomic_release.sh [REF] [--dry-run]` (REF defaults to `fa654ba`).
`--dry-run` prints every remote command and changes nothing. **Run only after owner sign-off.**

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

# ---- STAGE (same filesystem as the live dir → atomic mv later) ----
ssh flashbot: sha256sum -c incoming/<...>.sha256              # integrity
              mkdir -p /home/ubuntu/releases/<short>-<ts>
              tar xzf incoming/release-<short>.tar.gz -C /home/ubuntu/releases/<short>-<ts>

# ---- ENV (copy only; never printed) ----
ssh flashbot: test -s CHATGPTFLASHBOT/.env && cp -p CHATGPTFLASHBOT/.env <stage>/.env   # size-checked, contents never shown

# ---- DISK HARD-STOP ----
ssh flashbot: avail=$(df -BG --output=avail /); [ avail >= 4 GB ] || ABORT (before any swap/build)

# ---- BUILD + VALIDATE IN STAGING ----
ssh flashbot: (cd <stage>/miniapp && npm ci && npm run build)
              (cd <stage>/admin   && npm ci && npm run build)
              (cd <stage> && docker compose -f docker-compose.yml -f docker-compose.prod.yml config -q)

# ---- PRE-SWAP SAFETY ----
ssh flashbot: assert prod alembic_current == 0042_search_model  (else HARD-STOP)

# ---- ATOMIC SWAP (preserve previous) ----
ssh flashbot: mv CHATGPTFLASHBOT           CHATGPTFLASHBOT.prev.<ts>     # rename (atomic)
              mv releases/<short>-<ts>      CHATGPTFLASHBOT              # rename (atomic)
              printf '%s\n' <full-sha> > CHATGPTFLASHBOT/.DEPLOYED_SHA

# ---- REBUILD + RECREATE + MIGRATE ----
ssh flashbot: cd CHATGPTFLASHBOT
              docker compose -f ... -f ... build                       # build new images (old containers keep running)
              docker compose -f ... -f ... up -d                       # migrate runs 0043/0044, THEN app services start
              docker compose -f ... -f ... up -d --force-recreate caddy # serve new dist/Caddyfile

# ---- VERIFY ----
ssh flashbot: alembic_current == 0044_missing_model_indexes
              4 indexes ix_users_bot_id / ix_gifts_buyer_id / ix_gifts_redeemed_by /
                ix_contest_entries_user_id present + indisvalid = t
              docker compose ps  (all healthy)
              bash scripts/smoke_test.sh
              docker compose logs --tail=40 api bot worker
```

## Risks (and mitigations)
| Risk | Impact | Mitigation |
|------|--------|------------|
| **Downtime on recreate** | api/bot/worker/beat restart during `up -d` (seconds–low minutes) | expected + accepted; build happens BEFORE recreate so a build failure never touches running containers |
| **Swap window** | ~ms gap where the live dir is briefly renamed | two back-to-back `mv` renames; running app containers use baked images; caddy is force-recreated afterwards |
| **Migration `CONCURRENTLY` interrupted** | an INVALID index left behind | `migration-runbook.md`: `DROP INDEX CONCURRENTLY IF EXISTS <name>` then re-run `alembic upgrade head` (idempotent) |
| **Disk pressure** (9.3 GB free, build on prod host) | a build could fill the disk shared with prod | HARD-STOP at 4 GB free BEFORE swap/build; build reuses the ~12 GB cache; no prune performed |
| **Image build not pre-verified** | Docker unavailable locally (residual limitation) — bumped deps unverified in an actual build | deps are manylinux/pure wheels for python:3.12-slim; build step will surface any failure BEFORE recreate (containers keep old image) |
| **Migrate fails** | app services won't start (fail-closed depends_on) → app down | roll back the dir swap + `up -d --build --force-recreate` (old code, additive schema is compatible) |
| **.env drift** | staging uses the current server `.env` (copied) | fa654ba adds no new config vars, so the existing `.env` is compatible |

## Rollback (exact)
```
# APP rollback — 0043/0044 are additive; the OLD code (2c6d678) runs fine on the indexed
# schema, so NO DB downgrade is needed. Swap back to the preserved release:
mv /home/ubuntu/CHATGPTFLASHBOT              /home/ubuntu/CHATGPTFLASHBOT.failed.<ts>
mv /home/ubuntu/CHATGPTFLASHBOT.prev.<ts>    /home/ubuntu/CHATGPTFLASHBOT
cd /home/ubuntu/CHATGPTFLASHBOT && docker compose -f docker-compose.yml -f docker-compose.prod.yml up -d --build --force-recreate

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
