// k6 load test for the Core API (Mini App + health + metrics).
//
// Scenarios (pick with SCENARIO env): smoke | load | spike | soak.
//   k6 run -e SCENARIO=smoke   -e BASE_URL=http://localhost:8000 loadtests/k6/api.js
//   k6 run -e SCENARIO=spike   -e BASE_URL=https://staging.example.com loadtests/k6/api.js
//
// Authenticated Mini App calls need a signed initData. Provide BOT_TOKEN to sign
// one inline (same HMAC scheme as api/deps.verify_init_data); without it, only
// the public health/metrics endpoints are exercised.
//
// HTML + JSON reports are written via handleSummary (see scripts/run_loadtests.sh).
import http from "k6/http";
import crypto from "k6/crypto";
import { check, sleep } from "k6";
import { htmlReport } from "https://raw.githubusercontent.com/benc-uk/k6-reporter/main/dist/bundle.js";
import { textSummary } from "https://jslib.k6.io/k6-summary/0.0.1/index.js";

const BASE_URL = __ENV.BASE_URL || "http://localhost:8000";
const BOT_TOKEN = __ENV.BOT_TOKEN || "";

const SCENARIOS = {
  smoke: { executor: "constant-vus", vus: 2, duration: "30s" },
  load: {
    executor: "ramping-vus",
    stages: [
      { duration: "1m", target: 50 },
      { duration: "3m", target: 50 },
      { duration: "1m", target: 0 },
    ],
  },
  spike: {
    executor: "ramping-vus",
    stages: [
      { duration: "10s", target: 5 },
      { duration: "20s", target: 300 }, // sudden spike
      { duration: "1m", target: 300 },
      { duration: "20s", target: 0 },
    ],
  },
  soak: { executor: "constant-vus", vus: 30, duration: "30m" },
};

const chosen = __ENV.SCENARIO || "smoke";

export const options = {
  scenarios: { [chosen]: SCENARIOS[chosen] },
  thresholds: {
    http_req_failed: ["rate<0.01"], // <1% errors
    http_req_duration: ["p(95)<800"], // 95th percentile under 800ms
  },
};

// Build a signed Telegram WebApp initData (matches api/deps.verify_init_data).
function signedInitData() {
  if (!BOT_TOKEN) return null;
  const user = JSON.stringify({ id: 99999001, username: "k6", language_code: "ru" });
  const authDate = Math.floor(Date.now() / 1000).toString();
  const fields = { auth_date: authDate, user: user };
  const dataCheck = Object.keys(fields)
    .sort()
    .map((k) => `${k}=${fields[k]}`)
    .join("\n");
  const secret = crypto.hmac("sha256", "WebAppData", BOT_TOKEN, "binary");
  const hash = crypto.hmac("sha256", secret, dataCheck, "hex");
  const params = new URLSearchParams(fields);
  params.append("hash", hash);
  return params.toString();
}

const INIT_DATA = signedInitData();

export default function () {
  // Public, no-auth endpoints — always exercised.
  check(http.get(`${BASE_URL}/health`), { "health 200": (r) => r.status === 200 });
  check(http.get(`${BASE_URL}/health/ready`), {
    "ready 200/503": (r) => r.status === 200 || r.status === 503,
  });

  // Authenticated Mini App endpoints — only when we can sign initData.
  if (INIT_DATA) {
    const headers = { "X-Init-Data": INIT_DATA };
    check(http.get(`${BASE_URL}/api/profile`, { headers }), {
      "profile ok": (r) => r.status === 200,
    });
    check(http.get(`${BASE_URL}/api/photo-effects`, { headers }), {
      "effects ok": (r) => r.status === 200,
    });
  }
  sleep(1);
}

export function handleSummary(data) {
  return {
    "loadtests/report.html": htmlReport(data),
    "loadtests/summary.json": JSON.stringify(data, null, 2),
    stdout: textSummary(data, { indent: " ", enableColors: true }),
  };
}
