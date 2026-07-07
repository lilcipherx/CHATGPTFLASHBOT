import { useCallback, useEffect, useMemo, useState } from "react";
import { adminsApi, api, type AdminAccount, type AdminSession, type AuditEntry } from "../api";
import { Select, opts } from "../components/Select";
import { Modal } from "../components/Modal";

// Identity & Access control center for panel admins (ТЗ §8). Grounded entirely in
// the real backend: a 4-role RANK hierarchy (support<moderator<admin<superadmin),
// the /admins CRUD (create / role / enable / disable / reset-2fa, superadmin-only,
// last-superadmin protected), and the audit log (per-action IP). Fields the model
// does not track (name/phone/geo/device, sessions, recovery codes, passkeys,
// invitations, password-policy, custom roles, groups, temp access) are surfaced as
// honestly-gated "requires backend" notes — never faked.

const ROLES = ["support", "moderator", "admin", "superadmin"];
const RANK: Record<string, number> = { support: 1, moderator: 2, admin: 3, superadmin: 4 };

interface RoleMeta { label: string; cls: string; icon: string; desc: string }
const ROLE_META: Record<string, RoleMeta> = {
  superadmin: { label: "Superadmin", cls: "pro", icon: "shield_person", desc: "Полный доступ: админы, флаги/гейты, AI-роутер, router-контейнеры, обслуживание." },
  admin: { label: "Admin", cls: "ok", icon: "admin_panel_settings", desc: "Аналитика, пользователи, тарифы, контент, рассылки, локализация, боты (просмотр)." },
  moderator: { label: "Moderator", cls: "warn", icon: "gavel", desc: "Эффекты, баннеры/карусель, галерея — модерация контента Mini App." },
  support: { label: "Support", cls: "muted", icon: "support_agent", desc: "Просмотр пользователей, CRM-заметки и теги, сообщения поддержки." },
};
const meta = (r: string): RoleMeta => ROLE_META[r] || { label: r, cls: "muted", icon: "person", desc: "" };
// 2FA is mandatory for these roles by default (server config `mfa_required_roles`).
const mfaRequired = (r: string) => RANK[r] >= RANK.admin;
const privileged = (r: string) => RANK[r] >= RANK.admin;

function initials(email: string): string {
  const name = email.split("@")[0] || email;
  const parts = name.split(/[._-]+/).filter(Boolean);
  return ((parts[0]?.[0] || "") + (parts[1]?.[0] || parts[0]?.[1] || "")).toUpperCase() || "?";
}
function fmtDate(s: string | null): string {
  if (!s) return "—";
  return new Date(s).toLocaleString("ru", { day: "2-digit", month: "short", year: "numeric", hour: "2-digit", minute: "2-digit" });
}
function fmtDay(s: string | null): string {
  if (!s) return "—";
  return new Date(s).toLocaleDateString("ru", { day: "2-digit", month: "short", year: "numeric" });
}
function ago(s: string | null): string {
  if (!s) return "никогда";
  const ms = Date.now() - new Date(s).getTime();
  const d = Math.floor(ms / 86400000);
  if (d <= 0) { const h = Math.floor(ms / 3600000); return h <= 0 ? "только что" : `${h} ч назад`; }
  if (d === 1) return "вчера";
  if (d < 30) return `${d} дн назад`;
  if (d < 365) return `${Math.floor(d / 30)} мес назад`;
  return `${Math.floor(d / 365)} г назад`;
}
function daysSince(s: string | null): number | null {
  if (!s) return null;
  return Math.floor((Date.now() - new Date(s).getTime()) / 86400000);
}

// Honest security score from REAL signals only.
function securityScore(a: AdminAccount): { score: number; issues: string[] } {
  let score = 100;
  const issues: string[] = [];
  if (!a.has_2fa) {
    score -= 40;
    issues.push(privileged(a.role) ? "2FA не включена у привилегированной роли" : "2FA не включена");
  }
  if (!a.last_login) { score -= 10; issues.push("Ни разу не входил"); }
  else { const d = daysSince(a.last_login); if (d !== null && d > 90) { score -= 15; issues.push(`Не входил больше 90 дней (${d} дн)`); } }
  if (mfaRequired(a.role) && !a.has_2fa) { score -= 10; issues.push("Роль требует 2FA по политике"); }
  return { score: Math.max(0, Math.min(100, score)), issues };
}
const scoreTone = (s: number) => (s >= 85 ? "ok" : s >= 60 ? "warn" : "danger");

// Strong random password (used by the create form's generator).
function genPassword(len = 20): string {
  const sets = "ABCDEFGHJKLMNPQRSTUVWXYZabcdefghijkmnpqrstuvwxyz23456789!@#$%^&*-_";
  const arr = new Uint32Array(len);
  crypto.getRandomValues(arr);
  return Array.from(arr, (n) => sets[n % sets.length]).join("");
}
function pwStrength(p: string): { score: number; label: string; cls: string } {
  let s = 0;
  if (p.length >= 8) s++; if (p.length >= 12) s++; if (p.length >= 16) s++;
  if (/[a-z]/.test(p) && /[A-Z]/.test(p)) s++;
  if (/\d/.test(p)) s++;
  if (/[^A-Za-z0-9]/.test(p)) s++;
  if (s <= 2) return { score: s, label: "слабый", cls: "danger" };
  if (s <= 4) return { score: s, label: "средний", cls: "warn" };
  return { score: s, label: "надёжный", cls: "ok" };
}

type Tab = "directory" | "roles" | "security";

