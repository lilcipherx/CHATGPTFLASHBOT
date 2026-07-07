import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { useLatestGuard } from "../lib/latestGuard";  // FIX: AUDIT13-M19
import { adminFetch, logout } from "../api";  // FIX: B18 - logout on 401
import { Select } from "../components/Select";
import { Switch } from "../components/Switch";
import { Modal } from "../components/Modal";

// Enterprise localization editor (ТЗ §8). Grounded in the REAL backend: bot text
// overrides stored as {locale:{key:text}} in the pricing KV table, applied live
// without a redeploy. Namespace (key prefix), variables ({placeholders}), status
// (override vs default), per-language coverage and per-key history are all derived
// from real data (key shape, i18n dicts, the audit log). Workflow concepts not
// modelled server-side (review states, comments, glossary/TM corpus, AI provider
// calls, language-pack CRUD, heavy import formats) are honestly gated, never faked.

// JSON wrapper over the shared `adminFetch` — inherits credential handling plus the
// transparent token refresh on 401 (no premature "session expired" mid-session).
async function lReq<T>(path: string, init: RequestInit = {}): Promise<T> {
  const res = await adminFetch(path, {
    ...init,
    headers: { ...(init.headers ?? {}), "Content-Type": "application/json" },
  });
  if (res.status === 401) { logout(); window.dispatchEvent(new CustomEvent("admin:unauth")); throw new Error("session expired"); }  // FIX: B18 + AUDIT-H8
  if (!res.ok) throw new Error(`API ${res.status}`);
  return res.json() as Promise<T>;
}

interface LocaleOpt { code: string; label: string }
interface Item { key: string; default: string; override: string | null }
interface Payload { locale: string; locales: LocaleOpt[]; items: Item[] }
interface LangStat { code: string; label: string; rtl: boolean; is_default: boolean; translated: number; missing: number; overrides: number; percent: number }
interface StatsPayload { total: number; languages: LangStat[] }
interface HistEntry { id: number; admin_id: number; action: string; created_at: string; text: string | null }
interface AuditRow { id: number; admin_id: number; action: string; target_id: string | null; created_at: string }

const apiL = {
  get: (locale: string) => lReq<Payload>(`/localization?locale=${encodeURIComponent(locale)}`),
  stats: () => lReq<StatsPayload>("/localization/stats"),
  history: (locale: string, key: string) => lReq<HistEntry[]>(`/localization/history?locale=${encodeURIComponent(locale)}&key=${encodeURIComponent(key)}`),
  recent: () => lReq<AuditRow[]>("/audit?action=localization&limit=50"),
  put: (locale: string, key: string, text: string) => lReq<{ ok: boolean }>("/localization", { method: "PUT", body: JSON.stringify({ locale, key, text }) }),
  del: (locale: string, key: string) => lReq<{ ok: boolean; existed: boolean }>(`/localization?locale=${encodeURIComponent(locale)}&key=${encodeURIComponent(key)}`, { method: "DELETE" }),
  translate: (locale: string, key: string) => lReq<{ text: string }>("/localization/translate", { method: "POST", body: JSON.stringify({ locale, key }) }),
};

