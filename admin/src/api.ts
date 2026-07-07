// FIX: AUDIT12-F2 - API base URL resolution.
// VITE_API_BASE must be either:
//   - empty string "" (default) → requests go to /api/admin/... from the DOMAIN ROOT,
//     so admin SPA at https://superaibot.duckdns.org/admin/ correctly hits
//     https://superaibot.duckdns.org/api/admin/... (NOT /admin/api/...).
//   - a full origin like "https://api.example.com" for cross-origin setups.
// NEVER set VITE_API_BASE to a relative path like "/admin" or "./" — that would
// break the SPA when served under /admin/ because fetch would resolve to
// /admin/api/admin/... (404). We strip any trailing slash to be safe.
const RAW_BASE = (import.meta.env.VITE_API_BASE ?? "").trim();
const BASE = RAW_BASE.endsWith("/") ? RAW_BASE.slice(0, -1) : RAW_BASE;
const ADMIN = `${BASE}/api/admin`;

// The real credential is the httpOnly `admin_access` cookie the server sets on
// login — it is NOT readable from JS, so an XSS payload cannot exfiltrate it. We
// keep the access token in MEMORY only, sent as a fallback Authorization header
// for cross-origin dev (vite on another port, where the cookie may not flow); it
// is never written to localStorage. localStorage holds only a non-sensitive
// "authed" flag + role so the SPA can render the right view across reloads (the
// cookie re-authenticates on same-origin prod).
let accessToken = "";

export function isAuthed(): boolean {
  return localStorage.getItem("admin_authed") === "1";
}

function clearLocalAuth(): void {
  accessToken = "";
  localStorage.removeItem("admin_authed");
  localStorage.removeItem("admin_role");
  localStorage.removeItem("admin_email");
}

export function logout(): void {
  // Best-effort server-side revocation (bumps token_version + clears the cookie).
  // Fire-and-forget: used by passive 401 handling where we don't navigate immediately.
  if (isAuthed()) {
    fetch(`${ADMIN}/auth/logout`, {
      method: "POST",
      credentials: "include",
      headers: accessToken ? { Authorization: `Bearer ${accessToken}` } : {},
    }).catch(() => {});
  }
  clearLocalAuth();
}

// AWAITABLE revoke-all for the "Завершить все сессии" action: we must wait for the
// server to bump token_version BEFORE the caller reloads/navigates — otherwise the
// reload can cancel the in-flight POST and the revocation silently never happens.
export async function revokeAllSessions(): Promise<void> {
  if (isAuthed()) {
    try {
      await fetch(`${ADMIN}/auth/logout`, {
        method: "POST",
        credentials: "include",
        headers: accessToken ? { Authorization: `Bearer ${accessToken}` } : {},
      });
    } catch { /* network error — still clear local state below */ }
  }
  clearLocalAuth();
}

export async function login(
  email: string,
  password: string,
  otp?: string,
): Promise<{ role: string; mfaSetup: boolean }> {
  const res = await fetch(`${ADMIN}/auth/login`, {
    method: "POST",
    credentials: "include",  // accept the httpOnly access cookie
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ email, password, otp: otp || null }),
  });
  if (res.status === 401) {
    const body = await res.json().catch(() => ({}));
    throw new Error(body.detail ?? "unauthorized");
  }
  if (!res.ok) throw new Error(`login failed (${res.status})`);
  const data = await res.json();
  accessToken = data.access_token;        // memory only — never persisted
  if (data.mfa_setup_required) {
    // Restricted session: only 2FA enrollment is permitted. Do NOT mark fully
    // authed yet — the SPA forces enrollment, then a fresh login. (§8)
    return { role: data.role, mfaSetup: true };
  }
  localStorage.setItem("admin_authed", "1");
  localStorage.setItem("admin_role", data.role);
  // Non-sensitive: lets the sidebar show who is signed in (the email typed here),
  // instead of a hardcoded placeholder. Cleared on logout.
  localStorage.setItem("admin_email", email.trim().toLowerCase());
  return { role: data.role, mfaSetup: false };
}

// Build an Error from a failed response, surfacing the server's `detail` (FastAPI
// HTTPException message) so a page's catch can show WHY a request was rejected
// (e.g. "title required") instead of a useless "API 400".
async function apiError(res: Response): Promise<Error> {
  let detail = "";
  try {
    const body = await res.json();
    if (typeof body?.detail === "string") detail = body.detail;
    else if (Array.isArray(body?.detail)) detail = body.detail.map((d: { msg?: string }) => d?.msg).filter(Boolean).join("; ");
  } catch {
    /* non-JSON / empty body — fall back to the status code */
  }
  return new Error(detail || `API ${res.status}`);
}

// Single-flight token refresh. The 30-min access cookie is renewed via the httpOnly
// `admin_refresh` cookie (7-day) BEFORE giving up on a 401 — so an expired access
// token silently renews instead of surfacing "session expired". Concurrent 401s
// (the dashboard fires several requests at once) share ONE refresh round-trip.
let refreshPromise: Promise<boolean> | null = null;
function tryRefresh(): Promise<boolean> {
  if (!refreshPromise) {
    refreshPromise = fetch(`${ADMIN}/auth/refresh`, {
      method: "POST",
      credentials: "include",       // carries the refresh cookie
      headers: { "Content-Type": "application/json" },
      body: "{}",
    })
      .then(async (r) => {
        if (!r.ok) return false;
        const data = await r.json().catch(() => null);
        if (data?.access_token) accessToken = data.access_token;  // memory-only fallback
        return true;
      })
      .catch(() => false)
      .finally(() => { refreshPromise = null; });
  }
  return refreshPromise;
}

function withAuth(init: RequestInit): RequestInit {
  return {
    ...init,
    credentials: "include",  // send the httpOnly access cookie
    headers: {
      ...(init.headers ?? {}),
      // Cookie is the primary credential; header is a dev/cross-origin fallback.
      ...(accessToken ? { Authorization: `Bearer ${accessToken}` } : {}),
    },
  };
}

// FIX: FRONTEND - 15s timeout on every admin API call so a hung request (API
// process wedged, network black-hole) doesn't leave the admin staring at a spinner
// forever. Legitimate long ops (CSV export, VACUUM) use StreamingResponse with their
// own server-side timeout, so 15s is safe for the JSON paths.
const ADMIN_FETCH_TIMEOUT_MS = 15_000;