export function Admins() {
  const [tab, setTab] = useState<Tab>("directory");
  const [rows, setRows] = useState<AdminAccount[] | null>(null);
  const [audit, setAudit] = useState<AuditEntry[]>([]);
  const [msg, setMsg] = useState("");

  const load = useCallback(() => {
    adminsApi.admins().then(setRows).catch((e) => { setMsg(String(e)); setRows([]); });
    api.audit({ limit: 500 }).then(setAudit).catch(() => setAudit([]));
  }, []);
  useEffect(() => { load(); }, [load]);

  const toast = (m: string) => setMsg(m);
  const guard = (p: Promise<unknown>) => p.then(load).catch((e) => setMsg(String(e)));

  // Per-admin activity derived from the real audit log (acting admin_id).
  const activity = useMemo(() => {
    const m = new Map<number, { lastAt: string; lastIp: string | null; count: number }>();
    for (const e of audit) {
      const cur = m.get(e.admin_id);
      if (!cur) m.set(e.admin_id, { lastAt: e.created_at, lastIp: e.ip, count: 1 });
      else { cur.count++; if (!cur.lastIp && e.ip) cur.lastIp = e.ip; }
    }
    return m;
  }, [audit]);

  return (
    <div>
      <div className="section-head">
        <div>
          <h1 className="page-title">Администраторы</h1>
          <p className="page-sub">Управление администраторами панели, ролями, доступом, 2FA и аудитом (только для superadmin).</p>
        </div>
      </div>

      {msg && (
        <p className={msg.startsWith("✅") ? "note-ok" : "note-err"}>
          <span className="ms sm">{msg.startsWith("✅") ? "check_circle" : "error"}</span>
          {msg}<button className="btn ghost sm" onClick={() => setMsg("")} aria-label="Скрыть">×</button>
        </p>
      )}

      <div className="page-stack">
        <Dashboard rows={rows} />

        <div className="seg-tabs" style={{ marginBottom: 0 }}>
          <button className={tab === "directory" ? "on" : ""} onClick={() => setTab("directory")}><span className="ms sm" style={{ verticalAlign: "-3px", marginRight: 4 }}>group</span>Администраторы</button>
          <button className={tab === "roles" ? "on" : ""} onClick={() => setTab("roles")}><span className="ms sm" style={{ verticalAlign: "-3px", marginRight: 4 }}>workspace_premium</span>Роли и доступ</button>
          <button className={tab === "security" ? "on" : ""} onClick={() => setTab("security")}><span className="ms sm" style={{ verticalAlign: "-3px", marginRight: 4 }}>security</span>Безопасность</button>
        </div>

        {tab === "directory" ? <DirectoryTab rows={rows} activity={activity} audit={audit} guard={guard} toast={toast} />
          : tab === "roles" ? <RolesTab rows={rows} />
            : <SecurityTab rows={rows} audit={audit} />}
      </div>
    </div>
  );
}

// ---------------- Dashboard ----------------
function Dashboard({ rows }: { rows: AdminAccount[] | null }) {
  const k = useMemo(() => {
    const r = rows || [];
    const lastLogin = r.map((a) => a.last_login).filter(Boolean).sort().slice(-1)[0] || null;
    return {
      total: r.length,
      active: r.filter((a) => a.is_active).length,
      disabled: r.filter((a) => !a.is_active).length,
      superadmin: r.filter((a) => a.role === "superadmin").length,
      admin: r.filter((a) => a.role === "admin").length,
      moderator: r.filter((a) => a.role === "moderator").length,
      support: r.filter((a) => a.role === "support").length,
      with2fa: r.filter((a) => a.has_2fa).length,
      no2fa: r.filter((a) => !a.has_2fa).length,
      risk: r.filter((a) => privileged(a.role) && !a.has_2fa && a.is_active).length,
      lastLogin,
    };
  }, [rows]);
  return (
    <div className="metrics">
      <Metric icon="group" label="Всего админов" value={k.total} />
      <Metric icon="check_circle" label="Активных" value={k.active} />
      <Metric icon="block" label="Отключённых" value={k.disabled} tone={k.disabled ? "purple" : undefined} />
      <Metric icon="shield_person" label="Superadmin" value={k.superadmin} />
      <Metric icon="admin_panel_settings" label="Admin" value={k.admin} small />
      <Metric icon="gavel" label="Moderator" value={k.moderator} small />
      <Metric icon="support_agent" label="Support" value={k.support} small />
      <Metric icon="verified_user" label="С 2FA" value={`${k.with2fa}/${k.total}`} small />
      <Metric icon="gpp_bad" label="Без 2FA" value={k.no2fa} tone={k.no2fa ? "danger" : undefined} small />
      <Metric icon="warning" label="Привил. без 2FA" value={k.risk} tone={k.risk ? "danger" : undefined} small />
      <Metric icon="login" label="Последний вход" value={ago(k.lastLogin)} small />
    </div>
  );
}

// ---------------- Directory ----------------
type ActivityMap = Map<number, { lastAt: string; lastIp: string | null; count: number }>;
type SortKey = "email" | "role" | "last_login" | "created_at" | "score";