const VAR_RE = /\{([^{}]+)\}/g;
const SIMPLE_VAR = /^\w+$/;
function variables(text: string): string[] {
  const out = new Set<string>();
  for (const m of text.matchAll(VAR_RE)) { const inner = m[1].trim(); if (SIMPLE_VAR.test(inner)) out.add(inner); }
  return [...out];
}
const isICU = (text: string) => /\{\s*\w+\s*,\s*(plural|select|selectordinal)\s*,/.test(text);
function namespaceOf(key: string): string { const i = key.indexOf("."); return i > 0 ? key.slice(0, i) : "general"; }
function effective(it: Item): string { return it.override ?? it.default; }
function statusOf(it: Item): { key: string; label: string; cls: string } {
  if (it.override !== null) return { key: "custom", label: "переопределён", cls: "pro" };
  if (!it.default) return { key: "missing", label: "нет перевода", cls: "danger" };
  return { key: "default", label: "стандарт", cls: "muted" };
}
// QA issues for a draft value vs its default (placeholder parity is the important one).
function qaIssues(def: string, value: string): string[] {
  const out: string[] = [];
  const dv = new Set(variables(def)); const vv = new Set(variables(value));
  const missing = [...dv].filter((v) => !vv.has(v));
  const extra = [...vv].filter((v) => !dv.has(v));
  if (missing.length) out.push(`пропущены переменные: ${missing.map((v) => "{" + v + "}").join(", ")}`);
  if (extra.length) out.push(`лишние переменные: ${extra.map((v) => "{" + v + "}").join(", ")}`);
  if (/ {2,}/.test(value)) out.push("двойные пробелы");
  if (/^\s|\s$/.test(value)) out.push("пробелы по краям");
  if (/\n{3,}/.test(value)) out.push("лишние переносы строк");
  if (value.length > 220) out.push("очень длинная строка");
  return out;
}
function fmtDate(s: string): string { return new Date(s).toLocaleString("ru", { day: "2-digit", month: "short", year: "numeric", hour: "2-digit", minute: "2-digit" }); }
function ago(s: string | null): string {
  if (!s) return "—";
  const d = Math.floor((Date.now() - new Date(s).getTime()) / 86400000);
  if (d <= 0) return "сегодня"; if (d === 1) return "вчера"; if (d < 30) return `${d} дн назад`;
  return new Date(s).toLocaleDateString("ru");
}
function useDebounced<T>(v: T, ms = 200): T {
  const [d, setD] = useState(v);
  useEffect(() => { const t = setTimeout(() => setD(v), ms); return () => clearTimeout(t); }, [v, ms]);
  return d;
}
const EMOJIS = ["✅", "❌", "⚠️", "🔥", "✨", "🎁", "💎", "🚀", "👍", "💰", "📷", "🎬", "🎵", "⭐", "🔔", "💬"];
const PAGE = 50;

export function Localization() {
  const [locale, setLocale] = useState("ru");
  const [locales, setLocales] = useState<LocaleOpt[]>([{ code: "ru", label: "🇷🇺 Русский" }]);
  const [items, setItems] = useState<Item[] | null>(null);
  const [draft, setDraft] = useState<Record<string, string>>({});
  const [stats, setStats] = useState<StatsPayload | null>(null);
  const [recent, setRecent] = useState<AuditRow[]>([]);
  const [msg, setMsg] = useState("");

  const [search, setSearch] = useState(""); const dq = useDebounced(search);
  const [ns, setNs] = useState("all");
  const [fStatus, setFStatus] = useState("all");
  const [fFlag, setFFlag] = useState("all");
  const [sort, setSort] = useState<{ key: "key" | "status" | "len"; dir: 1 | -1 }>({ key: "key", dir: 1 });
  const [page, setPage] = useState(0);
  const [sel, setSel] = useState<Set<string>>(new Set());
  const [editor, setEditor] = useState<string | null>(null);
  const [showLangs, setShowLangs] = useState(false);
  const searchRef = useRef<HTMLInputElement>(null);

  // FIX: AUDIT13-M19 - guard against out-of-order locale loads. Rapidly switching the
  // language Select fires overlapping apiL.get() calls; without this a slower earlier
  // response could resolve last and overwrite items/draft with the wrong language.
  const guard = useLatestGuard();
  const load = useCallback(async (loc: string) => {
    const isLatest = guard();
    try {
      const data = await apiL.get(loc);
      if (!isLatest()) return;
      setLocales(data.locales); setItems(data.items);
      const d: Record<string, string> = {};
      for (const it of data.items) d[it.key] = effective(it);
      setDraft(d); setMsg("");
    } catch (e) { if (isLatest()) { setMsg(String(e)); setItems([]); } }
  }, [guard]);
  useEffect(() => { load(locale); setPage(0); setSel(new Set()); }, [locale, load]);
  useEffect(() => { apiL.stats().then(setStats).catch(() => setStats(null)); apiL.recent().then(setRecent).catch(() => setRecent([])); }, [locale]);

  // Ctrl+F focuses search globally on the page.
  useEffect(() => {
    const h = (e: KeyboardEvent) => { if ((e.ctrlKey || e.metaKey) && e.key.toLowerCase() === "f") { e.preventDefault(); searchRef.current?.focus(); } };
    window.addEventListener("keydown", h); return () => window.removeEventListener("keydown", h);
  }, []);

  const list = items || [];
  const namespaces = useMemo(() => {
    const m = new Map<string, { total: number; custom: number }>();
    for (const it of list) { const n = namespaceOf(it.key); const e = m.get(n) || { total: 0, custom: 0 }; e.total++; if (it.override !== null) e.custom++; m.set(n, e); }
    return [...m.entries()].sort((a, b) => a[0].localeCompare(b[0]));
  }, [list]);

  const filtered = useMemo(() => {
    const q = dq.trim().toLowerCase();
    const out = list.filter((it) => {
      if (ns !== "all" && namespaceOf(it.key) !== ns) return false;
      const st = statusOf(it).key;
      if (fStatus !== "all" && st !== fStatus) return false;
      const val = draft[it.key] ?? effective(it);
      if (fFlag === "vars" && variables(it.default).length === 0) return false;
      if (fFlag === "icu" && !isICU(it.default) && !isICU(val)) return false;
      if (fFlag === "long" && effective(it).length <= 220) return false;
      if (fFlag === "qa" && qaIssues(it.default, val).length === 0) return false;
      if (q && ![it.key, it.default, it.override ?? "", namespaceOf(it.key), ...variables(it.default)].some((x) => x.toLowerCase().includes(q))) return false;
      return true;
    });
    out.sort((a, b) => {
      let av: string | number = "", bv: string | number = "";
      if (sort.key === "key") { av = a.key; bv = b.key; }
      else if (sort.key === "status") { av = statusOf(a).key; bv = statusOf(b).key; }
      else { av = effective(a).length; bv = effective(b).length; }
      return av < bv ? -sort.dir : av > bv ? sort.dir : 0;
    });
    return out;
  }, [list, dq, ns, fStatus, fFlag, sort, draft]);

  const pageCount = Math.max(1, Math.ceil(filtered.length / PAGE));
  const pageItems = filtered.slice(page * PAGE, page * PAGE + PAGE);
  useEffect(() => { if (page >= pageCount) setPage(0); }, [pageCount, page]);

  const dash = useMemo(() => {
    const custom = list.filter((i) => i.override !== null).length;
    const missing = list.filter((i) => !i.default && i.override === null).length;
    const withVars = list.filter((i) => variables(i.default).length > 0).length;
    const qa = list.filter((i) => qaIssues(i.default, draft[i.key] ?? effective(i)).length > 0).length;
    return { total: list.length, custom, missing, std: list.length - custom - missing, ns: namespaces.length, withVars, qa };
  }, [list, namespaces, draft]);
  const lastChange = recent[0]?.created_at ?? null;

  function setDraftFor(key: string, v: string) { setDraft((d) => ({ ...d, [key]: v })); }
  async function save(it: Item, text?: string) {
    const value = text ?? draft[it.key] ?? "";
    try { await apiL.put(locale, it.key, value); setItems((rs) => (rs || []).map((r) => r.key === it.key ? { ...r, override: value } : r)); setMsg("✅ Сохранено"); apiL.recent().then(setRecent).catch(() => {}); apiL.stats().then(setStats).catch(() => {}); }
    catch (e) { setMsg(String(e)); }
  }
  async function revert(it: Item) {
    try { await apiL.del(locale, it.key); setItems((rs) => (rs || []).map((r) => r.key === it.key ? { ...r, override: null } : r)); setDraftFor(it.key, it.default); setMsg("✅ Сброшено к стандартному тексту"); apiL.stats().then(setStats).catch(() => {}); }
    catch (e) { setMsg(String(e)); }
  }

  async function bulkRevert() {
    const targets = list.filter((i) => sel.has(i.key) && i.override !== null);
    if (!targets.length) return;
    if (!confirm(`Сбросить ${targets.length} переопределений к стандартному тексту?`)) return;
    for (const it of targets) await apiL.del(locale, it.key);
    setSel(new Set()); load(locale); setMsg("✅ Готово");
  }
  function exportData(fmt: "json" | "csv" | "yaml") {
    const rows = (sel.size ? list.filter((i) => sel.has(i.key)) : filtered);
    let data = "";
    if (fmt === "json") data = JSON.stringify(Object.fromEntries(rows.map((i) => [i.key, effective(i)])), null, 2);
    else if (fmt === "yaml") data = rows.map((i) => `${i.key}: ${JSON.stringify(effective(i))}`).join("\n");
    else data = "key,namespace,default,override,status\n" + rows.map((i) => `${i.key},${namespaceOf(i.key)},${JSON.stringify(i.default)},${JSON.stringify(i.override ?? "")},${statusOf(i).key}`).join("\n");
    const blob = new Blob([data], { type: "text/plain" }); const a = document.createElement("a");
    a.href = URL.createObjectURL(blob); a.download = `locale-${locale}.${fmt}`; a.click();
    setTimeout(() => URL.revokeObjectURL(a.href), 1000);  // FIX: F66 - release the blob URL after the download starts
  }
  async function importJson(file: File) {
    try {
      const obj = JSON.parse(await file.text());
      if (typeof obj !== "object" || Array.isArray(obj)) throw new Error("Ожидался объект {key: text}");
      const known = new Map(list.map((i) => [i.key, i]));
      const entries = Object.entries(obj).filter(([, v]) => typeof v === "string");
      const unknown = entries.filter(([k]) => !known.has(k)).length;
      const broken = entries.filter(([k, v]) => { const it = known.get(k); return it && qaIssues(it.default, String(v)).some((x) => x.startsWith("пропущ") || x.startsWith("лишн")); }).length;
      if (!confirm(`Импортировать ${entries.length} строк? Неизвестных ключей: ${unknown}, с проблемой переменных: ${broken}. Применяется как переопределения.`)) return;
      for (const [k, v] of entries) if (known.has(k)) await apiL.put(locale, k, String(v));
      load(locale); setMsg(`✅ Импортировано: ${entries.length - unknown}${unknown ? ` · пропущено: ${unknown}` : ""}`);
    } catch (e) { setMsg("Ошибка импорта: " + String(e)); }
  }

  const curLang = stats?.languages.find((l) => l.code === locale);
  const editorIdx = editor ? filtered.findIndex((i) => i.key === editor) : -1;
  const editorItem = editor ? list.find((i) => i.key === editor) || null : null;

  return (
    <div>
      <div className="section-head">
        <div>
          <h1 className="page-title">Редактор локализации</h1>
          <p className="page-sub">Переопределение любой строки бота для языка — применяется вживую, без передеплоя. Namespace, переменные, статус и история выводятся из реальных данных.</p>
        </div>
        <div className="form-row" style={{ gap: "var(--sp-2)" }}>
          <button className="btn ghost" onClick={() => setShowLangs(true)}><span className="ms sm">translate</span> Языки{curLang ? ` · ${curLang.percent}%` : ""}</button>
        </div>
      </div>

      {msg && (
        <p className={msg.startsWith("✅") ? "note-ok" : "note-err"}>
          <span className="ms sm">{msg.startsWith("✅") ? "check_circle" : "error"}</span>{msg}
          <button className="btn ghost sm" onClick={() => setMsg("")} aria-label="Скрыть">×</button>
        </p>
      )}

      <div className="page-stack">
        <div className="metrics">
          <Metric icon="vpn_key" label="Всего ключей" value={dash.total} />
          <Metric icon="edit_note" label="Переопределено" value={dash.custom} tone={dash.custom ? "purple" : undefined} />
          <Metric icon="translate" label="Без перевода" value={dash.missing} tone={dash.missing ? "danger" : undefined} small />
          <Metric icon="article" label="Стандартных" value={dash.std} small />
          <Metric icon="folder" label="Namespace" value={dash.ns} small />
          <Metric icon="language" label="Языков" value={stats?.languages.length ?? locales.length} small />
          <Metric icon="data_object" label="С переменными" value={dash.withVars} small />
          <Metric icon="rule" label="QA-замечаний" value={dash.qa} tone={dash.qa ? "danger" : undefined} small />
          <Metric icon="history" label="Последнее изменение" value={ago(lastChange)} small />
        </div>

        {/* Sticky toolbar */}
        <div className="panel" style={{ padding: "var(--sp-3) var(--sp-4)", position: "sticky", top: 0, zIndex: 5 }}>
          <div className="section-head" style={{ margin: 0 }}>
            <div className="form-row" style={{ gap: "var(--sp-2)", flexWrap: "wrap" }}>
              <Select width={180} ariaLabel="Язык" value={locale} onChange={setLocale} options={locales.map((l) => ({ value: l.code, label: l.label }))} />
              <input ref={searchRef} style={{ width: 240 }} placeholder="Поиск: ключ, текст, переменные (Ctrl+F)" value={search} onChange={(e) => setSearch(e.target.value)} />
              <Select width={150} ariaLabel="Статус" value={fStatus} onChange={setFStatus} options={[{ value: "all", label: "Все статусы" }, { value: "custom", label: "Переопределены" }, { value: "missing", label: "Без перевода" }, { value: "default", label: "Стандарт" }]} />
              <Select width={160} ariaLabel="Признак" value={fFlag} onChange={setFFlag} options={[{ value: "all", label: "Без доп. фильтра" }, { value: "vars", label: "С переменными" }, { value: "icu", label: "ICU / plural" }, { value: "long", label: "Очень длинные" }, { value: "qa", label: "С QA-ошибкой" }]} />
            </div>
            <div className="form-row" style={{ gap: "var(--sp-2)" }}>
              <Select width={120} ariaLabel="Экспорт" value="" onChange={(v) => v && exportData(v as "json")} options={[{ value: "", label: "Экспорт…" }, { value: "json", label: "JSON" }, { value: "yaml", label: "YAML" }, { value: "csv", label: "CSV" }]} />
              <label className="btn ghost sm" style={{ cursor: "pointer" }}><span className="ms sm">upload</span> Импорт
                <input type="file" accept="application/json" hidden onChange={(e) => { const f = e.target.files?.[0]; if (f) importJson(f); e.target.value = ""; }} /></label>
            </div>
          </div>
          {sel.size > 0 && (
            <div className="form-row" style={{ gap: "var(--sp-2)", flexWrap: "wrap", marginTop: "var(--sp-3)", paddingTop: "var(--sp-3)", borderTop: "1px solid var(--border)" }}>
              <span className="pill pro">{sel.size} выбрано</span>
              <button className="btn ghost sm" onClick={bulkRevert}><span className="ms sm">undo</span> Сбросить к стандарту</button>
              <button className="btn ghost sm" onClick={() => exportData("json")}><span className="ms sm">download</span> Экспорт выбранных</button>
              <button className="btn ghost sm" onClick={() => setSel(new Set())}>Снять</button>
            </div>
          )}
        </div>

        <div style={{ display: "grid", gridTemplateColumns: "minmax(0, 1fr)", gap: "var(--sp-4)" }}>
          <div className="loc-layout">
            {/* Namespace rail */}
            <div className="panel loc-rail">
              <div className="panel-title sm" style={{ margin: "0 0 var(--sp-2)" }}><span className="ms sm">account_tree</span> Namespace</div>
              <button className={"loc-ns" + (ns === "all" ? " on" : "")} onClick={() => setNs("all")}><span>Все</span><span className="pill muted">{list.length}</span></button>
              {namespaces.map(([n, c]) => (
                <button key={n} className={"loc-ns" + (ns === n ? " on" : "")} onClick={() => setNs(n)} title={`${c.custom} переопределено`}>
                  <span className="code-key" style={{ fontSize: 12 }}>{n}</span>
                  <span className="pill muted">{c.custom > 0 ? `${c.custom}/` : ""}{c.total}</span>
                </button>
              ))}
            </div>

            {/* Table */}
            <div className="panel" style={{ minWidth: 0 }}>
              {items === null ? <div className="page-stack">{Array.from({ length: 6 }).map((_, i) => <div key={i} className="skeleton" style={{ height: 44 }} />)}</div>
                : filtered.length === 0 ? (
                  <EmptyState icon="translate" title={list.length === 0 ? "Строк нет" : "Ничего не найдено"}
                    desc={list.length === 0 ? "Для выбранного языка нет ключей, либо сессия истекла." : "Измените поиск, namespace или фильтры."} />
                ) : (
                  <>
                    <div className="table-wrap sticky" tabIndex={0} style={{ border: "none" }}>
                      <table className="tbl">
                        <thead><tr>
                          <th style={{ width: 30 }}><input type="checkbox" className="fx-check" aria-label="Выбрать" checked={pageItems.every((i) => sel.has(i.key))} onChange={(e) => setSel((s) => { const n = new Set(s); pageItems.forEach((i) => e.target.checked ? n.add(i.key) : n.delete(i.key)); return n; })} /></th>
                          <th style={{ cursor: "pointer" }} onClick={() => setSort((s) => ({ key: "key", dir: s.key === "key" && s.dir === 1 ? -1 : 1 }))}>Ключ</th>
                          <th>Стандартный текст</th>
                          <th>Перевод / переопределение</th>
                          <th style={{ cursor: "pointer", width: 130 }} onClick={() => setSort((s) => ({ key: "status", dir: s.key === "status" && s.dir === 1 ? -1 : 1 }))}>Статус</th>
                          <th style={{ cursor: "pointer", width: 60, textAlign: "right" }} onClick={() => setSort((s) => ({ key: "len", dir: s.key === "len" && s.dir === 1 ? -1 : 1 }))}>Длина</th>
                          <th style={{ width: 70 }}></th>
                        </tr></thead>
                        <tbody>
                          {pageItems.map((it) => {
                            const st = statusOf(it); const val = draft[it.key] ?? effective(it);
                            const vars = variables(it.default); const issues = qaIssues(it.default, val);
                            return (
                              <tr key={it.key}>
                                <td><input type="checkbox" className="fx-check" aria-label="Выбрать" checked={sel.has(it.key)} onChange={() => setSel((s) => { const n = new Set(s); n.has(it.key) ? n.delete(it.key) : n.add(it.key); return n; })} /></td>
                                <td style={{ maxWidth: 220 }}>
                                  <b className="code-key" style={{ cursor: "pointer", fontSize: 12 }} onClick={() => setEditor(it.key)}>{it.key}</b>
                                  <div className="form-row" style={{ gap: 4, margin: "3px 0 0", flexWrap: "wrap" }}>
                                    <span className="pill muted" style={{ fontSize: 10 }}>{namespaceOf(it.key)}</span>
                                    {isICU(it.default) && <span className="pill warn" style={{ fontSize: 10 }}>ICU</span>}
                                    {issues.length > 0 && <span className="pill danger" style={{ fontSize: 10 }} title={issues.join("; ")}>QA</span>}
                                  </div>
                                </td>
                                <td className="muted" style={{ maxWidth: 280, whiteSpace: "nowrap", overflow: "hidden", textOverflow: "ellipsis" }} title={it.default}>{it.default || "—"}</td>
                                <td style={{ maxWidth: 320 }}>
                                  <div className="loc-cell" onClick={() => setEditor(it.key)} title="Открыть редактор">
                                    {val || <span className="muted">пусто</span>}
                                  </div>
                                  {vars.length > 0 && <div className="form-row" style={{ gap: 3, margin: "3px 0 0", flexWrap: "wrap" }}>{vars.slice(0, 4).map((v) => <span key={v} className="code-key" style={{ fontSize: 10 }}>{`{${v}}`}</span>)}</div>}
                                </td>
                                <td><span className={"pill " + st.cls}>{st.label}</span></td>
                                <td className="muted" style={{ textAlign: "right" }}>{val.length}</td>
                                <td>
                                  <div className="form-row" style={{ gap: 2, flexWrap: "nowrap" }}>
                                    <button className="btn ghost sm" title="Редактор" onClick={() => setEditor(it.key)}><span className="ms sm">edit</span></button>
                                    <button className="btn ghost sm" title="Сбросить к стандарту" disabled={it.override === null} onClick={() => revert(it)}><span className="ms sm">undo</span></button>
                                  </div>
                                </td>
                              </tr>
                            );
                          })}
                        </tbody>
                      </table>
                    </div>
                    {pageCount > 1 && (
                      <div className="pager">
                        <span className="muted">{filtered.length} строк · стр. {page + 1} из {pageCount}</span>
                        <div className="pg-nums">
                          <button className="btn ghost sm" disabled={page === 0} onClick={() => setPage((p) => p - 1)}>←</button>
                          <button className="btn ghost sm" disabled={page >= pageCount - 1} onClick={() => setPage((p) => p + 1)}>→</button>
                        </div>
                      </div>
                    )}
                  </>
                )}
            </div>
          </div>
        </div>
      </div>

      {editorItem && (
        <EditorDrawer item={editorItem} locale={locale} draft={draft[editorItem.key] ?? effective(editorItem)}
          setDraft={(v) => setDraftFor(editorItem.key, v)} onSave={(v) => save(editorItem, v)} onRevert={() => revert(editorItem)}
          onClose={() => setEditor(null)}
          onNav={(d) => { const ni = editorIdx + d; if (ni >= 0 && ni < filtered.length) setEditor(filtered[ni].key); }}
          hasPrev={editorIdx > 0} hasNext={editorIdx >= 0 && editorIdx < filtered.length - 1} />
      )}
      {showLangs && <LanguageManager stats={stats} current={locale} onPick={(c) => { setLocale(c); setShowLangs(false); }} onClose={() => setShowLangs(false)} />}
    </div>
  );
}

// ---------------- Editor drawer (split view) ----------------
function EditorDrawer({ item, locale, draft, setDraft, onSave, onRevert, onClose, onNav, hasPrev, hasNext }: {
  item: Item; locale: string; draft: string; setDraft: (v: string) => void;
  onSave: (v: string) => void; onRevert: () => void; onClose: () => void;
  onNav: (d: number) => void; hasPrev: boolean; hasNext: boolean;
}) {
  const [history, setHistory] = useState<HistEntry[] | null>(null);
  const [autosave, setAutosave] = useState(false);
  const [translating, setTranslating] = useState(false);
  const [transErr, setTransErr] = useState("");
  const undo = useRef<string[]>([]); const redo = useRef<string[]>([]);
  const taRef = useRef<HTMLTextAreaElement>(null);
  const rtl = locale === "ar";

  useEffect(() => { setHistory(null); apiL.history(locale, item.key).then(setHistory).catch(() => setHistory([])); }, [locale, item.key]);

  const defVars = variables(item.default); const issues = qaIssues(item.default, draft);
  const dirty = draft !== effective(item);

  function change(v: string) { undo.current.push(draft); redo.current = []; setDraft(v); }
  function doUndo() { const prev = undo.current.pop(); if (prev !== undefined) { redo.current.push(draft); setDraft(prev); } }
  function doRedo() { const nx = redo.current.pop(); if (nx !== undefined) { undo.current.push(draft); setDraft(nx); } }
  function insert(s: string) { const ta = taRef.current; if (!ta) { change(draft + s); return; } const a = ta.selectionStart, b = ta.selectionEnd; change(draft.slice(0, a) + s + draft.slice(b)); requestAnimationFrame(() => { ta.focus(); ta.selectionStart = ta.selectionEnd = a + s.length; }); }
  function commit() { onSave(draft); }
  // Machine-translate the RU source into this locale and drop it into the draft for
  // review. Pushes onto the undo stack so the admin can revert with Ctrl+Z.
  async function aiTranslate() {
    if (translating || locale === "ru") return;
    setTranslating(true); setTransErr("");
    try { const r = await apiL.translate(locale, item.key); change(r.text); }
    catch (e) { setTransErr(String(e).replace(/^Error:\s*/, "")); }
    finally { setTranslating(false); }
  }

  function onKey(e: React.KeyboardEvent) {
    if ((e.ctrlKey || e.metaKey) && e.key.toLowerCase() === "s") { e.preventDefault(); commit(); }
    else if ((e.ctrlKey || e.metaKey) && e.key.toLowerCase() === "z" && !e.shiftKey) { e.preventDefault(); doUndo(); }
    else if ((e.ctrlKey || e.metaKey) && (e.key.toLowerCase() === "y" || (e.shiftKey && e.key.toLowerCase() === "z"))) { e.preventDefault(); doRedo(); }
    else if (e.altKey && e.key === "ArrowDown") { e.preventDefault(); onNav(1); }
    else if (e.altKey && e.key === "ArrowUp") { e.preventDefault(); onNav(-1); }
  }

  // Sample values so the live preview reads naturally.
  const preview = draft.replace(VAR_RE, (m, inner) => SIMPLE_VAR.test(inner.trim()) ? sampleFor(inner.trim()) : m);

  return (
    <Modal title={item.key} icon="edit_note" onClose={onClose} wide
      footer={<>
        <button className="btn ghost" disabled={!hasPrev} title="Предыдущая (Alt+↑)" onClick={() => onNav(-1)}><span className="ms sm">keyboard_arrow_up</span></button>
        <button className="btn ghost" disabled={!hasNext} title="Следующая (Alt+↓)" onClick={() => onNav(1)}><span className="ms sm">keyboard_arrow_down</span></button>
        <button className="btn ghost spacer" disabled={item.override === null} onClick={onRevert}><span className="ms sm">undo</span> К стандарту</button>
        <button className="btn" disabled={!dirty} onClick={commit}><span className="ms sm">save</span> Сохранить</button>
      </>}>
      <div onKeyDown={onKey} className="loc-editor">
        {/* Left: source + preview */}
        <div className="loc-editor-col">
          <KV label="Namespace · ключ"><span className="pill muted">{namespaceOf(item.key)}</span> <span className="code-key" style={{ fontSize: 12 }}>{item.key}</span></KV>
          <div className="cfg-field">
            <span className="cfg-cap">Стандартный текст (RU-исходник / шаблон)</span>
            <div className="loc-source" dir={rtl ? "rtl" : "ltr"}>{item.default || <span className="muted">—</span>}</div>
          </div>
          <div className="cfg-field">
            <span className="cfg-cap">Переменные шаблона</span>
            {defVars.length === 0 ? <span className="cfg-hint">нет</span> : (
              <div className="chip-row">{defVars.map((v) => {
                const ok = variables(draft).includes(v);
                return <span className="chip" key={v} style={{ borderColor: ok ? "var(--border)" : "var(--danger)" }}><span className="code-key" style={{ fontSize: 11 }}>{`{${v}}`}</span>{!ok && <span className="ms sm" style={{ color: "var(--danger)" }}>warning</span>}</span>;
              })}</div>
            )}
          </div>
          <div className="cfg-field">
            <span className="cfg-cap">Live-превью (Telegram)</span>
            <div className="tg-preview"><div className="tg-bubble"><div className="tg-text" dir={rtl ? "rtl" : "ltr"}>{preview}</div></div></div>
          </div>
        </div>

        {/* Right: translation + QA + history */}
        <div className="loc-editor-col">
          <div className="cfg-field">
            <div className="form-row" style={{ justifyContent: "space-between", margin: 0 }}>
              <span className="cfg-cap">Перевод / переопределение</span>
              <span className="muted" style={{ fontSize: 11 }}>{draft.length} симв.</span>
            </div>
            <textarea ref={taRef} value={draft} dir={rtl ? "rtl" : "ltr"} rows={6} style={{ width: "100%", resize: "vertical", fontFamily: "inherit" }}
              onChange={(e) => change(e.target.value)} onBlur={() => { if (autosave && dirty) commit(); }} autoFocus />
            <div className="form-row" style={{ gap: 4, margin: "4px 0 0", flexWrap: "wrap", alignItems: "center" }}>
              <button className="btn ghost sm" title="Отменить (Ctrl+Z)" onClick={doUndo}><span className="ms sm">undo</span></button>
              <button className="btn ghost sm" title="Повторить (Ctrl+Shift+Z)" onClick={doRedo}><span className="ms sm">redo</span></button>
              {locale !== "ru" && (
                <button className="btn ghost sm" disabled={translating || !item.default} title="Перевести RU-исходник в этот язык через AI-роутинг — переменные сохраняются" onClick={aiTranslate}>
                  <span className="ms sm">{translating ? "hourglass_empty" : "translate"}</span> {translating ? "Перевод…" : "Перевести AI"}
                </button>
              )}
              {defVars.map((v) => <button key={v} className="btn ghost sm" style={{ fontSize: 11 }} onClick={() => insert(`{${v}}`)}>{`{${v}}`}</button>)}
              <span className="loc-emoji">{EMOJIS.map((e) => <button key={e} onClick={() => insert(e)} aria-label={e}>{e}</button>)}</span>
            </div>
            {transErr && <span className="cfg-hint" style={{ color: "var(--danger)", marginTop: 4 }}><span className="ms sm" style={{ verticalAlign: "-3px" }}>error</span> Перевод не удался: {transErr}</span>}
          </div>

          {issues.length > 0 && (
            <div className="cfg-field">
              <span className="cfg-cap" style={{ color: "var(--danger)" }}>QA-замечания</span>
              <div className="chip-row">{issues.map((i) => <span className="chip" key={i} style={{ borderColor: "var(--danger)" }}>{i}</span>)}</div>
            </div>
          )}

          <div className="cfg-field">
            <div className="form-row" style={{ justifyContent: "space-between", margin: 0, alignItems: "center" }}>
              <span className="cfg-cap"><span className="ms sm" style={{ verticalAlign: "-3px" }}>history</span> История изменений (с откатом)</span>
              <Switch checked={autosave} onChange={setAutosave} label="Автосохр. при потере фокуса" />
            </div>
            {history === null ? <span className="cfg-hint">Загрузка…</span>
              : history.length === 0 ? <span className="cfg-hint">Изменений пока нет.</span>
                : (
                  <div style={{ display: "flex", flexDirection: "column", gap: 6, maxHeight: 220, overflow: "auto" }}>
                    {history.map((h) => (
                      <div key={h.id} className="loc-hist">
                        <div className="form-row" style={{ justifyContent: "space-between", margin: 0, fontSize: 11 }}>
                          <span><span className={"pill " + (h.action.includes("clear") ? "muted" : "ok")} style={{ fontSize: 10 }}>{h.action.includes("clear") ? "сброс" : "set"}</span> <span className="muted">#{h.admin_id}</span></span>
                          <span className="muted">{fmtDate(h.created_at)}</span>
                        </div>
                        {h.text !== null && <div className="loc-source" style={{ marginTop: 4, fontSize: 12 }}>{h.text || <span className="muted">пусто</span>}</div>}
                        {h.text !== null && h.text !== draft && (
                          <button className="btn ghost sm" style={{ marginTop: 4 }} onClick={() => change(h.text || "")}><span className="ms sm">restore</span> Откатить к этой версии</button>
                        )}
                      </div>
                    ))}
                  </div>
                )}
          </div>
        </div>
      </div>

      <p className="cfg-hint" style={{ marginTop: "var(--sp-4)" }}>
        <span className="ms sm" style={{ verticalAlign: "-3px" }}>info</span>{" "}
        Превью, проверка переменных, история, откат и AI-перевод (через AI-роутинг платформы, с сохранением переменных) работают на реальных данных. Workflow ревью (Draft → Review → Approved), комментарии/обсуждения, Translation Memory и глоссарий требуют отдельных таблиц и эндпоинтов — здесь редактируется значение строки с живым применением. ICU-конструкции (plural/select) сохраняются как есть; визуальный ICU-конструктор — отдельная задача.
      </p>
    </Modal>
  );
}

function sampleFor(name: string): string {
  const n = name.toLowerCase();
  if (n.includes("name")) return "Алекс";
  if (n.includes("price") || n.includes("amount") || n.includes("cost")) return "499";
  if (n.includes("count") || n.includes("num") || n.includes("qty")) return "3";
  if (n.includes("model")) return "GPT-5";
  if (n.includes("sub") || n.includes("plan") || n.includes("tier")) return "Premium";
  if (n.includes("date") || n.includes("day")) return "21 июня";
  return `{${name}}`;
}

// ---------------- Language Manager ----------------
function LanguageManager({ stats, current, onPick, onClose }: {
  stats: StatsPayload | null; current: string; onPick: (c: string) => void; onClose: () => void;
}) {
  const [q, setQ] = useState("");
  const [fav, setFav] = useState<string[]>(() => { try { return JSON.parse(localStorage.getItem("loc_fav") || "[]"); } catch { return []; } });
  const toggleFav = (c: string) => setFav((f) => { const n = f.includes(c) ? f.filter((x) => x !== c) : [...f, c]; localStorage.setItem("loc_fav", JSON.stringify(n)); return n; });
  const langs = (stats?.languages || []).filter((l) => !q.trim() || l.label.toLowerCase().includes(q.toLowerCase()) || l.code.includes(q.toLowerCase()));
  const sorted = [...langs].sort((a, b) => (fav.includes(b.code) ? 1 : 0) - (fav.includes(a.code) ? 1 : 0) || b.percent - a.percent);

  return (
    <Modal title="Менеджер языков" icon="translate" onClose={onClose} wide>
      <input placeholder="Поиск языка…" value={q} onChange={(e) => setQ(e.target.value)} style={{ width: "100%", marginBottom: "var(--sp-3)" }} />
      {stats === null ? <div className="loading">Загрузка…</div> : (
        <div className="table-wrap" tabIndex={0} style={{ border: "none" }}>
          <table className="tbl">
            <thead><tr><th></th><th>Язык</th><th>Locale</th><th>Прогресс</th><th style={{ textAlign: "right" }}>Строк</th><th style={{ textAlign: "right" }}>Переопр.</th><th></th></tr></thead>
            <tbody>
              {sorted.map((l) => (
                <tr key={l.code} style={l.code === current ? { background: "var(--panel-2)" } : undefined}>
                  <td><button className="btn ghost sm" onClick={() => toggleFav(l.code)} aria-label="В избранное"><span className="ms sm" style={{ color: fav.includes(l.code) ? "var(--accent)" : "var(--hint)" }}>{fav.includes(l.code) ? "star" : "star_border"}</span></button></td>
                  <td><b>{l.label}</b>{l.is_default && <span className="pill ok" style={{ marginLeft: 6 }}>default</span>}{l.rtl && <span className="pill warn" style={{ marginLeft: 6 }}>RTL</span>}</td>
                  <td className="code-key">{l.code}</td>
                  <td style={{ minWidth: 160 }}>
                    <div className="form-row" style={{ gap: 8, margin: 0, alignItems: "center" }}>
                      <div style={{ flex: 1, height: 6, borderRadius: 3, background: "var(--panel-2)", overflow: "hidden" }}>
                        <div style={{ width: `${l.percent}%`, height: "100%", background: l.percent >= 95 ? "var(--accent)" : l.percent >= 60 ? "var(--warn)" : "var(--danger)" }} />
                      </div>
                      <span className="muted" style={{ fontSize: 11, width: 34 }}>{l.percent}%</span>
                    </div>
                  </td>
                  <td style={{ textAlign: "right" }}>{l.translated.toLocaleString("ru")}</td>
                  <td style={{ textAlign: "right" }}>{l.overrides}</td>
                  <td><button className="btn sm" disabled={l.code === current} onClick={() => onPick(l.code)}>{l.code === current ? "текущий" : "открыть"}</button></td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
      <p className="cfg-hint" style={{ marginTop: "var(--sp-4)" }}>
        <span className="ms sm" style={{ verticalAlign: "-3px" }}>info</span>{" "}
        Прогресс = доля ключей с собственным переводом локали (остальные берут RU-фолбэк). Список языков фиксирован в конфиге (<code className="code-key">LANGUAGES</code>). Создание/клонирование/версионирование языковых пакетов, fallback-цепочки и пользовательские locale потребуют модели языковых пакетов на бэкенде — сейчас языки добавляются в коде.
      </p>
    </Modal>
  );
}

// ---------------- shared ----------------
function EmptyState({ icon, title, desc }: { icon: string; title: string; desc: string }) {
  return (
    <div className="empty-state">
      <div className="es-icon"><span className="ms">{icon}</span></div>
      <p className="es-title">{title}</p>
      <p className="es-desc">{desc}</p>
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
