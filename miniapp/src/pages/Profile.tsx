import WebApp from "@twa-dev/sdk";
import { useEffect, useState } from "react";
import { api, Profile, StoreOffers } from "../api/client";
import { BonusReferral } from "../components/BonusReferral";
import { getLang, LANG_LABELS, onLangChange, syncLang, t } from "../i18n";
import { haptic } from "../theme";

// Humanize the sub_tier slug for display ("premium_x2" → "Premium X2").
function subTierLabel(tier: string | null): string {
  if (tier === "premium_x2") return "Premium X2";
  if (tier === "premium") return "Premium";
  return tier ?? "Premium";
}

// Pack id -> i18n label key. Labels stay in the frontend; the offer SETS + their
// live Stars prices come from the admin-configured storefront (api.storeOffers()),
// so the admin controls which packs/qtys appear without a frontend release.
const PACK_KEYS: { pack: string; key: string }[] = [
  { pack: "image_pack", key: "pack_image" },
  { pack: "video_pack", key: "pack_video" },
  { pack: "music_pack", key: "pack_music" },
];

export function ProfilePage({
  profile,
  error,
  onReload,
}: {
  profile: Profile | null;
  error?: string | null;
  onReload: () => void;
}) {
  // FIX: AUDIT12-F8 - subscribe to language changes so the UI re-renders when the
  // bot-side language_code arrives via /api/profile and syncLang() fires.
  const [, setLangTick] = useState(0);
  useEffect(() => onLangChange(() => setLangTick((n) => n + 1)), []);

  // FIX: AUDIT12-F8 - when profile arrives, sync the Mini App language with the
  // bot-side language_code. No localStorage, no reload — syncLang() updates the
  // reactive _lang and notifies subscribers (this component included).
  useEffect(() => {
    if (profile?.language_code) {
      syncLang(profile.language_code);
    }
  }, [profile?.language_code]);

  const [msg, setMsg] = useState("");
  const [promo, setPromo] = useState("");
  const [promoMsg, setPromoMsg] = useState("");
  const [promoBusy, setPromoBusy] = useState(false);
  const [store, setStore] = useState(false);
  const [storeMsg, setStoreMsg] = useState("");

  async function applyPromo() {
    const code = promo.trim();
    if (!code || promoBusy) return;
    setPromoBusy(true); setPromoMsg("");
    try {
      const r = await api.redeemPromo(code);
      if (r.ok) { setPromoMsg(t("promo_ok", { n: r.amount })); setPromo(""); haptic("heavy"); onReload(); }
      else setPromoMsg(r.status === "already" ? t("promo_already") : t("promo_invalid"));
    } catch (e) {
      // FIX: AUDIT13-M16 - the thrown message is an i18n key; translate it.
      setPromoMsg(t(e instanceof Error ? e.message : "err_generic"));
    } finally {
      setPromoBusy(false);
    }
  }

  async function buy(req: Record<string, unknown>) {
    haptic("medium");
    setMsg("");
    try {
      const url = await api.invoiceLink(req);
      WebApp.openInvoice(url, (status) => {
        if (status === "paid") { setMsg(t("paid")); haptic("heavy"); onReload(); }
        else if (status === "cancelled") { setMsg(t("pay_cancelled")); }
        else if (status === "failed") { setMsg(t("pay_failed")); }
      });
    } catch (e) {
      // FIX: AUDIT13-M16 - translate the i18n key instead of surfacing it raw.
      const m = t(e instanceof Error ? e.message : "err_generic");
      setMsg(m);
      setStoreMsg(m);
    }
  }

  if (!profile) {
    if (error) {
      return (
        <div className="center">
          <div className="error-banner">{t("profile_error")}</div>
          <button className="btn accent" onClick={() => { haptic(); onReload(); }}>
            {t("retry")}
          </button>
        </div>
      );
    }
    return <div className="center"><span className="spinner" /> {t("loading")}</div>;
  }

  // FIX: null-safety - a user with no usage row can come back with a null
  // mini_app_quota; `q.used`/`q.limit` would then crash the whole Profile tab.
  const q = profile.mini_app_quota ?? { used: 0, limit: 0 };
  // FIX: AUDIT12-F8 - read the live language via getLang() so we re-render after sync.
  const currentLang = getLang();

  return (
    <div className="content profile-page">
      <div className={"banner" + (profile.is_premium ? "" : " flat")}>
        <span className="kicker">{profile.is_premium ? "Premium" : t("tier_free")}</span>
        <b>{profile.is_premium ? `⭐️ ${subTierLabel(profile.sub_tier)}` : t("free_plan")}</b>
        <p>{profile.is_premium ? t("premium_active") : t("connect_hint")}</p>
      </div>

      <div className="stat-row">
        <div className="stat"><div className="v">{q.used}/{q.limit}</div><div className="k">{t("stat_photo")}</div></div>
        <div className="stat"><div className="v">✨ {profile.credits}</div><div className="k">{t("stat_credits")}</div></div>
      </div>

      <BonusReferral onClaimed={onReload} />

      <div>
        <div className="section-title">{t("balances")}</div>
        <div className="list">
          {/* FIX: null-safety - balances may be null/partial for a fresh user;
              deep access profile.balances.image would crash the tab. */}
          <div className="item"><span>{t("bal_image")}</span><span className="val">{profile.balances?.image ?? 0}</span></div>
          <div className="item"><span>{t("bal_video")}</span><span className="val">{profile.balances?.video ?? 0}</span></div>
          <div className="item"><span>{t("bal_music")}</span><span className="val">{profile.balances?.music ?? 0}</span></div>
        </div>
      </div>

      <div>
        <div className="section-title">{t("promo_title")}</div>
        <div className="btn-row">
          <input
            className="prompt-input"
            style={{ flex: 1 }}
            value={promo}
            placeholder={t("promo_ph")}
            onChange={(e) => setPromo(e.target.value)}
          />
          <button className="btn-sm" disabled={promoBusy || !promo.trim()} onClick={applyPromo}>
            {promoBusy ? "…" : t("promo_apply")}
          </button>
        </div>
        {promoMsg && <div className="muted" style={{ marginTop: 6 }}>{promoMsg}</div>}
      </div>

      <button className="btn accent store-cta" onClick={() => { haptic("medium"); setStore(true); }}>
        {t("store")}
      </button>

      {/* FIX: AUDIT12-F8 - language is now read-only in the Mini App.
          It syncs automatically from /api/profile (which mirrors the bot-side
          /language command). To change it, the user runs /language in Telegram.
          This avoids drift between the bot and the Mini App. */}
      <div className="settings-row lang-display">
        <span>{t("language")}</span>
        <span className="lang-current">{LANG_LABELS[currentLang] ?? currentLang}</span>
      </div>

      {msg && <div className="error-banner">{msg}</div>}

      {store && <StoreSheet onClose={() => { setStore(false); setStoreMsg(""); }} onBuy={buy} msg={storeMsg} />}
    </div>
  );
}

