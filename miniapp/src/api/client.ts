import WebApp from "@twa-dev/sdk";
import { getLang } from "../i18n";

const BASE = import.meta.env.VITE_API_BASE ?? "";

/** Resolve a server media path against the API origin. Banner/effect images come
 *  back as root-relative paths (e.g. "/media/banners/x.png") which, rendered raw,
 *  would resolve against the Mini App's own origin — broken when the app is served
 *  cross-origin from the API (the real Telegram deploy). Prefix those with BASE;
 *  pass absolute (http/https/data/blob) URLs and empty values through untouched. */
export function mediaUrl(path: string | null | undefined): string {
  if (!path) return "";
  if (/^(https?:|data:|blob:)/i.test(path)) return path;
  return path.startsWith("/") ? `${BASE}${path}` : path;
}

function headers(): HeadersInit {
  return { "X-Init-Data": WebApp.initData ?? "" };
}

// FIX: FRONTEND - fetchWithTimeout: a hung API call (provider down, network black-hole)
// used to leave the Mini App spinner running forever. 15s is well above any legitimate
// request (image gen polls separately), so a timeout = real failure -> show the error.
const FETCH_TIMEOUT_MS = 15_000;

function fetchWithTimeout(input: string, init: RequestInit = {}): Promise<Response> {
  const ctrl = new AbortController();
  const timer = setTimeout(() => ctrl.abort(), FETCH_TIMEOUT_MS);
  return fetch(input, { ...init, signal: ctrl.signal }).finally(() => clearTimeout(timer));
}

// FIX: AUDIT-35 / AUDIT-U7 - map HTTP status → an i18n error KEY (translated by the
// caller). Single source of truth instead of the same object inlined in three places.
// 413 (upload/dimensions too large) now surfaces the accurate "too big" message and 503
// (upload failed / service unavailable) the server message, instead of a generic
// "something went wrong". Unmapped statuses fall back to err_generic.
const ERROR_KEY: Record<number, string> = {
  401: "err_auth", 402: "err_limit", 413: "err_too_big",
  429: "err_rate", 500: "err_server", 503: "err_server",
};
export function errKeyForStatus(status: number): string {
  return ERROR_KEY[status] || "err_generic";
}

async function get<T>(path: string): Promise<T> {
  const res = await fetchWithTimeout(`${BASE}/api${path}`, { headers: headers() });
  if (!res.ok) throw new Error(errKeyForStatus(res.status));
  return res.json() as Promise<T>;
}

async function postJson<T>(path: string, body: unknown): Promise<T> {
  const res = await fetchWithTimeout(`${BASE}/api${path}`, {
    method: "POST",
    headers: { ...headers(), "Content-Type": "application/json" },
    body: JSON.stringify(body),
  });
  if (!res.ok) throw new Error(errKeyForStatus(res.status));
  return res.json() as Promise<T>;
}

// FIX: AUDIT-U3 - a per-submit-intent idempotency token. The Create flow generates one
// synchronously per generation and sends it here so the backend (miniapp.effect_generate /
// free_model_generate) can dedup twin submits (double-tap / retry / replay) within its
// short TTL window instead of charging + queueing the same job twice.
export function newIdempotencyKey(): string {
  try {
    if (typeof crypto !== "undefined" && "randomUUID" in crypto) return crypto.randomUUID();
  } catch { /* fall through */ }
  return `${Date.now()}-${Math.random().toString(36).slice(2)}`;
}

async function uploadEffect(
  path: string,
  fields: Record<string, string>,
  photos: File[],
  signal?: AbortSignal,  // FIX: AUDIT-3 - accept caller signal
  idempotencyKey?: string,  // FIX: AUDIT-U3 - per-submit-intent dedup token
): Promise<{ job_id: string; cost: number }> {
  const form = new FormData();
  for (const [k, v] of Object.entries(fields)) form.append(k, v);
  if (idempotencyKey) form.append("idempotency_key", idempotencyKey);
  for (const p of photos) form.append("photos", p);
  // FIX: FRONTEND - uploads can legitimately take longer (30 MB photo), so allow 60s.
  const ctrl = new AbortController();
  const timer = setTimeout(() => ctrl.abort(), 60_000);
  // FIX: AUDIT-3 - also abort if caller signal fires
  if (signal) {
    if (signal.aborted) ctrl.abort();
    else signal.addEventListener("abort", () => ctrl.abort());
  }
  try {
    const res = await fetch(`${BASE}/api${path}`, {
      method: "POST", headers: headers(), body: form, signal: ctrl.signal,
    });
    if (res.status === 402) throw new Error("LIMIT");  // callers map "LIMIT" → err_limit
    if (!res.ok) throw new Error(errKeyForStatus(res.status));  // FIX: AUDIT-35 / AUDIT-U7
    return res.json();
  } finally {
    clearTimeout(timer);
  }
}

