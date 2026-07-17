// AI-настройка — единая страница для всего, что раньше было размазано на три
// раздела (AI-роутинг / Провайдеры / Ключи API), которые ссылались друг на друга.
// Контейнер лишь переключает вкладки; сами страницы переиспользуются как есть.
import { lazy, Suspense, type ReactNode } from "react";

import { useTabParam } from "../lib/useTabParam";

const AIRouting = lazy(() => import("./AIRouting").then((m) => ({ default: m.AIRouting })));
const Providers = lazy(() => import("./Providers").then((m) => ({ default: m.Providers })));
const ApiKeys = lazy(() => import("./ApiKeys").then((m) => ({ default: m.ApiKeys })));

// Mirror App.tsx's role ranks so a lower-privilege admin only sees the tabs they may
// use (the backend require_role remains the authoritative gate).
const ROLE_RANK: Record<string, number> = { support: 1, moderator: 2, admin: 3, superadmin: 4 };

interface TabDef {
  id: string;
  label: string;
  icon: string;
  minRole: keyof typeof ROLE_RANK;
  el: ReactNode;
}

export function AISetup() {
  const role = localStorage.getItem("admin_role") ?? "support";  // fail closed (App.tsx)
  const myRank = ROLE_RANK[role] ?? 1;

  const tabs: TabDef[] = [
    { id: "routing", label: "Роутинг", icon: "memory", minRole: "superadmin", el: <AIRouting /> },
    { id: "providers", label: "Провайдеры", icon: "dns", minRole: "admin", el: <Providers /> },
    { id: "keys", label: "Ключи API", icon: "key", minRole: "admin", el: <ApiKeys /> },
  ].filter((t) => myRank >= ROLE_RANK[t.minRole]);

  const [tab, setTab] = useTabParam(tabs.map((t) => t.id), tabs[0]?.id ?? "providers");
  const active = tabs.find((t) => t.id === tab) ?? tabs[0];

  return (
    <div>
      <div className="seg-tabs wrap" style={{ marginBottom: "var(--sp-5)" }}>
        {tabs.map((t) => (
          <button key={t.id} className={tab === t.id ? "on" : ""} onClick={() => setTab(t.id)}>
            <span className="ms sm" style={{ verticalAlign: "-3px", marginRight: 4 }}>{t.icon}</span>
            {t.label}
          </button>
        ))}
      </div>
      <Suspense fallback={<div className="loading" style={{ padding: "var(--sp-6)" }}>Загрузка…</div>}>
        {active?.el}
      </Suspense>
    </div>
  );
}