function fetchWithTimeout(input: string, init: RequestInit = {}): Promise<Response> {
  const ctrl = new AbortController();
  const timer = setTimeout(() => ctrl.abort(), ADMIN_FETCH_TIMEOUT_MS);
  // Preserve a caller-supplied signal too: if either fires, the request aborts.
  const userSignal = init.signal;
  // FIX: AUDIT-71 - capture listener and remove it in finally to prevent leak
  const onAbort = () => ctrl.abort();
  if (userSignal) {
    if (userSignal.aborted) ctrl.abort();
    else userSignal.addEventListener("abort", onAbort);
  }
  return fetch(input, { ...init, signal: ctrl.signal }).finally(() => {
    clearTimeout(timer);
    if (userSignal) userSignal.removeEventListener("abort", onAbort);
  });
}

// Credentialed admin fetch with one transparent refresh-and-retry on 401. Pages with
// their own fetch wrappers import this so they get the same auto-refresh as `req`.
// `path` is relative to the /api/admin base. Never logs out by itself — the caller
// decides what a post-refresh 401 means (req throws "session expired").
export async function adminFetch(path: string, init: RequestInit = {}): Promise<Response> {
  let res = await fetchWithTimeout(`${ADMIN}${path}`, withAuth(init));
  if (res.status === 401 && (await tryRefresh())) {
    res = await fetchWithTimeout(`${ADMIN}${path}`, withAuth(init));  // retry once with fresh token
  }
  return res;
}

async function req<T>(path: string, init: RequestInit = {}): Promise<T> {
  const res = await adminFetch(path, {
    ...init,
    headers: { ...(init.headers ?? {}), "Content-Type": "application/json" },
  });
  if (res.status === 401) {
    // FIX: AUDIT12-L4 - universal 401 → logout
    logout();
    window.dispatchEvent(new CustomEvent("admin:unauth"));  // FIX: FINAL-1 - App.tsx listens, swaps to Login in-place (was: redirect to /login which Caddy serves as miniapp)
    throw new Error("session expired");
  }
  if (!res.ok) throw await apiError(res);
  return res.json() as Promise<T>;
}

async function reqUpload<T>(path: string, file: File): Promise<T> {
  const form = new FormData();
  form.append("file", file);
  const res = await adminFetch(path, { method: "POST", body: form });
  if (res.status === 401) {
    // FIX: AUDIT12-L4 - universal 401 → logout
    logout();
    window.dispatchEvent(new CustomEvent("admin:unauth"));  // FIX: FINAL-1 - App.tsx listens, swaps to Login in-place (was: redirect to /login which Caddy serves as miniapp)
    throw new Error("session expired");
  }
  if (!res.ok) throw await apiError(res);
  return res.json() as Promise<T>;
}

export interface RevenueCurrency {
  total: number;
  count: number;
  avg_check: number;
  by_gateway: Record<string, number>;
}

export type DashboardPeriod = "day" | "week" | "month" | "all";

export interface Dashboard {
  period: DashboardPeriod;
  total_users: number;
  new_users: number;
  new_users_7d: number;
  active_subscriptions: number;
  banned_users: number;
  credits_total: number;
  paid_transactions: number;
  paying_users: number;
  conversion_pct: number;
  dau: number;
  wau: number;
  mau: number;
  revenue_by_currency: Record<string, RevenueCurrency>;
  revenue_by_gateway: Record<string, number>;
  jobs_by_status: Record<string, number>;
  completed_generations: number;
  pending_jobs: number;
}

export interface Payment {
  tx_id: string;
  user_id: number;
  product: string;
  duration_months: number | null;
  qty: number | null;
  amount: number;
  currency: string;
  gateway: string;
  gateway_tx_id: string | null;
  status: string;
  credits_added: number | null;
  created_at: string;
  paid_at: string | null;
}
export interface PaymentsPage {
  items: Payment[];
  total: number;
  limit: number;
  offset: number;
  has_more: boolean;
}
export interface PaymentGateway {
  gateway: string;
  count: number;
  paid: number;
  success_pct: number;
  revenue_by_currency: Record<string, number>;
  last_at: string | null;
}
export interface PaymentsStats {
  days: number;
  totals: { count: number; paid: number; failed: number; pending: number; refunded: number; refund_pending: number };
  by_status: Record<string, number>;
  by_gateway: PaymentGateway[];
  revenue_by_currency: Record<string, number>;
  avg_check_by_currency: Record<string, number>;
  revenue_by_day: { date: string; amount: number; count: number }[];
  paid_users: number;
}

export interface GatewayField {
  field: string;
  label: string;
  secret: boolean;
  configured: boolean;
  value: string;            // masked tail for secrets; full value for non-secret
  source: "db" | "env" | "none";
}
export interface GatewayStatus {
  id: string;
  label: string;
  fields: GatewayField[];
  ready: boolean;
}
export interface PaymentsQuery {
  status?: string; gateway?: string; user_id?: number;
  since?: string; until?: string; limit?: number; offset?: number;
}

export interface UserRow {
  user_id: number;
  username: string | null;
  sub_tier: string | null;
  is_premium: boolean;
  is_banned: boolean;
  phone: string | null;
  country: string | null;
  credits: number;
  created_at: string | null;
}

export type UserSort = "created_desc" | "created_asc" | "credits_desc" | "credits_asc";

export interface UserFilters {
  q?: string;
  premium?: boolean;
  banned?: boolean;
  country?: string;
  language?: string;
  has_phone?: boolean;
  sort?: UserSort;
  limit?: number;
  offset?: number;
}

export interface UsersPage {
  items: UserRow[];
  total: number;
  limit: number;
  offset: number;
  sort: UserSort;
}

export interface AIAccount {
  id: number;
  name: string;
  kind: string;
  base_url: string;
  api_key: string;
  modality: string;
  tier: number;
  priority: number;
  weight: number;
  enabled: boolean;
  status: string;
  avg_latency_ms?: number;
  last_latency_ms?: number | null;
  success_rate?: number;
  spend_micros?: number;
  spend_usd?: number;
  spend_limit_micros?: number;
  spend_limit_usd?: number;
  over_budget?: boolean;
  cooldown_until: string | null;
  total_requests: number;
  total_errors: number;
  last_error: string | null;
  last_used_at?: string | null;
  created_at?: string | null;
}


