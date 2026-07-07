import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { api, type AuditEntry, type AuditStats } from "../api";
import { Select } from "../components/Select";
import { Switch } from "../components/Switch";
import { useLatestGuard } from "../lib/latestGuard";
import { Modal } from "../components/Modal";

// Audit Center (ТЗ §8) — CloudTrail / Datadog / Splunk class, grounded in the REAL
// backend. The admin_audit_log row already stores before/after JSON + ip; the
// reworked /audit reader now exposes them (+ joined admin email/role) and supports
// rich filters/pagination, and /audit/stats powers the dashboard. Severity, category
// and status are DERIVED from the action verb client-side (clearly labelled) — never
// invented data. Capabilities that need columns we don't store (geo/ASN/VPN, device/
// OS/browser, session/trace ids, checksum/signature/immutability, true streaming) are
// honestly gated.

const PAGE = 100;
const RENDER_CAP = 400;
const WINDOWS = [
  { value: "7", label: "7 дней" }, { value: "30", label: "30 дней" },
  { value: "90", label: "90 дней" }, { value: "365", label: "Год" },
];
const DATE_PRESETS = [
  { value: "", label: "Любая дата" }, { value: "today", label: "Сегодня" },
  { value: "yesterday", label: "Вчера" }, { value: "hour", label: "Последний час" },
  { value: "24h", label: "24 часа" }, { value: "week", label: "Неделя" },
  { value: "month", label: "Месяц" },
];
const ROLES = [
  { value: "", label: "Все роли" }, { value: "superadmin", label: "Superadmin" },
  { value: "admin", label: "Admin" }, { value: "moderator", label: "Moderator" },
  { value: "support", label: "Support" },
];
const SEVERITIES = [
  { value: "", label: "Любая severity" }, { value: "security", label: "SECURITY" },
  { value: "warning", label: "WARNING" }, { value: "update", label: "UPDATE" },
  { value: "create", label: "CREATE" }, { value: "info", label: "INFO" },
];
const CAT_ICON: Record<string, string> = {
  banner: "ad_units", payment: "payments", admin: "shield_person", ai: "smart_toy",
  provider: "hub", localization: "translate", maintenance: "build", job: "bolt",
  promo: "sell", gate: "verified_user", broadcast: "campaign", user: "person",
  bot: "smart_toy", effect: "auto_awesome", contest: "emoji_events", crm: "contacts",
  feedback: "feedback", channel_post: "feed", referral: "share", flag: "flag",
  export: "download", business_config: "tune", moderation: "gavel", agent: "support_agent",
};

const DESTRUCTIVE = ["delete", "clear", "cancel", "flush", "revoke", "refund", "disable", "deactivate", "close", "purge", "remove", "reset"];
const CREATE_V = ["create", "make", "add", "upsert", "import"];
const UPDATE_V = ["update", "set", "edit", "toggle", "enable", "role", "settings", "interval", "image", "expiry"];

function categoryOf(action: string): string { return action.split(".", 1)[0] || "—"; }
function verbOf(action: string): string { const p = action.split("."); return p[p.length - 1] || ""; }
function severityOf(action: string): { key: string; label: string; cls: string; icon: string } {
  const a = action.toLowerCase(); const v = verbOf(a);
  if (a.startsWith("admin.") || /security|login|logout|password|2fa|moderation/.test(a))
    return { key: "security", label: "SECURITY", cls: "danger", icon: "shield" };
  if (DESTRUCTIVE.some((d) => v.startsWith(d))) return { key: "warning", label: "WARNING", cls: "warn", icon: "warning" };
  if (CREATE_V.some((c) => v.startsWith(c))) return { key: "create", label: "CREATE", cls: "ok", icon: "add_circle" };
  if (UPDATE_V.some((u) => v.startsWith(u))) return { key: "update", label: "UPDATE", cls: "pro", icon: "edit" };
  return { key: "info", label: "INFO", cls: "muted", icon: "info" };
}
const catIcon = (action: string) => CAT_ICON[categoryOf(action)] ?? "bolt";
const ROLE_CLS: Record<string, string> = { superadmin: "danger", admin: "pro", moderator: "warn", support: "muted" };

