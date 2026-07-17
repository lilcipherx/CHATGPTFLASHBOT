// Доступ и безопасность — единая страница для того, что раньше было тремя разделами
// (Админы / Безопасность / Аудит-лог). Контейнер лишь переключает вкладки; сами
// страницы переиспользуются как есть (внутренности не переписываются).
import { lazy, Suspense, useState, type ReactNode } from "react";

const Admins = lazy(() => import("./Admins").then((m) => ({ default: m.Admins })));
const Security = lazy(() => import("./Security").then((m) => ({ default: m.Security })));
const Audit = lazy(() => import("./Audit").then((m) => ({ default: m.Audit })));

const ROLE_RANK: Record<string, number> = { support: 1, moderator: 2, admin: 3, superadmin: 4 };

interface TabDef {
  id: string;
  label: string;
  icon: string;
  minRole: keyof typeof ROLE_RANK;
  el: ReactNode;
}

export function AccessSecurity() {
  const role = localStorage.getItem("admin_role") ?? "support";  // fail closed (App.tsx)
  const myRank = ROLE_RANK[role] ?? 1;

  const tabs: TabDef[] = [
    { id: "admins", label: "Админы", icon: "admin_panel_settings", minRole: "superadmin", el: <Admins /> },
    { id: "security", label: "Безопасность", icon: "shield", minRole: "superadmin", el: <Security /> },
    { id: "audit", label: "Аудит-лог", icon: "receipt_long", minRole: "support", el: <Audit /> },
  ].filter((t) => myRank >= ROLE_RANK[t.minRole]);

  const [tab, setTab] = useState<string>(tabs[0]?.id ?? "audit");
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