export interface AIModelRow {
  key: string;
  title: string;
  upstream_model: string;
  modality: string;
  account_kind: string | null;   // backend pin: omniroute|kie|muapi|apimart|direct… (null = any)
  premium: boolean;
  search?: boolean;   // offer this model in the internet-search (/s) picker
  cost: number;
  cost_micros?: number;   // provider cost / себестоимость per request, micro-USD
  price_in_micros?: number;    // token pricing: micro-USD per 1M input tokens
  price_out_micros?: number;   // token pricing: micro-USD per 1M output tokens
  enabled: boolean;
  sort_order: number;
}

export type EffectKind = "photo" | "video";

export interface EffectAdminRow {
  id: number;
  kind: EffectKind;
  name_ru: string;
  category: string;
  provider: string | null;
  recommended_model: string | null;
  compatible_models: string[];
  prompt_template: string | null;
  prompt_mode: "hidden" | "optional" | "required";
  default_params: Record<string, unknown>;
  max_photos: number;
  preview_url: string | null;
  thumbnail_url: string | null;
  badge: string | null;
  is_ad: boolean;
  author: string | null;
  is_trending: boolean;
  enabled: boolean;
  sort_order: number;
  price: number;
  effective_price?: number;   // override or computed model cost (read-only, server-derived)
  gen_count: number;
}

export type EffectPayload = Omit<EffectAdminRow, "id" | "kind" | "gen_count" | "effective_price">;

// Router dashboard (OmniRoute / LiteLLM / custom) to open or embed from the panel.
export interface RouterPanel { id: string; name: string; url: string; }

// Per-model generation-parameter schema (drives the editor's friendly controls).
export interface ModelSpec {
  key: string;
  title: string;
  default: Record<string, unknown>;
  models?: [string, string][];
  qualities?: string[];
  ratios?: string[];
  durations?: number[];
  resolutions?: string[];
  modes?: [string, string][];
  audio?: boolean;
  fourk?: boolean;
  seed?: boolean;
  prompt_enhance?: boolean;
}

export interface UserCard {
  user_id: number;
  username: string | null;
  language_code: string;
  phone: string | null;
  country: string | null;
  created_at: string | null;
  sub_tier: string | null;
  is_premium: boolean;
  sub_expires: string | null;
  is_banned: boolean;
  credits: number;
  credits_used: number;
  referred_by: number | null;
  referrals_count: number;
  premium_purchase_count: number;
  premium_purchases: { product: string; months: number | null; amount: number; gateway: string; at: string }[];
  balances: { image: number; video: number; music: number };
  transactions: { product: string; amount: number; gateway: string; status: string; created_at: string }[];
  jobs: { service: string; status: string; created_at: string }[];
}

export interface BroadcastRow {
  id: number;
  status: string;
  sent: number;
  failed: number;
  segment: Record<string, unknown>;
  content?: Record<string, unknown> | null;
  scheduled_at?: string | null;
  admin_id?: number;
  author?: string | null;
  created_at: string;
}

export interface PromoRow {
  code: string;
  reward_type: string;
  reward_amount: number;
  max_uses: number;
  used: number;
  is_active: boolean;
  new_user_days: number;
  expires_at: string | null;
}

export interface BannerRow {
  id: number;
  image_url: string;
  title: string | null;
  subtitle: string | null;
  link_url: string | null;
  locale: string | null;   // null = shown to all languages
  sort_order: number;
  enabled: boolean;
  impressions?: number;
  clicks?: number;
  created_at?: string | null;
}

export type BannerPayload = Omit<BannerRow, "id" | "created_at" | "impressions" | "clicks">;

export interface CarouselBehavior {
  animation: "slide" | "fade";
  speed_ms: number;
  autoplay: boolean;
  pause_on_interaction: boolean;
  loop: boolean;
  show_indicators: boolean;
  show_arrows: boolean;
  manual_swipe: boolean;
}

export interface ReferralSettings {
  enabled: boolean;
  reward_credits: number;
  daily_invite_limit: number;
  reward_on_register: boolean;
  require_subscription: boolean;
  invitee_reward_credits: number;
  milestones: Record<string, number>;
  age_fraud_enabled: boolean;
  min_referred_age_hours: number;
  stats: {
    total_referrals: number;
    rewarded: number;
    top_referrers: { user_id: number; count: number }[];
  };
}

export interface ProviderKeyRow {
  name: string;
  label: string;
  configured: boolean;
  masked: string;
  source: "db" | "env" | "none";
}

export interface AuditEntry {
  id: number;
  admin_id: number;
  admin_email: string | null;
  admin_role: string | null;
  action: string;
  target_type: string | null;
  target_id: string | null;
  before: Record<string, unknown> | null;
  after: Record<string, unknown> | null;
  ip: string | null;
  created_at: string;
}
export interface AuditStats {
  days: number;
  total: number;
  today: number;
  last_hour: number;
  distinct_admins: number;
  admins_total: number;
  last_action_at: string | null;
  last_login_at: string | null;
  buckets: { create: number; update: number; delete: number; security: number; other: number };
  by_category: { category: string; count: number }[];
  by_day: { date: string; count: number }[];
  top_admins: { admin_id: number; email: string | null; role: string | null; count: number; last_at: string | null }[];
  top_actions: { action: string; count: number }[];
}
export interface SecurityOverview {
  self: {
    id: number; email: string; role: string; role_rank: number; is_active: boolean;
    has_2fa: boolean; mfa_required: boolean; last_login: string | null;
    created_at: string | null; updated_at: string | null; token_version: number;
  };
  org: {
    admins_total: number; active: number; with_2fa: number; without_2fa: number;
    by_role: Record<string, number>; missing_required_2fa: number;
  };
  policy: {
    ip_allowlist_configured: boolean; ip_allowlist_count: number;
    mfa_required_roles: string[]; enc_secret_configured: boolean;
    jwt_secret_default: boolean; secure_cookies: boolean; password_algo: string;
    cookie: { httponly: boolean; samesite: string; secure: boolean };
    access_ttl_minutes: number; env: string;
  };
  score: number;
  checks: { id: string; label: string; ok: boolean; weight: number; rec: string }[];
  recommendations: { id: string; text: string }[];
  events: {
    id: number; action: string; admin_id: number; admin_email: string | null;
    target_type: string | null; target_id: string | null; ip: string | null; created_at: string;
  }[];
  last_security_event_at: string | null;
}

