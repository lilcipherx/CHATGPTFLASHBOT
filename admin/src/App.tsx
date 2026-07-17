import { lazy, Suspense, useEffect, useState, type ReactNode } from "react";
import { Link, NavLink, Navigate, Route, Routes, useLocation, useNavigate } from "react-router-dom";
import { isAuthed, logout } from "./api";
import { CommandPalette } from "./components/CommandPalette";
import { ErrorBoundary } from "./components/ErrorBoundary";
import { Login } from "./pages/Login";

// Route-level code splitting: each page ships as its own chunk, so the admin
// boots with a small bundle and loads a section only when its route is opened.
// (Pages use named exports → adapt to React.lazy's default-export contract.)
const Dashboard = lazy(() => import("./pages/Dashboard").then((m) => ({ default: m.Dashboard })));
const Users = lazy(() => import("./pages/Users").then((m) => ({ default: m.Users })));
const Payments = lazy(() => import("./pages/Payments").then((m) => ({ default: m.Payments })));
const Pricing = lazy(() => import("./pages/Pricing").then((m) => ({ default: m.Pricing })));
const Promos = lazy(() => import("./pages/Promos").then((m) => ({ default: m.Promos })));
const Referrals = lazy(() => import("./pages/Referrals").then((m) => ({ default: m.Referrals })));
const Broadcasts = lazy(() => import("./pages/Broadcasts").then((m) => ({ default: m.Broadcasts })));
const Effects = lazy(() => import("./pages/Effects").then((m) => ({ default: m.Effects })));
const Banners = lazy(() => import("./pages/Banners").then((m) => ({ default: m.Banners })));
// AI-настройка объединяет AI-роутинг + Провайдеры + Ключи API в одну страницу с вкладками.
const AISetup = lazy(() => import("./pages/AISetup").then((m) => ({ default: m.AISetup })));
const Features = lazy(() => import("./pages/Features").then((m) => ({ default: m.Features })));
// Доступ и безопасность объединяет Админы + Безопасность + Аудит-лог в одну страницу.
const AccessSecurity = lazy(() => import("./pages/AccessSecurity").then((m) => ({ default: m.AccessSecurity })));
const Health = lazy(() => import("./pages/Health").then((m) => ({ default: m.Health })));
const Gallery = lazy(() => import("./pages/Gallery").then((m) => ({ default: m.Gallery })));
const Analytics = lazy(() => import("./pages/Analytics").then((m) => ({ default: m.Analytics })));
const Localization = lazy(() => import("./pages/Localization").then((m) => ({ default: m.Localization })));
const Contests = lazy(() => import("./pages/Contests").then((m) => ({ default: m.Contests })));
const ChannelPosts = lazy(() => import("./pages/ChannelPosts").then((m) => ({ default: m.ChannelPosts })));
const Feedback = lazy(() => import("./pages/Feedback").then((m) => ({ default: m.Feedback })));
const CustomButtons = lazy(() => import("./pages/CustomButtons").then((m) => ({ default: m.CustomButtons })));
const Bots = lazy(() => import("./pages/Bots").then((m) => ({ default: m.Bots })));
const Maintenance = lazy(() => import("./pages/Maintenance").then((m) => ({ default: m.Maintenance })));
const Scheduler = lazy(() => import("./pages/Scheduler").then((m) => ({ default: m.Scheduler })));

interface RouteDef {
  slug: string;       // URL segment → /admin/#/<slug>
  label: string;
  icon: string;
  section: string;
  el: ReactNode;
  minRole?: "support" | "moderator" | "admin" | "superadmin";  // FIX: AUDIT-13 - role-based route visibility
}

