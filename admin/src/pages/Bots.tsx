import { useCallback, useEffect, useMemo, useState } from "react";
import { botsApi, api, type BotInstanceRow, type BotStats, type BotStat, type AuditEntry, type BotTokenCheck } from "../api";
import { Select } from "../components/Select";
import { Switch } from "../components/Switch";
import { Modal } from "../components/Modal";

// White Label platform for multi-bot Telegram (ТЗ §0). Grounded in the REAL
// architecture: many bot tokens run on ONE shared backend (bot.multi launcher,
// single dispatcher), users attributed per-bot via User.bot_id (soft tenancy).
// Backed end-to-end: registry CRUD (title/token/active/default), encrypted tokens
// (only a masked tail is ever returned), per-bot real engagement (users/requests/
// last activity) and the audit log. Concepts the platform does NOT model yet —
// per-bot domains/environments/licenses/branding/deploy and per-bot config
// (models/keys/prices/locales) — are honestly gated with notes, never faked,
// because configuration is currently GLOBAL across all bots (hard per-tenant
// isolation is a documented later increment).

const EMPTY_STAT: BotStat = { users: 0, requests: 0, last_user_at: null, last_request_at: null };

function initials(s: string): string {
  const parts = s.trim().split(/\s+/).filter(Boolean);
  return ((parts[0]?.[0] || "") + (parts[1]?.[0] || parts[0]?.[1] || "")).toUpperCase() || "B";
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
// A bot's stats live under its id; the default bot ALSO owns the NULL-bot_id
// ("legacy") bucket, so fold that in for the default.
function statFor(b: BotInstanceRow, s: BotStats | null): BotStat {
  if (!s) return EMPTY_STAT;
  const own = s.stats[String(b.id)] || EMPTY_STAT;
  if (!b.is_default) return own;
  const legacy = s.stats["legacy"] || EMPTY_STAT;
  return {
    users: own.users + legacy.users,
    requests: own.requests + legacy.requests,
    last_user_at: [own.last_user_at, legacy.last_user_at].filter(Boolean).sort().slice(-1)[0] || null,
    last_request_at: [own.last_request_at, legacy.last_request_at].filter(Boolean).sort().slice(-1)[0] || null,
  };
}
// Connection state is REAL: tg_bot_id is filled by get_me() on first successful
// launch. No id yet ⇒ the launcher hasn't connected this token.
function connection(b: BotInstanceRow): { key: string; label: string; cls: string } {
  if (b.tg_bot_id) return { key: "connected", label: "подключён", cls: "ok" };
  return { key: "pending", label: "ожидает запуска", cls: "warn" };
}
function botStatus(b: BotInstanceRow): { key: string; label: string; cls: string } {
  if (!b.active) return { key: "disabled", label: "отключён", cls: "muted" };
  if (!b.tg_bot_id) return { key: "pending", label: "pending", cls: "warn" };
  return { key: "live", label: "работает", cls: "ok" };
}
const TOKEN_RE = /^\d{6,}:[A-Za-z0-9_-]{30,}$/;
function useDebounced<T>(v: T, ms = 200): T {
  const [d, setD] = useState(v);
  useEffect(() => { const t = setTimeout(() => setD(v), ms); return () => clearTimeout(t); }, [v, ms]);
  return d;
}

type Tab = "registry" | "architecture" | "deploy";

export function Bots() {
  const [tab, setTab] = useState<Tab>("registry");
  const [rows, setRows] = useState<BotInstanceRow[] | null>(null);
  const [stats, setStats] = useState<BotStats | null>(null);
  const [audit, setAudit] = useState<AuditEntry[]>([]);
  const [msg, setMsg] = useState("");

  const load = useCallback(() => {
    botsApi.list().then(setRows).catch((e) => { setMsg(String(e)); setRows([]); });
    botsApi.stats().then(setStats).catch(() => setStats(null));
    api.audit({ action: "bot.", limit: 200 }).then(setAudit).catch(() => setAudit([]));
  }, []);
  useEffect(() => { load(); }, [load]);

  const toast = (m: string) => setMsg(m);
  const guard = (p: Promise<unknown>) => p.then(load).catch((e) => setMsg(String(e)));

  return (
    <div>
      <div className="section-head">
        <div>
          <h1 className="page-title">Боты (White Label)</h1>
          <p className="page-sub">Платформа White Label: несколько Telegram-ботов на одном бэкенде. Токены шифруются; изменения применяются при следующем запуске лаунчера.</p>
        </div>
      </div>

      {msg && (
        <p className={msg.startsWith("✅") ? "note-ok" : "note-err"}>
          <span className="ms sm">{msg.startsWith("✅") ? "check_circle" : "error"}</span>
          {msg}<button className="btn ghost sm" onClick={() => setMsg("")} aria-label="Скрыть">×</button>
        </p>
      )}

      <div className="page-stack">
        <Dashboard rows={rows} stats={stats} />

        <div className="seg-tabs" style={{ marginBottom: 0 }}>
          <button className={tab === "registry" ? "on" : ""} onClick={() => setTab("registry")}><span className="ms sm" style={{ verticalAlign: "-3px", marginRight: 4 }}>smart_toy</span>Реестр ботов</button>
          <button className={tab === "architecture" ? "on" : ""} onClick={() => setTab("architecture")}><span className="ms sm" style={{ verticalAlign: "-3px", marginRight: 4 }}>account_tree</span>Архитектура</button>
          <button className={tab === "deploy" ? "on" : ""} onClick={() => setTab("deploy")}><span className="ms sm" style={{ verticalAlign: "-3px", marginRight: 4 }}>rocket_launch</span>Деплой и мониторинг</button>
        </div>

        {tab === "registry" ? <RegistryTab rows={rows} stats={stats} audit={audit} guard={guard} toast={toast} />
          : tab === "architecture" ? <ArchitectureTab rows={rows} />
            : <DeployTab rows={rows} stats={stats} />}
      </div>
    </div>
  );
}

// ---------------- Dashboard ----------------
function Dashboard({ rows, stats }: { rows: BotInstanceRow[] | null; stats: BotStats | null }) {
  const k = useMemo(() => {
    const r = rows || [];
    const lastReg = r.map((b) => b.created_at).filter(Boolean).sort().slice(-1)[0] || null;
    const lastReq = Object.values(stats?.stats || {}).map((s) => s.last_request_at).filter(Boolean).sort().slice(-1)[0] || null;
    return {
      total: r.length,
      active: r.filter((b) => b.active).length,
      disabled: r.filter((b) => !b.active).length,
      connected: r.filter((b) => b.tg_bot_id).length,
      pending: r.filter((b) => b.active && !b.tg_bot_id).length,
      def: r.filter((b) => b.is_default).length,
      users: stats?.totals.users ?? 0,
      requests: stats?.totals.requests ?? 0,
      lastReg, lastReq,
    };
  }, [rows, stats]);
  return (
    <div className="metrics">
      <Metric icon="smart_toy" label="Всего ботов" value={k.total} />
      <Metric icon="check_circle" label="Активных" value={k.active} />
      <Metric icon="block" label="Отключённых" value={k.disabled} tone={k.disabled ? "purple" : undefined} small />
      <Metric icon="link" label="Подключено" value={k.connected} small />
      <Metric icon="pending" label="Pending" value={k.pending} tone={k.pending ? "danger" : undefined} small />
      <Metric icon="star" label="По умолчанию" value={k.def} small />
      <Metric icon="group" label="Всего пользователей" value={k.users} />
      <Metric icon="bolt" label="Всего запросов" value={k.requests} />
      <Metric icon="schedule" label="Последний запрос" value={ago(k.lastReq)} small />
      <Metric icon="event" label="Последняя регистрация" value={ago(k.lastReg)} small />
    </div>
  );
}

// ---------------- Registry ----------------
type SortKey = "title" | "status" | "users" | "requests" | "created_at" | "last";

function RegistryTab({ rows, stats, audit, guard, toast }: {
  rows: BotInstanceRow[] | null; stats: BotStats | null; audit: AuditEntry[];
  guard: (p: Promise<unknown>) => void; toast: (m: string) => void;
}) {
  const [q, setQ] = useState(""); const dq = useDebounced(q);
  const [fStatus, setFStatus] = useState("all");
  const [fConn, setFConn] = useState("all");
  const [sort, setSort] = useState<{ key: SortKey; dir: 1 | -1 }>({ key: "users", dir: -1 });
  const [sel, setSel] = useState<Set<number>>(new Set());
  const [detail, setDetail] = useState<BotInstanceRow | null>(null);
  const [showCreate, setShowCreate] = useState(false);

  const list = rows || [];
  const filtered = useMemo(() => {
    const out = list.filter((b) => {
      if (fStatus !== "all" && botStatus(b).key !== fStatus) return false;
      if (fConn !== "all" && connection(b).key !== fConn) return false;
      if (dq.trim()) { const s = dq.toLowerCase(); if (![b.title, b.username || "", String(b.tg_bot_id || ""), String(b.id)].some((x) => x.toLowerCase().includes(s))) return false; }
      return true;
    });
    out.sort((a, b) => {
      const sa = statFor(a, stats), sb = statFor(b, stats);
      let av: string | number = "", bv: string | number = "";
      if (sort.key === "title") { av = a.title.toLowerCase(); bv = b.title.toLowerCase(); }
      else if (sort.key === "status") { av = a.active ? (a.tg_bot_id ? 2 : 1) : 0; bv = b.active ? (b.tg_bot_id ? 2 : 1) : 0; }
      else if (sort.key === "users") { av = sa.users; bv = sb.users; }
      else if (sort.key === "requests") { av = sa.requests; bv = sb.requests; }
      else if (sort.key === "created_at") { av = a.created_at || ""; bv = b.created_at || ""; }
      else { av = sa.last_request_at || ""; bv = sb.last_request_at || ""; }
      return av < bv ? -sort.dir : av > bv ? sort.dir : 0;
    });
    return out;
  }, [list, dq, fStatus, fConn, sort, stats]);

  const toggleSort = (key: SortKey) => setSort((s) => s.key === key ? { key, dir: s.dir === 1 ? -1 : 1 } : { key, dir: -1 });
  const arr = (key: SortKey) => sort.key === key ? (sort.dir === 1 ? " ↑" : " ↓") : "";
  const allSel = filtered.length > 0 && filtered.every((b) => sel.has(b.id));

  async function bulk(kind: "enable" | "disable" | "delete") {
    const targets = list.filter((b) => sel.has(b.id));
    if (kind === "delete" && !confirm(`Удалить ${targets.length} бот(ов)? Это действие необратимо.`)) return;
    if (kind === "disable" && targets.some((b) => b.is_default) && !confirm("В выборке бот по умолчанию — отключить всё равно?")) return;
    for (const b of targets) {
      // FIX: AUDIT-24 - per-item try/catch
      try {
        if (kind === "enable" && !b.active) await botsApi.update(b.id, { active: true });
        else if (kind === "disable" && b.active) await botsApi.update(b.id, { active: false });
        else if (kind === "delete") await botsApi.remove(b.id);
      } catch (e) { toast(`❌ ${b.title}: ${e}`); }
    }
    setSel(new Set()); guard(Promise.resolve()); toast("✅ Готово. Перезапустите лаунчер для применения.");
  }

  function exportData(fmt: "json" | "yaml" | "env") {
    // Tokens are never exported (encrypted, only masked tail is known to the panel).
    const safe = filtered.map((b) => ({ id: b.id, title: b.title, username: b.username, tg_bot_id: b.tg_bot_id, active: b.active, is_default: b.is_default, token_masked: b.token_masked }));
    let data = "";
    if (fmt === "json") data = JSON.stringify(safe, null, 2);
    else if (fmt === "yaml") data = safe.map((b) => `- id: ${b.id}\n  title: ${JSON.stringify(b.title)}\n  username: ${JSON.stringify(b.username || "")}\n  active: ${b.active}\n  default: ${b.is_default}`).join("\n");  // FIX: AUDIT-42 - escape username
    else data = safe.map((b) => `BOT_${b.id}_TITLE=${JSON.stringify(b.title)}\nBOT_${b.id}_USERNAME=${JSON.stringify(b.username || "")}\nBOT_${b.id}_ACTIVE=${b.active ? 1 : 0}`).join("\n");  // FIX: AUDIT-42 - escape ENV values
    const blob = new Blob([data], { type: "text/plain" }); const a = document.createElement("a");
    a.href = URL.createObjectURL(blob); a.download = `bots.${fmt}`; a.click();
    URL.revokeObjectURL(a.href);  // FIX: AUDIT-92 - immediate revoke;  // FIX: F61 - release the blob URL after the download starts
  }

  return (
    <div className="page-stack">
      <div className="panel" style={{ padding: "var(--sp-3) var(--sp-4)" }}>
        <div className="section-head" style={{ margin: 0 }}>
          <div className="form-row" style={{ gap: "var(--sp-2)", flexWrap: "wrap" }}>
            <input style={{ width: 220 }} placeholder="Поиск: название, @username, Bot ID" value={q} onChange={(e) => setQ(e.target.value)} />
            <Select width={150} ariaLabel="Статус" value={fStatus} onChange={setFStatus} options={[{ value: "all", label: "Все статусы" }, { value: "live", label: "Работают" }, { value: "pending", label: "Pending" }, { value: "disabled", label: "Отключены" }]} />
            <Select width={170} ariaLabel="Подключение" value={fConn} onChange={setFConn} options={[{ value: "all", label: "Все подключения" }, { value: "connected", label: "Подключены" }, { value: "pending", label: "Ожидают запуска" }]} />
          </div>
          <div className="form-row" style={{ gap: "var(--sp-2)" }}>
            <Select width={130} ariaLabel="Экспорт" value="" onChange={(v) => v && exportData(v as "json")} options={[{ value: "", label: "Экспорт…" }, { value: "json", label: "JSON" }, { value: "yaml", label: "YAML" }, { value: "env", label: "ENV" }]} />
            <button className="btn" onClick={() => setShowCreate(true)}><span className="ms sm">add</span> Добавить бота</button>
          </div>
        </div>
        {sel.size > 0 && (
          <div className="form-row" style={{ gap: "var(--sp-2)", flexWrap: "wrap", marginTop: "var(--sp-3)", paddingTop: "var(--sp-3)", borderTop: "1px solid var(--border)" }}>
            <span className="pill pro">{sel.size} выбрано</span>
            <button className="btn ghost sm" onClick={() => bulk("enable")}><span className="ms sm">check_circle</span> Включить</button>
            <button className="btn ghost sm" onClick={() => bulk("disable")}><span className="ms sm">block</span> Отключить</button>
            <button className="btn ghost sm" onClick={() => bulk("delete")}><span className="ms sm" style={{ color: "var(--danger)" }}>delete</span> Удалить</button>
            <button className="btn ghost sm" onClick={() => setSel(new Set())}>Снять</button>
          </div>
        )}
      </div>

      <div className="panel">
        {rows === null ? <div className="loading">Загрузка…</div>
          : filtered.length === 0 ? (
            <EmptyState icon="smart_toy" title={list.length === 0 ? "White Label-ботов нет" : "Ничего не найдено"}
              desc={list.length === 0 ? "Работает один бот из .env (BOT_TOKEN). Добавьте токен от @BotFather, чтобы запустить дополнительный бренд на этом же бэкенде." : "Измените поиск или фильтры."}
              action={list.length === 0 ? <button className="btn" onClick={() => setShowCreate(true)}><span className="ms sm">add</span> Создать White Label Bot</button> : undefined} />
          ) : (
            <div className="table-wrap sticky" tabIndex={0} style={{ border: "none" }}>
              <table className="tbl">
                <thead><tr>
                  <th style={{ width: 32 }}><input type="checkbox" className="fx-check" aria-label="Выбрать" checked={allSel} onChange={(e) => setSel(e.target.checked ? new Set(filtered.map((b) => b.id)) : new Set())} /></th>
                  <th style={{ cursor: "pointer" }} onClick={() => toggleSort("title")}>Бот{arr("title")}</th>
                  <th>@username</th>
                  <th>Bot ID</th>
                  <th style={{ cursor: "pointer" }} onClick={() => toggleSort("status")}>Статус{arr("status")}</th>
                  <th>Подключение</th>
                  <th style={{ cursor: "pointer", textAlign: "right" }} onClick={() => toggleSort("users")}>Польз.{arr("users")}</th>
                  <th style={{ cursor: "pointer", textAlign: "right" }} onClick={() => toggleSort("requests")}>Запросов{arr("requests")}</th>
                  <th style={{ cursor: "pointer" }} onClick={() => toggleSort("last")}>Посл. запрос{arr("last")}</th>
                  <th style={{ cursor: "pointer" }} onClick={() => toggleSort("created_at")}>Создан{arr("created_at")}</th>
                  <th>Default</th>
                  <th style={{ width: 90 }}>Действия</th>
                </tr></thead>
                <tbody>
                  {filtered.map((b) => {
                    const st = botStatus(b); const cn = connection(b); const s = statFor(b, stats);
                    return (
                      <tr key={b.id}>
                        <td><input type="checkbox" className="fx-check" aria-label="Выбрать" checked={sel.has(b.id)} onChange={() => setSel((x) => { const n = new Set(x); n.has(b.id) ? n.delete(b.id) : n.add(b.id); return n; })} /></td>
                        <td>
                          <div className="form-row" style={{ gap: 8, alignItems: "center", margin: 0, flexWrap: "nowrap" }}>
                            <span className="avatar">{initials(b.title)}</span>
                            <div style={{ minWidth: 0 }}>
                              <b style={{ cursor: "pointer", display: "block" }} onClick={() => setDetail(b)}>{b.title}</b>
                              <span className="muted" style={{ fontSize: 11 }}>ID {b.id}</span>
                            </div>
                          </div>
                        </td>
                        <td className="muted">{b.username ? "@" + b.username : "—"}</td>
                        <td className="code-key" style={{ fontSize: 11 }}>{b.tg_bot_id || "—"}</td>
                        <td><span className={"status-dot " + (st.key === "live" ? "on" : st.key === "pending" ? "cool" : "off")} /><span className={"pill " + st.cls}>{st.label}</span></td>
                        <td><span className={"pill " + cn.cls}>{cn.label}</span></td>
                        <td style={{ textAlign: "right" }}>{s.users.toLocaleString("ru")}</td>
                        <td style={{ textAlign: "right" }}>{s.requests.toLocaleString("ru")}</td>
                        <td className="muted" style={{ whiteSpace: "nowrap" }} title={fmtDate(s.last_request_at)}>{ago(s.last_request_at)}</td>
                        <td className="muted" style={{ whiteSpace: "nowrap" }} title={fmtDate(b.created_at)}>{fmtDay(b.created_at)}</td>
                        <td>{b.is_default ? <span className="pill ok">★</span> : <button className="btn ghost sm" title="Сделать ботом по умолчанию" onClick={() => confirm(`Сделать «${b.title}» ботом по умолчанию?`) && guard(botsApi.update(b.id, { is_default: true }))}>сделать</button>}</td>
                        <td>
                          <div className="form-row" style={{ gap: 2, flexWrap: "nowrap" }}>
                            <button className="btn ghost sm" title="Карточка" onClick={() => setDetail(b)}><span className="ms sm">visibility</span></button>
                            <button className="btn ghost sm" title={b.active ? "Отключить" : "Включить"} onClick={() => guard(botsApi.update(b.id, { active: !b.active }))}><span className="ms sm">{b.active ? "block" : "check_circle"}</span></button>
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
        <BotCard b={detail} stat={statFor(detail, stats)}
          history={audit.filter((e) => e.target_id === String(detail.id))}
          guard={guard} toast={toast} onClose={() => setDetail(null)} />
      )}
      {showCreate && <CreateBot onClose={() => setShowCreate(false)} guard={guard} toast={toast} titles={list.map((b) => b.title.toLowerCase())} hasDefault={list.some((b) => b.is_default)} />}
    </div>
  );
}

// ---------------- Bot detail ----------------
function BotCard({ b, stat, history, guard, toast, onClose }: {
  b: BotInstanceRow; stat: BotStat; history: AuditEntry[];
  guard: (p: Promise<unknown>) => void; toast: (m: string) => void; onClose: () => void;
}) {
  const [title, setTitle] = useState(b.title);
  const [rotate, setRotate] = useState("");
  const [showRotate, setShowRotate] = useState(false);
  const st = botStatus(b); const cn = connection(b);
  const rotateValid = rotate === "" || TOKEN_RE.test(rotate.trim());

  function saveTitle() { if (title.trim() && title.trim() !== b.title) guard(botsApi.update(b.id, { title: title.trim() })); }
  function doRotate() {
    if (!TOKEN_RE.test(rotate.trim())) { toast("Неверный формат токена"); return; }
    if (!confirm("Заменить токен бота? Старый токен перестанет работать, изменения применятся при перезапуске лаунчера.")) return;
    guard(botsApi.update(b.id, { token: rotate.trim() })); setRotate(""); toast("✅ Токен заменён. Перезапустите лаунчер.");
  }

  return (
    <Modal title={b.title} icon="smart_toy" onClose={onClose} wide
      footer={<>
        <button className="btn ghost spacer" onClick={() => guard(botsApi.update(b.id, { active: !b.active }))}><span className="ms sm">{b.active ? "block" : "check_circle"}</span> {b.active ? "Отключить" : "Включить"}</button>
        <button className="btn danger" onClick={() => { if (confirm(`Удалить бота «${b.title}»? Необратимо.`)) { guard(botsApi.remove(b.id)); onClose(); } }}><span className="ms sm">delete</span> Удалить</button>
      </>}>
      <div className="form-row" style={{ gap: 8, marginBottom: "var(--sp-3)", alignItems: "center", flexWrap: "wrap" }}>
        <span className="avatar lg">{initials(b.title)}</span>
        <span className={"pill " + st.cls}>{st.label}</span>
        <span className={"pill " + cn.cls}>{cn.label}</span>
        {b.is_default && <span className="pill ok">по умолчанию</span>}
      </div>
      <div style={{ marginBottom: "var(--sp-4)" }}>
        <TokenCheck run={() => botsApi.check(b.id)} label="Проверить токен (getMe)" />
      </div>

      <div className="form-grid">
        <KV label="Название (бренд)">
          <div className="form-row" style={{ gap: 6, margin: 0, flexWrap: "nowrap" }}>
            <input style={{ flex: 1 }} value={title} onChange={(e) => setTitle(e.target.value)} />
            <button className="btn ghost sm" disabled={!title.trim() || title.trim() === b.title} onClick={saveTitle} title="Сохранить"><span className="ms sm">save</span></button>
          </div>
        </KV>
        <KV label="@username">{b.username ? <a href={`https://t.me/${b.username}`} target="_blank" rel="noreferrer">@{b.username}</a> : <span className="muted">появится после подключения</span>}</KV>
        <KV label="Telegram Bot ID"><span className="code-key">{b.tg_bot_id || "—"}</span></KV>
        <KV label="Instance ID"><span className="code-key">{b.id}</span></KV>
        <KV label="Токен (маска)"><span className="code-key">{b.token_masked}</span> <span className="cfg-hint">полный токен не хранится в открытом виде</span></KV>
        <KV label="Бот по умолчанию">{b.is_default ? "да — владеет legacy-пользователями (bot_id = NULL)" : <button className="btn ghost sm" onClick={() => confirm("Сделать ботом по умолчанию?") && guard(botsApi.update(b.id, { is_default: true }))}>сделать по умолчанию</button>}</KV>
        <KV label="Создан">{fmtDate(b.created_at)}</KV>
        <KV label="Изменён">{fmtDate(b.updated_at)}</KV>
      </div>

      <div style={{ marginTop: "var(--sp-4)" }}>
        <span className="panel-title sm" style={{ margin: "0 0 var(--sp-2)" }}><span className="ms sm">monitoring</span> Реальная статистика (атрибуция через bot_id)</span>
        <div className="metrics">
          <Metric icon="group" label="Пользователей" value={stat.users} small />
          <Metric icon="bolt" label="Запросов" value={stat.requests} small />
          <Metric icon="person_add" label="Посл. пользователь" value={ago(stat.last_user_at)} small />
          <Metric icon="schedule" label="Посл. запрос" value={ago(stat.last_request_at)} small />
        </div>
      </div>

      <div style={{ marginTop: "var(--sp-4)" }}>
        <span className="panel-title sm" style={{ margin: "0 0 var(--sp-2)" }}><span className="ms sm">key</span> Ротация токена (security)</span>
        <div className="form-row" style={{ gap: 6, margin: 0, flexWrap: "nowrap" }}>
          <input style={{ flex: 1 }} type={showRotate ? "text" : "password"} placeholder="новый токен 123456:ABC…" value={rotate} onChange={(e) => setRotate(e.target.value)} />
          <button className="btn ghost sm" onClick={() => setShowRotate((s) => !s)}><span className="ms sm">{showRotate ? "visibility_off" : "visibility"}</span></button>
          <button className="btn" disabled={!rotate.trim() || !rotateValid} onClick={doRotate}><span className="ms sm">autorenew</span> Заменить</button>
        </div>
        {!rotateValid && <span className="cfg-hint" style={{ color: "var(--danger)" }}>Формат: цифры, двоеточие, ≥30 символов</span>}
        {rotate.trim() && rotateValid && <div style={{ marginTop: 6 }}><TokenCheck run={() => botsApi.checkToken(rotate.trim())} label="Проверить новый токен" /></div>}
      </div>

      <div style={{ marginTop: "var(--sp-4)" }}>
        <span className="panel-title sm" style={{ margin: "0 0 var(--sp-2)" }}><span className="ms sm">history</span> История изменений</span>
        {history.length === 0 ? <p className="cfg-hint" style={{ margin: 0 }}>Записей нет.</p> : (
          <div style={{ display: "flex", flexDirection: "column", gap: 4 }}>
            {history.slice(0, 8).map((e) => (
              <div key={e.id} className="form-row" style={{ justifyContent: "space-between", fontSize: 12, margin: 0 }}>
                <span><span className={"pill " + (e.action.includes("delete") ? "danger" : "ok")}>{e.action}</span> <span className="muted">#{e.admin_id} · {e.ip || "—"}</span></span>
                <span className="muted">{fmtDate(e.created_at)}</span>
              </div>
            ))}
          </div>
        )}
      </div>

      <p className="cfg-hint" style={{ marginTop: "var(--sp-4)" }}>
        <span className="ms sm" style={{ verticalAlign: "-3px" }}>info</span>{" "}
        Описание, Mini App URL, домен, environment, язык, timezone, лицензия и брендинг (лого/тема/цвета) не хранятся для отдельного бота — конфигурация платформы сейчас <b>общая для всех ботов</b> (см. вкладку «Архитектура»). Лаунчер работает в режиме polling, поэтому webhook/allowed-updates не используются. Команды бота, About, Menu Button и Business Mode настраиваются через Bot API — потребуют отдельного эндпоинта.
      </p>
    </Modal>
  );
}

// ---------------- Create bot ----------------
function CreateBot({ onClose, guard, toast, titles, hasDefault }: {
  onClose: () => void; guard: (p: Promise<unknown>) => void; toast: (m: string) => void; titles: string[]; hasDefault: boolean;
}) {
  const [title, setTitle] = useState("");
  const [token, setToken] = useState("");
  const [show, setShow] = useState(false);
  const [isDefault, setIsDefault] = useState(false);
  const [busy, setBusy] = useState(false);  // FIX: AUDIT12-L2 - create-bot in-flight guard

  const tokenValid = TOKEN_RE.test(token.trim());
  const dup = titles.includes(title.trim().toLowerCase());
  const ok = title.trim().length > 0 && tokenValid && !dup;

  async function submit() {
    if (!ok) return;
    setBusy(true);
    try {
      await guard(botsApi.create(title.trim(), token.trim(), isDefault));
      toast("✅ Бот добавлен. Перезапустите лаунчер, чтобы он начал работать."); onClose();
    } finally { setBusy(false); }
  }

  return (
    <Modal title="Новый White Label Bot" icon="add_circle" onClose={onClose} wide
      footer={<>
        <button className="btn ghost spacer" onClick={onClose}>Отмена</button>
        <button className="btn" disabled={!ok || busy} onClick={submit}><span className="ms sm">check</span> Создать</button>
      </>}>
      <div className="form-grid">
        <KV label="Название (бренд)">
          <input placeholder="Например, Acme AI" value={title} onChange={(e) => setTitle(e.target.value)} autoFocus />
          {dup && <span className="cfg-hint" style={{ color: "var(--danger)" }}>Бот с таким названием уже есть</span>}
        </KV>
        <KV label="Токен от @BotFather">
          <div className="form-row" style={{ gap: 6, margin: 0, flexWrap: "nowrap" }}>
            <input style={{ flex: 1 }} type={show ? "text" : "password"} placeholder="123456789:ABCdef…" value={token} onChange={(e) => setToken(e.target.value)} />
            <button className="btn ghost sm" onClick={() => setShow((s) => !s)}><span className="ms sm">{show ? "visibility_off" : "visibility"}</span></button>
          </div>
          {token && !tokenValid && <span className="cfg-hint" style={{ color: "var(--danger)" }}>Неверный формат токена</span>}
          {token && tokenValid && <span className="cfg-hint" style={{ color: "var(--accent)" }}>Формат корректен · хранится в зашифрованном виде</span>}
          {tokenValid && <div style={{ marginTop: 6 }}><TokenCheck run={() => botsApi.checkToken(token.trim())} /></div>}
        </KV>
      </div>
      <div className="form-row" style={{ gap: 12, marginTop: "var(--sp-3)", alignItems: "center" }}>
        <Switch checked={isDefault} onChange={setIsDefault} label="Сделать ботом по умолчанию" />
        {isDefault && hasDefault && <span className="pill warn">текущий бот по умолчанию будет снят</span>}
      </div>
      <p className="cfg-hint" style={{ marginTop: "var(--sp-4)" }}>
        <span className="ms sm" style={{ verticalAlign: "-3px" }}>info</span>{" "}
        Бэкенд принимает название, токен и флаг «по умолчанию». @username и Bot ID определятся автоматически через <code className="code-key">get_me()</code> при первом запуске лаунчера. Slug, описание, домен, Mini App URL, язык, timezone, environment, логотип и favicon — это per-bot конфигурация, которой сейчас нет в модели (см. вкладку «Архитектура»); бот сразу активен и работает на общем бэкенде.
      </p>
    </Modal>
  );
}

// ---------------- Architecture ----------------
// What is currently GLOBAL (shared by every bot) vs. not modelled per-bot. Each row
// points to the page that actually owns that configuration today.
interface ConfigRow { area: string; icon: string; scope: "global" | "none"; page: string; note: string }
const CONFIG: ConfigRow[] = [
  { area: "AI-модели и роутинг", icon: "hub", scope: "global", page: "AI-роутинг", note: "Аккаунты, модели и стратегия маршрутизации общие для всех ботов." },
  { area: "API-ключи провайдеров", icon: "key", scope: "global", page: "Ключи API", note: "Один набор ключей на платформу (OpenAI и пр.)." },
  { area: "Провайдеры медиа/видео", icon: "dns", scope: "global", page: "Провайдеры", note: "Kill-switch провайдеров общий." },
  { area: "Тарифы и подписки", icon: "payments", scope: "global", page: "Тарифы / Подписки", note: "Цены, паки и подписки задаются глобально." },
  { area: "Функции и гейты", icon: "toggle_on", scope: "global", page: "Функции и гейты", note: "Feature-флаги и гейт-каналы применяются ко всем ботам." },
  { area: "Локализации", icon: "translate", scope: "global", page: "Локализация", note: "Тексты интерфейса общие (8 языков)." },
  { area: "Эффекты Mini App", icon: "auto_fix_high", scope: "global", page: "Эффекты", note: "Каталог эффектов общий." },
  { area: "Карусель / баннеры", icon: "view_carousel", scope: "global", page: "Карусель", note: "Слайды Mini App общие." },
  { area: "Брендинг / тема / цвета", icon: "palette", scope: "none", page: "—", note: "Логотип, тема, primary/accent, шрифты, splash — не моделируются per-bot." },
  { area: "Домены и Mini App URL", icon: "language", scope: "none", page: "—", note: "Один домен Mini App на платформу; per-bot домены/SSL/DNS не моделируются." },
  { area: "Environment (dev/stage/prod)", icon: "lan", scope: "none", page: "—", note: "Окружение задаётся на уровне бэкенда (ENV), не на бота." },
  { area: "Лицензия / seats / лимиты", icon: "verified", scope: "none", page: "—", note: "Лицензирование клиентов White Label не моделируется." },
];

function ArchitectureTab({ rows }: { rows: BotInstanceRow[] | null }) {
  const n = (rows || []).length;
  return (
    <div className="page-stack">
      <div className="panel">
        <div className="panel-title"><span className="ms sm">account_tree</span> Как устроен White Label</div>
        <div className="form-grid">
          <KV label="Модель"><b>Один бэкенд — много ботов.</b> Лаунчер <code className="code-key">bot.multi</code> опрашивает (polling) все активные токены через один диспетчер; обработчики и логика общие.</KV>
          <KV label="Мульти-аренда">Soft-tenancy: пользователь привязан к боту через <code className="code-key">User.bot_id</code> (ставится один раз при <code className="code-key">/start</code>). Это даёт атрибуцию и сегментацию без дублирования логики.</KV>
          <KV label="Безопасность токенов">Токены шифруются (та же крипта, что у ключей AI-аккаунтов); наружу отдаётся только маска последних 6 символов.</KV>
          <KV label="Бот по умолчанию">Владеет legacy-пользователями (<code className="code-key">bot_id = NULL</code>) и служит фолбэком маршрутизации.</KV>
        </div>
        <p className="cfg-hint" style={{ marginTop: "var(--sp-3)" }}>
          Сейчас зарегистрировано <b>{n}</b> бот(ов). Архитектура масштабируется на неограниченное число ботов без изменения кода — добавление токена не требует деплоя, только перезапуска лаунчера.
        </p>
      </div>

      <div className="panel">
        <div className="panel-title"><span className="ms sm">tune</span> Конфигурация: общая vs по боту</div>
        <p className="cfg-hint" style={{ marginTop: 0 }}>Где сегодня живёт каждая настройка. «Общая» — применяется ко всем ботам; «—» — не моделируется на уровне бота.</p>
        <div className="table-wrap sticky" tabIndex={0} style={{ border: "none" }}>
          <table className="tbl">
            <thead><tr><th>Подсистема</th><th>Область</th><th>Где настраивается</th><th>Комментарий</th></tr></thead>
            <tbody>
              {CONFIG.map((c) => (
                <tr key={c.area}>
                  <td><span className="ms sm" style={{ verticalAlign: "-3px", marginRight: 6, color: "var(--hint)" }}>{c.icon}</span>{c.area}</td>
                  <td>{c.scope === "global" ? <span className="pill pro">общая</span> : <span className="pill muted">не модел.</span>}</td>
                  <td className="muted">{c.page}</td>
                  <td className="cfg-hint" style={{ margin: 0 }}>{c.note}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
        <p className="cfg-hint" style={{ marginTop: "var(--sp-4)" }}>
          <span className="ms sm" style={{ verticalAlign: "-3px" }}>info</span>{" "}
          Индивидуальные модели/цены/подписки/функции/ключи/провайдеры/локализации/эффекты <b>на каждого бота</b>, версионирование конфигураций, клонирование, бэкапы и собственные темы требуют перехода от soft-tenancy к <b>hard-изоляции</b>: композитные ключи (<code className="code-key">bot_id</code> в таблицах конфигов) + слой переопределений поверх глобальных значений. Это задокументированный следующий инкремент архитектуры — он включается без переписывания текущей модели (глобальные значения становятся дефолтом, per-bot — override).
        </p>
      </div>
    </div>
  );
}

// ---------------- Deploy & monitoring ----------------
function DeployTab({ rows, stats }: { rows: BotInstanceRow[] | null; stats: BotStats | null }) {
  const list = rows || [];
  return (
    <div className="page-stack">
      <div className="panel">
        <div className="panel-title"><span className="ms sm">rocket_launch</span> Деплой</div>
        <div className="form-grid">
          <KV label="Модель деплоя"><b>Единый деплой.</b> Все боты работают на одном кодовом образе и бэкенде — отдельной версии/коммита/билда на бота нет.</KV>
          <KV label="Применение изменений">Добавление/выключение/удаление бота и ротация токена применяются при следующем <b>перезапуске лаунчера</b> (он читает активные инстансы на старте).</KV>
          <KV label="Health платформы">БД, Redis, очередь и воркеры — общие для всех ботов. Их состояние — на странице <b>«Здоровье»</b>.</KV>
          <KV label="Подключение бота">Реальный сигнал: бот «подключён», когда лаунчер успешно вызвал <code className="code-key">get_me()</code> и заполнил <code className="code-key">tg_bot_id</code>/<code className="code-key">@username</code>.</KV>
        </div>
      </div>

      <div className="panel">
        <div className="panel-title"><span className="ms sm">lan</span> Состояние подключения ботов</div>
        {rows === null ? <div className="loading">Загрузка…</div>
          : list.length === 0 ? <EmptyState icon="lan" title="Ботов нет" desc="Добавьте бота в реестре, чтобы увидеть его состояние." />
            : (
              <div className="table-wrap" tabIndex={0} style={{ border: "none" }}>
                <table className="tbl">
                  <thead><tr><th>Бот</th><th>Статус</th><th>Подключение</th><th style={{ textAlign: "right" }}>Пользователей</th><th>Последний запрос</th></tr></thead>
                  <tbody>
                    {list.map((b) => {
                      const st = botStatus(b); const cn = connection(b); const s = statFor(b, stats);
                      return (
                        <tr key={b.id}>
                          <td><span className="avatar" style={{ width: 22, height: 22, fontSize: 10, marginRight: 6 }}>{initials(b.title)}</span>{b.title}</td>
                          <td><span className={"status-dot " + (st.key === "live" ? "on" : st.key === "pending" ? "cool" : "off")} /><span className={"pill " + st.cls}>{st.label}</span></td>
                          <td><span className={"pill " + cn.cls}>{cn.label}</span></td>
                          <td style={{ textAlign: "right" }}>{s.users.toLocaleString("ru")}</td>
                          <td className="muted">{ago(s.last_request_at)}</td>
                        </tr>
                      );
                    })}
                  </tbody>
                </table>
              </div>
            )}
      </div>

      <div className="panel">
        <div className="panel-title"><span className="ms sm">monitoring</span> Мониторинг и аналитика</div>
        <p className="cfg-hint" style={{ marginTop: 0 }}>
          Реальные per-bot метрики — пользователи и запросы (атрибуция через <code className="code-key">bot_id</code>) — показаны в реестре и карточке бота. Глобальные DAU/MAU, retention, конверсия, выручка и популярные модели — на странице <b>«Аналитика»</b>.
        </p>
        <p className="cfg-hint" style={{ marginTop: "var(--sp-3)" }}>
          <span className="ms sm" style={{ verticalAlign: "-3px" }}>info</span>{" "}
          Версии/коммиты/билды/логи деплоя и rollback на бота, per-bot CPU/RAM/latency/uptime, бэкап-восстановление и автоматические бэкапы конфигов — требуют per-bot изоляции (см. «Архитектура») и таблицы событий с <code className="code-key">bot_id</code>. Разбивка аналитики по боту в реальном времени появится, когда события генерации начнут нести <code className="code-key">bot_id</code> напрямую (сейчас он выводится через пользователя).
        </p>
      </div>
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
// Live token probe (Telegram getMe — one read-only call, NOT polling). Shows the
// real @username / Bot ID / latency, or why the token is rejected, before save.
function TokenCheck({ run, label = "Проверить токен" }: { run: () => Promise<BotTokenCheck>; label?: string }) {
  const [busy, setBusy] = useState(false);
  const [res, setRes] = useState<BotTokenCheck | null>(null);
  const [err, setErr] = useState("");
  async function go() {
    setBusy(true); setErr(""); setRes(null);
    try { setRes(await run()); } catch (e) { setErr(String(e)); } finally { setBusy(false); }
  }
  return (
    <div className="form-row" style={{ gap: 8, margin: 0, alignItems: "center", flexWrap: "wrap" }}>
      <button className="btn ghost sm" disabled={busy} onClick={go}>
        <span className="ms sm">{busy ? "hourglass_empty" : "wifi_tethering"}</span> {busy ? "Проверка…" : label}
      </button>
      {res && (res.ok
        ? <span className="cfg-hint" style={{ color: "var(--accent)", margin: 0 }}>✅ @{res.username || "—"} · Bot ID {res.tg_bot_id} · {res.latency_ms} мс</span>
        : <span className="cfg-hint" style={{ color: "var(--danger)", margin: 0 }}>✕ {res.detail || "токен недействителен"}{res.status_code ? ` (HTTP ${res.status_code})` : ""}</span>)}
      {err && <span className="cfg-hint" style={{ color: "var(--danger)", margin: 0 }}>{err}</span>}
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