export interface CrmNote {
  id: number;
  user_id: number;
  admin_id: number;
  text: string;
  created_at: string | null;
}

export interface CrmData {
  notes: CrmNote[];
  tags: string[];
}

export interface ComplaintRow {
  id: number;
  user_id: number;
  content: string;
  resolved: boolean;
  created_at: string | null;
}

export interface RatingRow {
  id: number;
  user_id: number;
  rating: "up" | "down";
  snippet: string | null;
  created_at: string | null;
}

export interface CronJobRow {
  name: string;
  label: string;
  enabled: boolean;
  interval_seconds: number;
  last_run_at: string | null;
  last_status: string | null;
}

export const api = {
  dashboard: (period: DashboardPeriod = "all") =>
    req<Dashboard>(`/dashboard?period=${period}`),

  // --- Scheduler (cron control) ---
  cronList: () => req<{ jobs: CronJobRow[] }>("/cron"),
  cronUpdate: (name: string, body: { enabled?: boolean; interval_seconds?: number }) =>
    req<{ ok: boolean; job: CronJobRow }>(`/cron/${encodeURIComponent(name)}`, {
      method: "POST", body: JSON.stringify(body),
    }),

  // --- Payments ---
  payments: (params: PaymentsQuery = {}) => {
    const q = new URLSearchParams();
    if (params.status) q.set("status", params.status);
    if (params.gateway) q.set("gateway", params.gateway);
    if (params.user_id != null) q.set("user_id", String(params.user_id));
    if (params.since) q.set("since", params.since);
    if (params.until) q.set("until", params.until);
    if (params.limit != null) q.set("limit", String(params.limit));
    if (params.offset != null) q.set("offset", String(params.offset));
    const qs = q.toString();
    return req<PaymentsPage>(`/payments${qs ? "?" + qs : ""}`);
  },
  paymentsStats: (days = 30) => req<PaymentsStats>(`/payments/stats?days=${days}`),
  // Payment-gateway credential config (superadmin to write).
  paymentGateways: () => req<GatewayStatus[]>("/payments/gateways"),
  setPaymentGateways: (fields: Record<string, string>) =>
    req<{ ok: boolean; changed: string[] }>("/payments/gateways", { method: "PUT", body: JSON.stringify({ fields }) }),
  clearPaymentGateway: (field: string) =>
    req<{ ok: boolean; cleared: boolean }>(`/payments/gateways/${encodeURIComponent(field)}`, { method: "DELETE" }),  // FIX: AUDIT-1
  refund: (txId: string) =>
    req<{
      ok: boolean;
      status?: string;            // 'refunded' | 'refund_pending'
      entitlement_revoked?: boolean;
      gateway_refund?: string;
      retryable?: boolean;
    }>(`/payments/${encodeURIComponent(txId)}/refund`, { method: "POST" }),  // FIX: AUDIT12-L3

  // --- Effect presets ---
  effects: (kind: EffectKind) => req<EffectAdminRow[]>(`/effects?kind=${kind}`),
  effectSpecs: (kind: EffectKind) => req<{ models: Record<string, ModelSpec> }>(`/effects/specs/${encodeURIComponent(kind)}`),  // FIX: AUDIT12-L3
  effectCreate: (kind: EffectKind, body: EffectPayload) =>
    req<EffectAdminRow>(`/effects?kind=${kind}`, { method: "POST", body: JSON.stringify(body) }),
  effectUpdate: (kind: EffectKind, id: number, body: EffectPayload) =>
    req<EffectAdminRow>(`/effects/${encodeURIComponent(kind)}/${id}`, { method: "PUT", body: JSON.stringify(body) }),  // FIX: AUDIT12-L3
  effectDelete: (kind: EffectKind, id: number) =>
    req(`/effects/${encodeURIComponent(kind)}/${id}`, { method: "DELETE" }),  // FIX: AUDIT12-L3
  effectPreview: (kind: EffectKind, id: number, file: File) =>
    reqUpload<{ ok: boolean; preview_url: string }>(`/effects/${encodeURIComponent(kind)}/${id}/preview`, file),  // FIX: AUDIT12-L3

  // --- AI routing ---
  aiAccounts: () => req<AIAccount[]>("/ai/accounts"),
  aiCreateAccount: (body: Partial<AIAccount> & { api_key: string }) =>
    req<AIAccount>("/ai/accounts", { method: "POST", body: JSON.stringify(body) }),
  aiUpdateAccount: (id: number, body: Partial<AIAccount>) =>
    req<AIAccount>(`/ai/accounts/${id}`, { method: "PUT", body: JSON.stringify(body) }),
  aiDeleteAccount: (id: number) =>
    req(`/ai/accounts/${id}`, { method: "DELETE" }),
  aiResetAccount: (id: number) =>
    req<AIAccount>(`/ai/accounts/${id}/reset`, { method: "POST" }),
  aiResetSpend: (id: number) =>
    req<AIAccount>(`/ai/accounts/${id}/reset-spend`, { method: "POST" }),
  aiTestAccount: (id: number) =>
    req<{ ok: boolean; status_code: number; latency_ms: number; detail: string }>(
      `/ai/accounts/${id}/test`, { method: "POST" }),
  aiExportConfig: () => req<{ version: number; accounts: unknown[]; models: unknown[] }>("/ai/export"),
  aiImportConfig: (body: { accounts: unknown[]; models: unknown[] }) =>
    req<{ ok: boolean; models: number; accounts: number }>("/ai/import", {
      method: "POST", body: JSON.stringify(body),
    }),
  aiModels: () => req<AIModelRow[]>("/ai/models"),
  aiUpsertModel: (key: string, body: Omit<AIModelRow, "key">) =>
    req(`/ai/models/${encodeURIComponent(key)}`, { method: "PUT", body: JSON.stringify(body) }),  // FIX: AUDIT-1
  aiDeleteModel: (key: string) =>
    req(`/ai/models/${encodeURIComponent(key)}`, { method: "DELETE" }),  // FIX: AUDIT12-L3
  aiHealth: () => req<Record<string, unknown>>("/ai/health"),
  aiStrategy: () => req<{ strategy: string; options: string[] }>("/ai/strategy"),
  aiSetStrategy: (strategy: string) =>
    req<{ ok: boolean; strategy: string }>("/ai/strategy", { method: "PUT", body: JSON.stringify({ strategy }) }),
  routerPanels: () => req<{ panels: RouterPanel[] }>("/ai/router-panels"),
  setRouterPanels: (panels: RouterPanel[]) =>
    req<{ panels: RouterPanel[] }>("/ai/router-panels", { method: "PUT", body: JSON.stringify({ panels }) }),

  // --- Feature flags ---
  flags: () => req<{ key: string; enabled: boolean; label: string; default: boolean }[]>("/flags"),
  setFlag: (key: string, enabled: boolean) =>
    req(`/flags/${encodeURIComponent(key)}`, { method: "PUT", body: JSON.stringify({ enabled }) }),  // FIX: AUDIT-1
  gates: () => req<{ channel: string; is_active: boolean }[]>("/gates"),
  upsertGate: (channel: string, is_active: boolean) =>
    req("/gates", { method: "PUT", body: JSON.stringify({ channel, is_active }) }),
  deleteGate: (channel: string) =>
    req<{ ok: boolean; deleted: boolean }>(`/gates/${encodeURIComponent(channel)}`, { method: "DELETE" }),
  checkGate: (channel: string) =>
    req<{ ok: boolean; bot_is_admin: boolean; members: number | null; title: string; detail: string }>(`/gates/${encodeURIComponent(channel)}/check`, { method: "POST" }),
  moderationWords: () => req<{ words: ModerationRule[] }>("/moderation-words"),
  setModerationWords: (words: ModerationRule[]) =>
    req<{ words: ModerationRule[] }>("/moderation-words", { method: "PUT", body: JSON.stringify({ words }) }),
  searchUsers: (f: UserFilters = {}) => {
    const p = new URLSearchParams();
    if (f.q) p.set("q", f.q);
    if (f.premium !== undefined) p.set("premium", String(f.premium));
    if (f.banned !== undefined) p.set("banned", String(f.banned));
    if (f.country) p.set("country", f.country);
    if (f.language) p.set("language", f.language);
    if (f.has_phone !== undefined) p.set("has_phone", String(f.has_phone));
    if (f.sort) p.set("sort", f.sort);
    if (f.limit !== undefined) p.set("limit", String(f.limit));
    if (f.offset !== undefined) p.set("offset", String(f.offset));
    const qs = p.toString();
    return req<UsersPage>(`/users${qs ? "?" + qs : ""}`);
  },
  userCountries: () => req<{ code: string; count: number }[]>("/users/countries"),
  userLanguages: () => req<{ code: string; count: number }[]>("/users/languages"),
  userCard: (id: number) => req<UserCard>(`/users/${id}`),
  ban: (id: number, banned: boolean) =>
    req(`/users/${id}/ban`, { method: "POST", body: JSON.stringify({ banned }) }),
  grantPremium: (id: number, months: number, tier = "premium") =>
    req(`/users/${id}/premium`, { method: "POST", body: JSON.stringify({ months, tier }) }),
  revokePremium: (id: number) =>
    req(`/users/${id}/premium/revoke`, { method: "POST" }),
  grantCredits: (id: number, pack: string, amount: number) =>
    req(`/users/${id}/credits`, { method: "POST", body: JSON.stringify({ pack, amount }) }),
  resetQuota: (id: number) => req(`/users/${id}/reset-quota`, { method: "POST" }),
  clearContext: (id: number) => req(`/users/${id}/clear-context`, { method: "POST" }),

  // --- Pricing / business config ---
  pricing: () => req<Record<string, unknown>>("/pricing"),
  setPricing: (key: string, value: unknown) =>
    req(`/pricing/${encodeURIComponent(key)}`, { method: "PUT", body: JSON.stringify({ value }) }),  // FIX: AUDIT-1
  businessConfig: () =>
    req<{ config: Record<string, unknown>; defaults: Record<string, unknown> }>("/business-config"),
  setBusinessConfig: (patch: Record<string, unknown>) =>
    req<{ ok: boolean; config: Record<string, unknown> }>("/business-config", {
      method: "PUT", body: JSON.stringify({ patch }),
    }),
  buttonStats: () =>
    req<{ clicks: Record<string, number> }>("/business-config/button-stats"),

  // --- Providers kill-switch ---
  providers: () => req<ProviderStatus[]>("/providers"),
  toggleProvider: (key: string) => req(`/providers/${encodeURIComponent(key)}/toggle`, { method: "POST" }),  // FIX: AUDIT-2

  // --- Native provider API keys ---
  providerKeys: () => req<ProviderKeyRow[]>("/provider-keys"),
  setProviderKeys: (keys: Record<string, string>) =>
    req<{ ok: boolean; changed: string[] }>("/provider-keys", { method: "PUT", body: JSON.stringify({ keys }) }),
  clearProviderKey: (name: string) =>
    req<{ ok: boolean; cleared: boolean }>(`/provider-keys/${encodeURIComponent(name)}`, { method: "DELETE" }),  // FIX: AUDIT-1
  testProviderKey: (name: string) =>
    req<{ ok: boolean; supported: boolean; status_code: number; latency_ms: number; detail: string }>(`/provider-keys/${encodeURIComponent(name)}/test`, { method: "POST" }),  // FIX: AUDIT12-L3
  openaiBaseUrl: () => req<{ value: string; source: "db" | "env" }>("/provider-base-url"),
  setOpenaiBaseUrl: (url: string) =>
    req<{ ok: boolean; value: string }>("/provider-base-url", { method: "PUT", body: JSON.stringify({ url }) }),
  // FIX: AUDIT13-M2 - Suno base URL + model, editable from the panel.
  sunoConfig: () =>
    req<{ base_url: { value: string; source: "db" | "env" }; model: { value: string; source: "db" | "env" } }>("/suno-config"),
  setSunoConfig: (base_url: string, model: string) =>
    req<{ ok: boolean; base_url: string; model: string }>("/suno-config", { method: "PUT", body: JSON.stringify({ base_url, model }) }),

  // --- Broadcasts ---
  broadcasts: () => req<BroadcastRow[]>("/broadcasts"),
  createBroadcast: (body: {
    segment: Record<string, unknown>;
    text: string;
    photo_url?: string | null;
    button_text?: string | null;
    button_url?: string | null;
    scheduled_at?: string | null;
    title?: string | null;
    comment?: string | null;
    description?: string | null;
  }) =>
    req<{ id: number; status: string }>("/broadcasts", { method: "POST", body: JSON.stringify(body) }),
  cancelBroadcast: (id: number) =>
    req<{ id: number; status: string }>(`/broadcasts/${id}/cancel`, { method: "POST" }),
  estimateBroadcast: (segment: Record<string, unknown>) =>
    req<{ count: number }>("/broadcasts/estimate", { method: "POST", body: JSON.stringify({ segment }) }),

  // --- Promo codes ---
  promos: () => req<PromoRow[]>("/promos"),
  createPromo: (body: { code: string; reward_type: string; reward_amount: number; max_uses: number; expires_at: string | null; new_user_days?: number }) =>
    req<{ ok: boolean; code: string }>("/promos", { method: "POST", body: JSON.stringify(body) }),
  togglePromo: (code: string) =>
    req<{ code: string; is_active: boolean }>(`/promos/${encodeURIComponent(code)}/toggle`, { method: "POST" }),
  setPromoExpiry: (code: string, expires_at: string | null) =>
    req<{ code: string; expires_at: string | null }>(`/promos/${encodeURIComponent(code)}/expiry`, { method: "PUT", body: JSON.stringify({ expires_at }) }),
  deletePromo: (code: string) =>
    req(`/promos/${encodeURIComponent(code)}`, { method: "DELETE" }),
  promoRedemptions: (code: string) =>
    req<{ user_id: number; redeemed_at: string | null }[]>(`/promos/${encodeURIComponent(code)}/redemptions`),
  promoBotUsername: () => req<{ username: string | null }>("/promos/bot-username"),

  // --- Referral program ---
  referralSettings: () => req<ReferralSettings>("/referrals/settings"),
  setReferralSettings: (body: Partial<Pick<ReferralSettings, "enabled" | "reward_credits" | "daily_invite_limit" | "reward_on_register" | "require_subscription" | "invitee_reward_credits" | "milestones" | "age_fraud_enabled" | "min_referred_age_hours">>) =>
    req<ReferralSettings>("/referrals/settings", { method: "PUT", body: JSON.stringify(body) }),

  // --- Mini App carousel banners ---
  banners: () => req<{ interval_ms: number; behavior: CarouselBehavior; banners: BannerRow[] }>("/banners"),
  bannerCreate: (body: BannerPayload) =>
    req<BannerRow>("/banners", { method: "POST", body: JSON.stringify(body) }),
  bannerUpdate: (id: number, body: BannerPayload) =>
    req<BannerRow>(`/banners/${id}`, { method: "PUT", body: JSON.stringify(body) }),
  bannerDelete: (id: number) =>
    req(`/banners/${id}`, { method: "DELETE" }),
  bannerImage: (id: number, file: File) =>
    reqUpload<{ ok: boolean; image_url: string }>(`/banners/${id}/image`, file),
  setCarouselInterval: (interval_ms: number) =>
    req<{ interval_ms: number }>("/banners/settings/interval", {
      method: "PUT", body: JSON.stringify({ interval_ms }),
    }),
  setCarouselSettings: (interval_ms: number, behavior: CarouselBehavior) =>
    req<{ interval_ms: number; behavior: CarouselBehavior }>("/banners/settings", {
      method: "PUT", body: JSON.stringify({ interval_ms, behavior }),
    }),

  // --- Feedback (ratings 👍/👎 + complaints) ---
  feedbackStats: () => req<{ up: number; down: number; complaints_open: number }>("/feedback/stats"),
  feedbackComplaints: (status: "open" | "resolved" | "all" = "open") =>
    req<ComplaintRow[]>(`/feedback/complaints?status=${status}`),
  feedbackRatings: (rating: "up" | "down" = "down", limit = 50) =>
    req<RatingRow[]>(`/feedback/ratings?rating=${rating}&limit=${limit}`),
  resolveComplaint: (id: number) =>
    req<{ ok: boolean }>(`/feedback/complaints/${id}/resolve`, { method: "POST" }),

  // --- Audit log ---
  audit: (f: {
    action?: string; admin_id?: number; target_type?: string; target_id?: string;
    q?: string; since?: string; until?: string; limit?: number; offset?: number;
  } = {}) => {
    const p = new URLSearchParams();
    if (f.action) p.set("action", f.action);
    if (f.admin_id !== undefined) p.set("admin_id", String(f.admin_id));
    if (f.target_type) p.set("target_type", f.target_type);
    if (f.target_id) p.set("target_id", f.target_id);
    if (f.q) p.set("q", f.q);
    if (f.since) p.set("since", f.since);
    if (f.until) p.set("until", f.until);
    if (f.limit !== undefined) p.set("limit", String(f.limit));
    if (f.offset !== undefined) p.set("offset", String(f.offset));
    const qs = p.toString();
    return req<AuditEntry[]>(`/audit${qs ? "?" + qs : ""}`);
  },
  auditStats: (days = 30) => req<AuditStats>(`/audit/stats?days=${days}`),
  // Full server-side CSV export of the FILTERED audit set (every matching row up to a
  // safety cap — not just the loaded page). Filters mirror `audit()`.
  exportAuditCsv: (f: {
    action?: string; admin_id?: number; target_type?: string; target_id?: string;
    q?: string; since?: string; until?: string;
  } = {}) => {
    const p = new URLSearchParams();
    if (f.action) p.set("action", f.action);
    if (f.admin_id !== undefined) p.set("admin_id", String(f.admin_id));
    if (f.target_type) p.set("target_type", f.target_type);
    if (f.target_id) p.set("target_id", f.target_id);
    if (f.q) p.set("q", f.q);
    if (f.since) p.set("since", f.since);
    if (f.until) p.set("until", f.until);
    const qs = p.toString();
    return downloadCsv(`/audit/export.csv${qs ? "?" + qs : ""}`, "audit-export.csv");
  },

  // --- Two-factor auth (self-service) ---
  twofaStatus: () => req<{ enabled: boolean; required: boolean }>("/auth/2fa/status"),
  twofaSetup: () => req<{ secret: string; uri: string }>("/auth/2fa/setup", { method: "POST" }),
  twofaEnable: (secret: string, code: string) =>
    req<{ ok: boolean; enabled: boolean; relogin_required?: boolean }>("/auth/2fa/enable", { method: "POST", body: JSON.stringify({ secret, code }) }),
  twofaDisable: (code: string) =>
    req<{ ok: boolean; enabled: boolean }>("/auth/2fa/disable", { method: "POST", body: JSON.stringify({ code }) }),
  changePassword: (current_password: string, new_password: string) =>
    req<{ ok: boolean; relogin_required: boolean }>("/auth/password", { method: "POST", body: JSON.stringify({ current_password, new_password }) }),
  securityOverview: () => req<SecurityOverview>("/auth/security"),

  // --- CSV exports (file downloads, not JSON) ---
  exportUsersCsv: () => downloadCsv("/exports/users.csv", "users.csv"),
  exportPaymentsCsv: () => downloadCsv("/exports/payments.csv", "payments.csv"),

  // --- CRM: notes & tags on a user ---
  crmGet: (userId: number) => req<CrmData>(`/crm/users/${userId}`),
  crmAddNote: (userId: number, text: string) =>
    req<CrmNote>(`/crm/users/${userId}/notes`, { method: "POST", body: JSON.stringify({ text }) }),
  crmDeleteNote: (noteId: number) =>
    req<{ ok: boolean }>(`/crm/notes/${noteId}`, { method: "DELETE" }),
  crmAddTag: (userId: number, tag: string) =>
    req<{ ok: boolean; tag: string }>(`/crm/users/${userId}/tags`, { method: "POST", body: JSON.stringify({ tag }) }),
  crmDeleteTag: (userId: number, tag: string) =>
    req<{ ok: boolean }>(`/crm/users/${userId}/tags/${encodeURIComponent(tag)}`, { method: "DELETE" }),

  // --- System Health + queue (ТЗ §8) ---
  queueHealth: () => req<QueueHealth>("/health-ops/queue"),
  systemHealth: () => req<SystemHealth>("/health-ops/system"),
  retryJob: (id: string) =>
    req<{ ok: boolean; job_id: string; status: string; enqueued: boolean }>(
      `/health-ops/jobs/${encodeURIComponent(id)}/retry`, { method: "POST" }),  // FIX: AUDIT12-L3
  cancelJob: (id: string) =>
    req<{ ok: boolean; job_id: string; status: string; refunded: boolean }>(
      `/health-ops/jobs/${encodeURIComponent(id)}/cancel`, { method: "POST" }),  // FIX: AUDIT12-L3
};

