"""Locust load test for the Core API.

Run (web UI):   locust -f loadtests/locust/locustfile.py --host http://localhost:8000
Run (headless): locust -f loadtests/locust/locustfile.py --host http://localhost:8000 \
                       --headless -u 100 -r 10 -t 5m --html loadtests/locust_report.html

Set BOT_TOKEN to sign Mini App initData (same scheme as api/deps.verify_init_data);
without it only the public health endpoints are hit.
"""
from __future__ import annotations

import hashlib
import hmac
import json
import os
import time
from urllib.parse import urlencode

from locust import HttpUser, between, task

BOT_TOKEN = os.environ.get("BOT_TOKEN", "")


def _signed_init_data(user_id: int = 99999001) -> str | None:
    if not BOT_TOKEN:
        return None
    fields = {
        "auth_date": str(int(time.time())),
        "user": json.dumps({"id": user_id, "username": "locust", "language_code": "ru"}),
    }
    data_check = "\n".join(f"{k}={fields[k]}" for k in sorted(fields))
    secret = hmac.new(b"WebAppData", BOT_TOKEN.encode(), hashlib.sha256).digest()
    fields["hash"] = hmac.new(secret, data_check.encode(), hashlib.sha256).hexdigest()
    return urlencode(fields)


class CoreApiUser(HttpUser):
    wait_time = between(0.5, 2.0)

    def on_start(self) -> None:
        self._init = _signed_init_data()

    @task(3)
    def health(self) -> None:
        self.client.get("/health", name="GET /health")

    @task(1)
    def readiness(self) -> None:
        # 503 (a dependency down) is an expected, non-error response for the probe.
        with self.client.get("/health/ready", name="GET /health/ready", catch_response=True) as r:
            if r.status_code in (200, 503):
                r.success()

    @task(5)
    def profile(self) -> None:
        if not self._init:
            return
        self.client.get(
            "/api/profile", headers={"X-Init-Data": self._init}, name="GET /api/profile"
        )

    @task(4)
    def photo_effects(self) -> None:
        if not self._init:
            return
        self.client.get(
            "/api/photo-effects", headers={"X-Init-Data": self._init}, name="GET /api/photo-effects"
        )
