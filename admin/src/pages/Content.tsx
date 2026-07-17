// Контент — объединяет всё, что админ показывает пользователям: «Эффекты» (каталог
// генераций), «Карусель» (промо-слайды) и «Кнопки-ссылки». Вкладки; страницы
// переиспользуются как есть.
import { lazy, Suspense, type ReactNode } from "react";

import { useTabParam } from "../lib/useTabParam";

const Effects = lazy(() => import("./Effects").then((m) => ({ default: m.Effects })));
const Banners = lazy(() => import("./Banners").then((m) => ({ default: m.Banners })));
const CustomButtons = lazy(() => import("./CustomButtons").then((m) => ({ default: m.CustomButtons })));

const ROLE_RANK: Record<string, number> = { support: 1, moderator: 2, admin: 3, superadmin: 4 };

interface TabDef {
  id: string;
  label: string;
  icon: string;
  minRole: keyof typeof ROLE_RANK;
  el: ReactNode;
}

export function Content() {
  const role = localStorage.getItem("admin_role") ?? "support";  // fail closed (App.tsx)
  const myRank = ROLE_RANK[role] ?? 1;

  const tabs: TabDef[] = [
    { id: "effects", label: "Эффекты", icon: "auto_awesome", minRole: "moderator", el: <Effects /> },
    { id: "carousel", label: "Карусель", icon: "view_carousel", minRole: "moderator", el: <Banners /> },
    { id: "buttons", label: "Кнопки-ссылки", icon: "link", minRole: "moderator", el: <CustomButtons /> },
  ].filter((t) => myRank >= ROLE_RANK[t.minRole]);

  const [tab, setTab] = useTabParam(tabs.map((t) => t.id), tabs[0]?.id ?? "effects");
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