export interface StuckJob {
  job_id: string;
  service: string;
  user_id: number;
  status: string;
  created_at: string;
}

export interface QueueHealth {
  counts: Record<string, number>;
  stuck_count: number;
  stuck_threshold_seconds: number;
  oldest_pending_age_seconds: number;
  stuck_jobs: StuckJob[];
}

export interface SystemHealth {
  db_ok: boolean;
  redis_ok: boolean;
  total_users: number;
  pending_jobs: number;
  avg_job_seconds: number;
  error_rate_pct: number;
  completed_24h: number;
  failed_24h: number;
  uptime_seconds: number;
  version: string;
}

export interface ProviderStatus {
  key: string;
  available: boolean;
  disabled: boolean;
  modality?: string;   // video | image | music
}

// Moderation stop-word rule: how `value` is matched against a message.
export interface ModerationRule { value: string; type: "substring" | "exact" | "regex"; }

// --- Panel admins management (ТЗ §8, superadmin-only) ---
export interface AdminAccount {
  id: number;
  email: string;
  role: string;
  is_active: boolean;
  has_2fa: boolean;
  last_login: string | null;
  created_at: string | null;
  updated_at: string | null;
  token_version: number;
}

export const adminsApi = {
  admins: () => req<AdminAccount[]>("/admins"),
  createAdmin: (email: string, password: string, role: string) =>
    req<AdminAccount>("/admins", { method: "POST", body: JSON.stringify({ email, password, role }) }),
  setAdminRole: (id: number, role: string) =>
    req<AdminAccount>(`/admins/${id}/role`, { method: "PUT", body: JSON.stringify({ role }) }),
  disableAdmin: (id: number) =>
    req<AdminAccount>(`/admins/${id}/disable`, { method: "POST" }),
  enableAdmin: (id: number) =>
    req<AdminAccount>(`/admins/${id}/enable`, { method: "POST" }),
  resetAdmin2fa: (id: number) =>
    req<AdminAccount>(`/admins/${id}/reset-2fa`, { method: "POST" }),
  adminSessions: (id: number) =>
    req<{ sessions: AdminSession[] }>(`/admins/${id}/sessions`),
  logoutAllAdmin: (id: number) =>
    req<AdminAccount>(`/admins/${id}/logout-all`, { method: "POST" }),
};

