import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { api } from "../api";
import { Select } from "../components/Select";
import { Switch } from "../components/Switch";
import { Modal } from "../components/Modal";

// Inline-keyboard constructor (ТЗ §8). Buttons live in business_config.custom_buttons
// as a rich list; the bot (/links) renders text+url, honouring optional enabled / row
// / icon. Extra fields (type/color/description) are admin-side metadata that persist.
type BType =
  | "https" | "http" | "link" | "miniapp" | "deeplink"
  | "channel" | "group" | "bot" | "callback" | "webapp" | "share";

interface Btn {
  id: string; text: string; url: string; type: BType;
  icon: string; color: string; description: string; enabled: boolean;
}
interface Row { id: string; buttons: Btn[]; }

const TYPES: { value: BType; label: string; scheme: string; botOk: boolean }[] = [
  { value: "https", label: "HTTPS", scheme: "https://", botOk: true },
  { value: "http", label: "HTTP", scheme: "http://", botOk: true },
  { value: "link", label: "Telegram (tg://)", scheme: "tg://", botOk: true },
  { value: "deeplink", label: "Deep Link (tg://)", scheme: "tg://", botOk: true },
  { value: "miniapp", label: "Mini App", scheme: "https://", botOk: true },
  { value: "channel", label: "Канал", scheme: "https://", botOk: true },
  { value: "group", label: "Группа", scheme: "https://", botOk: true },
  { value: "bot", label: "Бот", scheme: "https://", botOk: true },
  { value: "callback", label: "Callback", scheme: "", botOk: false },
  { value: "webapp", label: "WebApp", scheme: "", botOk: false },
  { value: "share", label: "Share", scheme: "", botOk: false },
];
const typeMeta = (t: BType) => TYPES.find((x) => x.value === t) ?? TYPES[0];

const ICONS: { label: string; emoji: string }[] = [
  { label: "Telegram", emoji: "✈️" }, { label: "Website", emoji: "🌐" }, { label: "Gift", emoji: "🎁" },
  { label: "Fire", emoji: "🔥" }, { label: "Rocket", emoji: "🚀" }, { label: "Premium", emoji: "💎" },
  { label: "Support", emoji: "🛟" }, { label: "Star", emoji: "⭐" }, { label: "Wallet", emoji: "👛" },
  { label: "Settings", emoji: "⚙️" }, { label: "AI", emoji: "🤖" }, { label: "Image", emoji: "🖼️" },
  { label: "Music", emoji: "🎵" }, { label: "Video", emoji: "🎬" }, { label: "Docs", emoji: "📄" },
  { label: "Link", emoji: "🔗" },
];
const COLORS: Record<string, string> = {
  "": "transparent", lime: "#d4ff3a", purple: "#7c5cff", blue: "#8fb6ff",
  amber: "#fbbf24", red: "#ffb4ab", gray: "#8f937a",
};
const ALLOWED = ["http://", "https://", "tg://"];
const DRAFT_KEY = "kb_draft_v1";

let _seq = 0;
const uid = () => `b${Date.now().toString(36)}${(_seq++).toString(36)}`;

function toBtn(raw: Record<string, unknown>): Btn {
  const t = (raw.type as BType) || "https";
  return {
    // Reuse the persisted stable id (used by the /r/{id} click tracker) or mint one.
    id: typeof raw.id === "string" && raw.id ? raw.id : uid(),
    text: String(raw.text ?? ""), url: String(raw.url ?? ""),
    type: TYPES.some((x) => x.value === t) ? t : "https",
    icon: String(raw.icon ?? ""), color: String(raw.color ?? ""),
    description: String(raw.description ?? ""),
    enabled: raw.enabled === undefined ? true : Boolean(raw.enabled),
  };
}
// Group the flat config list into rows, mirroring build_links_keyboard exactly:
// consecutive buttons sharing a numeric `row` form one row; no `row` => own row.
function toRows(raw: Record<string, unknown>[]): Row[] {
  const rows: Row[] = [];
  let cur: number | null = null;
  for (const r of raw || []) {
    const btn = toBtn(r);
    const key = typeof r.row === "number" ? (r.row as number) : null;
    if (key !== null && rows.length && key === cur) rows[rows.length - 1].buttons.push(btn);
    else { rows.push({ id: uid(), buttons: [btn] }); cur = key; }
  }
  return rows;
}
function fromRows(rows: Row[]): Record<string, unknown>[] {
  const out: Record<string, unknown>[] = [];
  rows.forEach((r, ri) => r.buttons.forEach((b) => out.push({
    id: b.id, text: b.text, url: b.url, type: b.type, icon: b.icon,
    color: b.color, description: b.description, enabled: b.enabled, row: ri,
  })));
  return out;
}
const allBtns = (rows: Row[]) => rows.flatMap((r) => r.buttons);

