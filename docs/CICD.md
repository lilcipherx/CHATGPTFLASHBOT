# CI/CD

## CI — `.github/workflows/ci.yml`
Runs on push/PR. Jobs:
| Job | What |
|-----|------|
| `lint` | `ruff check .` (gate) + `ruff format --check` (informational) |
| `typecheck` | `mypy` (informational, non-blocking — tighten over time) |
| `test` | `pytest` + coverage, floor `--fail-under=50` (raise as coverage grows) |
| `migrations` | `alembic upgrade head` + `scripts/check_migrations.py` (model↔migration drift) |
| `frontend` | matrix (miniapp/admin): `npm ci` → Vitest → `vite build` |
| `security` | `pip-audit` (deps) + `bandit` (static) |
| `docker` | `docker build` (buildx + GHA cache), no push |

Tests use the zero-infra config (SQLite + fakeredis), so no service containers
are needed and CI is fast.

## Release — `.github/workflows/release.yml`
On a `vX.Y.Z` tag: build + push the image to **GHCR**
(`ghcr.io/<owner>/<repo>:<version>`), then a `deploy` job that POSTs to
`DEPLOY_WEBHOOK` **only if that secret is set** (inert otherwise — wire your
target with no code change).

### Cut a release
```bash
git tag v1.2.0 && git push origin v1.2.0
```
Update `CHANGELOG.md` first; the tag should match the top entry.

## Dependabot — `.github/dependabot.yml`
Weekly PRs for pip, npm (miniapp + admin), GitHub Actions, and Docker.

## Required secrets
| Secret | Used by |
|--------|---------|
| `GITHUB_TOKEN` | auto — GHCR push |
| `DEPLOY_WEBHOOK` | optional — triggers deploy on release |

## Raising the bar over time
- Increase the coverage floor as suites grow.
- Flip `typecheck` to a gate once `mypy` is clean.
- Add the Playwright e2e (`npm run e2e`) as a post-deploy job against staging.