export interface AdminSession { device: string; ip: string; last_at: string | null; count: number; }

export interface BotInstanceRow {
  id: number;
  title: string;
  token_masked: string;
  tg_bot_id: number | null;
  username: string | null;
  active: boolean;
  is_default: boolean;
  created_at: string | null;
  updated_at: string | null;
}

export interface BotStat {
  users: number;
  requests: number;
  last_user_at: string | null;
  last_request_at: string | null;
}
export interface BotStats {
  stats: Record<string, BotStat>;   // key = bot id, or "legacy" for NULL bot_id
  totals: { users: number; requests: number };
}

export const botsApi = {
  list: () => req<BotInstanceRow[]>("/bots"),
  stats: () => req<BotStats>("/bots/stats"),
  create: (title: string, token: string, is_default: boolean) =>
    req<BotInstanceRow>("/bots", { method: "POST", body: JSON.stringify({ title, token, is_default }) }),
  update: (id: number, body: Partial<{ title: string; token: string; active: boolean; is_default: boolean }>) =>
    req<BotInstanceRow>(`/bots/${id}`, { method: "PUT", body: JSON.stringify(body) }),
  remove: (id: number) =>
    req<{ ok: boolean }>(`/bots/${id}`, { method: "DELETE" }),
  checkToken: (token: string) =>
    req<BotTokenCheck>("/bots/check-token", { method: "POST", body: JSON.stringify({ token }) }),
  check: (id: number) =>
    req<BotTokenCheck>(`/bots/${id}/check`, { method: "POST" }),
};