// per-button validation for /links rendering.
// Mirrors the bot's build_links_keyboard exactly: a button shows when it is enabled
// and has text + an http(s)/tg URL. The `type` is admin-side metadata only — the bot
// renders any valid-URL button regardless of type — so it never gates the preview.
function validate(b: Btn): { level: "ok" | "warn" | "err"; msg: string } {
  if (!b.text.trim()) return { level: "err", msg: "Нет текста" };
  if (!b.url.trim()) return { level: "err", msg: "Нет ссылки" };
  if (!ALLOWED.some((s) => b.url.startsWith(s))) return { level: "err", msg: "Схема должна быть http(s):// или tg://" };
  if (!b.enabled) return { level: "warn", msg: "Выключена — скрыта в боте" };
  return { level: "ok", msg: "Готова к показу" };
}

export function CustomButtons() {
  const [rows, setRows] = useState<Row[] | null>(null);
  const [past, setPast] = useState<Row[][]>([]);
  const [future, setFuture] = useState<Row[][]>([]);
  const [savedJson, setSavedJson] = useState("");
  const [saving, setSaving] = useState(false);
  const [msg, setMsg] = useState("");
  const [edit, setEdit] = useState<{ rowId: string; btn: Btn } | null>(null);
  const [io, setIo] = useState(false);
  const [sel, setSel] = useState<Set<string>>(new Set());
  const [q, setQ] = useState("");
  const [fStatus, setFStatus] = useState("all");
  const [fType, setFType] = useState("all");
  const [clicks, setClicks] = useState<Record<string, number>>({});

  const load = useCallback(() => {
    api.businessConfig()
      .then((d) => {
        const raw = (d.config.custom_buttons as Record<string, unknown>[]) ?? [];
        const r = toRows(raw);
        setRows(r); setSavedJson(JSON.stringify(fromRows(r))); setPast([]); setFuture([]);
      })
      .catch((e) => { setMsg(String(e)); setRows([]); });
  }, []);
  useEffect(() => { load(); }, [load]);
  // Real click counts from the /r/{id} redirect tracker (best-effort; empty on error).
  useEffect(() => { api.buttonStats().then((d) => setClicks(d.clicks || {})).catch(() => {}); }, []);

  // autosave working draft (does not touch the bot until "Save").
  useEffect(() => { if (rows) localStorage.setItem(DRAFT_KEY, JSON.stringify(fromRows(rows))); }, [rows]);

  // history-aware mutation.
  const commit = useCallback((next: Row[]) => {
    setRows((cur) => { if (cur) setPast((p) => [...p.slice(-49), cur]); return next; });
    setFuture([]);
  }, []);
  const undo = useCallback(() => {
    setPast((p) => { if (!p.length) return p; const prev = p[p.length - 1];
      setRows((cur) => { if (cur) setFuture((f) => [cur, ...f]); return prev; });
      return p.slice(0, -1); });
  }, []);
  const redo = useCallback(() => {
    setFuture((f) => { if (!f.length) return f; const nx = f[0];
      setRows((cur) => { if (cur) setPast((p) => [...p, cur]); return nx; });
      return f.slice(1); });
  }, []);

  const dirty = useMemo(() => rows != null && JSON.stringify(fromRows(rows)) !== savedJson, [rows, savedJson]);

  const save = useCallback(async () => {
    if (!rows) return;
    const flat = fromRows(rows).map((b) => ({ ...b, text: String(b.text).trim(), url: String(b.url).trim() }));
    setSaving(true);
    try {
      await api.setBusinessConfig({ custom_buttons: flat });
      setSavedJson(JSON.stringify(fromRows(rows)));
      setMsg("✅ Кнопки сохранены и применены в боте (/links)");
    } catch (e) {
      const s = String(e);
      setMsg(s.includes("403") ? "⛔ Сохранение конфигурации доступно только роли superadmin" : s);
    } finally { setSaving(false); }
  }, [rows]);

  // hotkeys: Ctrl+Z / Ctrl+Y(Shift+Z) / Ctrl+S
  useEffect(() => {
    const h = (e: KeyboardEvent) => {
      if (!(e.ctrlKey || e.metaKey)) return;
      const k = e.key.toLowerCase();
      if (k === "z" && !e.shiftKey) { e.preventDefault(); undo(); }
      else if (k === "y" || (k === "z" && e.shiftKey)) { e.preventDefault(); redo(); }
      else if (k === "s") { e.preventDefault(); save(); }
    };
    window.addEventListener("keydown", h);
    return () => window.removeEventListener("keydown", h);
  }, [undo, redo, save]);

  // ---- row / button ops (all via commit) ----
  const mut = (fn: (draft: Row[]) => Row[]) => { if (rows) commit(fn(rows.map((r) => ({ ...r, buttons: [...r.buttons] })))); };
  const newBtn = (): Btn => ({ id: uid(), text: "Новая кнопка", url: "https://", type: "https", icon: "", color: "", description: "", enabled: true });

  const addRow = () => mut((d) => [...d, { id: uid(), buttons: [newBtn()] }]);
  const addBtn = (rowId: string) => mut((d) => d.map((r) => r.id === rowId ? { ...r, buttons: [...r.buttons, newBtn()] } : r));
  const delRow = (rowId: string) => { if (confirm("Удалить строку со всеми кнопками?")) mut((d) => d.filter((r) => r.id !== rowId)); };
  const dupRow = (rowId: string) => mut((d) => {
    const i = d.findIndex((r) => r.id === rowId); if (i < 0) return d;
    const copy: Row = { id: uid(), buttons: d[i].buttons.map((b) => ({ ...b, id: uid() })) };
    return [...d.slice(0, i + 1), copy, ...d.slice(i + 1)];
  });
  const moveRow = (rowId: string, dir: -1 | 1) => mut((d) => {
    const i = d.findIndex((r) => r.id === rowId); const j = i + dir;
    if (i < 0 || j < 0 || j >= d.length) return d;
    const n = [...d]; [n[i], n[j]] = [n[j], n[i]]; return n;
  });
  const delBtn = (rowId: string, btnId: string) => mut((d) =>
    d.map((r) => r.id === rowId ? { ...r, buttons: r.buttons.filter((b) => b.id !== btnId) } : r).filter((r) => r.buttons.length));
  const patchBtn = (rowId: string, btnId: string, patch: Partial<Btn>) => mut((d) =>
    d.map((r) => r.id === rowId ? { ...r, buttons: r.buttons.map((b) => b.id === btnId ? { ...b, ...patch } : b) } : r));
  const dupBtn = (rowId: string, btnId: string) => mut((d) =>
    d.map((r) => {
      if (r.id !== rowId) return r;
      const i = r.buttons.findIndex((b) => b.id === btnId); if (i < 0) return r;
      const copy = { ...r.buttons[i], id: uid() };
      return { ...r, buttons: [...r.buttons.slice(0, i + 1), copy, ...r.buttons.slice(i + 1)] };
    }));

  // ---- drag & drop (buttons between rows, rows reorder) ----
  const drag = useRef<{ type: "btn" | "row"; rowId: string; btnId?: string } | null>(null);
  const [overRow, setOverRow] = useState<string | null>(null);
  function dropOnRow(rowId: string) {
    const dd = drag.current; drag.current = null; setOverRow(null);
    if (!dd) return;
    if (dd.type === "row") {
      mut((d) => { const from = d.findIndex((r) => r.id === dd.rowId); const to = d.findIndex((r) => r.id === rowId);
        if (from < 0 || to < 0 || from === to) return d; const n = [...d]; const [m] = n.splice(from, 1); n.splice(to, 0, m); return n; });
    } else if (dd.btnId) { moveBtn(dd.rowId, dd.btnId, rowId, -1); }
  }
  function dropOnBtn(rowId: string, beforeBtnId: string) {
    const dd = drag.current; drag.current = null; setOverRow(null);
    if (!dd || dd.type !== "btn" || !dd.btnId) return;
    const idx = rows?.find((r) => r.id === rowId)?.buttons.findIndex((b) => b.id === beforeBtnId) ?? -1;
    moveBtn(dd.rowId, dd.btnId, rowId, idx);
  }
  function moveBtn(srcRow: string, btnId: string, dstRow: string, dstIdx: number) {
    mut((d) => {
      let moved: Btn | undefined;
      let next = d.map((r) => r.id !== srcRow ? r : { ...r, buttons: r.buttons.filter((b) => { if (b.id === btnId) { moved = b; return false; } return true; }) });
      if (!moved) return d;
      next = next.map((r) => {
        if (r.id !== dstRow) return r;
        const arr = [...r.buttons]; const at = dstIdx < 0 ? arr.length : dstIdx; arr.splice(at, 0, moved as Btn); return { ...r, buttons: arr };
      });
      return next.filter((r) => r.buttons.length);
    });
  }

  // ---- bulk ----
  const toggleSel = (id: string) => setSel((s) => { const n = new Set(s); n.has(id) ? n.delete(id) : n.add(id); return n; });
  const bulkSet = (enabled: boolean) => { mut((d) => d.map((r) => ({ ...r, buttons: r.buttons.map((b) => sel.has(b.id) ? { ...b, enabled } : b) }))); };
  const bulkDelete = () => { if (!sel.size || !confirm(`Удалить выбранные кнопки (${sel.size})?`)) return;
    mut((d) => d.map((r) => ({ ...r, buttons: r.buttons.filter((b) => !sel.has(b.id)) })).filter((r) => r.buttons.length)); setSel(new Set()); };

  // ---- import / export ----
  function exportData(fmt: "json" | "csv" | "yaml"): string {
    const list = rows ? fromRows(rows) : [];
    if (fmt === "json") return JSON.stringify(list, null, 2);
    if (fmt === "csv") {
      const cols = ["text", "url", "type", "icon", "color", "description", "enabled", "row"];
      const esc = (v: unknown) => { const s = String(v ?? ""); return /[",\n]/.test(s) ? `"${s.replace(/"/g, '""')}"` : s; };
      return [cols.join(","), ...list.map((b) => cols.map((c) => esc(b[c])).join(","))].join("\n");
    }
    // minimal YAML emitter for this flat list.
    return list.map((b) => "- " + Object.entries(b).map(([k, v]) =>
      `${k}: ${typeof v === "string" ? JSON.stringify(v) : v}`).join("\n  ")).join("\n");
  }
  function importData(text: string, fmt: "json" | "csv"): Record<string, unknown>[] {
    if (fmt === "json") { const v = JSON.parse(text); if (!Array.isArray(v)) throw new Error("Ожидался массив кнопок"); return v; }
    const lines = text.trim().split(/\r?\n/); const cols = lines[0].split(",").map((s) => s.trim());
    return lines.slice(1).filter(Boolean).map((line) => {
      const cells: string[] = []; let cur = "", inQ = false;
      for (let i = 0; i < line.length; i++) { const c = line[i];
        if (inQ) { if (c === '"' && line[i + 1] === '"') { cur += '"'; i++; } else if (c === '"') inQ = false; else cur += c; }
        else if (c === '"') inQ = true; else if (c === ",") { cells.push(cur); cur = ""; } else cur += c; }
      cells.push(cur);
      const o: Record<string, unknown> = {};
      cols.forEach((c, i) => { o[c] = c === "enabled" ? cells[i] !== "false" : c === "row" ? Number(cells[i]) || 0 : cells[i]; });
      return o;
    });
  }

  // ---- derived ----
  const flat = useMemo(() => (rows ? allBtns(rows) : []), [rows]);
  const filtered = useMemo(() => flat.filter((b) => {
    if (fStatus === "active" && !b.enabled) return false;
    if (fStatus === "disabled" && b.enabled) return false;
    if (fType !== "all" && b.type !== fType) return false;
    if (q.trim()) { const s = q.toLowerCase(); if (!b.text.toLowerCase().includes(s) && !b.url.toLowerCase().includes(s) && !typeMeta(b.type).label.toLowerCase().includes(s)) return false; }
    return true;
  }), [flat, q, fStatus, fType]);
  const kpi = useMemo(() => ({
    total: flat.length, active: flat.filter((b) => b.enabled).length,
    disabled: flat.filter((b) => !b.enabled).length, rows: rows?.length ?? 0,
    invalid: flat.filter((b) => validate(b).level === "err").length,
    clicks: flat.reduce((a, b) => a + (clicks[b.id] || 0), 0),
  }), [flat, rows, clicks]);

  return (
    <div>
      <h1 className="page-title">Конструктор кнопок</h1>
      <p className="page-sub">Визуальный редактор Inline Keyboard для команды бота <code className="code-key">/links</code>: строки, drag&amp;drop, типы, иконки и живой предпросмотр Telegram.</p>

      {msg && (
        <p className={msg.startsWith("✅") ? "note-ok" : "note-err"}>
          <span className="ms sm">{msg.startsWith("✅") ? "check_circle" : msg.startsWith("⛔") ? "block" : "error"}</span>
          {msg}<button className="btn ghost sm" onClick={() => setMsg("")} aria-label="Скрыть">×</button>
        </p>
      )}

      <div className="page-stack">
        <div className="metrics">
          <Metric icon="smart_button" label="Всего кнопок" value={kpi.total} />
          <Metric icon="visibility" label="Активных" value={kpi.active} />
          <Metric icon="visibility_off" label="Выключенных" value={kpi.disabled} tone={kpi.disabled ? "purple" : undefined} />
          <Metric icon="table_rows" label="Строк" value={kpi.rows} />
          <Metric icon="error" label="С ошибками" value={kpi.invalid} tone={kpi.invalid ? "danger" : undefined} />
          <Metric icon="ads_click" label="Клики (всего)" value={kpi.clicks} hint="Реальные клики через редирект-трекер /r/{id}. Считаются на публичном деплое (webhook); локально кнопки ведут на прямой URL." />
        </div>

        {/* Toolbar */}
        <div className="panel" style={{ padding: "var(--sp-3) var(--sp-4)" }}>
          <div className="section-head" style={{ margin: 0 }}>
            <div className="form-row" style={{ gap: "var(--sp-2)", flexWrap: "wrap" }}>
              {/* FIX: AUDIT12-M13/M14 - aria-label + maxLength 255 on button search. */}
              <input style={{ width: 200 }} placeholder="Поиск по тексту / ссылке / типу" value={q} onChange={(e) => setQ(e.target.value)} maxLength={255} aria-label="Поиск кнопки" />
              <Select width={150} ariaLabel="Статус" value={fStatus} onChange={setFStatus}
                options={[{ value: "all", label: "Все статусы" }, { value: "active", label: "Активные" }, { value: "disabled", label: "Выключенные" }]} />
              <Select width={150} ariaLabel="Тип" value={fType} onChange={setFType}
                options={[{ value: "all", label: "Все типы" }, ...TYPES.map((t) => ({ value: t.value, label: t.label }))]} />
            </div>
            <div className="form-row" style={{ gap: "var(--sp-2)", flexWrap: "wrap" }}>
              <button className="btn ghost sm" onClick={undo} disabled={!past.length} title="Отменить (Ctrl+Z)"><span className="ms sm">undo</span></button>
              <button className="btn ghost sm" onClick={redo} disabled={!future.length} title="Повторить (Ctrl+Y)"><span className="ms sm">redo</span></button>
              <button className="btn ghost sm" onClick={() => setIo(true)} title="Импорт / экспорт"><span className="ms sm">import_export</span> Импорт/Экспорт</button>
              {dirty && <span className="pill warn">● не сохранено</span>}
              <button className="btn" onClick={save} disabled={saving || !dirty} title="Сохранить (Ctrl+S)">
                <span className="ms sm">save</span> {saving ? "Сохранение…" : "Сохранить"}
              </button>
            </div>
          </div>
          {sel.size > 0 && (
            <div className="form-row" style={{ marginTop: "var(--sp-3)", gap: "var(--sp-2)", flexWrap: "wrap", paddingTop: "var(--sp-3)", borderTop: "1px solid var(--border)" }}>
              <span className="pill pro">{sel.size} выбрано</span>
              <button className="btn ghost sm" onClick={() => bulkSet(true)}><span className="ms sm">visibility</span> Включить</button>
              <button className="btn ghost sm" onClick={() => bulkSet(false)}><span className="ms sm">visibility_off</span> Выключить</button>
              <button className="btn ghost sm" onClick={bulkDelete}><span className="ms sm" style={{ color: "var(--danger)" }}>delete</span> Удалить</button>
              <button className="btn ghost sm" onClick={() => setSel(new Set())}>Снять выделение</button>
            </div>
          )}
        </div>

        {rows === null ? (
          <div className="panel"><div className="loading">Загрузка…</div></div>
        ) : rows.length === 0 ? (
          <div className="panel">
            <div className="empty-state">
              <div className="es-icon"><span className="ms">smart_button</span></div>
              <p className="es-title">Кнопок пока нет</p>
              <p className="es-desc">Соберите Inline Keyboard для команды <code className="code-key">/links</code>: добавьте строки и кнопки, расставьте их перетаскиванием и проверьте в живом предпросмотре Telegram.</p>
              <button className="btn" onClick={addRow}><span className="ms sm">add</span> Создать первую кнопку</button>
            </div>
          </div>
        ) : (
          <div className="bc-grid">
            {/* Row editor */}
            <div className="panel" style={{ margin: 0, minWidth: 0 }}>
              <div className="section-head">
                <div className="panel-title" style={{ margin: 0 }}><span className="ms sm">dashboard_customize</span> Раскладка клавиатуры</div>
                <button className="btn ghost sm" onClick={addRow}><span className="ms sm">add</span> Строка</button>
              </div>
              <div style={{ display: "flex", flexDirection: "column", gap: "var(--sp-3)" }}>
                {rows.map((r, ri) => (
                  <div key={r.id} className={"kbrow" + (overRow === r.id ? " over" : "")}
                    onDragOver={(e) => { e.preventDefault(); if (overRow !== r.id) setOverRow(r.id); }}
                    onDragLeave={() => overRow === r.id && setOverRow(null)}
                    onDrop={(e) => { e.preventDefault(); dropOnRow(r.id); }}>
                    <div className="kb-rowno" draggable onDragStart={() => (drag.current = { type: "row", rowId: r.id })} title="Перетащите строку">
                      <span className="ms sm">drag_indicator</span>{ri + 1}
                    </div>
                    <div className="kb-btns">
                      {r.buttons.map((b) => {
                        const v = validate(b);
                        return (
                          <div key={b.id} className={"kbtn" + (b.enabled ? "" : " off")}
                            draggable onDragStart={(e) => { e.stopPropagation(); drag.current = { type: "btn", rowId: r.id, btnId: b.id }; }}
                            onDragOver={(e) => e.preventDefault()}
                            onDrop={(e) => { e.preventDefault(); e.stopPropagation(); dropOnBtn(r.id, b.id); }}
                            onDoubleClick={() => setEdit({ rowId: r.id, btn: b })}
                            title={v.msg}>
                            {b.color && <span className="kb-dot" style={{ background: COLORS[b.color] }} />}
                            {v.level !== "ok" && <span className="ms sm" style={{ fontSize: 14, color: v.level === "err" ? "var(--danger)" : "var(--warn)" }}>{v.level === "err" ? "error" : "warning"}</span>}
                            <span className="kb-label" onClick={() => setEdit({ rowId: r.id, btn: b })} style={{ cursor: "pointer" }}>
                              {b.icon && b.icon + " "}{b.text || "—"}
                            </span>
                            <button className="kb-x" onClick={() => delBtn(r.id, b.id)} title="Удалить"><span className="ms sm">close</span></button>
                          </div>
                        );
                      })}
                      <button className="kb-addbtn" onClick={() => addBtn(r.id)}><span className="ms sm">add</span> Кнопка</button>
                    </div>
                    <div className="kb-rowops">
                      <button className="btn ghost sm" onClick={() => moveRow(r.id, -1)} disabled={ri === 0} title="Вверх"><span className="ms sm">keyboard_arrow_up</span></button>
                      <button className="btn ghost sm" onClick={() => moveRow(r.id, 1)} disabled={ri === rows.length - 1} title="Вниз"><span className="ms sm">keyboard_arrow_down</span></button>
                      <button className="btn ghost sm" onClick={() => dupRow(r.id)} title="Дублировать строку"><span className="ms sm">content_copy</span></button>
                      <button className="btn ghost sm" onClick={() => delRow(r.id)} title="Удалить строку"><span className="ms sm" style={{ color: "var(--danger)" }}>delete</span></button>
                    </div>
                  </div>
                ))}
              </div>
              <p className="cfg-hint" style={{ marginTop: "var(--sp-3)" }}>
                <span className="ms sm" style={{ verticalAlign: "-3px" }}>info</span>{" "}
                Перетаскивайте кнопки между строками, строки — за иконку слева. Двойной клик по кнопке — редактирование. Бот рисует кнопки именно так (несколько в строке = один ряд клавиатуры).
              </p>
            </div>

            {/* Live Telegram preview */}
            <div className="bc-preview">
              <div className="panel-title sm" style={{ marginBottom: "var(--sp-3)" }}><span className="ms sm">smartphone</span> Предпросмотр Telegram</div>
              <TgkPreview rows={rows} />
            </div>
          </div>
        )}

        {/* Table */}
        {rows && rows.length > 0 && (
          <div className="panel">
            <div className="panel-title"><span className="ms sm">table_chart</span> Все кнопки {q || fStatus !== "all" || fType !== "all" ? `(${filtered.length} из ${flat.length})` : `(${flat.length})`}</div>
            <div className="table-wrap" tabIndex={0} style={{ border: "none" }}>
              <table className="tbl">
                <thead>
                  <tr>
                    <th style={{ width: 32 }}><input type="checkbox" className="fx-check" aria-label="Выбрать" checked={filtered.length > 0 && filtered.every((b) => sel.has(b.id))}
                      onChange={(e) => setSel(e.target.checked ? new Set(filtered.map((b) => b.id)) : new Set())} /></th>
                    <th>Preview</th><th>Тип</th><th>URL</th><th style={{ textAlign: "right" }}>Клики</th><th>Статус</th><th style={{ width: 200 }}>Действия</th>
                  </tr>
                </thead>
                <tbody>
                  {filtered.map((b) => {
                    const rowId = rows.find((r) => r.buttons.some((x) => x.id === b.id))!.id;
                    const v = validate(b);
                    return (
                      <tr key={b.id}>
                        <td><input type="checkbox" className="fx-check" aria-label="Выбрать" checked={sel.has(b.id)} onChange={() => toggleSel(b.id)} /></td>
                        <td>
                          <div className="form-row" style={{ gap: 8 }}>
                            {b.color && <span className="kb-dot" style={{ background: COLORS[b.color] }} />}
                            <b>{b.icon && b.icon + " "}{b.text || <span className="muted">—</span>}</b>
                          </div>
                          {b.description && <div className="muted clamp-2" style={{ fontSize: 11, maxWidth: 220 }}>{b.description}</div>}
                        </td>
                        <td><span className="pill muted">{typeMeta(b.type).label}</span></td>
                        <td className="code-key" style={{ maxWidth: 220, overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap" }} title={b.url}>{b.url || "—"}</td>
                        <td style={{ textAlign: "right", fontVariantNumeric: "tabular-nums" }}>
                          {clicks[b.id] ? <b>{clicks[b.id].toLocaleString("ru")}</b> : <span className="muted">0</span>}
                        </td>
                        <td><span className={"pill " + (v.level === "err" ? "danger" : !b.enabled ? "muted" : v.level === "warn" ? "warn" : "ok")}>{!b.enabled ? "Выключена" : v.level === "err" ? "Ошибка" : v.level === "warn" ? "Внимание" : "Активна"}</span></td>
                        <td>
                          <div className="form-row" style={{ gap: 2, flexWrap: "nowrap" }}>
                            <button className="btn ghost sm" title="Редактировать" onClick={() => setEdit({ rowId, btn: b })}><span className="ms sm">edit</span></button>
                            <button className="btn ghost sm" title="Дублировать" onClick={() => dupBtn(rowId, b.id)}><span className="ms sm">content_copy</span></button>
                            <button className="btn ghost sm" title={b.enabled ? "Выключить" : "Включить"} onClick={() => patchBtn(rowId, b.id, { enabled: !b.enabled })}><span className="ms sm">{b.enabled ? "visibility_off" : "visibility"}</span></button>
                            <button className="btn ghost sm" title="Копировать ссылку" onClick={() => { navigator.clipboard?.writeText(b.url); setMsg("✅ Ссылка скопирована"); }}><span className="ms sm">link</span></button>
                            <button className="btn ghost sm" title="Копировать JSON" onClick={() => { navigator.clipboard?.writeText(JSON.stringify({ text: b.text, url: b.url, type: b.type, icon: b.icon, color: b.color, enabled: b.enabled })); setMsg("✅ JSON скопирован"); }}><span className="ms sm">data_object</span></button>
                            <button className="btn ghost sm" title="Удалить" onClick={() => delBtn(rowId, b.id)}><span className="ms sm" style={{ color: "var(--danger)" }}>delete</span></button>
                          </div>
                        </td>
                      </tr>
                    );
                  })}
                </tbody>
              </table>
            </div>
            <p className="cfg-hint" style={{ marginTop: "var(--sp-3)" }}>
              <span className="ms sm" style={{ verticalAlign: "-3px" }}>history</span>{" "}
              Клики считаются редирект-трекером: на публичном деплое бот ведёт http(s)-кнопки через <code className="code-key">/r/&#123;id&#125;</code> → лог клика → 302 на реальный URL (локально/без webhook — прямой URL, счётчик не растёт). Журнал изменений — в общем «Аудит-логе» (действия <code className="code-key">business_config.update</code>).
            </p>
          </div>
        )}
      </div>

      {edit && (
        <ButtonModal entry={edit} onClose={() => setEdit(null)}
          onSave={(b) => { patchBtn(edit.rowId, edit.btn.id, b); setEdit(null); }} />
      )}
      {io && <ImportExportModal onClose={() => setIo(false)} exportData={exportData}
        onImport={(text, fmt, mode) => {
          try {
            const parsed = importData(text, fmt);
            const next = toRows(parsed);
            commit(mode === "replace" || !rows ? next : [...rows, ...next]);
            setMsg(`✅ Импортировано кнопок: ${parsed.length}`); setIo(false);
          } catch (e) { setMsg("Ошибка импорта: " + String(e)); }
        }} />}
    </div>
  );
}

// ---------- subcomponents ----------
function TgkPreview({ rows }: { rows: Row[] }) {
  const visible = rows.map((r) => r.buttons.filter((b) => b.enabled && b.text.trim() && ALLOWED.some((s) => b.url.startsWith(s))))
    .filter((bs) => bs.length);
  return (
    <div>
      <div className="tgk-msg">Полезные ссылки:</div>
      {visible.length === 0 ? (
        <p className="cfg-hint" style={{ marginTop: 8 }}>Нет валидных кнопок для показа в боте.</p>
      ) : (
        <div className="tgk">
          {visible.map((bs, i) => (
            <div className="tgk-row" key={i}>
              {bs.map((b) => <div className="tgk-btn" key={b.id}>{b.icon && b.icon + " "}{b.text}</div>)}
            </div>
          ))}
        </div>
      )}
    </div>
  );
}

function ButtonModal({ entry, onClose, onSave }: { entry: { rowId: string; btn: Btn }; onClose: () => void; onSave: (b: Partial<Btn>) => void }) {
  const [b, setB] = useState<Btn>(entry.btn);
  const set = <K extends keyof Btn>(k: K, v: Btn[K]) => setB((p) => ({ ...p, [k]: v }));
  const v = validate(b);
  const scheme = typeMeta(b.type).scheme;
  return (
    <Modal title="Кнопка" icon="smart_button" onClose={onClose} wide
      footer={<>
        <button className="btn ghost spacer" onClick={onClose}>Отмена</button>
        <button className="btn" onClick={() => onSave(b)}><span className="ms sm">save</span> Применить</button>
      </>}>
      <div className="form-grid">
        <div className="cfg-field"><span className="cfg-cap">Текст кнопки</span>
          {/* FIX: AUDIT12-M13/M14 - aria-label + maxLength 255 on button text. */}
          <input value={b.text} onChange={(e) => set("text", e.target.value)} maxLength={255} aria-label="Текст кнопки" /></div>
        <div className="cfg-field"><span className="cfg-cap">Тип ссылки</span>
          <Select width="100%" ariaLabel="Тип" value={b.type} onChange={(val) => set("type", val as BType)} options={TYPES.map((t) => ({ value: t.value, label: t.label }))} /></div>
      </div>
      <div className="cfg-field" style={{ marginTop: "var(--sp-3)" }}>
        <span className="cfg-cap">URL {scheme && <span className="muted">· обычно {scheme}…</span>}</span>
        {/* FIX: AUDIT12-M13/M14 - aria-label + maxLength 2048 on button URL. */}
        <input className="mono" value={b.url} onChange={(e) => set("url", e.target.value)} placeholder={scheme + "…"} type="url" maxLength={2048} aria-label="URL кнопки" />
        <span className="cfg-hint" style={{ color: v.level === "err" ? "var(--danger)" : v.level === "warn" ? "var(--warn)" : "var(--accent)" }}>
          <span className="ms sm" style={{ verticalAlign: "-3px" }}>{v.level === "ok" ? "check_circle" : v.level === "warn" ? "warning" : "error"}</span> {v.msg}
        </span>
      </div>
      <div className="cfg-field" style={{ marginTop: "var(--sp-3)" }}><span className="cfg-cap">Описание (внутреннее)</span>
        {/* FIX: AUDIT12-M13/M14 - aria-label + maxLength 500 on button description. */}
        <input value={b.description} onChange={(e) => set("description", e.target.value)} maxLength={500} aria-label="Описание кнопки" /></div>

      <div className="cfg-field" style={{ marginTop: "var(--sp-4)" }}><span className="cfg-cap">Иконка (emoji)</span>
        <div className="icon-grid">
          <button className={b.icon === "" ? "on" : ""} onClick={() => set("icon", "")} title="Без иконки">∅</button>
          {ICONS.map((ic) => <button key={ic.label} className={b.icon === ic.emoji ? "on" : ""} title={ic.label} onClick={() => set("icon", ic.emoji)}>{ic.emoji}</button>)}
        </div>
        {/* FIX: AUDIT12-M13/M14 - aria-label + maxLength 32 on custom emoji. */}
        <input style={{ marginTop: "var(--sp-2)" }} placeholder="или свой emoji" value={b.icon} onChange={(e) => set("icon", e.target.value)} maxLength={32} aria-label="Свой emoji" />
      </div>
      <div className="cfg-field" style={{ marginTop: "var(--sp-4)" }}><span className="cfg-cap">Цвет-метка (для админки)</span>
        <div className="swatches">
          {Object.keys(COLORS).map((c) => (
            <span key={c} className={"swatch" + (b.color === c ? " on" : "")} title={c || "без цвета"}
              style={{ background: c ? COLORS[c] : "var(--panel-2)", borderStyle: c ? "solid" : "dashed", borderColor: c ? undefined : "var(--border-hi)" }}
              onClick={() => set("color", c)} />
          ))}
        </div>
        <span className="cfg-hint">Telegram показывает кнопки без цвета — это пометка для удобства в админке.</span>
      </div>
      <div style={{ marginTop: "var(--sp-4)" }}>
        <Switch checked={b.enabled} onChange={(val) => set("enabled", val)} label="Активна (видна в боте)" />
      </div>
    </Modal>
  );
}

function ImportExportModal({ onClose, exportData, onImport }: {
  onClose: () => void;
  exportData: (f: "json" | "csv" | "yaml") => string;
  onImport: (text: string, fmt: "json" | "csv", mode: "replace" | "append") => void;
}) {
  const [tab, setTab] = useState<"export" | "import">("export");
  const [fmt, setFmt] = useState<"json" | "csv" | "yaml">("json");
  const [text, setText] = useState("");
  const [mode, setMode] = useState<"replace" | "append">("replace");
  const download = () => {
    const data = exportData(fmt); const blob = new Blob([data], { type: "text/plain" });
    const a = document.createElement("a"); a.href = URL.createObjectURL(blob); a.download = `buttons.${fmt}`; a.click();
    URL.revokeObjectURL(a.href);  // FIX: AUDIT-92 - immediate revoke;  // FIX: F62 - release the blob URL after the download starts
  };
  return (
    <Modal title="Импорт / Экспорт" icon="import_export" onClose={onClose} wide>
      <div className="seg-tabs" style={{ marginBottom: "var(--sp-4)" }}>
        <button className={tab === "export" ? "on" : ""} onClick={() => setTab("export")}>Экспорт</button>
        <button className={tab === "import" ? "on" : ""} onClick={() => setTab("import")}>Импорт</button>
      </div>
      {tab === "export" ? (
        <>
          <div className="form-row" style={{ gap: "var(--sp-2)", marginBottom: "var(--sp-3)" }}>
            <Select width={130} ariaLabel="Формат" value={fmt} onChange={(v) => setFmt(v as typeof fmt)}
              options={[{ value: "json", label: "JSON" }, { value: "csv", label: "CSV" }, { value: "yaml", label: "YAML" }]} />
            <button className="btn ghost sm" onClick={() => { navigator.clipboard?.writeText(exportData(fmt)); }}><span className="ms sm">content_copy</span> Копировать</button>
            <button className="btn sm" onClick={download}><span className="ms sm">download</span> Скачать .{fmt}</button>
          </div>
          {/* FIX: AUDIT12-M13 - aria-label on export textarea (readOnly). */}
          <textarea readOnly style={{ minHeight: 220, fontFamily: "ui-monospace, monospace", fontSize: 12 }} value={exportData(fmt)} aria-label="Экспорт данных" />
        </>
      ) : (
        <>
          <div className="form-row" style={{ gap: "var(--sp-2)", marginBottom: "var(--sp-3)", flexWrap: "wrap" }}>
            <Select width={130} ariaLabel="Формат" value={fmt === "yaml" ? "json" : fmt} onChange={(v) => setFmt(v as typeof fmt)}
              options={[{ value: "json", label: "JSON" }, { value: "csv", label: "CSV" }]} />
            <Select width={170} ariaLabel="Режим" value={mode} onChange={(v) => setMode(v as typeof mode)}
              options={[{ value: "replace", label: "Заменить всё" }, { value: "append", label: "Добавить к текущим" }]} />
            <button className="btn sm" onClick={() => onImport(text, fmt === "yaml" ? "json" : fmt, mode)} disabled={!text.trim()}><span className="ms sm">upload</span> Импортировать</button>
          </div>
          {/* FIX: AUDIT12-M13/M14 - aria-label + maxLength 100000 on import textarea. */}
          <textarea style={{ minHeight: 220, fontFamily: "ui-monospace, monospace", fontSize: 12 }} placeholder="Вставьте JSON-массив или CSV…" value={text} onChange={(e) => setText(e.target.value)} maxLength={100000} aria-label="Импорт данных" />
          <p className="cfg-hint">JSON и CSV поддерживают импорт. YAML — только экспорт.</p>
        </>
      )}
    </Modal>
  );
}

function Metric({ icon, label, value, tone, small, hint }: {
  icon: string; label: string; value: number | string; tone?: "purple" | "danger"; small?: boolean; hint?: string;
}) {
  return (
    <div className={"metric" + (tone ? " " + tone : "")} title={hint}>
      <span className="glow" />
      <div className="top"><span className="lbl">{label}</span><span className="ms sm">{icon}</span></div>
      <div><div className="num" style={small ? { fontSize: 16 } : undefined}>{typeof value === "number" ? value.toLocaleString("ru") : value}</div></div>
    </div>
  );
}