function DirectoryTab({ rows, activity, audit, guard, toast }: {
  rows: AdminAccount[] | null; activity: ActivityMap; audit: AuditEntry[];
  guard: (p: Promise<unknown>) => void; toast: (m: string) => void;
}) {
  const [q, setQ] = useState("");
  const [fRole, setFRole] = useState("all");
  const [fStatus, setFStatus] = useState("all");
  const [f2fa, setF2fa] = useState("all");
  const [sort, setSort] = useState<{ key: SortKey; dir: 1 | -1 }>({ key: "role", dir: -1 });
  const [sel, setSel] = useState<Set<number>>(new Set());
  const [detail, setDetail] = useState<AdminAccount | null>(null);
  const [showCreate, setShowCreate] = useState(false);

  const list = rows || [];
  const superCount = list.filter((a) => a.role === "superadmin" && a.is_active).length;

  const filtered = useMemo(() => {
    const out = list.filter((a) => {
      if (fRole !== "all" && a.role !== fRole) return false;
      if (fStatus === "active" && !a.is_active) return false;
      if (fStatus === "disabled" && a.is_active) return false;
      if (f2fa === "on" && !a.has_2fa) return false;
      if (f2fa === "off" && a.has_2fa) return false;
      if (q.trim()) { const s = q.toLowerCase(); if (![a.email, a.role, String(a.id)].some((x) => x.toLowerCase().includes(s))) return false; }
      return true;
    });
    out.sort((a, b) => {
      let av: string | number = "", bv: string | number = "";
      if (sort.key === "email") { av = a.email; bv = b.email; }
      else if (sort.key === "role") { av = RANK[a.role] || 0; bv = RANK[b.role] || 0; }
      else if (sort.key === "last_login") { av = a.last_login || ""; bv = b.last_login || ""; }
      else if (sort.key === "created_at") { av = a.created_at || ""; bv = b.created_at || ""; }
      else { av = securityScore(a).score; bv = securityScore(b).score; }
      return av < bv ? -sort.dir : av > bv ? sort.dir : 0;
    });
    return out;
  }, [list, q, fRole, fStatus, f2fa, sort]);

  const toggleSort = (key: SortKey) => setSort((s) => s.key === key ? { key, dir: s.dir === 1 ? -1 : 1 } : { key, dir: 1 });
  const sortArrow = (key: SortKey) => sort.key === key ? (sort.dir === 1 ? " ↑" : " ↓") : "";
  const allSel = filtered.length > 0 && filtered.every((a) => sel.has(a.id));

  const isLastSuper = (a: AdminAccount) => a.role === "superadmin" && a.is_active && superCount <= 1;
  // FIX: SUPERADMIN-13 - self-action guard (mirrors backend SUPERADMIN-1/2).
  // The backend already rejects self-demotion / self-disable with 400, but we
  // also block at the UI so the user never sees a confusing error toast. We
  // match by email (lowercased, same as login() stores in localStorage) since
  // admin_id is not persisted client-side.
  const selfEmail = (localStorage.getItem("admin_email") || "").toLowerCase();
  const isSelf = (a: AdminAccount) => a.email.toLowerCase() === selfEmail;

  function changeRole(a: AdminAccount, role: string) {
    if (role === a.role) return;
    if (isSelf(a) && role !== "superadmin") { toast("Нельзя понизить себя — попросите другого superadmin"); return; }
    if (role !== "superadmin" && isLastSuper(a)) { toast("Нельзя понизить последнего активного superadmin"); return; }
    if (!confirm(`Изменить роль ${a.email}: ${meta(a.role).label} → ${meta(role).label}?`)) return;
    guard(adminsApi.setAdminRole(a.id, role));
  }
  function toggleActive(a: AdminAccount) {
    if (a.is_active) {
      if (isSelf(a)) { toast("Нельзя отключить себя — используйте выход"); return; }
      if (isLastSuper(a)) { toast("Нельзя отключить последнего активного superadmin"); return; }
      if (!confirm(`Отключить ${a.email}? Все его сессии будут немедленно завершены (revoke).`)) return;
      guard(adminsApi.disableAdmin(a.id));
    } else guard(adminsApi.enableAdmin(a.id));
  }
  function reset2fa(a: AdminAccount) {
    if (!a.has_2fa) return;
    if (!confirm(`Сбросить 2FA для ${a.email}? Ему придётся заново пройти настройку при следующем входе.`)) return;
    guard(adminsApi.resetAdmin2fa(a.id));
  }
  function logoutAll(a: AdminAccount) {
    if (!confirm(`Завершить ВСЕ сессии ${a.email}? Все его access/refresh-токены будут отозваны — придётся войти заново.`)) return;
    guard(adminsApi.logoutAllAdmin(a.id)); toast("✅ Сессии завершены");
  }

  async function bulk(kind: "enable" | "disable" | "reset2fa") {
    const targets = list.filter((a) => sel.has(a.id));
    if (kind === "disable") {
      // FIX: SUPERADMIN-14 - bulk-disable must also skip self + last superadmin.
      if (targets.some(isSelf)) { toast("В выборке ваша учётка — снимите себя"); return; }
      if (targets.some(isLastSuper)) { toast("В выборке последний superadmin — снимите его"); return; }
      if (!confirm(`Отключить ${targets.length} админ(ов)? Их сессии будут завершены.`)) return;
    }
    if (kind === "reset2fa" && !confirm(`Сбросить 2FA у ${targets.filter((a) => a.has_2fa).length} админ(ов)?`)) return;
    // FIX: AUDIT-20 - per-item try/catch + count
    let ok = 0, failed = 0;
    for (const a of targets) {
      try {
        if (kind === "enable" && !a.is_active) await adminsApi.enableAdmin(a.id);
        else if (kind === "disable" && a.is_active) await adminsApi.disableAdmin(a.id);
        else if (kind === "reset2fa" && a.has_2fa) await adminsApi.resetAdmin2fa(a.id);
        ok++;
      } catch (e) { failed++; toast(`❌ ${a.email}: ${e}`); }
    }
    setSel(new Set()); guard(Promise.resolve());
    toast(`✅ Готово: ${ok}${failed ? `, ошибок: ${failed}` : ""}`);
  }

  function exportData(fmt: "csv" | "json") {
    const data = fmt === "json"
      ? JSON.stringify(filtered, null, 2)
      // FIX: AUDIT-14 - CSV escape fields containing comma/quote/newline
      : (() => {
          const csvEsc = (v: unknown) => /[",\n]/.test(String(v)) ? '"' + String(v).replace(/"/g, '""') + '"' : String(v);
          return "id,email,role,active,2fa,last_login,created_at\n" + filtered.map((a) =>
            [a.id, a.email, a.role, a.is_active, a.has_2fa, a.last_login || "", a.created_at || ""].map(csvEsc).join(",")).join("\n");
        })();
    const blob = new Blob([data], { type: "text/plain" });
    const el = document.createElement("a");
    el.href = URL.createObjectURL(blob); el.download = `admins.${fmt}`; el.click();
    URL.revokeObjectURL(el.href);  // FIX: AUDIT-92 - immediate revoke;  // FIX: F59 - release the blob URL after the download starts
  }

  return (
    <div className="page-stack">
      <div className="panel" style={{ padding: "var(--sp-3) var(--sp-4)" }}>
        <div className="section-head" style={{ margin: 0 }}>
          <div className="form-row" style={{ gap: "var(--sp-2)", flexWrap: "wrap" }}>
            <input style={{ width: 220 }} placeholder="Поиск: email, роль, ID" value={q} onChange={(e) => setQ(e.target.value)} />
            <Select width={150} ariaLabel="Роль" value={fRole} onChange={setFRole} options={[{ value: "all", label: "Все роли" }, ...ROLES.map((r) => ({ value: r, label: meta(r).label }))]} />
            <Select width={140} ariaLabel="Статус" value={fStatus} onChange={setFStatus} options={[{ value: "all", label: "Все статусы" }, { value: "active", label: "Активные" }, { value: "disabled", label: "Отключённые" }]} />
            <Select width={130} ariaLabel="2FA" value={f2fa} onChange={setF2fa} options={[{ value: "all", label: "2FA: все" }, { value: "on", label: "С 2FA" }, { value: "off", label: "Без 2FA" }]} />
          </div>
          <div className="form-row" style={{ gap: "var(--sp-2)" }}>
            <Select width={130} ariaLabel="Экспорт" value="" onChange={(v) => v && exportData(v as "csv")} options={[{ value: "", label: "Экспорт…" }, { value: "csv", label: "CSV" }, { value: "json", label: "JSON" }]} />
            <button className="btn" onClick={() => setShowCreate(true)}><span className="ms sm">person_add</span> Добавить</button>
          </div>
        </div>
        {sel.size > 0 && (
          <div className="form-row" style={{ gap: "var(--sp-2)", flexWrap: "wrap", marginTop: "var(--sp-3)", paddingTop: "var(--sp-3)", borderTop: "1px solid var(--border)" }}>
            <span className="pill pro">{sel.size} выбрано</span>
            <button className="btn ghost sm" onClick={() => bulk("enable")}><span className="ms sm">check_circle</span> Включить</button>
            <button className="btn ghost sm" onClick={() => bulk("disable")}><span className="ms sm">block</span> Отключить</button>
            <button className="btn ghost sm" onClick={() => bulk("reset2fa")}><span className="ms sm">lock_reset</span> Сбросить 2FA</button>
            <button className="btn ghost sm" onClick={() => setSel(new Set())}>Снять</button>
          </div>
        )}
      </div>

      <div className="panel">
        {rows === null ? <div className="loading">Загрузка…</div>
          : filtered.length === 0 ? (
            <EmptyState icon="group_off" title={list.length === 0 ? "Администраторов нет" : "Ничего не найдено"}
              desc={list.length === 0 ? "Добавьте первого администратора панели." : "Измените поиск или фильтры."}
              action={list.length === 0 ? <button className="btn" onClick={() => setShowCreate(true)}><span className="ms sm">person_add</span> Создать администратора</button> : undefined} />
          ) : (
            <div className="table-wrap sticky" tabIndex={0} style={{ border: "none" }}>
              <table className="tbl">
                <thead><tr>
                  <th style={{ width: 32 }}><input type="checkbox" className="fx-check" aria-label="Выбрать" checked={allSel} onChange={(e) => setSel(e.target.checked ? new Set(filtered.map((a) => a.id)) : new Set())} /></th>
                  <th style={{ cursor: "pointer" }} onClick={() => toggleSort("email")}>Администратор{sortArrow("email")}</th>
                  <th style={{ cursor: "pointer" }} onClick={() => toggleSort("role")}>Роль{sortArrow("role")}</th>
                  <th>Статус</th>
                  <th>2FA</th>
                  <th style={{ cursor: "pointer" }} onClick={() => toggleSort("score")}>Security{sortArrow("score")}</th>
                  <th style={{ cursor: "pointer" }} onClick={() => toggleSort("last_login")}>Последний вход{sortArrow("last_login")}</th>
                  <th>Активность</th>
                  <th>IP</th>
                  <th style={{ cursor: "pointer" }} onClick={() => toggleSort("created_at")}>Создан{sortArrow("created_at")}</th>
                  <th style={{ width: 120 }}>Действия</th>
                </tr></thead>
                <tbody>
                  {filtered.map((a) => {
                    const m = meta(a.role); const sc = securityScore(a); const act = activity.get(a.id);
                    return (
                      <tr key={a.id}>
                        <td><input type="checkbox" className="fx-check" aria-label="Выбрать" checked={sel.has(a.id)} onChange={() => setSel((s) => { const n = new Set(s); n.has(a.id) ? n.delete(a.id) : n.add(a.id); return n; })} /></td>
                        <td>
                          <div className="form-row" style={{ gap: 8, alignItems: "center", margin: 0, flexWrap: "nowrap" }}>
                            <span className="avatar">{initials(a.email)}</span>
                            <div style={{ minWidth: 0 }}>
                              <b style={{ cursor: "pointer", display: "block" }} onClick={() => setDetail(a)}>{a.email}</b>
                              <span className="muted" style={{ fontSize: 11 }}>ID {a.id}{isLastSuper(a) && " · защищён"}</span>
                            </div>
                          </div>
                        </td>
                        <td><span className={"pill " + m.cls} title={m.desc}><span className="ms sm" style={{ verticalAlign: "-3px", marginRight: 3 }}>{m.icon}</span>{m.label}</span></td>
                        <td><span className={"status-dot " + (a.is_active ? "on" : "off")} /><span className={"pill " + (a.is_active ? "ok" : "muted")}>{a.is_active ? "активен" : "отключён"}</span></td>
                        <td>{a.has_2fa ? <span className="pill ok"><span className="ms sm" style={{ verticalAlign: "-3px" }}>verified_user</span></span>
                          : <span className={"pill " + (privileged(a.role) ? "danger" : "muted")}>нет</span>}</td>
                        <td><span className={"pill " + scoreTone(sc.score)}>{sc.score}</span></td>
                        <td className="muted" style={{ whiteSpace: "nowrap" }} title={fmtDate(a.last_login)}>{ago(a.last_login)}</td>
                        <td className="muted" style={{ whiteSpace: "nowrap" }} title={act ? `${act.count} действий` : ""}>{act ? ago(act.lastAt) : "—"}</td>
                        <td className="code-key" style={{ fontSize: 11 }}>{act?.lastIp || "—"}</td>
                        <td className="muted" style={{ whiteSpace: "nowrap" }} title={fmtDate(a.created_at)}>{fmtDay(a.created_at)}</td>
                        <td>
                          <div className="form-row" style={{ gap: 2, flexWrap: "nowrap" }}>
                            <button className="btn ghost sm" title="Карточка" onClick={() => setDetail(a)}><span className="ms sm">visibility</span></button>
                            <button className={"btn ghost sm"} title={a.is_active ? "Отключить" : "Включить"} onClick={() => toggleActive(a)}><span className="ms sm">{a.is_active ? "block" : "check_circle"}</span></button>
                            {a.has_2fa && <button className="btn ghost sm" title="Сбросить 2FA" onClick={() => reset2fa(a)}><span className="ms sm">lock_reset</span></button>}
                          </div>
                        </td>
                      </tr>
                    );
                  })}
                </tbody>
              </table>
            </div>
          )}
      </div>

      {detail && (
        <AdminCard a={detail} isLastSuper={isLastSuper(detail)} activity={activity.get(detail.id)}
          history={audit.filter((e) => e.admin_id === detail.id || e.target_id === String(detail.id))}
          onClose={() => setDetail(null)}
          onRole={(r) => changeRole(detail, r)} onToggle={() => toggleActive(detail)} onReset2fa={() => reset2fa(detail)}
          onLogoutAll={() => logoutAll(detail)} />
      )}
      {showCreate && <CreateAdmin onClose={() => setShowCreate(false)} guard={guard} toast={toast} exists={list.map((a) => a.email)} />}
    </div>
  );
}

// ---------------- Admin detail card ----------------
function AdminCard({ a, isLastSuper, activity, history, onClose, onRole, onToggle, onReset2fa, onLogoutAll }: {
  a: AdminAccount; isLastSuper: boolean; activity?: { lastAt: string; lastIp: string | null; count: number };
  history: AuditEntry[]; onClose: () => void; onRole: (r: string) => void; onToggle: () => void; onReset2fa: () => void; onLogoutAll: () => void;
}) {
  const m = meta(a.role); const sc = securityScore(a);
  const [sessions, setSessions] = useState<AdminSession[] | null>(null);
  useEffect(() => { adminsApi.adminSessions(a.id).then((r) => setSessions(r.sessions)).catch(() => setSessions([])); }, [a.id]);
  return (
    <Modal title={a.email} icon={m.icon} onClose={onClose} wide
      footer={<>
        <button className="btn ghost spacer" disabled={isLastSuper} onClick={onToggle}>
          <span className="ms sm">{a.is_active ? "block" : "check_circle"}</span> {a.is_active ? "Отключить" : "Включить"}
        </button>
        <button className="btn ghost" onClick={onLogoutAll}><span className="ms sm">logout</span> Завершить все сессии</button>
        {a.has_2fa && <button className="btn ghost" onClick={onReset2fa}><span className="ms sm">lock_reset</span> Сбросить 2FA</button>}
      </>}>
      <div className="form-row" style={{ gap: 8, marginBottom: "var(--sp-4)", alignItems: "center" }}>
        <span className="avatar lg">{initials(a.email)}</span>
        <span className={"pill " + m.cls}><span className="ms sm" style={{ verticalAlign: "-3px", marginRight: 3 }}>{m.icon}</span>{m.label}</span>
        <span className={"pill " + (a.is_active ? "ok" : "muted")}>{a.is_active ? "активен" : "отключён"}</span>
        <span className={"pill " + (a.has_2fa ? "ok" : privileged(a.role) ? "danger" : "muted")}>2FA {a.has_2fa ? "вкл" : "выкл"}</span>
        <span className={"pill " + scoreTone(sc.score)}>Security {sc.score}/100</span>
        {isLastSuper && <span className="pill warn">последний superadmin</span>}
      </div>

      <div className="form-grid">
        <KV label="Email"><span className="code-key">{a.email}</span></KV>
        <KV label="ID"><span className="code-key">{a.id}</span></KV>
        <KV label="Роль">
          <Select ariaLabel="Роль" value={a.role} onChange={onRole} options={opts(ROLES)} />
        </KV>
        <KV label="Статус">{a.is_active ? "активен" : "отключён"}</KV>
        <KV label="Последний вход">{fmtDate(a.last_login)} <span className="muted">({ago(a.last_login)})</span></KV>
        <KV label="Последняя активность">{activity ? `${fmtDate(activity.lastAt)} · ${activity.count} действий` : "нет в журнале"}</KV>
        <KV label="Последний IP (из аудита)"><span className="code-key">{activity?.lastIp || "—"}</span></KV>
        <KV label="Создан">{fmtDate(a.created_at)}</KV>
        <KV label="Изменён">{fmtDate(a.updated_at)}</KV>
        <KV label="Поколение сессии (token_version)"><span className="code-key">{a.token_version}</span></KV>
      </div>

      {sc.issues.length > 0 && (
        <div style={{ marginTop: "var(--sp-4)" }}>
          <span className="panel-title sm" style={{ margin: "0 0 var(--sp-2)" }}><span className="ms sm">gpp_maybe</span> Замечания безопасности</span>
          <div className="chip-row">{sc.issues.map((i) => <span className="chip" key={i} style={{ borderColor: "var(--danger)" }}>{i}</span>)}</div>
        </div>
      )}

      <div style={{ marginTop: "var(--sp-4)" }}>
        <span className="panel-title sm" style={{ margin: "0 0 var(--sp-2)" }}><span className="ms sm">devices</span> Активные сессии (по входам)</span>
        {sessions === null ? <p className="cfg-hint" style={{ margin: 0 }}>Загрузка…</p>
          : sessions.length === 0 ? <p className="cfg-hint" style={{ margin: 0 }}>Успешных входов в журнале нет.</p>
            : (
              <div className="table-wrap" tabIndex={0} style={{ border: "none", maxHeight: 180, overflow: "auto" }}>
                <table className="tbl">
                  <thead><tr><th>Устройство</th><th>IP</th><th>Последний вход</th><th style={{ textAlign: "right" }}>Входов</th></tr></thead>
                  <tbody>
                    {sessions.map((s, i) => (
                      <tr key={i}>
                        <td><span className="ms sm" style={{ verticalAlign: "-3px", marginRight: 6, color: "var(--hint)" }}>computer</span>{s.device}</td>
                        <td className="code-key" style={{ fontSize: 11 }}>{s.ip}</td>
                        <td className="muted" style={{ whiteSpace: "nowrap" }}>{fmtDate(s.last_at)} <span style={{ fontSize: 11 }}>({ago(s.last_at)})</span></td>
                        <td style={{ textAlign: "right", fontVariantNumeric: "tabular-nums" }}>{s.count}</td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            )}
        <p className="cfg-hint" style={{ marginTop: "var(--sp-2)" }}>JWT-сессии без сокет-трекинга — сгруппировано по устройству+IP из истории входов. «Завершить все сессии» отзывает все токены (token_version).</p>
      </div>

      <div style={{ marginTop: "var(--sp-4)" }}>
        <span className="panel-title sm" style={{ margin: "0 0 var(--sp-2)" }}><span className="ms sm">history</span> История действий</span>
        {history.length === 0 ? <p className="cfg-hint" style={{ margin: 0 }}>Записей в журнале нет.</p> : (
          <div className="table-wrap" tabIndex={0} style={{ border: "none", maxHeight: 220, overflow: "auto" }}>
            <table className="tbl">
              <thead><tr><th>Дата</th><th>Действие</th><th>Объект</th><th>IP</th></tr></thead>
              <tbody>
                {history.slice(0, 25).map((e) => (
                  <tr key={e.id}>
                    <td className="muted" style={{ whiteSpace: "nowrap" }}>{fmtDate(e.created_at)}</td>
                    <td><span className={"pill " + (e.action.includes("disable") || e.action.includes("delete") ? "danger" : e.action.includes("role") ? "warn" : "ok")}>{e.action}</span></td>
                    <td className="code-key">{e.target_type ? `${e.target_type}:${e.target_id}` : "—"}</td>
                    <td className="code-key" style={{ fontSize: 11 }}>{e.ip || "—"}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </div>

      <p className="cfg-hint" style={{ marginTop: "var(--sp-4)" }}>
        <span className="ms sm" style={{ verticalAlign: "-3px" }}>info</span>{" "}
        Имя/фамилия, телефон, фото, timezone, язык, recovery-коды, passkeys и отдельный список активных сессий с гео/устройством не хранятся в модели администратора — для них потребуется расширение схемы. IP и устройство показываются из журнала действий (audit log), который пишет IP на каждое действие. Отключение администратора и смена 2FA уже инвалидируют все его токены через <code className="code-key">token_version</code>.
      </p>
    </Modal>
  );
}

// ---------------- Create admin ----------------
function CreateAdmin({ onClose, guard, toast, exists }: {
  onClose: () => void; guard: (p: Promise<unknown>) => void; toast: (m: string) => void; exists: string[];
}) {
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [confirm2, setConfirm2] = useState("");
  const [role, setRole] = useState("support");
  const [show, setShow] = useState(false);
  const [busy, setBusy] = useState(false);  // FIX: AUDIT12-L2 - create-admin in-flight guard

  const emailValid = /^[^\s@]+@[^\s@]+\.[^\s@]+$/.test(email.trim());
  const dup = exists.map((e) => e.toLowerCase()).includes(email.trim().toLowerCase());
  const st = pwStrength(password);
  const mismatch = confirm2.length > 0 && confirm2 !== password;
  const ok = emailValid && !dup && password.length >= 8 && !mismatch;

  function generate() { const p = genPassword(); setPassword(p); setConfirm2(p); setShow(true); }
  async function submit() {
    if (!ok) return;
    if (mfaRequired(role)) {
      if (!confirm(`Роль ${meta(role).label} требует 2FA — администратор настроит её при первом входе. Создать?`)) return;
    }
    setBusy(true);
    try {
      await guard(adminsApi.createAdmin(email.trim().toLowerCase(), password, role));
      toast("✅ Администратор создан"); onClose();
    } finally { setBusy(false); }
  }

  return (
    <Modal title="Новый администратор" icon="person_add" onClose={onClose} wide
      footer={<>
        <button className="btn ghost spacer" onClick={onClose}>Отмена</button>
        <button className="btn" disabled={!ok || busy} onClick={submit}><span className="ms sm">check</span> Создать</button>
      </>}>
      <div className="form-grid">
        <KV label="Email">
          <input placeholder="admin@example.com" value={email} onChange={(e) => setEmail(e.target.value)} autoFocus />
          {email && !emailValid && <span className="cfg-hint" style={{ color: "var(--danger)" }}>Неверный email</span>}
          {dup && <span className="cfg-hint" style={{ display: "block", marginTop: 4, fontSize: 12, color: "var(--danger)" }}>Такой email уже существует</span>}
        </KV>
        <KV label="Роль">
          <Select ariaLabel="Роль" value={role} onChange={setRole} options={ROLES.map((r) => ({ value: r, label: meta(r).label }))} />
          {/* FIX: UI - display:block so the role description drops onto its own line
              below the Select. KV wraps children in a <div>, so the `.cfg-field >
              .cfg-hint` rule (direct-child) never matched this nested span and it
              flowed inline to the right of the inline-block Select (collision). */}
          <span className="cfg-hint" style={{ display: "block", marginTop: 4, fontSize: 12, color: "var(--hint)", lineHeight: 1.45 }}>{meta(role).desc}</span>
        </KV>
        <KV label="Пароль">
          <div className="form-row" style={{ gap: 6, margin: 0, flexWrap: "nowrap" }}>
            <input style={{ flex: 1 }} type={show ? "text" : "password"} value={password} onChange={(e) => setPassword(e.target.value)} placeholder="минимум 8 символов" />
            <button className="btn ghost sm" title={show ? "Скрыть" : "Показать"} onClick={() => setShow((s) => !s)}><span className="ms sm">{show ? "visibility_off" : "visibility"}</span></button>
            <button className="btn ghost sm" title="Сгенерировать" onClick={generate}><span className="ms sm">auto_awesome</span></button>
          </div>
          {password && (
            <div className="form-row" style={{ gap: 6, margin: "6px 0 0", alignItems: "center" }}>
              <div style={{ flex: 1, height: 6, borderRadius: 3, background: "var(--panel-2)", overflow: "hidden" }}>
                <div style={{ width: `${(st.score / 6) * 100}%`, height: "100%", background: `var(--${st.cls === "ok" ? "accent" : st.cls})`, transition: "width .2s" }} />
              </div>
              <span className={"pill " + st.cls}>{st.label}</span>
            </div>
          )}
        </KV>
        <KV label="Подтверждение пароля">
          <input type={show ? "text" : "password"} value={confirm2} onChange={(e) => setConfirm2(e.target.value)} placeholder="повторите пароль" />
          {mismatch && <span className="cfg-hint" style={{ color: "var(--danger)" }}>Пароли не совпадают</span>}
        </KV>
      </div>
      <p className="cfg-hint" style={{ marginTop: "var(--sp-4)" }}>
        <span className="ms sm" style={{ verticalAlign: "-3px" }}>info</span>{" "}
        Бэкенд принимает email, пароль и роль. Имя, timezone, язык и приглашения по email (invite-flow вместо прямого пароля) потребуют расширения модели и почтового сервиса — пока администратор создаётся сразу с паролем. {mfaRequired(role) && <>Роль <b>{meta(role).label}</b> обязана включить 2FA при первом входе (политика <code className="code-key">mfa_required_roles</code>).</>}
      </p>
    </Modal>
  );
}

// ---------------- Roles & access (RBAC) ----------------
// Permission matrix derived from the REAL require_role decorators across api/admin/*.
// `min` = lowest role with any access; `elevated` = role required for the privileged
// (mutating) subset. Access is rank-based: role satisfies a requirement if its rank
// is >= the required rank (see core.services.admin_auth.role_allows).
interface Area { area: string; icon: string; min: string; elevated: string; note?: string }
const AREAS: Area[] = [
  { area: "Пользователи", icon: "group", min: "support", elevated: "admin", note: "просмотр/поиск — support; изменение баланса/блокировка — admin" },
  { area: "CRM (заметки, теги)", icon: "contacts", min: "support", elevated: "admin", note: "заметки — support; удаление — admin" },
  { area: "Поддержка / сообщения", icon: "forum", min: "support", elevated: "support" },
  { area: "Эффекты Mini App", icon: "auto_fix_high", min: "moderator", elevated: "admin" },
  { area: "Баннеры / Карусель", icon: "view_carousel", min: "moderator", elevated: "admin" },
  { area: "Галерея", icon: "photo_library", min: "moderator", elevated: "moderator" },
  { area: "Аналитика", icon: "insights", min: "admin", elevated: "admin" },
  { area: "Источники трафика", icon: "travel_explore", min: "admin", elevated: "admin" },
  { area: "Здоровье / очередь", icon: "monitor_heart", min: "admin", elevated: "admin" },
  { area: "Локализация", icon: "translate", min: "admin", elevated: "admin" },
  { area: "Каналы / Автопостинг", icon: "campaign", min: "admin", elevated: "admin" },
  { area: "Конкурсы", icon: "emoji_events", min: "admin", elevated: "admin" },
  { area: "Отзывы", icon: "reviews", min: "admin", elevated: "admin" },
  { area: "AI-агенты", icon: "smart_toy", min: "admin", elevated: "admin" },
  { area: "Экспорт CSV", icon: "download", min: "admin", elevated: "admin" },
  { area: "Тарифы / Биллинг", icon: "payments", min: "admin", elevated: "superadmin", note: "чтение/правки — admin; критичные операции — superadmin" },
  { area: "Рассылки / Промокоды", icon: "send", min: "admin", elevated: "admin" },
  { area: "Боты (White Label)", icon: "robot_2", min: "admin", elevated: "superadmin", note: "список — admin; создание/удаление — superadmin" },
  { area: "Feature Flags / Гейты", icon: "toggle_on", min: "admin", elevated: "superadmin", note: "просмотр — admin; изменение флагов — superadmin" },
  { area: "AI-роутинг", icon: "hub", min: "admin", elevated: "superadmin", note: "чтение — admin; управление аккаунтами/моделями — superadmin" },
  { area: "Router-контейнеры", icon: "dns", min: "superadmin", elevated: "superadmin" },
  { area: "Обслуживание", icon: "build", min: "superadmin", elevated: "superadmin" },
  { area: "Администраторы", icon: "shield_person", min: "superadmin", elevated: "superadmin" },
];

function cellState(role: string, area: Area): "full" | "view" | "none" {
  const r = RANK[role] || 0;
  if (r >= RANK[area.elevated]) return "full";
  if (r >= RANK[area.min]) return "view";
  return "none";
}

function RolesTab({ rows }: { rows: AdminAccount[] | null }) {
  const counts = useMemo(() => {
    const m: Record<string, number> = {};
    for (const a of rows || []) m[a.role] = (m[a.role] || 0) + 1;
    return m;
  }, [rows]);

  return (
    <div className="page-stack">
      <div className="prov-grid">
        {ROLES.slice().reverse().map((r) => {
          const m = meta(r); const areas = AREAS.filter((a) => cellState(r, a) !== "none").length;
          return (
            <div className="prov-card" key={r}>
              <div className="form-row" style={{ justifyContent: "space-between", margin: 0, alignItems: "center" }}>
                <div className="form-row" style={{ gap: 8, margin: 0, alignItems: "center" }}>
                  <span className={"pill " + m.cls}><span className="ms sm" style={{ verticalAlign: "-3px", marginRight: 3 }}>{m.icon}</span>{m.label}</span>
                  <span className="muted" style={{ fontSize: 12 }}>ранг {RANK[r]}</span>
                </div>
                <span className="pill muted">{counts[r] || 0} чел.</span>
              </div>
              <p className="cfg-hint" style={{ margin: "var(--sp-2) 0" }}>{m.desc}</p>
              <div className="form-row" style={{ gap: 6, margin: 0, flexWrap: "wrap" }}>
                <span className="pill ok">{areas} зон доступа</span>
                {mfaRequired(r) ? <span className="pill warn">2FA обязателен</span> : <span className="pill muted">2FA опционально</span>}
              </div>
            </div>
          );
        })}
      </div>

      <div className="panel">
        <div className="panel-title"><span className="ms sm">grid_on</span> Матрица доступа (по рангу ролей)</div>
        <p className="cfg-hint" style={{ marginTop: 0 }}>
          Доступ рассчитывается на сервере по рангу: роль удовлетворяет требованию, если её ранг ≥ требуемого (<code className="code-key">role_allows</code>). Ниже — реальные требования из <code className="code-key">require_role</code> по разделам админки.
        </p>
        <div className="table-wrap sticky" tabIndex={0} style={{ border: "none" }}>
          <table className="tbl">
            <thead><tr>
              <th>Раздел</th>
              {ROLES.slice().reverse().map((r) => <th key={r} style={{ textAlign: "center" }}>{meta(r).label}</th>)}
              <th>Мин. роль</th>
            </tr></thead>
            <tbody>
              {AREAS.map((a) => (
                <tr key={a.area}>
                  <td><span className="ms sm" style={{ verticalAlign: "-3px", marginRight: 6, color: "var(--hint)" }}>{a.icon}</span>{a.area}{a.note && <span className="cfg-hint" style={{ display: "block", marginLeft: 24 }}>{a.note}</span>}</td>
                  {ROLES.slice().reverse().map((r) => {
                    const s = cellState(r, a);
                    return <td key={r} style={{ textAlign: "center" }}>
                      {s === "full" ? <span className="pill ok" title="Полный доступ">✓</span>
                        : s === "view" ? <span className="pill warn" title="Просмотр / ограниченный">◑</span>
                          : <span className="muted">—</span>}
                    </td>;
                  })}
                  <td><span className={"pill " + meta(a.min).cls}>{meta(a.min).label}</span></td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
        <p className="cfg-hint" style={{ marginTop: "var(--sp-4)" }}>
          <span className="ms sm" style={{ verticalAlign: "-3px" }}>info</span>{" "}
          ✓ — полный доступ к разделу, ◑ — просмотр или ограниченный набор действий (мутации требуют более высокой роли). Кастомные роли, индивидуальные override-разрешения по каждому verb (view/create/edit/delete/export), группы администраторов и временные права потребуют замены ранговой модели на гранулярную RBAC-таблицу и поддержки в <code className="code-key">require_role</code> — сейчас доступ строго ранговый.
        </p>
      </div>
    </div>
  );
}

// ---------------- Security ----------------
function SecurityTab({ rows, audit }: { rows: AdminAccount[] | null; audit: AuditEntry[] }) {
  const list = rows || [];
  const cov = list.length ? Math.round((list.filter((a) => a.has_2fa).length / list.length) * 100) : 0;
  const risk = list.filter((a) => privileged(a.role) && !a.has_2fa && a.is_active);
  const neverLogged = list.filter((a) => !a.last_login && a.is_active);
  const stale = list.filter((a) => { const d = daysSince(a.last_login); return a.is_active && d !== null && d > 90; });
  const adminAudit = audit.filter((e) => /^(admin\.|auth)/.test(e.action) || e.target_type === "admin");

  return (
    <div className="page-stack">
      <div className="metrics">
        <Metric icon="verified_user" label="Покрытие 2FA" value={`${cov}%`} tone={cov < 100 ? "danger" : undefined} />
        <Metric icon="warning" label="Привил. без 2FA" value={risk.length} tone={risk.length ? "danger" : undefined} />
        <Metric icon="login" label="Ни разу не входили" value={neverLogged.length} tone={neverLogged.length ? "purple" : undefined} small />
        <Metric icon="schedule" label="Неактивны >90д" value={stale.length} tone={stale.length ? "purple" : undefined} small />
        <Metric icon="history" label="Событий аудита" value={audit.length} small />
      </div>

      <div className="panel">
        <div className="panel-title"><span className="ms sm">gpp_maybe</span> Требуют внимания</div>
        {risk.length === 0 && neverLogged.length === 0 && stale.length === 0 ? (
          <EmptyState icon="verified" title="Всё в порядке" desc="Все привилегированные администраторы используют 2FA, нет залежавшихся аккаунтов." />
        ) : (
          <div className="page-stack">
            {risk.length > 0 && <RiskRow icon="gpp_bad" cls="danger" title="Привилегированная роль без 2FA" admins={risk} hint="Включите 2FA или сбросьте, чтобы форсировать настройку при входе." />}
            {neverLogged.length > 0 && <RiskRow icon="login" cls="warn" title="Ни разу не входили" admins={neverLogged} hint="Возможно, приглашение не было использовано." />}
            {stale.length > 0 && <RiskRow icon="schedule" cls="warn" title="Неактивны более 90 дней" admins={stale} hint="Рассмотрите отключение неиспользуемых аккаунтов." />}
          </div>
        )}
      </div>

      <div className="panel">
        <div className="panel-title"><span className="ms sm">manage_history</span> Журнал безопасности (действия над администраторами)</div>
        {adminAudit.length === 0 ? <p className="cfg-hint" style={{ margin: 0 }}>Записей нет (или журнал недоступен для вашей роли).</p> : (
          <div className="table-wrap sticky" tabIndex={0} style={{ border: "none", maxHeight: 420, overflow: "auto" }}>
            <table className="tbl">
              <thead><tr><th>Дата</th><th>Действие</th><th>Кто (admin_id)</th><th>Объект</th><th>IP</th></tr></thead>
              <tbody>
                {adminAudit.slice(0, 60).map((e) => (
                  <tr key={e.id}>
                    <td className="muted" style={{ whiteSpace: "nowrap" }}>{fmtDate(e.created_at)}</td>
                    <td><span className={"pill " + (e.action.includes("disable") || e.action.includes("delete") ? "danger" : e.action.includes("role") || e.action.includes("2fa") ? "warn" : "ok")}>{e.action}</span></td>
                    <td className="muted">#{e.admin_id}</td>
                    <td className="code-key">{e.target_type ? `${e.target_type}:${e.target_id}` : "—"}</td>
                    <td className="code-key" style={{ fontSize: 11 }}>{e.ip || "—"}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </div>

      <div className="panel">
        <div className="panel-title"><span className="ms sm">policy</span> Политики и факторы аутентификации</div>
        <div className="form-grid">
          <KV label="Фактор аутентификации">TOTP (authenticator) — реализован сервером, self-service настройка/отключение.</KV>
          <KV label="Ревокация сессий">Через <code className="code-key">token_version</code>: отключение админа и смена 2FA немедленно инвалидируют все его токены (access+refresh).</KV>
          <KV label="MFA-политика">Роли admin и superadmin обязаны включить 2FA при первом входе (<code className="code-key">mfa_required_roles</code>).</KV>
          <KV label="IP allow-list">Доступ к админ-API ограничивается списком IP (<code className="code-key">admin_ip_allowlist</code>), если он задан.</KV>
        </div>
        <p className="cfg-hint" style={{ marginTop: "var(--sp-4)" }}>
          <span className="ms sm" style={{ verticalAlign: "-3px" }}>info</span>{" "}
          Отдельный список активных сессий с устройством/гео/Session-ID и принудительный «logout всех», история входов с результатом и причиной отказа, recovery/backup-коды, passkeys и WebAuthn, политика паролей (длина/история/срок), блокировка после N попыток и captcha, уведомления о входе/смене прав — требуют новых таблиц (sessions, login_attempts) и интеграций. Сейчас безопасность построена на TOTP + JWT с ревокацией через <code className="code-key">token_version</code> и журнале аудита с IP на каждое действие.
        </p>
      </div>
    </div>
  );
}

function RiskRow({ icon, cls, title, admins, hint }: { icon: string; cls: string; title: string; admins: AdminAccount[]; hint: string }) {
  return (
    <div className="cfg-field" style={{ padding: "var(--sp-3)", border: "1px solid var(--border)", borderRadius: "var(--r)" }}>
      <div className="form-row" style={{ gap: 8, margin: 0, alignItems: "center" }}>
        <span className={"pill " + cls}><span className="ms sm" style={{ verticalAlign: "-3px", marginRight: 3 }}>{icon}</span>{title}</span>
        <span className="muted" style={{ fontSize: 12 }}>{admins.length}</span>
      </div>
      <div className="chip-row" style={{ marginTop: "var(--sp-2)" }}>
        {admins.map((a) => <span className="chip" key={a.id}><span className="avatar" style={{ width: 18, height: 18, fontSize: 9, marginRight: 4 }}>{initials(a.email)}</span>{a.email}</span>)}
      </div>
      <span className="cfg-hint" style={{ marginTop: 4 }}>{hint}</span>
    </div>
  );
}

// ---------------- shared ----------------
function EmptyState({ icon, title, desc, action }: { icon: string; title: string; desc: string; action?: React.ReactNode }) {
  return (
    <div className="empty-state">
      <div className="es-icon"><span className="ms">{icon}</span></div>
      <p className="es-title">{title}</p>
      <p className="es-desc">{desc}</p>
      {action && <div style={{ marginTop: "var(--sp-3)" }}>{action}</div>}
    </div>
  );
}
function KV({ label, children }: { label: string; children: React.ReactNode }) {
  return <div className="cfg-field"><span className="cfg-cap">{label}</span><div>{children}</div></div>;
}
function Metric({ icon, label, value, tone, small }: { icon: string; label: string; value: number | string; tone?: "purple" | "danger"; small?: boolean }) {
  return (
    <div className={"metric" + (tone ? " " + tone : "")}>
      <span className="glow" />
      <div className="top"><span className="lbl">{label}</span><span className="ms sm">{icon}</span></div>
      <div><div className="num" style={small ? { fontSize: 16 } : undefined}>{typeof value === "number" ? value.toLocaleString("ru") : value}</div></div>
    </div>
  );
}
