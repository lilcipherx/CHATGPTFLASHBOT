// Цены и промо — объединяет разделы «Цены» и «Промокоды» в одну страницу с
// вкладками. Контейнер лишь переключает вкладки; сами страницы переиспользуются.
import { lazy, Suspense, type ReactNode } from "react";

import { useTabParam } from "../lib/useTabParam";

const Pricing = lazy(() => import("./Pricing").then((m) => ({ default: m.Pricing })));
const Promos = lazy(() => import("./Promos").then((m) => ({ default: m.Promos })));

const ROLE_RANK: Record<string, number> = { support: 1, moderator: 2, admin: 3, superadmin: 4 };

interface TabDef {
  id: string;
  label: string;
  icon: string;
  minRole: keyof typeof ROLE_RANK;
  el: ReactNode;
}

export function PricingPromos() {
  const role = localStorage.getItem("admin_role") ?? "support";  // fail closed (App.tsx)
  const myRank = ROLE_RANK[role] ?? 1;

  const tabs: TabDef[] = [
    { id: "pricing", label: "Цены", icon: "sell", minRole: "superadmin", el: <Pricing /> },
    { id: "promos", label: "Промокоды", icon: "confirmation_number", minRole: "moderator", el: <Promos /> },
  ].filter((t) => myRank >= ROLE_RANK[t.minRole]);

  const [tab, setTab] = useTabParam(tabs.map((t) => t.id), tabs[0]?.id ?? "promos");
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