// Single source of truth for the router AND the sidebar: each page has its own
// stable URL slug. Grouped into a few self-explanatory sections (watch → people →
// money → outreach → AI engine → settings); order within a section is by use.
const ROUTES: RouteDef[] = [
  // Обзор — что происходит прямо сейчас
  { slug: "dashboard", minRole: "support", label: "Дашборд", icon: "dashboard", section: "Обзор", el: <Dashboard /> },
  { slug: "analytics", minRole: "moderator", label: "Аналитика", icon: "analytics", section: "Обзор", el: <Analytics /> },
  { slug: "health", minRole: "moderator", label: "Здоровье системы", icon: "monitor_heart", section: "Обзор", el: <Health /> },

  // Пользователи — люди и их обращения
  { slug: "users", minRole: "support", label: "Пользователи", icon: "group", section: "Пользователи", el: <Users /> },
  { slug: "feedback", minRole: "support", label: "Оценки и жалобы", icon: "thumbs_up_down", section: "Пользователи", el: <Feedback /> },
  { slug: "gallery", minRole: "moderator", label: "Галерея", icon: "photo_library", section: "Пользователи", el: <Gallery /> },

  // Монетизация — деньги
  { slug: "payments", minRole: "support", label: "Платежи", icon: "payments", section: "Монетизация", el: <Payments /> },
  { slug: "pricing", minRole: "superadmin", label: "Цены", icon: "sell", section: "Монетизация", el: <Pricing /> },  // FIX: SUPERADMIN-7 - price changes affect revenue; superadmin-only
  { slug: "promo-codes", minRole: "moderator", label: "Промокоды", icon: "confirmation_number", section: "Монетизация", el: <Promos /> },
  { slug: "referrals", minRole: "moderator", label: "Рефералы", icon: "group_add", section: "Монетизация", el: <Referrals /> },
  { slug: "contests", minRole: "moderator", label: "Конкурсы", icon: "celebration", section: "Монетизация", el: <Contests /> },

  // Маркетинг — общение с аудиторией
  { slug: "broadcast", minRole: "moderator", label: "Рассылки", icon: "campaign", section: "Маркетинг", el: <Broadcasts /> },
  { slug: "autoposting", minRole: "moderator", label: "Автопостинг", icon: "rss_feed", section: "Маркетинг", el: <ChannelPosts /> },
  { slug: "carousel", minRole: "moderator", label: "Карусель", icon: "view_carousel", section: "Маркетинг", el: <Banners /> },
  { slug: "buttons", minRole: "moderator", label: "Кнопки-ссылки", icon: "link", section: "Маркетинг", el: <CustomButtons /> },
  { slug: "effects", minRole: "moderator", label: "Эффекты", icon: "auto_awesome", section: "Маркетинг", el: <Effects /> },

  // AI и контент — движок генерации
  // AI-роутинг + Провайдеры + Ключи API объединены в «AI-настройка» (вкладки). minRole=admin
  // открывает страницу; вкладка «Роутинг» гейтится superadmin внутри AISetup (+ backend RBAC).
  { slug: "ai-setup", minRole: "admin", label: "AI-настройка", icon: "memory", section: "AI и контент", el: <AISetup /> },
  { slug: "feature-flags", minRole: "superadmin", label: "Функции", icon: "tune", section: "AI и контент", el: <Features /> },  // FIX: SUPERADMIN-9 - feature flags + gates control who sees what; superadmin-only

  // Система — настройки и доступ
  // Админы + Безопасность + Аудит-лог объединены в «Доступ и безопасность» (вкладки).
  // minRole=support открывает страницу ради вкладки «Аудит-лог»; вкладки Админы/
  // Безопасность гейтятся superadmin внутри AccessSecurity (+ backend RBAC).
  { slug: "access-security", minRole: "support", label: "Доступ и безопасность", icon: "shield", section: "Система", el: <AccessSecurity /> },
  { slug: "white-label", minRole: "admin", label: "Боты (white-label)", icon: "smart_toy", section: "Система", el: <Bots /> },
  { slug: "localization", minRole: "admin", label: "Локализация", icon: "translate", section: "Система", el: <Localization /> },
  { slug: "maintenance", minRole: "superadmin", label: "Обслуживание", icon: "build", section: "Система", el: <Maintenance /> },  // FIX: SUPERADMIN-10 - VACUUM/backup/flush cache are destructive; superadmin-only
  { slug: "scheduler", minRole: "superadmin", label: "Планировщик", icon: "schedule", section: "Система", el: <Scheduler /> },  // FIX: AUDIT-SCHED - admin-controlled cron on/off + interval
];

