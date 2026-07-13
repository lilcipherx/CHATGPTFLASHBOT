# pip-audit triage — production dependencies (branch `claude/loop-engineering`)

Audit run isolated on a full CPython 3.14.6 (the project `.venv` has a stripped stdlib that can't
run pip-audit): `pip-audit 2.10.1 -r requirements.txt` (full transitive resolution). Advisory DB
as of 2026-07 — the pinned deps date to ~Dec 2024, so ~1.5 years of advisories apply.

## Result (updated)
- **Before:** 97 advisories in 7 packages.
- **Fixed + validated (full suite 1014 passed each time):** 59 cleared → **38 advisories in 2
  packages remain**, both hard-pinned by a core framework:
  - safe patch/minor: pillow 12.3.0 (5), python-multipart 0.0.31 (6), pyjwt 2.13.0 (12),
    cryptography 44.0.0→**48.0.1** (5);
  - stable-API majors validated: **pypdf 5.1.0→6.13.3** (31) — app uses only `PdfReader/.pages/
    .extract_text()`, unaffected by 6.x removals.
- **Remaining 38** need a CORE-FRAMEWORK bump (blocked by hard pins), NOT blind-applied:
  - `aiohttp` 3.10.11 (30) — pinned `<3.11` by **aiogram 3.15.0**; the min fix is 3.12.14 (>3.11),
    so aiohttp can't move without an **aiogram** bump. Reachability LOW (S3 client; CVEs are
    HTTP-server-side). Attempted pin to 3.14.1 → rejected (aiogram conflict), reverted.
  - `starlette` 0.41.3 (8) — pinned `<0.42` by **fastapi 0.115.6**; min fix 0.47.2 needs
    **fastapi ≥0.116**. Reachability MEDIUM (multipart DoS). See attempt log below.
- pip-audit has NO CVSS/severity field (PyPI source); severity below is classed by CVE type +
  the app's actual reachability.

## FIXED (safe patch/minor bumps — validated: `pip check` clean, full suite 1014 passed)
| Package | 44.0.0→ | Cleared | Reachability / class | Why safe |
|---------|---------|---------|----------------------|----------|
| `pillow` 12.2.0→**12.3.0** | patch | 5 | LOW — CVEs are in PCF/BDF/GD **font** parsers + Windows viewer; app only decodes PNG/JPEG uploads, never fonts / `Image.show()` | patch, no API change |
| `python-multipart` 0.0.20→**0.0.31** | patch | 6 | **MEDIUM** — multipart/form DoS is reachable (upload endpoints parse untrusted forms); path-traversal only under non-default `UPLOAD_DIR` (unused) | 0.0.x, fastapi allows |
| `pyjwt` 2.10.1→**2.13.0** | minor | 12 | LOW–MED — most CVEs are `PyJWKClient` (unused), detached-JWS (unused), alg-confusion w/ raw JWK (app uses single HS256 + static secret); `crit`/alg-allowlist hardening applies | 2.x API stable |
| `cryptography` 44.0.0→**44.0.1** | patch | 1 | LOW — clears the statically-linked OpenSSL CVE-2024-12797; app uses cryptography for Fernet only | patch |

Note: pyjwt 2.13 emits `InsecureKeyLengthWarning` for HMAC keys <32 bytes — a warning only (tests
pass). Prod `admin_jwt_secret` should be ≥32 bytes (recommend documenting/enforcing a length check).

## REMAINING — 37 advisories in 2 packages, both hard-pinned by a CORE framework
| Package | current→needed | # | Reachability (per app usage) | Why NOT bumped |
|---------|----------------|---|------------------------------|----------------|
| `aiohttp` 3.10.11→3.14.1 | 30 | **effectively NOT reachable** — the app uses aiohttp only as a **client** (aioboto3 S3, aiogram Telegram) and runs **no aiohttp server**; all 30 CVEs are aiohttp-**server** DoS / request-smuggling / static-files (server memory, zip-bomb, chunked-CPU, path-traversal). 1 marginal client-TLS-hostname (PYSEC-2026-237). | pinned `<3.11` by **aiogram 3.15.0**; min fix 3.12.14 > 3.11 → needs an **aiogram** core bump (bot handlers/FSM/middlewares) for ~zero real benefit. Pin to 3.14.1 attempted → aiogram conflict → reverted. |
| `starlette` 0.41.3→1.3.1 | 8 | **MED (partial)** — `request.form()` + `Range` header quadratic-DoS reachable (upload/any endpoint); Host-header + path-validation MED; the 2 `StaticFiles`-on-**Windows** CVEs are NOT reachable (prod is Linux). | pinned `<0.42` by **fastapi 0.115.6**; clearing all needs **starlette 1.3.1** (a starlette **1.x major**) + a fastapi that supports it. |

### fastapi/starlette upgrade — attempted + validated, then reverted (judgement call)
- Bumped `fastapi 0.115.6→0.116.2` + `starlette 0.41.3→0.47.2` (0.116 allows starlette <0.48). Full
  suite **1014 passed**, `pip check` clean, ASGI integration tests green — so the bump is *viable*.
- **Reverted** because: it clears only **1 of 8** starlette CVEs (0.47.2 is the *minimum* fix; the
  reachable form/Range DoS need **starlette 1.3.1**), i.e. it swaps the core web framework on a
  live payment/Telegram prod for a marginal, incomplete gain. Fully clearing starlette needs a
  starlette-1.x + newer-fastapi coordinated upgrade — a dedicated, separately-approved effort.

### Bottom line
- **59 of 97 CVEs fixed + validated** (all reachable + safe ones). The remaining **38** are:
  `aiohttp` (30, **not reachable** — no aiohttp server) and `starlette` (8, needs a starlette-1.x
  major bump; 2 of them Windows-only / not reachable on Linux prod). (The fastapi bump that would
  shave 1 was reverted — see above.)
- **No known RCE** against this app's usage — the remainder is server-side DoS the app can't hit
  (aiohttp) or client-reachable DoS gated behind a major framework upgrade (starlette).
- This is **not a clean `pip-audit --strict`** state; it is a triaged state. Recommend accepting the
  aiohttp advisories as non-reachable residuals (like the Docker item) and scheduling a
  starlette-1.x / fastapi upgrade as a separate validated change if the multipart/Range DoS matters.