export type EffectKind = "photo" | "video";

export interface EffectSummary {
  id: number;
  kind: EffectKind;
  name: string;
  author: string | null;
  category: string;
  badge: string | null;
  is_ad: boolean;
  preview_url: string | null;
  recommended_model: string | null;
  price: number;
}

export interface ModelCard {
  key: string;
  title: string;
  default: Record<string, string | number | boolean>;
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

export interface EffectDetail {
  id: number;
  kind: EffectKind;
  name: string;
  author: string | null;
  category: string;
  preview_url: string | null;
  max_photos: number;
  prompt_mode?: "hidden" | "optional" | "required";
  recommended_model: string | null;
  default_params: Record<string, string | number | boolean>;
  models: ModelCard[];
  price: number;
}

// Free model choice (§ variant 3): pick a VIDEO_SPECS / PHOTO_SPECS model directly.
export interface FreeModel {
  key: string;
  kind: EffectKind;
  title: string;
  description: string;
  max_photos: number;
  price: number;
  default_params: Record<string, string | number | boolean>;
  card: ModelCard;
}

export interface Profile {
  user_id: number;
  sub_tier: string | null;
  is_premium: boolean;
  credits: number;
  // FIX: AUDIT12-F8 - language_code from the user's bot settings (/language).
  // Mini App syncs its UI language to this on every profile load.
  language_code?: string;
  mini_app_quota: { used: number; limit: number };
  balances: { image: number; video: number; music: number };
  sections?: { photo: boolean; video: boolean };
}

export interface Banner {
  id: number;
  image_url: string;
  title: string | null;
  subtitle: string | null;
  link_url: string | null;
}

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

export interface CarouselData {
  interval_ms: number;
  behavior: CarouselBehavior;
  slides: Banner[];
}

export interface PhotoEffect {
  id: number;
  name: string;
  category: string;
  thumbnail: string | null;
  badge: string | null;
  is_ad: boolean;
}

export interface VideoEffect {
  id: number;
  name: string;
  category: string;
  provider: string;
  thumbnail: string | null;
}

export interface JobStatus {
  status: "pending" | "processing" | "complete" | "failed";
  result_url: string | null;
  error: string | null;
}

export interface HistoryItem {
  id: string;
  kind: "photo" | "video";
  preset_id: number | null;
  status: "pending" | "processing" | "complete" | "failed";
  result_url: string | null;
  created_at: string;
}

export interface BonusStatus {
  can_claim: boolean;
  streak: number;
  next_amount: number;
}

export interface BonusClaim {
  claimed: boolean;
  amount: number;
  streak: number;
  already_today: boolean;
  credits: number;
}

export interface ReferralInfo {
  link: string;
  invited: number;
  earned: number;
}

export interface StoreOffer {
  qty: number;
  stars: number;
}
export interface PremiumOffer {
  months: number;
  stars: number;
}
export interface StoreOffers {
  credits: StoreOffer[];
  packs: Record<string, StoreOffer[]>;
  premium: PremiumOffer[];
}

export interface PromoResult {
  ok: boolean;
  status: "ok" | "invalid" | "already";
  amount: number;
  reward_type: string;
  credits: number;
}

export const api = {
  profile: () => get<Profile>("/profile"),
  // FIX: AUDIT-M15 - use the live language (getLang) not the frozen module-load
  // snapshot (LANG), so banners follow the language synced from /profile.
  banners: () => get<CarouselData>(`/banners?locale=${encodeURIComponent(getLang())}`),
  // Fire-and-forget carousel engagement tracking (errors are swallowed by callers).
  bannerImpression: (id: number) => postJson<{ ok: boolean }>(`/banners/${id}/impression`, {}),
  bannerClick: (id: number) => postJson<{ ok: boolean }>(`/banners/${id}/click`, {}),
  photoEffects: (category = "all") => get<PhotoEffect[]>(`/photo-effects?category=${encodeURIComponent(category)}`),  // FIX: AUDIT13-L23
  videoEffects: (category = "all") => get<VideoEffect[]>(`/video-effects?category=${encodeURIComponent(category)}`),  // FIX: AUDIT13-L23

  photoRatios: () => get<string[]>("/photo-ratios"),

  // Higgsfield-style preset catalog
  listEffects: (kind: EffectKind, category = "all", trending = false) =>
    get<EffectSummary[]>(`/effects?kind=${encodeURIComponent(kind)}&category=${encodeURIComponent(category)}&trending=${trending}`),  // FIX: AUDIT13-L23
  effectDetail: (kind: EffectKind, id: number) => get<EffectDetail>(`/effects/${encodeURIComponent(kind)}/${id}`),  // FIX: AUDIT12-L3
  effectCost: (kind: EffectKind, id: number, model: string, params: Record<string, unknown>) =>
    postJson<{ cost: number; currency: string }>(`/effects/${encodeURIComponent(kind)}/${id}/cost`, { model, params }),  // FIX: AUDIT12-L3
  effectGenerate: (
    kind: EffectKind,
    id: number,
    model: string,
    params: Record<string, unknown>,
    prompt: string,
    photos: File[],
    signal?: AbortSignal,  // FIX: AUDIT13-L21 - forward caller abort into the upload
    idempotencyKey?: string,  // FIX: AUDIT-U3
  ) =>
    uploadEffect(`/effects/${encodeURIComponent(kind)}/${id}/generate`, { model, params: JSON.stringify(params), prompt }, photos, signal, idempotencyKey),  // FIX: AUDIT12-L3

  // Free model choice (§ variant 3): browse/price/generate a model directly.
  freeModels: (kind: EffectKind) => get<FreeModel[]>(`/models/${encodeURIComponent(kind)}`),
  freeModelCost: (kind: EffectKind, model: string, params: Record<string, unknown>) =>
    postJson<{ cost: number; currency: string }>(`/models/${encodeURIComponent(kind)}/${encodeURIComponent(model)}/cost`, { params }),
  freeModelGenerate: (kind: EffectKind, model: string, params: Record<string, unknown>, prompt: string, photos: File[], signal?: AbortSignal, idempotencyKey?: string) =>  // FIX: AUDIT13-L21, AUDIT-U3
    uploadEffect(`/models/${encodeURIComponent(kind)}/${encodeURIComponent(model)}/generate`, { params: JSON.stringify(params), prompt }, photos, signal, idempotencyKey),

  job: (jobId: string) => get<JobStatus>(`/jobs/${encodeURIComponent(jobId)}`),  // FIX: AUDIT12-L3
  history: () => get<HistoryItem[]>("/jobs"),

  // Admin-configured storefront (offer sets + live Stars prices)
  storeOffers: () => get<StoreOffers>("/billing/offers"),

  // Daily bonus + referrals (profile card)
  bonusStatus: () => get<BonusStatus>("/bonus"),
  bonusClaim: () => postJson<BonusClaim>("/bonus/claim", {}),
  referrals: () => get<ReferralInfo>("/referrals"),
  redeemPromo: (code: string) => postJson<PromoResult>("/promo", { code }),

  async invoiceLink(req: Record<string, unknown>): Promise<string> {
    const { url } = await postJson<{ url: string }>("/billing/invoice-link", req);
    return url;
  },
};

export async function pollJob(
  jobId: string,
  onTick?: (s: JobStatus) => void,
  signal?: AbortSignal,
): Promise<JobStatus> {
  // `signal` lets the caller stop polling when its component unmounts (the user
  // closed the sheet mid-generation): without it the loop runs for up to 3 min,
  // hitting the API every 3s and calling onTick — which setStates on an unmounted
  // component (React warning + wasted requests + leak).
  for (let i = 0; i < 60; i++) {
    if (signal?.aborted) return { status: "failed", result_url: null, error: "aborted" };
    const s = await api.job(jobId);
    if (signal?.aborted) return { status: "failed", result_url: null, error: "aborted" };
    onTick?.(s);
    if (s.status === "complete" || s.status === "failed") return s;
    if (signal?.aborted) return { status: "failed", result_url: null, error: "aborted" };
    await new Promise((r) => setTimeout(r, 3000));
  }
  return { status: "failed", result_url: null, error: "timeout" };
}