function fmtDate(s: string): string { return new Date(s).toLocaleString("ru", { day: "2-digit", month: "short", year: "numeric", hour: "2-digit", minute: "2-digit", second: "2-digit" }); }
function fmtTime(s: string): string { return new Date(s).toLocaleTimeString("ru", { hour: "2-digit", minute: "2-digit", second: "2-digit" }); }
function ago(s: string | null): string {
  if (!s) return "—";
  const m = Math.floor((Date.now() - new Date(s).getTime()) / 60000);
  if (m < 1) return "только что"; if (m < 60) return `${m} мин назад`;
  const h = Math.floor(m / 60); if (h < 24) return `${h} ч назад`;
  const d = Math.floor(h / 24); if (d < 30) return `${d} дн назад`;
  return new Date(s).toLocaleDateString("ru");
}
const fmtInt = (n: number | undefined) => (n ?? 0).toLocaleString("ru");

function rangeFor(preset: string): { since?: string; until?: string } {
  const now = new Date();
  const sod = (d: Date) => { const x = new Date(d); x.setHours(0, 0, 0, 0); return x; };
  if (preset === "today") return { since: sod(now).toISOString() };
  if (preset === "yesterday") { const y = new Date(now); y.setDate(y.getDate() - 1); return { since: sod(y).toISOString(), until: sod(now).toISOString() }; }
  if (preset === "hour") return { since: new Date(now.getTime() - 3600e3).toISOString() };
  if (preset === "24h") return { since: new Date(now.getTime() - 864e5).toISOString() };
  if (preset === "week") return { since: new Date(now.getTime() - 7 * 864e5).toISOString() };
  if (preset === "month") return { since: new Date(now.getTime() - 30 * 864e5).toISOString() };
  return {};
}

interface Filters { q: string; category: string; adminId: string; role: string; severity: string; targetType: string; targetId: string; preset: string }
const EMPTY: Filters = { q: "", category: "", adminId: "", role: "", severity: "", targetType: "", targetId: "", preset: "" };

function useDebounced<T>(v: T, ms = 300): T {
  const [d, setD] = useState(v);
  useEffect(() => { const t = setTimeout(() => setD(v), ms); return () => clearTimeout(t); }, [v, ms]);
  return d;
}