// Stable projection for the command palette. ROUTES is a module constant, so build
// this once instead of re-allocating on every AdminShell render — a fresh array each
// render would invalidate CommandPalette's `filtered` useMemo (its `items` dep).
// FIX: SUPERADMIN-12 - the command palette must also respect role visibility.
// We can't filter at module load (no role yet), so AdminShell filters PALETTE_ITEMS
// by role before passing to CommandPalette. The unfiltered list is kept for the
// route table itself; the palette gets a role-filtered slice.
const PALETTE_ITEMS = ROUTES.map(({ slug, label, icon, section, minRole }) => ({
  id: slug, label, icon, section, minRole,
}));

function NotFound() {
  return (
    <div className="empty-state">
      <div className="es-icon"><span className="ms">error</span></div>
      <h3 className="es-title">Страница не найдена</h3>
      <p className="es-desc">
        Такого раздела нет. <Link to="/dashboard">Вернуться на дашборд</Link>.
      </p>
    </div>
  );
}

// FIX: SUPERADMIN-12 - client-side role guard. The sidebar filters by role, but
// nothing stopped a user from typing /admins directly into the URL bar. The page
// would render, fire API calls, and the backend would 403 — leaving the user on
// a broken screen. This wrapper checks the route's minRole against the current
// admin's role (read from localStorage where login() puts it) and shows a clear
// "insufficient role" message instead of mounting the page. The backend RBAC
// (require_role) remains the authoritative check — this is purely UX.
const ROLE_RANK: Record<string, number> = { support: 1, moderator: 2, admin: 3, superadmin: 4 };
function RoleGuard({ minRole, children }: { minRole?: string; children: ReactNode }) {
  // FIX: AUDIT-U4 - fail CLOSED: an absent/unknown role must map to the LOWEST
  // privilege (support/rank 1), never admin/rank 3. A partial localStorage clear
  // (admin_authed set, admin_role missing) previously unhid admin-level pages.
  const role = localStorage.getItem("admin_role") ?? "support";
  const myRank = ROLE_RANK[role] ?? 1;
  const requiredRank = ROLE_RANK[minRole ?? "admin"] ?? 3;
  if (myRank < requiredRank) {
    return (
      <div className="empty-state">
        <div className="es-icon"><span className="ms">lock</span></div>
        <h3 className="es-title">Недостаточно прав</h3>
        <p className="es-desc">
          Этот раздел доступен только роли <b>{minRole}</b>.
          Ваша роль: <b>{role}</b>.
        </p>
        <p className="es-desc">
          <Link to="/dashboard">Вернуться на дашборд</Link>
        </p>
      </div>
    );
  }
  return <>{children}</>;
}