export interface BotTokenCheck {
  ok: boolean;
  tg_bot_id: number | null;
  username: string | null;
  name: string | null;
  status_code: number;
  latency_ms: number;
  detail: string;
}

// CSV endpoints return a file, not JSON — fetch with the same credentials as
// `req`/`reqUpload` (httpOnly cookie + optional Bearer fallback), then trigger a
// browser download via a Blob + a temporary <a>.
async function downloadCsv(path: string, filename: string): Promise<void> {  // FIX: AUDIT-14 - uses longer timeout for downloads
  // FIX: AUDIT-14 - downloads can take >15s for large exports; use 120s timeout
  const ctrl = new AbortController();
  const timer = setTimeout(() => ctrl.abort(), 120_000);
  try {
    // FIX: AUDIT-FINAL-10 - prefix with `${ADMIN}` so the request hits
    // /api/admin/<path> (Caddy → api:8000). Without this, callers passing
    // "/exports/users.csv" hit "/exports/users.csv" → 404 (Caddy has no such
    // route, falls through to miniapp SPA index.html).
    const res = await fetch(`${ADMIN}${path}`, { credentials: "include", signal: ctrl.signal });
    if (res.status === 401) {
      // FIX: AUDIT12-L4 - universal 401 → logout
      logout();
      window.dispatchEvent(new CustomEvent("admin:unauth"));  // FIX: FINAL-1 - App.tsx listens, swaps to Login in-place (was: redirect to /login which Caddy serves as miniapp)
      throw new Error("session expired");
    }
    if (!res.ok) throw new Error(`API ${res.status}`);
    const blob = await res.blob();
    const url = URL.createObjectURL(blob);
    const a = document.createElement("a");
    a.href = url;
    a.download = filename;
    document.body.appendChild(a);
    a.click();
    a.remove();
    URL.revokeObjectURL(url);
  } finally { clearTimeout(timer); }
}