// All paid actions live behind one "Store" button so the profile stays a clean
// overview instead of a wall of price buttons. Reuses the full-screen .sheet shell.
function StoreSheet({ onClose, onBuy, msg }: {
  onClose: () => void;
  onBuy: (req: Record<string, unknown>) => void;
  msg?: string;
}) {
  const [offers, setOffers] = useState<StoreOffers | null>(null);
  const [err, setErr] = useState(false);
  useEffect(() => {
    let ignore = false;
    api.storeOffers().then((o) => { if (!ignore) setOffers(o); }).catch(() => { if (!ignore) setErr(true); });
    return () => { ignore = true; };
  }, []);

  // FIX: UI-3 - lock background scroll while the full-screen store sheet is open
  // (parity with CreateSheet; the sheet is position:fixed; inset:0 over the app).
  useEffect(() => {
    const prev = document.body.style.overflow;
    document.body.style.overflow = "hidden";
    return () => { document.body.style.overflow = prev; };
  }, []);

  return (
    <div className="sheet">
      <div className="sheet-head">
        <button className="back" onClick={onClose}>{t("back")}</button>
        <b>{t("store_title")}</b>
      </div>
      <div className="sheet-body">
        {msg && <div className="error-banner">{msg}</div>}
        {!offers ? (
          <div className="center">
            {err
              ? <div className="error-banner">{t("profile_error")}</div>
              : <><span className="spinner" /> {t("loading")}</>}
          </div>
        ) : (
          <>
            {offers.credits.length > 0 && (
              <div>
                <div className="section-title">{t("buy_credits")}</div>
                <div className="btn-row">
                  {offers.credits.map((o) => (
                    <button key={o.qty} className="btn-sm" onClick={() => onBuy({ kind: "credits", qty: o.qty })}>✨ {o.qty} · ⭐{o.stars}</button>
                  ))}
                </div>
              </div>
            )}
            {offers.premium.length > 0 && (
              <div>
                <div className="section-title">{t("connect_premium")}</div>
                <div className="btn-row">
                  {offers.premium.map((o) => (
                    <button key={o.months} className="btn-sm" onClick={() => onBuy({ kind: "sub", product: "premium", months: o.months })}>{t("dur_months", { n: o.months })} · ⭐{o.stars}</button>
                  ))}
                </div>
              </div>
            )}
            {PACK_KEYS.map((p) => {
              const list = offers.packs[p.pack] ?? [];
              if (list.length === 0) return null;
              return (
                <div key={p.pack}>
                  <div className="section-title">{t(p.key)} · {t("pack_suffix")}</div>
                  <div className="btn-row">
                    {list.map((o) => (
                      <button key={o.qty} className="btn-sm" onClick={() => onBuy({ kind: "pack", pack: p.pack, qty: o.qty })}>{o.qty} {t("generations")} · ⭐{o.stars}</button>
                    ))}
                  </div>
                </div>
              );
            })}
          </>
        )}
      </div>
    </div>
  );
}
