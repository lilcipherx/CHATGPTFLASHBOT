# Loop Engineering — AWS inventory

Actual AWS state, independently verified read-only via `ssh flashbot`. Zero-trust: nothing
here is copied from `docs/audit/aws-production-inventory.md` — that older doc is a hypothesis
to be re-checked. AWS receives ONLY the exact merged `origin/main` SHA (never server-only edits).

## Access (from `~/.ssh/config`, no keys shown)
- Host alias `flashbot` → HostName `18.198.8.92`, User `ubuntu`.

## Verification status: PENDING
No `ssh flashbot` connection has been made yet in this loop. AWS discovery is scheduled for
the security/ops domain loop (L7), read-only first:
- `git`-less directory-swap deploy layout (per hypothesis) — to confirm.
- Running containers + image tags (`:latest` vs digest-pinned) — to confirm drift claim.
- Host port exposure vs Security Group — to confirm 5432/6379/9000/9001/20128/8000 not public.
- `alembic current` on host DB — expect `0042_search_model`.
- `ufw` status, `.env` perms, backup cron, disk usage.

## Hypotheses to falsify (from older audit doc — UNVERIFIED)
- EC2 Ubuntu 24.04, Docker 29.x / Compose v2.40.x, ~62% disk.
- Live containers on `:latest` (repo is digest-pinned → drift).
- Some internal ports bound `0.0.0.0`, protected only by Security Group (`ufw` inactive).

## Deployed SHA
- Target after this loop's merge: TBD (== merged `origin/main`).
- Currently deployed: UNKNOWN until verified.

## Rollback evidence
- Not yet captured.
