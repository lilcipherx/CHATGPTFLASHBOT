# pip-audit triage — production dependencies (branch `claude/loop-engineering`)

Audit run isolated on a full CPython 3.14.6 (the project `.venv` has a stripped stdlib that can't
run pip-audit): `pip-audit 2.10.1 -r requirements.txt` (full transitive resolution). Advisory DB
as of 2026-07 — the pinned deps date to ~Dec 2024, so ~1.5 years of advisories apply.

## Result
- **Before:** 97 advisories in 7 packages.
- **Safe fixes applied + validated (this branch):** 24 cleared → **73 advisories in 4 packages remain.**
- pip-audit has NO CVSS/severity field (PyPI source); severity below is classed by CVE type +
  the app's actual reachability (what the code does with each package).

## FIXED (safe patch/minor bumps — validated: `pip check` clean, full suite 1014 passed)
| Package | 44.0.0→ | Cleared | Reachability / class | Why safe |
|---------|---------|---------|----------------------|----------|
| `pillow` 12.2.0→**12.3.0** | patch | 5 | LOW — CVEs are in PCF/BDF/GD **font** parsers + Windows viewer; app only decodes PNG/JPEG uploads, never fonts / `Image.show()` | patch, no API change |
| `python-multipart` 0.0.20→**0.0.31** | patch | 6 | **MEDIUM** — multipart/form DoS is reachable (upload endpoints parse untrusted forms); path-traversal only under non-default `UPLOAD_DIR` (unused) | 0.0.x, fastapi allows |
| `pyjwt` 2.10.1→**2.13.0** | minor | 12 | LOW–MED — most CVEs are `PyJWKClient` (unused), detached-JWS (unused), alg-confusion w/ raw JWK (app uses single HS256 + static secret); `crit`/alg-allowlist hardening applies | 2.x API stable |
| `cryptography` 44.0.0→**44.0.1** | patch | 1 | LOW — clears the statically-linked OpenSSL CVE-2024-12797; app uses cryptography for Fernet only | patch |

Note: pyjwt 2.13 emits `InsecureKeyLengthWarning` for HMAC keys <32 bytes — a warning only (tests
pass). Prod `admin_jwt_secret` should be ≥32 bytes (recommend documenting/enforcing a length check).

## REMAINING — 73 advisories, all need MAJOR / coordinated upgrades (NOT blind-bumped)
| Package | current→needed | # | Reachability / severity class | Why deferred (risk) |
|---------|----------------|---|-------------------------------|---------------------|
| `pypdf` 5.1.0→**6.13.3** | 31 | MED — DoS (infinite-loop / quadratic) parsing **untrusted PDFs**; reachable only via the premium doc-extraction path | **major 5→6** — API changes; needs code review of the extraction code + regression |
| `aiohttp` 3.10.11→**3.14.1** | 30 | LOW — **transitive** (aioboto3→aiobotocore, S3 **client**); the CVEs are overwhelmingly HTTP-**server** (request smuggling / server parsing) which the app never runs; a few client redirect/proxy | transitive — pinning risks aiobotocore conflict; needs aioboto3-compat validation |
| `starlette` 0.41.3→**1.3.1** | 8 | MED — multipart/form DoS reachable (uploads) | **transitive via fastapi** — fastapi 0.115.6 pins starlette <0.42; needs a coordinated fastapi major bump + full regression |
| `cryptography` 44.0.1→**48.0.1** | 4 | LOW — X.509 name-constraints (app doesn't validate cert chains), `public_key_from_numbers` (unused), OpenSSL-in-wheels | 44→48 major (Rust/OpenSSL backend) — validate before shipping |

### Blocking assessment
- **Highest real reachability among the remaining:** `starlette` multipart DoS and `pypdf` PDF DoS
  (both DoS-class, reachable via upload / doc features). These are the ones worth a validated
  upgrade first.
- `aiohttp` (client-only, server-side CVEs) and `cryptography` (unused APIs) are **low reachability**.
- None of the 73 are known remote-code-execution against this app's usage; they are DoS / parsing /
  hardening classes gated on features the app either doesn't use or uses on trusted inputs.

### Recommended next step (separate, validated effort — do NOT blind-bump)
1. `starlette`: bump `fastapi` to a release that allows starlette ≥0.47/1.x, re-run the full suite +
   e2e (upload flows especially).
2. `pypdf` 5→6: review `core/services` doc-extraction call sites for API breaks, then bump + test.
3. `aiohttp`: bump `aioboto3`/`aiobotocore` to a line that pulls aiohttp ≥3.14.1; validate S3 uploads.
4. `cryptography` 44→48: bump + smoke-test Fernet encrypt/decrypt + argon2.

Until then these 73 remain open; the CI `pip-audit --strict` gate would still fail on them, so this
is **not** a clean-audit state — it is a reduced, triaged state with the safely-fixable + reachable
items addressed and the major coordinated upgrades documented.