export function Audit() {
  const [days, setDays] = useState("30");
  const [stats, setStats] = useState<AuditStats | null>(null);
  const [view, setView] = useState<"table" | "timeline">("table");

  const [f, setF] = useState<Filters>(EMPTY);
  const dq = useDebounced(f.q);
  const [rows, setRows] = useState<AuditEntry[] | null>(null);
  const [page, setPage] = useState(0);
  const [err, setErr] = useState("");
  const [live, setLive] = useState(false);
  const [newCount, setNewCount] = useState(0);
  const [sel, setSel] = useState<Set<number>>(new Set());
  const [exporting, setExporting] = useState(false);
  const [detail, setDetail] = useState<AuditEntry | null>(null);
  const [saved, setSaved] = useState<{ name: string; f: Filters }[]>(() => {
    try { return JSON.parse(localStorage.getItem("audit_saved") || "[]"); } catch { return []; }
  });
  const newestId = useRef(0);
  const guardStats = useLatestGuard();
  const guardRows = useLatestGuard();

  const loadStats = useCallback(() => {
    const isLatest = guardStats();
    api.auditStats(Number(days))
      .then((s) => { if (isLatest()) setStats(s); })
      .catch(() => { if (isLatest()) setStats(null); });
  }, [days, guardStats]);
  useEffect(loadStats, [loadStats]);

  const query = useCallback((p: number) => {
    const r = rangeFor(f.preset);
    return {
      q: dq.trim() || undefined,
      action: f.category || undefined,
      admin_id: f.adminId.trim() ? Number(f.adminId.trim()) : undefined,
      target_type: f.targetType || undefined,
      target_id: f.targetId || undefined,
      since: r.since, until: r.until,
      limit: PAGE, offset: p * PAGE,
    };
  }, [dq, f.category, f.adminId, f.targetType, f.targetId, f.preset]);

  const load = useCallback((p: number) => {
    const isLatest = guardRows();
    setRows(null); setErr("");
    api.audit(query(p)).then((rs) => {
      if (!isLatest()) return;  // a newer filter/page request superseded this one
      setRows(rs); setSel(new Set());
      if (rs.length) newestId.current = Math.max(newestId.current, rs[0].id);
    }).catch((e) => { if (isLatest()) { setRows([]); setErr(String(e)); } });
  }, [query, guardRows]);
  useEffect(() => { load(page); }, [load, page]);
  useEffect(() => { setPage(0); }, [dq, f.category, f.adminId, f.targetType, f.targetId, f.preset]);

  // Live mode — poll page 0 and surface a "new events" counter.
  useEffect(() => {
    if (!live) return;
    const id = setInterval(() => {
      api.audit(query(0)).then((rs) => {
        const added = rs.filter((r) => r.id > newestId.current).length;
        if (added) setNewCount((c) => c + added);
        if (page === 0) { setRows(rs); /* FIX: AUDIT-2 - don't clear sel on live polls */ }
        if (rs.length) newestId.current = Math.max(newestId.current, rs[0].id);
      }).catch(() => {});
    }, 8000);
    return () => clearInterval(id);
  }, [live, query, page]);

  // Client-side refine: role + derived severity (not server columns).
  const visible = useMemo(() => {
    let list = rows || [];
    if (f.role) list = list.filter((r) => r.admin_role === f.role);
    if (f.severity) list = list.filter((r) => severityOf(r.action).key === f.severity);
    return list.slice(0, RENDER_CAP);
  }, [rows, f.role, f.severity]);

  const hasMore = (rows?.length ?? 0) === PAGE;
  const filtersOn = JSON.stringify(f) !== JSON.stringify(EMPTY);

  function quick(patch: Partial<Filters>) { setF({ ...EMPTY, ...patch }); }
  function saveCurrent() {
    const name = prompt("Название сохранённого фильтра:");
    if (!name) return;
    const next = [...saved.filter((s) => s.name !== name), { name, f }];
    setSaved(next); localStorage.setItem("audit_saved", JSON.stringify(next));
  }
  function delSaved(name: string) {
    const next = saved.filter((s) => s.name !== name);
    setSaved(next); localStorage.setItem("audit_saved", JSON.stringify(next));
  }

  function toggleSel(id: number) { setSel((s) => { const n = new Set(s); n.has(id) ? n.delete(id) : n.add(id); return n; }); }
  const chosen = () => (sel.size ? (rows || []).filter((r) => sel.has(r.id)) : visible);
  function copyIds() { navigator.clipboard?.writeText(chosen().map((r) => r.id).join(", ")); }
  function copyJson() { navigator.clipboard?.writeText(JSON.stringify(chosen(), null, 2)); }
  // Full server-side export of the entire FILTERED set (every matching row, not just
  // the loaded page). Role/severity are client-only refinements, so they aren't
  // applied here — the file covers all rows matching the server filters.
  async function exportAll() {
    setExporting(true); setErr("");
    try {
      const r = rangeFor(f.preset);
      await api.exportAuditCsv({
        action: f.category || undefined,
        admin_id: f.adminId.trim() ? Number(f.adminId.trim()) : undefined,
        target_type: f.targetType || undefined,
        target_id: f.targetId || undefined,
        q: dq.trim() || undefined,
        since: r.since, until: r.until,
      });
    } catch (e) { setErr(String(e)); } finally { setExporting(false); }
  }
  function exportData(fmt: "json" | "csv") {
    const rs = chosen();
    let data: string;
    if (fmt === "json") data = JSON.stringify(rs, null, 2);
    else data = "id,time,action,category,severity,admin,role,target,ip\n" + rs.map((r) =>
      [r.id, r.created_at, r.action, categoryOf(r.action), severityOf(r.action).key,
        r.admin_email ?? r.admin_id, r.admin_role ?? "", `${r.target_type ?? ""}:${r.target_id ?? ""}`, r.ip ?? ""]
        .map((x) => JSON.stringify(String(x))).join(",")).join("\n");
    const blob = new Blob([data], { type: "text/plain" });
    const a = document.createElement("a"); a.href = URL.createObjectURL(blob);
    a.download = `audit-export.${fmt}`; a.click();
    URL.revokeObjectURL(a.href);  // FIX: AUDIT-92 - immediate revoke;  // FIX: F60 - release the blob URL after the download starts
  }

  const b = stats?.buckets;
  const dayMax = Math.max(1, ...(stats?.by_day ?? []).map((d) => d.count));
  const catMax = Math.max(1, ...(stats?.by_category ?? []).map((c) => c.count));

  return (
    <div>
      <div className="section-head">
        <div>
          <h1 className="page-title">Аудит-центр</h1>
          <p className="page-sub">Неизменяемый журнал действий администраторов: поиск, расширенные фильтры, просмотр изменений (diff) и аналитика. Severity и категория выводятся из действия.</p>
        </div>
        <div className="form-row" style={{ gap: "var(--sp-2)", margin: 0 }}>
          <Select width={130} ariaLabel="Период статистики" value={days} onChange={setDays} options={WINDOWS} />
          <button className="btn ghost sm" onClick={() => { loadStats(); load(page); }}><span className="ms sm">refresh</span> Обновить</button>
        </div>
      </div>

      {err && <p className="note-err"><span className="ms sm">error</span>{err}<button className="btn ghost sm" onClick={() => setErr("")} style={{ marginLeft: "auto" }}>×</button></p>}

      <div className="page-stack">
        {/* Dashboard */}
        <div className="metrics">
          <Metric icon="receipt_long" label="Всего событий" value={fmtInt(stats?.total)} />
          <Metric icon="today" label="Сегодня" value={fmtInt(stats?.today)} tone="purple" />
          <Metric icon="schedule" label="За час" value={fmtInt(stats?.last_hour)} small />
          <Metric icon="add_circle" label="Создания" value={fmtInt(b?.create)} small />
          <Metric icon="edit" label="Изменения" value={fmtInt(b?.update)} small />
          <Metric icon="delete" label="Удаления" value={fmtInt(b?.delete)} tone={b?.delete ? "danger" : undefined} small />
          <Metric icon="shield" label="Безопасность" value={fmtInt(b?.security)} tone={b?.security ? "danger" : undefined} small />
          <Metric icon="group" label="Администраторов" value={`${fmtInt(stats?.distinct_admins)}/${fmtInt(stats?.admins_total)}`} small />
          <Metric icon="history" label="Последнее действие" value={ago(stats?.last_action_at ?? null)} small />
          <Metric icon="login" label="Последний вход" value={ago(stats?.last_login_at ?? null)} small />
        </div>

        {/* Statistics: activity chart + categories + top admins */}
        <div className="prov-grid" style={{ gridTemplateColumns: "2fr 1fr" }}>
          <div className="panel">
            <div className="panel-title sm"><span className="ms sm">bar_chart</span> Активность по дням</div>
            {!stats || stats.by_day.length === 0 ? <p className="cfg-hint">Нет данных за период.</p> : (
              <div style={{ display: "flex", alignItems: "flex-end", gap: 3, height: 110, padding: "8px 0" }}>
                {stats.by_day.map((d) => (
                  <div key={d.date} title={`${d.date}: ${d.count}`} style={{ flex: 1, minWidth: 2, height: `${Math.max(2, Math.round(d.count / dayMax * 100))}%`, background: "var(--accent)", borderRadius: "3px 3px 0 0", opacity: 0.85 }} />
                ))}
              </div>
            )}
            <div className="panel-title sm" style={{ marginTop: "var(--sp-3)" }}><span className="ms sm">category</span> По категориям</div>
            <div className="page-stack" style={{ gap: 6, marginTop: 6 }}>
              {(stats?.by_category ?? []).slice(0, 8).map((c) => (
                <button key={c.category} className="loc-ns" onClick={() => quick({ category: c.category })} style={{ cursor: "pointer" }}>
                  <span><span className="ms sm" style={{ verticalAlign: "-3px", marginRight: 6 }}>{CAT_ICON[c.category] ?? "bolt"}</span>{c.category}</span>
                  <span className="form-row" style={{ gap: 8, margin: 0, alignItems: "center", flex: 1, justifyContent: "flex-end" }}>
                    <span style={{ width: "40%", maxWidth: 160, height: 6, borderRadius: 3, background: "var(--panel-2)", overflow: "hidden" }}>
                      <span style={{ display: "block", width: `${c.count / catMax * 100}%`, height: "100%", background: "var(--accent)" }} />
                    </span>
                    <span className="muted" style={{ width: 44, textAlign: "right" }}>{fmtInt(c.count)}</span>
                  </span>
                </button>
              ))}
            </div>
          </div>

          <div className="panel">
            <div className="panel-title sm"><span className="ms sm">leaderboard</span> Активные администраторы</div>
            {!stats || stats.top_admins.length === 0 ? <p className="cfg-hint">Нет данных.</p> : (
              <div className="page-stack" style={{ gap: 8 }}>
                {stats.top_admins.map((a) => (
                  <button key={a.admin_id} className="loc-ns" style={{ cursor: "pointer" }} onClick={() => quick({ adminId: String(a.admin_id) })}>
                    <span style={{ minWidth: 0 }}>
                      <b style={{ fontSize: 12.5 }}>{a.email ?? `#${a.admin_id}`}</b>
                      {a.role && <span className={"pill " + (ROLE_CLS[a.role] ?? "muted")} style={{ marginLeft: 6, fontSize: 10 }}>{a.role}</span>}
                      <div className="muted" style={{ fontSize: 11 }}>{ago(a.last_at)}</div>
                    </span>
                    <span className="pill pro">{fmtInt(a.count)}</span>
                  </button>
                ))}
              </div>
            )}
          </div>
        </div>

        {/* Sticky toolbar: search + filters + quick + live */}
        <div className="panel" style={{ padding: "var(--sp-3)", position: "sticky", top: 0, zIndex: 6 }}>
          <div className="form-row" style={{ gap: "var(--sp-2)", flexWrap: "wrap", margin: 0 }}>
            {/* FIX: AUDIT12-M13/M14 - aria-label + maxLength 255 on audit log search. */}
            <input className="grow" style={{ minWidth: 220 }} placeholder="Поиск: действие, объект, IP… (Ctrl+/)" value={f.q} onChange={(e) => setF({ ...f, q: e.target.value })} maxLength={255} aria-label="Поиск по журналу аудита" />
            {/* FIX: AUDIT12-M13/M14 - aria-label + maxLength 32 on admin_id filter. */}
            <input type="number" placeholder="admin_id" style={{ width: 110 }} value={f.adminId} onChange={(e) => setF({ ...f, adminId: e.target.value })} min={0} max={10_000_000} aria-label="Фильтр по admin_id" />
            <Select width={150} ariaLabel="Роль" value={f.role} onChange={(v) => setF({ ...f, role: v })} options={ROLES} />
            <Select width={170} ariaLabel="Severity" value={f.severity} onChange={(v) => setF({ ...f, severity: v })} options={SEVERITIES} />
            <Select width={160} ariaLabel="Дата" value={f.preset} onChange={(v) => setF({ ...f, preset: v })} options={DATE_PRESETS} />
            {filtersOn && <button className="btn ghost sm" onClick={() => setF(EMPTY)}><span className="ms sm">close</span> Сброс</button>}
          </div>

          <div className="form-row" style={{ gap: 6, flexWrap: "wrap", marginTop: "var(--sp-3)", alignItems: "center" }}>
            <span className="muted" style={{ fontSize: 11 }}>Быстро:</span>
            <button className="chip" style={{ cursor: "pointer" }} onClick={() => quick({ preset: "today" })}>Сегодня</button>
            <button className="chip" style={{ cursor: "pointer" }} onClick={() => quick({ severity: "warning" })}>Удаления</button>
            <button className="chip" style={{ cursor: "pointer" }} onClick={() => quick({ severity: "create" })}>Создания</button>
            <button className="chip" style={{ cursor: "pointer" }} onClick={() => quick({ severity: "security" })}>Безопасность</button>
            <button className="chip" style={{ cursor: "pointer" }} onClick={() => quick({ category: "ai" })}>AI</button>
            <button className="chip" style={{ cursor: "pointer" }} onClick={() => quick({ category: "payment" })}>Платежи</button>
            <button className="chip" style={{ cursor: "pointer" }} onClick={() => quick({ category: "user" })}>Пользователи</button>
            <span style={{ flex: 1 }} />
            <button className="btn ghost sm" onClick={saveCurrent} disabled={!filtersOn} title="Сохранить текущий фильтр"><span className="ms sm">bookmark_add</span></button>
            <Switch checked={live} onChange={(v) => { setLive(v); setNewCount(0); }} label="Live" />
            {live && newCount > 0 && <button className="pill ok" style={{ cursor: "pointer" }} onClick={() => { setNewCount(0); setPage(0); load(0); }}>{newCount} новых ↑</button>}
          </div>

          {saved.length > 0 && (
            <div className="form-row" style={{ gap: 6, flexWrap: "wrap", marginTop: "var(--sp-2)", alignItems: "center" }}>
              <span className="muted" style={{ fontSize: 11 }}>Сохранённые:</span>
              {saved.map((s) => (
                <span key={s.name} className="chip">
                  <button style={{ background: "none", border: "none", color: "inherit", cursor: "pointer", padding: 0, font: "inherit" }} onClick={() => setF(s.f)}>{s.name}</button>
                  <button className="ms sm" style={{ background: "none", border: "none", color: "var(--hint)", cursor: "pointer" }} onClick={() => delSaved(s.name)} aria-label="Удалить">close</button>
                </span>
              ))}
            </div>
          )}

          {/* selection toolbar */}
          <div className="form-row" style={{ gap: "var(--sp-2)", flexWrap: "wrap", marginTop: "var(--sp-3)", paddingTop: "var(--sp-3)", borderTop: "1px solid var(--border)", alignItems: "center" }}>
            <div className="seg-tabs" style={{ margin: 0 }}>
              <button className={view === "table" ? "on" : ""} onClick={() => setView("table")}><span className="ms sm" style={{ verticalAlign: "-3px", marginRight: 4 }}>table_rows</span>Таблица</button>
              <button className={view === "timeline" ? "on" : ""} onClick={() => setView("timeline")}><span className="ms sm" style={{ verticalAlign: "-3px", marginRight: 4 }}>timeline</span>Timeline</button>
            </div>
            <span style={{ flex: 1 }} />
            {sel.size > 0 && <span className="pill pro">{sel.size} выбрано</span>}
            <span className="muted" style={{ fontSize: 11 }} title="Копирование/экспорт выбранных или видимых строк (текущая страница)">{sel.size ? "выбранные:" : "видимые:"}</span>
            <button className="btn ghost sm" onClick={copyIds}><span className="ms sm">tag</span> ID</button>
            <button className="btn ghost sm" onClick={copyJson}><span className="ms sm">data_object</span> JSON</button>
            <button className="btn ghost sm" onClick={() => exportData("csv")}><span className="ms sm">download</span> CSV</button>
            <button className="btn ghost sm" onClick={() => exportData("json")}><span className="ms sm">download</span> JSON</button>
            <button className="btn sm" disabled={exporting} onClick={exportAll} title="Серверный экспорт ВСЕХ строк под текущие фильтры (не только страница)">
              <span className="ms sm">{exporting ? "hourglass_top" : "cloud_download"}</span> {exporting ? "Экспорт…" : "Экспорт всего (CSV)"}
            </button>
          </div>
        </div>

        {/* Events */}
        <div className="panel">
          {rows === null ? <Skeleton />
            : visible.length === 0 ? (
              <EmptyState icon="manage_search" title={rows.length === 0 ? "Событий не найдено" : "Под клиентские фильтры ничего не подходит"}
                desc={rows.length === 0 ? (filtersOn ? "Измените или сбросьте фильтры — за выбранные условия записей нет." : "Журнал аудита пуст.") : "Снимите фильтр по роли или severity."}
                onRefresh={() => load(page)} />
            ) : view === "table" ? (
              <>
                <div className="table-wrap sticky" tabIndex={0} style={{ border: "none" }}>
                  <table className="tbl">
                    <thead><tr>
                      <th style={{ width: 28 }}><input type="checkbox" className="fx-check" aria-label="Выбрать" checked={visible.every((r) => sel.has(r.id))} onChange={(e) => setSel((s) => { const n = new Set(s); visible.forEach((r) => e.target.checked ? n.add(r.id) : n.delete(r.id)); return n; })} /></th>
                      <th>Время</th><th>Severity</th><th>Действие</th><th>Администратор</th><th>Объект</th><th>IP</th><th style={{ width: 30 }}></th>
                    </tr></thead>
                    <tbody>
                      {visible.map((r) => {
                        const sv = severityOf(r.action); const hasDiff = !!(r.before || r.after);
                        return (
                          <tr key={r.id} style={{ cursor: "pointer" }} onClick={() => setDetail(r)}>
                            <td onClick={(e) => e.stopPropagation()}><input type="checkbox" className="fx-check" aria-label="Выбрать" checked={sel.has(r.id)} onChange={() => toggleSel(r.id)} /></td>
                            <td className="muted" style={{ whiteSpace: "nowrap" }} title={fmtDate(r.created_at)}>{fmtTime(r.created_at)}</td>
                            <td><span className={"pill " + sv.cls} style={{ fontSize: 10 }}>{sv.label}</span></td>
                            <td><span className="ms sm" style={{ verticalAlign: "-3px", marginRight: 5, color: "var(--hint)" }}>{catIcon(r.action)}</span><span className="code-key" style={{ fontSize: 12 }}>{r.action}</span></td>
                            <td>{r.admin_email ? <span><b style={{ fontSize: 12.5 }}>{r.admin_email}</b>{r.admin_role && <span className={"pill " + (ROLE_CLS[r.admin_role] ?? "muted")} style={{ marginLeft: 5, fontSize: 9 }}>{r.admin_role}</span>}</span> : <span className="muted">#{r.admin_id}</span>}</td>
                            <td className="muted">{r.target_type ? <span className="code-key" style={{ fontSize: 11 }}>{r.target_type}:{r.target_id ?? ""}</span> : "—"}</td>
                            <td className="muted" style={{ fontSize: 11 }}>{r.ip ?? "—"}</td>
                            <td>{hasDiff && <span className="ms sm" style={{ color: "var(--hint)" }}>difference</span>}</td>
                          </tr>
                        );
                      })}
                    </tbody>
                  </table>
                </div>
                <Pager page={page} hasMore={hasMore} count={visible.length} onPrev={() => setPage((p) => p - 1)} onNext={() => setPage((p) => p + 1)} />
              </>
            ) : (
              <>
                <div className="page-stack" style={{ gap: 0 }}>
                  {visible.map((r) => {
                    const sv = severityOf(r.action);
                    return (
                      <button key={r.id} className="audit-tl" onClick={() => setDetail(r)}>
                        <span className={"audit-tl-dot " + sv.cls}><span className="ms sm">{sv.icon}</span></span>
                        <span style={{ minWidth: 0, flex: 1 }}>
                          <span className="form-row" style={{ margin: 0, gap: 8, alignItems: "center" }}>
                            <span className="code-key" style={{ fontSize: 12 }}>{r.action}</span>
                            <span className={"pill " + sv.cls} style={{ fontSize: 9 }}>{sv.label}</span>
                            {(r.before || r.after) && <span className="pill muted" style={{ fontSize: 9 }}>diff</span>}
                          </span>
                          <span className="muted" style={{ fontSize: 11.5 }}>
                            {r.admin_email ?? `#${r.admin_id}`}{r.target_type ? ` · ${r.target_type}:${r.target_id ?? ""}` : ""}{r.ip ? ` · ${r.ip}` : ""}
                          </span>
                        </span>
                        <span className="muted" style={{ fontSize: 11, whiteSpace: "nowrap" }} title={fmtDate(r.created_at)}>{fmtTime(r.created_at)}</span>
                      </button>
                    );
                  })}
                </div>
                <Pager page={page} hasMore={hasMore} count={visible.length} onPrev={() => setPage((p) => p - 1)} onNext={() => setPage((p) => p + 1)} />
              </>
            )}
        </div>

        <GatedCard icon="travel_explore" title="Geo / устройство / трассировка / неизменяемость"
          text="IP-гео (страна/город/ASN/ISP/VPN), устройство (browser/OS/platform), session/request/trace/correlation ID и криптографическая неизменяемость (checksum/hash/подпись) требуют расширения схемы admin_audit_log (и сбора user-agent/гео + хеш-цепочки записей). Реальный IP, before/after-снимки, автор и время уже доступны и показываются. Стриминг (SSE/WebSocket) и ClickHouse для десятков миллионов событий — на стороне инфраструктуры; здесь работают серверная паг* + Live-поллинг." />
      </div>

      {detail && <EventDrawer e={detail} onClose={() => setDetail(null)}
        onHistory={() => { setF({ ...EMPTY, targetType: detail.target_type || "", targetId: detail.target_id || "" }); setDetail(null); }}
        onAdmin={() => { setF({ ...EMPTY, adminId: String(detail.admin_id) }); setDetail(null); }} />}
    </div>
  );
}

// ---------- event drawer: full event + diff + JSON ----------
function diffFields(before: Record<string, unknown> | null, after: Record<string, unknown> | null) {
  const keys = new Set([...Object.keys(before || {}), ...Object.keys(after || {})]);
  const out: { field: string; b: unknown; a: unknown; kind: "added" | "removed" | "changed" }[] = [];
  for (const k of keys) {
    const bv = before?.[k]; const av = after?.[k];
    if (JSON.stringify(bv) === JSON.stringify(av)) continue;
    out.push({ field: k, b: bv, a: av, kind: bv === undefined ? "added" : av === undefined ? "removed" : "changed" });
  }
  return out;
}
const cell = (v: unknown) => v === undefined ? "—" : typeof v === "object" ? JSON.stringify(v) : String(v);

function EventDrawer({ e, onClose, onHistory, onAdmin }: { e: AuditEntry; onClose: () => void; onHistory: () => void; onAdmin: () => void }) {
  const sv = severityOf(e.action);
  const diffs = diffFields(e.before, e.after);
  const hasState = !!(e.before || e.after);
  return (
    <Modal title={e.action} icon={catIcon(e.action)} onClose={onClose} wide
      footer={<>
        <button className="btn ghost" onClick={onAdmin}><span className="ms sm">person</span> Действия админа</button>
        {e.target_type && <button className="btn ghost" onClick={onHistory}><span className="ms sm">history</span> История объекта</button>}
        <button className="btn spacer" onClick={() => navigator.clipboard?.writeText(JSON.stringify(e, null, 2))}><span className="ms sm">content_copy</span> Копировать JSON</button>
      </>}>
      <div className="form-grid">
        <KV k="Severity (выведено)"><span className={"pill " + sv.cls}>{sv.label}</span></KV>
        <KV k="Категория">{categoryOf(e.action)}</KV>
        <KV k="Администратор">{e.admin_email ?? `#${e.admin_id}`}{e.admin_role && <span className={"pill " + (ROLE_CLS[e.admin_role] ?? "muted")} style={{ marginLeft: 6 }}>{e.admin_role}</span>}</KV>
        <KV k="Время">{fmtDate(e.created_at)}</KV>
        <KV k="Объект">{e.target_type ? <span className="code-key">{e.target_type}:{e.target_id ?? ""}</span> : "—"}</KV>
        <KV k="IP-адрес"><span className="code-key">{e.ip ?? "—"}</span></KV>
        <KV k="Event ID"><span className="code-key">{e.id}</span></KV>
        <KV k="Статус (выведено)"><span className="pill ok">success</span></KV>
      </div>

      {hasState ? (
        <>
          {diffs.length > 0 && (
            <div className="cfg-field" style={{ marginTop: "var(--sp-4)" }}>
              <span className="cfg-cap"><span className="ms sm" style={{ verticalAlign: "-3px" }}>difference</span> Изменения полей ({diffs.length})</span>
              <div className="table-wrap" tabIndex={0} style={{ border: "1px solid var(--border)", marginTop: 6 }}>
                <table className="tbl"><thead><tr><th>Поле</th><th>Было</th><th>Стало</th></tr></thead>
                  <tbody>
                    {diffs.map((d) => (
                      <tr key={d.field}>
                        <td><span className="code-key" style={{ fontSize: 12 }}>{d.field}</span></td>
                        <td style={{ color: d.kind === "added" ? "var(--hint)" : "var(--danger)" }}>{cell(d.b)}</td>
                        <td style={{ color: d.kind === "removed" ? "var(--hint)" : "var(--ok)" }}>{cell(d.a)}</td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            </div>
          )}
          <div className="form-grid" style={{ marginTop: "var(--sp-3)" }}>
            <JsonBlock title="Before" obj={e.before} />
            <JsonBlock title="After" obj={e.after} />
          </div>
        </>
      ) : <p className="cfg-hint" style={{ marginTop: "var(--sp-4)" }}><span className="ms sm" style={{ verticalAlign: "-3px" }}>info</span> Это действие не сопровождается снимком состояния (before/after) — оно не меняет объект (например, экспорт или просмотр).</p>}
    </Modal>
  );
}

function JsonBlock({ title, obj }: { title: string; obj: Record<string, unknown> | null }) {
  return (
    <div className="cfg-field">
      <span className="cfg-cap">{title}</span>
      <pre className="log-view" style={{ maxHeight: 220, fontSize: 11.5 }}>{obj ? JSON.stringify(obj, null, 2) : "— нет данных —"}</pre>
    </div>
  );
}

// ---------- shared ----------
function KV({ k, children }: { k: string; children: React.ReactNode }) {
  return <div className="form-row" style={{ justifyContent: "space-between", margin: 0, fontSize: 13, padding: "6px 0", borderBottom: "1px solid var(--border)" }}><span className="muted">{k}</span><span style={{ fontWeight: 600, textAlign: "right" }}>{children}</span></div>;
}
function Pager({ page, hasMore, count, onPrev, onNext }: { page: number; hasMore: boolean; count: number; onPrev: () => void; onNext: () => void }) {
  if (page === 0 && !hasMore) return null;
  return (
    <div className="pager">
      <span className="muted">стр. {page + 1} · показано {count}{count >= RENDER_CAP ? ` (окно ${RENDER_CAP})` : ""}</span>
      <div className="pg-nums">
        <button className="btn ghost sm" disabled={page === 0} onClick={onPrev}>←</button>
        <button className="btn ghost sm" disabled={!hasMore} onClick={onNext}>→</button>
      </div>
    </div>
  );
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
function EmptyState({ icon, title, desc, onRefresh }: { icon: string; title: string; desc: string; onRefresh?: () => void }) {
  return (
    <div className="empty-state">
      <div className="es-icon"><span className="ms">{icon}</span></div>
      <p className="es-title">{title}</p>
      <p className="es-desc">{desc}</p>
      {onRefresh && <button className="btn ghost sm" style={{ marginTop: "var(--sp-3)" }} onClick={onRefresh}><span className="ms sm">refresh</span> Обновить</button>}
    </div>
  );
}
function GatedCard({ icon, title, text }: { icon: string; title: string; text: string }) {
  return (
    <div className="prov-card off">
      <div className="pc-head"><span className="prov-logo"><span className="ms">{icon}</span></span><div className="pc-name">{title} <span className="pill muted" style={{ marginLeft: 4, fontSize: 10 }}>требует расширения схемы</span></div></div>
      <p className="pc-desc">{text}</p>
    </div>
  );
}
function Skeleton() {
  return <div className="page-stack">{Array.from({ length: 8 }).map((_, i) => <div key={i} className="skeleton" style={{ height: 40 }} />)}</div>;
}