function AdminShell({ onLogout }: { onLogout: () => void }) {
  const navigate = useNavigate();
  const location = useLocation();
  const role = localStorage.getItem("admin_role") ?? "support";  // FIX: AUDIT-U4 fail closed
  const email = localStorage.getItem("admin_email") || "admin";
  const initial = email.trim().charAt(0).toUpperCase() || "A";

  // Route → page meta drives the document title and breadcrumb (active highlight
  // is handled by NavLink against the URL, the single source of truth).
  const current = ROUTES.find((r) => location.pathname === `/${r.slug}`);
  useEffect(() => {
    document.title = current ? `${current.label} · ИИ Бот Admin` : "ИИ Бот Admin";
  }, [current]);

  let lastSection = "";
  return (
    <div className="admin-layout">
      <CommandPalette
        items={PALETTE_ITEMS.filter((it) => {
          // FIX: SUPERADMIN-12 - mirror the sidebar filter so a `support` user
          // can't Cmd+K into a superadmin-only page either.
          const myRank = ROLE_RANK[role] ?? 3;
          const requiredRank = ROLE_RANK[it.minRole ?? "admin"] ?? 3;
          return myRank >= requiredRank;
        })}
        onSelect={(slug) => navigate(`/${slug}`)}
      />
      <aside className="sidebar">
        <div className="sb-brand">
          <span className="name"><span className="dot" /> ИИ Бот</span>
          <span
            className="sb-kbd-hint"
            title="Быстрый переход"
            onClick={() =>
              window.dispatchEvent(new KeyboardEvent("keydown", { key: "k", ctrlKey: true }))
            }
          >
            ⌘K
          </span>
        </div>

        <nav className="navi">
          {ROUTES.filter((n) => {
            // FIX: AUDIT-13 + SUPERADMIN-12 - filter sidebar routes by role.
            // Uses the same ROLE_RANK map as RoleGuard above so the sidebar and
            // the route guard can never disagree on what's visible.
            const myRank = ROLE_RANK[role] ?? 3;
            const requiredRank = ROLE_RANK[n.minRole ?? "admin"] ?? 3;
            return myRank >= requiredRank;
          }).map((n) => {
            const showSection = n.section !== lastSection;
            lastSection = n.section;
            return (
              <div key={n.slug} style={{ display: "contents" }}>
                {showSection && <div className="navi-section">{n.section}</div>}
                <NavLink
                  to={`/${n.slug}`}
                  className={({ isActive }) => "navi-item" + (isActive ? " active" : "")}
                >
                  {({ isActive }) => (
                    <>
                      <span className={"ms" + (isActive ? " fill" : "")}>{n.icon}</span>
                      <span>{n.label}</span>
                    </>
                  )}
                </NavLink>
              </div>
            );
          })}
        </nav>

        <div className="sb-foot">
          <div className="sb-ava" title={email}>{initial}</div>
          <div className="sb-id">
            <div className="who" title={email}>{email}</div>
            <div className="role">{role}</div>
          </div>
          <button className="sb-logout" title="Выйти" onClick={() => { logout(); onLogout(); }}>
            <span className="ms sm">logout</span>
          </button>
        </div>
      </aside>

      <main className="main">
        {current && (
          <nav className="crumbs" aria-label="breadcrumb">
            <span>Админка</span>
            <span className="ms">chevron_right</span>
            <span>{current.section}</span>
            <span className="ms">chevron_right</span>
            <b>{current.label}</b>
          </nav>
        )}
        {/* Keyed by URL so a crashed section recovers automatically once the admin
            navigates elsewhere; the boundary also catches failed lazy-chunk loads. */}
        <ErrorBoundary key={location.pathname}>
          <Suspense fallback={<div className="loading">Загрузка…</div>}>
            <Routes>
              {/* Open the dashboard for the bare app URL (and redirect old deep-links). */}
              <Route path="/" element={<Navigate to="/dashboard" replace />} />
              {ROUTES.map((r) => (
                <Route key={r.slug} path={`/${r.slug}`} element={
                  <RoleGuard minRole={r.minRole}>{r.el}</RoleGuard>
                } />
              ))}
              <Route path="*" element={<NotFound />} />
            </Routes>
          </Suspense>
        </ErrorBoundary>
      </main>
    </div>
  );
}

export function App() {
  const [authed, setAuthed] = useState(isAuthed());
  // FIX: AUDIT-2 - listen for admin:unauth event from api.ts logout()
  useEffect(() => {
    const onUnauth = () => setAuthed(false);
    window.addEventListener("admin:unauth", onUnauth);
    return () => window.removeEventListener("admin:unauth", onUnauth);
  }, []);
  if (!authed) return <Login onAuthed={() => setAuthed(true)} />;
  return <AdminShell onLogout={() => setAuthed(false)} />;
}
