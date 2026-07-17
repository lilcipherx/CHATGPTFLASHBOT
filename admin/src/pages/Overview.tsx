// Дашборд — объединяет живой обзор (KPI) и «Аналитику» (глубокие графики) в одну
// страницу с вкладками. Контейнер лишь переключает вкладки.
import { lazy, Suspense, useState, type ReactNode } from "react";

const Dashboard = lazy(() => import("./Dashboard").then((m) => ({ default: m.Dashboard })));
const Analytics = lazy(() => import("./Analytics").then((m) => ({ default: m.Analytics })));

const ROLE_RANK: Record<string, number> = { support: 1, moderator: 2, admin: 3, superadmin: 4 };

interface TabDef {
  id: string;
  label: string;
  icon: string;
  minRole: keyof typeof ROLE_RANK;
  el: ReactNode;
}

export function Overview() {
  const role = localStorage.getItem("admin_role") ?? "support";  // fail closed (App.tsx)
  const myRank = ROLE_RANK[role] ?? 1;

  const tabs: TabDef[] = [
    { id: "dashboard", label: "Дашборд", icon: "dashboard", minRole: "support", el: <Dashboard /> },
    { id: "analytics", label: "Аналитика", icon: "analytics", minRole: "moderator", el: <Analytics /> },
  ].filter((t) => myRank >= ROLE_RANK[t.minRole]);

  const [tab, setTab] = useState<string>(tabs[0]?.id ?? "dashboard");
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