// ---- Maintenance Center (§8) types ----
export interface MaintOverview {
  engine: string;
  db: {
    engine: string; size_bytes: number; logical_bytes?: number; page_size?: number;
    page_count?: number; freelist_pages?: number; free_bytes?: number;
    fragmentation_pct?: number; path?: string;
  };
  disk: { total_bytes: number; used_bytes: number; free_bytes: number; percent: number; path: string };
  redis: {
    ok: boolean; used_memory_bytes?: number; keys?: number; hits?: number; misses?: number;
    hit_rate_pct?: number | null; uptime_seconds?: number; version?: string;
  };
  counts: {
    users: number; jobs_total: number; jobs_by_status: Record<string, number>;
    transactions: number; audit_entries: number;
  };
  log: { path: string; exists: boolean; size_bytes: number };
  storage_backend: string;
  backup: { supported: boolean; last_backup_at: string | null; note: string };
  uptime_seconds: number;
  generated_at: string;
}
export interface MaintTable { name: string; rows: number; indexes: number }
export interface MaintDatabase {
  engine: string; tables: MaintTable[]; total_rows: number;
  page?: { page_count: number; page_size: number; freelist_pages: number; fragmentation_pct: number; free_bytes: number; size_bytes: number };
}
export interface MaintDbOpResult {
  ok: boolean; op: string; result: string; duration_ms: number;
  size_before: number; size_after: number; reclaimed_bytes: number;
}
export interface MaintStorageCategory { name: string; bytes: number; files: number }
export interface MaintStorage {
  backend: string; path?: string; bucket?: string; note?: string; exists?: boolean;
  categories: MaintStorageCategory[]; total_bytes?: number; total_files?: number;
}
export interface MaintCache {
  redis: MaintOverview["redis"]; app_cache_keys: number; prefixes: string[];
}
export interface MaintQueue {
  counts: Record<string, number>; stuck_count: number; stuck_threshold_seconds: number;
  oldest_pending_age_seconds: number;
  stuck_jobs: { job_id: string; service: string; user_id: number; status: string; created_at: string }[];
}
export interface MaintAuditRow {
  id: number; admin_id: number; action: string; target_type: string | null;
  target_id: string | null; ip: string | null; created_at: string;
}

// Maintenance (§8): superadmin DB backup + Maintenance Center telemetry/ops.
export const maintenanceApi = {
  overview: () => req<MaintOverview>("/maintenance/overview"),
  database: () => req<MaintDatabase>("/maintenance/database"),
  dbOp: (op: string) => req<MaintDbOpResult>(`/maintenance/database/${encodeURIComponent(op)}`, { method: "POST" }),  // FIX: AUDIT-1
  storage: () => req<MaintStorage>("/maintenance/storage"),
  cache: () => req<MaintCache>("/maintenance/cache"),
  cacheFlush: () => req<{ ok: boolean; deleted: number }>("/maintenance/cache/flush", { method: "POST" }),
  queue: () => req<MaintQueue>("/health-ops/queue"),
  jobRetry: (id: string) => req<{ ok: boolean; status: string; enqueued: boolean }>(`/health-ops/jobs/${encodeURIComponent(id)}/retry`, { method: "POST" }),  // FIX: AUDIT12-L3
  jobCancel: (id: string) => req<{ ok: boolean; status: string; refunded: boolean }>(`/health-ops/jobs/${encodeURIComponent(id)}/cancel`, { method: "POST" }),  // FIX: AUDIT12-L3
  audit: (params: { action?: string; since?: string; limit?: number } = {}) => {
    const qs = new URLSearchParams();
    if (params.action) qs.set("action", params.action);
    if (params.since) qs.set("since", params.since);
    qs.set("limit", String(params.limit ?? 100));
    return req<MaintAuditRow[]>(`/audit?${qs.toString()}`);
  },
  // Streams a DB snapshot. 501 on Postgres deployments (use pg_dump server-side).
  downloadBackup: async (): Promise<void> => {
    const res = await adminFetch("/maintenance/backup", {});
    if (res.status === 401) {
      // FIX: AUDIT12-L4 - universal 401 → logout
      logout();
      window.dispatchEvent(new CustomEvent("admin:unauth"));  // FIX: FINAL-1 - App.tsx listens, swaps to Login in-place (was: redirect to /login which Caddy serves as miniapp)
      throw new Error("session expired");
    }
    if (res.status === 501) throw new Error("postgres_use_pgdump");
    if (res.status === 403) throw new Error("forbidden");
    if (!res.ok) throw new Error(`API ${res.status}`);
    const blob = await res.blob();
    const url = URL.createObjectURL(blob);
    const a = document.createElement("a");
    a.href = url;
    a.download = "backup.sqlite";
    document.body.appendChild(a);
    a.click();
    a.remove();
    URL.revokeObjectURL(url);
  },
  logs: (limit = 200) =>
    req<{ path: string; lines: string[]; count: number }>(`/maintenance/logs?limit=${limit}`),
};
