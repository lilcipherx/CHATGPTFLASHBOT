import WebApp from "@twa-dev/sdk";
import { useEffect, useState } from "react";
import { api, Profile } from "./api/client";
import { syncLang, t } from "./i18n";
import { Icon } from "./components/Icons";
import { Home } from "./pages/Home";
import { History } from "./pages/History";
import { ProfilePage } from "./pages/Profile";
import { Trends } from "./pages/Trends";
import { Create } from "./pages/Create";
import { haptic } from "./theme";

type Tab = "home" | "trends" | "create" | "history" | "profile";

// Opened outside Telegram (a plain browser) there is no signed initData, so every
// API call is rejected. Instead of showing a wall of "Ошибка 401" on each tab, gate
// the whole app with a clear "open in Telegram" screen. It appears ONLY when there
// is no Telegram context AND the backend actually refused us (401) — so a dev server
// with DEV_WEBAPP_BYPASS on, where requests succeed, still renders the full app.
function TelegramGate() {
  return (
    <div className="app">
      <div className="gate">
        <div className="gate-mark"><Icon name="profile" /></div>
        <h2>{t("gate_title")}</h2>
        <p>{t("gate_sub")}</p>
      </div>
    </div>
  );
}

const TABS: { id: Tab; key: string }[] = [
  { id: "home", key: "tab_home" },
  { id: "trends", key: "tab_trends" },
  { id: "create", key: "tab_create" },
  { id: "history", key: "tab_history" },
  { id: "profile", key: "tab_profile" },
];

export function App() {
  const [tab, setTab] = useState<Tab>("home");
  const [profile, setProfile] = useState<Profile | null>(null);
  const [profileError, setProfileError] = useState<string | null>(null);
  // §10 — replay target handed from History to the Create page.
  const [createPrefill, setCreatePrefill] = useState<{ kind: "photo" | "video"; presetId: number } | null>(null);

  const reloadProfile = () => {
    setProfileError(null);
    return api
      .profile()
      .then((p) => {
        setProfile(p);
        setProfileError(null);
        // FIX: AUDIT-FINAL-7 - sync the Mini App language to the bot-side
        // language_code IMMEDIATELY when /profile returns. Previously syncLang
        // was only called from Profile.tsx, so the app stayed in the wrong
        // language for the entire first session until the user opened Profile.
        if (p?.language_code) syncLang(p.language_code);
      })
      .catch((e) => { setProfile(null); setProfileError(e instanceof Error ? e.message : String(e)); });
  };
  // Patch just the credits chip after a generation spends them (no full reload).
  const applyCredits = (credits: number) => setProfile((p) => (p ? { ...p, credits } : p));
  useEffect(() => {
    reloadProfile();
  }, []);

  // No Telegram context + the backend refused us → not signed in. Show the gate.
  // FIX: AUDIT-FINAL-7 - api/client.ts throws `new Error("err_auth")` on 401
  // (NOT "ERROR_401"), so the old comparison was always false and TelegramGate
  // was dead code. Users outside Telegram saw a blank app instead of the gate.
  if (!WebApp.initData && profileError && profileError === "err_auth") {
    return <TelegramGate />;
  }

  // FIX: AUDIT-M14 - an in-Telegram user whose signed session expires gets a 401
  // ("err_auth") with a truthy initData, so the gate above never fires. Instead of
  // leaving credits stuck on "—" and grids in a misleading empty state, show an
  // explicit error + retry (re-sends fresh initData) rather than a half-broken app.
  if (profileError === "err_auth") {
    return (
      <div className="app">
        <div className="center">
          <div>{t("err_server")}</div>
          <button className="btn" onClick={() => { haptic(); reloadProfile(); }}>{t("retry")}</button>
        </div>
      </div>
    );
  }

  // FIX: AUDIT13-M18 - a NON-auth failure of the initial profile load (500 / rate-limit
  // / timeout) previously fell through and rendered the app with credits stuck on "—"
  // and no retry anywhere on Home/Trends/Create. Show an explicit error + retry when we
  // have no profile data at all. (Once profile has loaded, a later reload failure keeps
  // the last-good UI rather than blanking it.)
  if (profileError && !profile) {
    return (
      <div className="app">
        <div className="center">
          <div>{t(profileError.startsWith("err_") ? profileError : "err_server")}</div>
          <button className="btn" onClick={() => { haptic(); reloadProfile(); }}>{t("retry")}</button>
        </div>
      </div>
    );
  }

  return (
    <div className="app">
      <header className="header">
        <div className="ava"><Icon name="profile" /></div>
        <h1>{t("brand")}</h1>
        <span className="chip">{profile?.credits ?? "—"} ✨</span>
      </header>

      {tab === "home" && <Home onCredits={applyCredits} sections={profile?.sections} />}
      {tab === "trends" && <Trends onCredits={applyCredits} sections={profile?.sections} />}
      {tab === "create" && (
        <Create
          onCredits={applyCredits}
          sections={profile?.sections}
          prefill={createPrefill}
          onPrefillConsumed={() => setCreatePrefill(null)}
        />
      )}
      {tab === "history" && (
        <History
          onCredits={applyCredits}
          onRecreate={(kind, presetId) => { setCreatePrefill({ kind, presetId }); setTab("create"); }}
        />
      )}
      {tab === "profile" && <ProfilePage profile={profile} error={profileError} onReload={reloadProfile} />}

      <nav className="nav">
        {TABS.map((x) => (
          <button
            key={x.id}
            className={tab === x.id ? "active" : ""}
            aria-current={tab === x.id ? "page" : undefined}  // FIX: AUDIT-10
            onClick={() => { haptic(); setTab(x.id); }}
          >
            <span className="ico"><Icon name={x.id} /></span>
            {t(x.key)}
          </button>
        ))}
      </nav>
    </div>
  );
}
