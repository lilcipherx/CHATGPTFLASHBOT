# Load & performance testing

Two complementary tools:

| Tool | File | Best for |
|------|------|----------|
| **k6** | `k6/api.js` | scripted scenarios (smoke/load/spike/soak), p95 thresholds, HTML report |
| **Locust** | `locust/locustfile.py` | interactive ramping, live web UI, Python tasks |

## Prerequisites
- k6 — https://grafana.com/docs/k6/latest/set-up/install-k6/
- Locust — `pip install locust`
- A running API (`uvicorn api.main:app` or the docker stack) reachable at `BASE_URL`.
- Optional `BOT_TOKEN` to sign Mini App `initData` and exercise authenticated routes.
  Without it, only the public `/health*` endpoints are load-tested.

## Run
```bash
# single scenario
BASE_URL=http://localhost:8000 BOT_TOKEN=123:test scripts/run_loadtests.sh smoke

# everything (smoke -> load -> spike -> soak) + Locust
BASE_URL=https://staging.example.com BOT_TOKEN=$BOT_TOKEN scripts/run_loadtests.sh all
```
Reports land in `loadtests/report-<scenario>.html` and `loadtests/locust_report.html`.

## Scenarios (k6)
| Scenario | Shape | Purpose |
|----------|-------|---------|
| `smoke` | 2 VUs, 30s | sanity / CI gate |
| `load`  | ramp to 50 VUs, 5m | expected steady load |
| `spike` | jump to 300 VUs | sudden surge resilience |
| `soak`  | 30 VUs, 30m | memory leaks / connection-pool exhaustion |

## Thresholds (build fails if breached)
- `http_req_failed < 1%`
- `http_req_duration p(95) < 800ms`

## Interpreting results / next steps
- **p95 climbing under `soak`** → check DB connection-pool sizing (`DB_POOL_SIZE`,
  PgBouncer) and for slow queries (`EXPLAIN ANALYZE`, see `scripts/db_maintenance.sql`).
- **errors under `spike`** → raise gunicorn workers (`-w`) and/or worker replicas;
  confirm Redis throttle limits (`bot/middlewares/throttle.py`) are appropriate.
- Always run against **staging**, never production, and with the **mock AI server**
  (`uvicorn scripts.mock_ai_server:app`) so generation paths don't hit paid providers.
