import { useEffect, useMemo, useRef, useState } from "react";
import type { ImgHTMLAttributes } from "react";
import { api, EffectAdminRow, EffectKind, EffectPayload, ModelSpec } from "../api";
import { Select } from "../components/Select";
import { Switch } from "../components/Switch";
import { Modal } from "../components/Modal";

// Preview <img> that degrades to the placeholder glyph if the URL fails to load
// (404 / expired link), instead of the browser's broken-image icon. Mirrors the
// null-preview fallback the call sites already render.
function ImgFallback(props: ImgHTMLAttributes<HTMLImageElement>) {
  const [bad, setBad] = useState(false);
  if (bad) return <span className="ms fx-noimg" style={props.style}>image</span>;
  return <img alt="" loading="lazy" {...props} onError={() => setBad(true)} />;
}

// ---- catalog constants (real backend model keys + display labels) ----
const MODELS: Record<EffectKind, { key: string; label: string }[]> = {
  photo: [
    { key: "nano_banana", label: "Nano Banana" }, { key: "seedream", label: "Seedream" },
    { key: "flux2", label: "Flux" }, { key: "gpt_image2", label: "GPT Image" },
    { key: "midjourney", label: "Midjourney" }, { key: "recraft", label: "Recraft" },
  ],
  video: [
    { key: "kling_ai", label: "Kling" }, { key: "veo", label: "Veo" },
    { key: "hailuo", label: "Hailuo" }, { key: "pika", label: "Pika" },
    { key: "seedance", label: "Seedance" }, { key: "grok", label: "Grok" },
    { key: "mj_video", label: "MJ Video" },
  ],
};
const CATS: Record<EffectKind, { key: string; label: string }[]> = {
  photo: [
    { key: "all", label: "Все" }, { key: "female", label: "Девушки" }, { key: "male", label: "Мужчины" },
    { key: "children", label: "Дети" }, { key: "couple", label: "Пары" },
  ],
  video: [
    { key: "all", label: "Все" }, { key: "dance", label: "Танцы" }, { key: "emotion", label: "Эмоции" },
    { key: "effect", label: "Эффекты" }, { key: "transform", label: "Трансформация" },
  ],
};
const PROMPT_VARS = ["{prompt}", "{style}", "{subject}", "{gender}", "{quality}", "{ratio}", "{seed}", "{negative}"];
const modelLabel = (k: string) => [...MODELS.photo, ...MODELS.video].find((m) => m.key === k)?.label ?? k;
const catLabel = (kind: EffectKind, k: string) => CATS[kind].find((c) => c.key === k)?.label ?? k;
const isVideo = (u?: string | null) => !!u && /\.(mp4|webm)(\?|$)/i.test(u);

// ---- _meta: rich CMS fields stored inside default_params under a reserved key.
// Safe — pricing/generation only read known param keys via .get(); _meta is ignored
// downstream and round-trips through the existing CRUD (no schema migration).
interface Meta {
  slug?: string; description?: string; full_description?: string; subcategory?: string;
  tags?: string[]; negative_prompt?: string; system_prompt?: string;
  gallery?: string[]; video_url?: string; gif_url?: string; version?: string;
  premium?: boolean; featured?: boolean; is_new?: boolean; is_popular?: boolean;
}
const getMeta = (dp: Record<string, unknown>): Meta => (dp?._meta as Meta) || {};
const genOnly = (dp: Record<string, unknown>): Record<string, unknown> => {
  const o = { ...(dp || {}) }; delete o._meta; return o;
};
const withMeta = (gen: Record<string, unknown>, meta: Meta): Record<string, unknown> => {
  const m: Meta = {}; // drop empties to keep the blob tidy
  (Object.keys(meta) as (keyof Meta)[]).forEach((k) => {
    const v = meta[k];
    if (v === "" || v === false || v == null || (Array.isArray(v) && !v.length)) return;
    (m as Record<string, unknown>)[k] = v;
  });
  return Object.keys(m).length ? { ...gen, _meta: m } : { ...gen };
};

// Human-readable chips for an effect's generation params (replaces a raw-JSON dump).
const _PARAM_LABEL: Record<string, string> = {
  model: "Вариант", quality: "Качество", ratio: "Формат", res: "Разрешение", mode: "Режим", count: "Кол-во",
};
const _FLAG_LABEL: Record<string, string> = {
  fourk: "4K", audio: "Звук", seed: "Фикс. сид", prompt_enhance: "Улучшение промпта", enhance: "Улучшение промпта",
};
function paramChips(params: Record<string, unknown>): string[] {
  const out: string[] = [];
  for (const [k, v] of Object.entries(params || {})) {
    if (v == null || v === "") continue;
    if (k === "duration") out.push(`${v} сек`);
    else if (k in _FLAG_LABEL) { if (v) out.push(_FLAG_LABEL[k]); }
    else if (k in _PARAM_LABEL) {
      const display = (k === "quality" || k === "res") ? String(v).toUpperCase() : String(v);
      out.push(`${_PARAM_LABEL[k]}: ${display}`);
    } else out.push(`${k}: ${v}`);
  }
  return out;
}

const EMPTY: EffectPayload = {
  name_ru: "", category: "all", provider: null, recommended_model: null,
  compatible_models: [], prompt_template: "{prompt}", prompt_mode: "optional", default_params: {},
  max_photos: 1, preview_url: null, thumbnail_url: null, badge: null,
  is_ad: false, author: null, is_trending: false, enabled: true, sort_order: 0, price: 0,
};
const rowToPayload = (r: EffectAdminRow): EffectPayload => ({
  name_ru: r.name_ru, category: r.category, provider: r.provider, recommended_model: r.recommended_model,
  compatible_models: r.compatible_models, prompt_template: r.prompt_template,
  prompt_mode: r.prompt_mode ?? "optional", default_params: r.default_params,
  max_photos: r.max_photos, preview_url: r.preview_url, thumbnail_url: r.thumbnail_url, badge: r.badge,
  is_ad: r.is_ad, author: r.author, is_trending: r.is_trending, enabled: r.enabled,
  sort_order: r.sort_order, price: r.price,
});

type SortKey = "sort_order" | "name_ru" | "price" | "gen_count";

export function Effects() {
  const [kind, setKind] = useState<EffectKind>("video");
  const [rows, setRows] = useState<EffectAdminRow[] | null>(null);
  const [view, setView] = useState<"grid" | "table">("grid");
  const [msg, setMsg] = useState("");
  const [q, setQ] = useState("");
  const [fCat, setFCat] = useState("all");
  const [fModel, setFModel] = useState("all");
  const [fStatus, setFStatus] = useState("all");
  const [fExtra, setFExtra] = useState("all"); // all|trend|premium|free|new
  const [sortKey, setSortKey] = useState<SortKey>("sort_order");
  const [sortDir, setSortDir] = useState<1 | -1>(1);
  const [page, setPage] = useState(0);
  const [pageSize, setPageSize] = useState(24);
  const [sel, setSel] = useState<Set<number>>(new Set());
  const [detail, setDetail] = useState<EffectAdminRow | null>(null);
  const [editor, setEditor] = useState<{ id: number | "new"; row: EffectAdminRow | null } | null>(null);

  const [specs, setSpecs] = useState<Record<string, ModelSpec>>({});
  const load = () => api.effects(kind).then((r) => setRows(r)).catch((e) => { setMsg(String(e)); setRows([]); });
  useEffect(() => { load(); setSel(new Set()); setPage(0); /* eslint-disable-next-line */ }, [kind]);
  // Per-model parameter schema for the editor's friendly controls (replaces raw JSON).
  useEffect(() => { api.effectSpecs(kind).then((d) => setSpecs(d.models || {})).catch(() => setSpecs({})); }, [kind]);

  const toast = (m: string) => setMsg(m);

  async function persist(r: EffectAdminRow, patch: Partial<EffectPayload>) {
    await api.effectUpdate(kind, r.id, { ...rowToPayload(r), ...patch });
  }
  async function toggleEnabled(r: EffectAdminRow) {
    try { await persist(r, { enabled: !r.enabled }); await load(); } catch (e) { toast(String(e)); }
  }
  async function savePrice(r: EffectAdminRow, price: number) {
    if (price === (r.price || 0)) return;   // unchanged — skip the round-trip
    try { await persist(r, { price }); await load(); toast(price ? `✅ Цена: ✨ ${price}` : "✅ Цена: авто"); }
    catch (e) { toast(String(e)); }
  }
  async function remove(r: EffectAdminRow) {
    if (!confirm(`Удалить «${r.name_ru}»? Действие необратимо.`)) return;
    try { await api.effectDelete(kind, r.id); setDetail(null); await load(); toast("✅ Эффект удалён"); }
    catch (e) { toast(String(e)); }
  }
  async function duplicate(r: EffectAdminRow) {
    try {
      const p = rowToPayload(r);
      await api.effectCreate(kind, { ...p, name_ru: p.name_ru + " (копия)", sort_order: (rows?.length ?? 0), preview_url: r.preview_url });
      toast("📋 Эффект продублирован"); await load();
    } catch (e) { toast(String(e)); }
  }

  // ---- drag reorder (persists sort_order) ----
  const drag = useRef<number | null>(null);
  const [over, setOver] = useState<number | null>(null);
  const reorderable = sortKey === "sort_order" && !q && fCat === "all" && fModel === "all" && fStatus === "all" && fExtra === "all";
  async function onDrop(targetId: number) {
    const src = drag.current; drag.current = null; setOver(null);
    if (src == null || src === targetId || !rows || !reorderable) return;
    const ordered = [...rows].sort((a, b) => a.sort_order - b.sort_order || a.id - b.id);
    const from = ordered.findIndex((r) => r.id === src), to = ordered.findIndex((r) => r.id === targetId);
    const [m] = ordered.splice(from, 1); ordered.splice(to, 0, m);
    const next = ordered.map((r, i) => ({ ...r, sort_order: i }));
    setRows(next); // optimistic
    try {
      for (const r of next) if (rows.find((o) => o.id === r.id)?.sort_order !== r.sort_order) await persist(r, { sort_order: r.sort_order });
      toast("✅ Порядок сохранён");
    } catch (e) { toast(String(e)); } finally { await load(); }
  }

  // ---- bulk ----
  const bulk = async (fn: (r: EffectAdminRow) => Promise<unknown>, after?: string) => {
    const targets = (rows || []).filter((r) => sel.has(r.id));
    // FIX: AUDIT-3 - per-item try/catch + summary toast
    let ok = 0, failed = 0;
    for (const r of targets) {
      try { await fn(r); ok++; }
      catch (e) { failed++; toast(`❌ #${r.id}: ${e}`); }
    }
    setSel(new Set()); await load();
    if (after) toast(`${after}: ${ok}${failed ? `, ошибок: ${failed}` : ""}`);
  };
  const bulkDelete = () => { if (sel.size && confirm(`Удалить выбранные эффекты (${sel.size})?`)) bulk((r) => api.effectDelete(kind, r.id), "✅ Удалено"); };
  const bulkEnable = (v: boolean) => bulk((r) => persist(r, { enabled: v }), "✅ Готово");
  const bulkPrice = () => { const p = prompt("Новая цена (✨) для выбранных:"); if (p == null) return; const n = Math.max(0, Number(p) || 0); bulk((r) => persist(r, { price: n }), "✅ Цена обновлена"); };
  const bulkCategory = () => { const c = prompt(`Категория для выбранных (${CATS[kind].map((x) => x.key).join("/")}):`); if (!c) return; bulk((r) => persist(r, { category: c }), "✅ Категория обновлена"); };
  const bulkModel = () => { const mdl = prompt(`Рекомендуемая модель (${MODELS[kind].map((x) => x.key).join("/")}):`); if (!mdl) return; bulk((r) => persist(r, { recommended_model: mdl }), "✅ Модель обновлена"); };

  function exportJson() {
    const list = (rows || []).filter((r) => !sel.size || sel.has(r.id));
    const blob = new Blob([JSON.stringify(list, null, 2)], { type: "application/json" });
    const a = document.createElement("a"); a.href = URL.createObjectURL(blob); a.download = `effects_${kind}.json`; a.click();
    URL.revokeObjectURL(a.href);  // FIX: AUDIT-92 - immediate revoke;  // FIX: F64 - release the blob URL after the download starts
  }
  const importRef = useRef<HTMLInputElement>(null);
  async function importJson(file: File) {
    try {
      const list = JSON.parse(await file.text());
      if (!Array.isArray(list)) throw new Error("Ожидался массив");
      let base = rows?.length ?? 0;
      // FIX: AUDIT-4 - per-item try/catch + count imported/failed
      let imported = 0, failed = 0;
      for (const r of list) {
        try { await api.effectCreate(kind, { ...EMPTY, ...rowToPayload({ ...EMPTY, ...r } as EffectAdminRow), sort_order: base++ }); imported++; }
        catch (e) { failed++; }
      }
      toast(`✅ Импортировано: ${imported}${failed ? `, ошибок: ${failed}` : ""}`); await load();
    } catch (e) { toast("Ошибка импорта: " + String(e)); }
  }

  // ---- derived ----
  const filtered = useMemo(() => {
    let r = rows || [];
    if (fCat !== "all") r = r.filter((x) => x.category === fCat);
    if (fModel !== "all") r = r.filter((x) => x.recommended_model === fModel || x.compatible_models.includes(fModel));
    if (fStatus !== "all") r = r.filter((x) => (fStatus === "on" ? x.enabled : !x.enabled));
    if (fExtra === "trend") r = r.filter((x) => x.is_trending);
    else if (fExtra === "premium") r = r.filter((x) => getMeta(x.default_params).premium);
    else if (fExtra === "free") r = r.filter((x) => x.price === 0);
    else if (fExtra === "new") r = r.filter((x) => getMeta(x.default_params).is_new);
    if (q.trim()) {
      const s = q.toLowerCase();
      r = r.filter((x) => {
        const m = getMeta(x.default_params);
        return [x.name_ru, x.author, x.recommended_model, x.prompt_template, String(x.id), m.description, (m.tags || []).join(" ")]
          .some((f) => String(f ?? "").toLowerCase().includes(s));
      });
    }
    const dir = sortDir;
    return [...r].sort((a, b) => {
      if (sortKey === "name_ru") return a.name_ru.localeCompare(b.name_ru) * dir;
      if (sortKey === "price") return (a.price - b.price) * dir;
      if (sortKey === "gen_count") return (a.gen_count - b.gen_count) * dir;
      return (a.sort_order - b.sort_order || a.id - b.id) * dir;
    });
  }, [rows, q, fCat, fModel, fStatus, fExtra, sortKey, sortDir]);

  const pageCount = Math.max(1, Math.ceil(filtered.length / pageSize));
  const paged = filtered.slice(page * pageSize, page * pageSize + pageSize);
  useEffect(() => { if (page >= pageCount) setPage(0); }, [page, pageCount]);

  const kpi = useMemo(() => {
    const r = rows || [];
    const gens = r.reduce((a, x) => a + (x.gen_count || 0), 0);
    const priced = r.filter((x) => x.price > 0);
    return {
      total: r.length, enabled: r.filter((x) => x.enabled).length, trend: r.filter((x) => x.is_trending).length,
      gens, avg: priced.length ? Math.round(priced.reduce((a, x) => a + x.price, 0) / priced.length) : 0,
      models: new Set(r.map((x) => x.recommended_model).filter(Boolean)).size,
      // Rough revenue estimate: generations × price per effect (priced ones only).
      // Ignores discounts / free quota, so it is labelled "≈".
      revenue: r.reduce((a, x) => a + (x.gen_count || 0) * (x.price || 0), 0),
    };
  }, [rows]);

  const sortHead = (k: SortKey, label: string) => (
    <th className="sortable" onClick={() => { if (sortKey === k) setSortDir((d) => (d === 1 ? -1 : 1)); else { setSortKey(k); setSortDir(1); } }}>
      {label}{sortKey === k && <span className="ms sort-ic">{sortDir === 1 ? "arrow_drop_up" : "arrow_drop_down"}</span>}
    </th>
  );

  return (
    <div>
      <h1 className="page-title">Эффекты Mini App</h1>
      <p className="page-sub">CMS управления AI-эффектами: библиотека, пресеты, промпт-билдер, совместимые модели и аналитика использования.</p>

      {msg && (
        <p className={msg.startsWith("✅") || msg.startsWith("📋") ? "note-ok" : "note-err"}>
          <span className="ms sm">{msg.startsWith("✅") ? "check_circle" : msg.startsWith("📋") ? "content_copy" : "error"}</span>
          {msg}<button className="btn ghost sm" onClick={() => setMsg("")} aria-label="Скрыть">×</button>
        </p>
      )}

      <div className="page-stack">
        <div className="metrics">
          <Metric icon="auto_awesome" label="Всего эффектов" value={kpi.total} />
          <Metric icon="visibility" label="Активных" value={kpi.enabled} />
          <Metric icon="local_fire_department" label="В тренде" value={kpi.trend} tone={kpi.trend ? "purple" : undefined} />
          <Metric icon="bolt" label="Генераций" value={kpi.gens} />
          <Metric icon="toll" label="Сред. цена" value={kpi.avg} />
          <Metric icon="hub" label="Моделей" value={kpi.models} />
          <Metric icon="payments" label="≈ Выручка" value={kpi.revenue ? `✨ ${kpi.revenue.toLocaleString("ru")}` : "—"} small hint="Оценка: Σ(генерации × цена) по платным эффектам. Без учёта скидок, акций и бесплатных лимитов — реальная выручка считается на странице «Платежи»." />
        </div>

        {/* Toolbar */}
        <div className="panel" style={{ padding: "var(--sp-3) var(--sp-4)" }}>
          <div className="section-head" style={{ margin: 0 }}>
            <div className="form-row" style={{ gap: "var(--sp-2)", flexWrap: "wrap" }}>
              <div className="seg-tabs">
                {(["video", "photo"] as EffectKind[]).map((k) => (
                  <button key={k} className={kind === k ? "on" : ""} onClick={() => setKind(k)}>{k === "video" ? "Видео" : "Фото"}</button>
                ))}
              </div>
              <div className="seg-tabs">
                <button className={view === "grid" ? "on" : ""} onClick={() => setView("grid")} title="Плитка"><span className="ms sm">grid_view</span></button>
                <button className={view === "table" ? "on" : ""} onClick={() => setView("table")} title="Таблица"><span className="ms sm">table_rows</span></button>
              </div>
            </div>
            <div className="form-row" style={{ gap: "var(--sp-2)", flexWrap: "wrap" }}>
              <button className="btn ghost sm" onClick={() => importRef.current?.click()} title="Импорт JSON"><span className="ms sm">upload</span></button>
              <input ref={importRef} type="file" accept="application/json" hidden onChange={(e) => e.target.files?.[0] && importJson(e.target.files[0])} />
              <button className="btn ghost sm" onClick={exportJson} title="Экспорт JSON"><span className="ms sm">download</span></button>
              <button className="btn" onClick={() => setEditor({ id: "new", row: null })}><span className="ms sm">add</span> Новый эффект</button>
            </div>
          </div>
          <div className="form-row" style={{ gap: "var(--sp-2)", flexWrap: "wrap", marginTop: "var(--sp-3)", paddingTop: "var(--sp-3)", borderTop: "1px solid var(--border)" }}>
            <input style={{ width: 220 }} placeholder="Поиск: название, автор, тег, prompt, ID" value={q} onChange={(e) => setQ(e.target.value)} />
            <Select width={150} ariaLabel="Категория" value={fCat} onChange={setFCat} options={[{ value: "all", label: "Все категории" }, ...CATS[kind].slice(1).map((c) => ({ value: c.key, label: c.label }))]} />
            <Select width={150} ariaLabel="Модель" value={fModel} onChange={setFModel} options={[{ value: "all", label: "Все модели" }, ...MODELS[kind].map((m) => ({ value: m.key, label: m.label }))]} />
            <Select width={140} ariaLabel="Статус" value={fStatus} onChange={setFStatus} options={[{ value: "all", label: "Все статусы" }, { value: "on", label: "Включённые" }, { value: "off", label: "Выключенные" }]} />
            <Select width={150} ariaLabel="Доп" value={fExtra} onChange={setFExtra} options={[{ value: "all", label: "Без доп. фильтра" }, { value: "trend", label: "В тренде" }, { value: "premium", label: "Premium" }, { value: "free", label: "Бесплатные" }, { value: "new", label: "Новинки" }]} />
            {(q || fCat !== "all" || fModel !== "all" || fStatus !== "all" || fExtra !== "all") && (
              <button className="btn ghost sm" onClick={() => { setQ(""); setFCat("all"); setFModel("all"); setFStatus("all"); setFExtra("all"); }}>Сбросить</button>
            )}
            <span className="cfg-hint" style={{ margin: "0 0 0 auto" }}>{filtered.length} из {rows?.length ?? 0}</span>
          </div>
          {sel.size > 0 && (
            <div className="form-row" style={{ gap: "var(--sp-2)", flexWrap: "wrap", marginTop: "var(--sp-3)", paddingTop: "var(--sp-3)", borderTop: "1px solid var(--border)" }}>
              <span className="pill pro">{sel.size} выбрано</span>
              <button className="btn ghost sm" onClick={() => bulkEnable(true)}><span className="ms sm">visibility</span> Вкл</button>
              <button className="btn ghost sm" onClick={() => bulkEnable(false)}><span className="ms sm">visibility_off</span> Выкл</button>
              <button className="btn ghost sm" onClick={bulkPrice}><span className="ms sm">toll</span> Цена</button>
              <button className="btn ghost sm" onClick={bulkCategory}><span className="ms sm">category</span> Категория</button>
              <button className="btn ghost sm" onClick={bulkModel}><span className="ms sm">hub</span> Модель</button>
              <button className="btn ghost sm" onClick={exportJson}><span className="ms sm">download</span> Экспорт</button>
              <button className="btn ghost sm" onClick={bulkDelete}><span className="ms sm" style={{ color: "var(--danger)" }}>delete</span> Удалить</button>
              <button className="btn ghost sm" onClick={() => setSel(new Set())}>Снять</button>
            </div>
          )}
        </div>

        {/* Content */}
        {rows === null ? (
          <div className={view === "grid" ? "fx-grid" : ""}>
            {view === "grid" ? Array.from({ length: 8 }).map((_, i) => <div key={i} className="fx-card"><div className="fx-media skeleton" style={{ aspectRatio: "4/5" }} /><div className="fx-body"><div className="skeleton" style={{ height: 14, width: "70%" }} /><div className="skeleton" style={{ height: 10, width: "40%" }} /></div></div>)
              : <div className="panel"><div className="loading">Загрузка…</div></div>}
          </div>
        ) : filtered.length === 0 ? (
          <div className="panel">
            <div className="empty-state">
              <div className="es-icon"><span className="ms">auto_awesome</span></div>
              <p className="es-title">{rows.length === 0 ? "Эффектов пока нет" : "Ничего не найдено"}</p>
              <p className="es-desc">{rows.length === 0 ? "Создайте первый AI-эффект: название, модель, промпт-шаблон и превью — всё в одном конструкторе." : "Измените поиск или фильтры."}</p>
              {rows.length === 0 && <button className="btn" onClick={() => setEditor({ id: "new", row: null })}><span className="ms sm">add</span> Создать первый эффект</button>}
            </div>
          </div>
        ) : view === "grid" ? (
          <>
            <div className="fx-grid">
              {paged.map((r) => (
                <EffectCard key={r.id} r={r} kind={kind} selected={sel.has(r.id)} reorderable={reorderable} over={over === r.id}
                  onSel={() => setSel((s) => { const n = new Set(s); n.has(r.id) ? n.delete(r.id) : n.add(r.id); return n; })}
                  onOpen={() => setDetail(r)} onEdit={() => setEditor({ id: r.id, row: r })} onToggle={() => toggleEnabled(r)} onDup={() => duplicate(r)}
                  onSavePrice={(p) => savePrice(r, p)}
                  onDragStart={() => (drag.current = r.id)} onDragOver={() => setOver(r.id)} onDrop={() => onDrop(r.id)} />
              ))}
            </div>
            <Pager page={page} pageCount={pageCount} pageSize={pageSize} total={filtered.length} setPage={setPage} setPageSize={setPageSize} />
          </>
        ) : (
          <div className="panel">
            <div className="table-wrap sticky" tabIndex={0} style={{ border: "none" }}>
              <table className="tbl">
                <thead>
                  <tr>
                    <th style={{ width: 32 }}><input type="checkbox" className="fx-check" aria-label="Выбрать" checked={paged.length > 0 && paged.every((r) => sel.has(r.id))}
                      onChange={(e) => setSel(e.target.checked ? new Set(paged.map((r) => r.id)) : new Set())} /></th>
                    <th>Превью</th>{sortHead("name_ru", "Название")}<th>Категория</th><th>Модель</th>
                    {sortHead("price", "Цена")}{sortHead("gen_count", "Ген.")}<th>Статус</th>{sortHead("sort_order", "#")}<th style={{ width: 140 }}>Действия</th>
                  </tr>
                </thead>
                <tbody>
                  {paged.map((r) => {
                    const m = getMeta(r.default_params);
                    return (
                      <tr key={r.id} draggable={reorderable} onDragStart={() => (drag.current = r.id)}
                        onDragOver={(e) => { if (reorderable) { e.preventDefault(); setOver(r.id); } }} onDrop={() => onDrop(r.id)}
                        style={over === r.id ? { outline: "1px solid var(--accent)" } : undefined}>
                        <td>{reorderable && <span className="ms sm drag-handle" style={{ cursor: "grab" }} draggable={reorderable} onDragStart={() => (drag.current = r.id)}>drag_indicator</span>}</td>
                        <td><input type="checkbox" className="fx-check" aria-label="Выбрать" checked={sel.has(r.id)} onChange={() => setSel((s) => { const n = new Set(s); n.has(r.id) ? n.delete(r.id) : n.add(r.id); return n; })} /></td>
                        <td>{r.preview_url ? (isVideo(r.preview_url) ? <video src={r.preview_url} muted className="thumb-xs" style={{ width: 44, height: 44, objectFit: "cover", borderRadius: 8 }} /> : <img src={r.preview_url} alt="" className="thumb-xs" loading="lazy" style={{ width: 44, height: 44, objectFit: "cover", borderRadius: 8 }} />) : <span className="muted">—</span>}</td>
                        <td><b style={{ cursor: "pointer" }} onClick={() => setDetail(r)}>{r.name_ru}</b>{r.author && <div className="muted" style={{ fontSize: 11 }}>by {r.author}</div>}</td>
                        <td><span className="pill muted">{catLabel(kind, r.category)}</span></td>
                        <td className="code-key">{modelLabel(r.recommended_model || "")}</td>
                        <td style={{ fontVariantNumeric: "tabular-nums" }} onClick={(e) => e.stopPropagation()}><PriceEdit r={r} onSave={(p) => savePrice(r, p)} /></td>
                        <td className="muted" style={{ fontVariantNumeric: "tabular-nums" }}>{r.gen_count.toLocaleString("ru")}</td>
                        <td><span className={"pill " + (r.enabled ? "ok" : "muted")}>{r.enabled ? "Активен" : "Скрыт"}</span>{(r.is_trending || m.premium || m.is_new) && <span className="muted" style={{ fontSize: 11, marginLeft: 4 }}>{r.is_trending ? "🔥" : ""}{m.premium ? "💎" : ""}{m.is_new ? "🆕" : ""}</span>}</td>
                        <td className="muted">{r.sort_order}</td>
                        <td>
                          <div className="form-row" style={{ gap: 2, flexWrap: "nowrap" }}>
                            <button className="btn ghost sm" title="Открыть" onClick={() => setDetail(r)}><span className="ms sm">visibility</span></button>
                            <button className="btn ghost sm" title="Редактировать" onClick={() => setEditor({ id: r.id, row: r })}><span className="ms sm">edit</span></button>
                            <button className="btn ghost sm" title="Дублировать" onClick={() => duplicate(r)}><span className="ms sm">content_copy</span></button>
                            <button className="btn ghost sm" title="Удалить" onClick={() => remove(r)}><span className="ms sm" style={{ color: "var(--danger)" }}>delete</span></button>
                          </div>
                        </td>
                      </tr>
                    );
                  })}
                </tbody>
              </table>
            </div>
            <Pager page={page} pageCount={pageCount} pageSize={pageSize} total={filtered.length} setPage={setPage} setPageSize={setPageSize} />
          </div>
        )}
      </div>

      {detail && (
        <DetailModal r={detail} kind={kind} onClose={() => setDetail(null)}
          onEdit={() => { setEditor({ id: detail.id, row: detail }); setDetail(null); }}
          onDup={() => { duplicate(detail); setDetail(null); }} onDelete={() => remove(detail)} />
      )}
      {editor && (
        <EffectEditor kind={kind} init={editor} specs={specs} onClose={() => setEditor(null)}
          onSaved={(reopenId) => { load(); if (reopenId != null) setEditor((e) => e && { id: reopenId, row: null }); }}
          toast={toast} />
      )}
    </div>
  );
}

// ---------- Inline price editor (grid card + table) ----------
// Click the price → number field → Enter/blur saves, Esc cancels. Shows the override
// (✨ N) or, on "авто", the real computed price so the admin sees what users pay.
function PriceEdit({ r, onSave, compact }: { r: EffectAdminRow; onSave: (price: number) => void; compact?: boolean }) {
  const [editing, setEditing] = useState(false);
  const [val, setVal] = useState(String(r.price || ""));
  useEffect(() => { if (!editing) setVal(String(r.price || "")); }, [r.price, editing]);
  const commit = () => { onSave(Math.max(0, Number(val) || 0)); setEditing(false); };
  if (editing) {
    return (
      <input className="px-edit mono" type="number" min={0} autoFocus value={val} placeholder="0=авто"
        onClick={(e) => e.stopPropagation()}
        onChange={(e) => setVal(e.target.value)}
        onBlur={commit}
        onKeyDown={(e) => {
          e.stopPropagation();
          if (e.key === "Enter") commit();
          else if (e.key === "Escape") { setVal(String(r.price || "")); setEditing(false); }
        }}
        style={{ width: 76, padding: "2px 6px", fontSize: 12.5 }} />
    );
  }
  return (
    <span className="px-show" title="Кликните, чтобы изменить цену (0 = авто)" style={{ cursor: "pointer" }}
      onClick={(e) => { e.stopPropagation(); setEditing(true); }}>
      {r.price
        ? <span className={compact ? "fx-price" : ""}>✨ {r.price}</span>
        : <span className="muted" style={{ fontWeight: 600 }}>авто{r.effective_price ? `: ${r.effective_price} ✨` : ""}</span>}
    </span>
  );
}

// ---------- Effect card (library) ----------
function EffectCard({ r, kind, selected, reorderable, over, onSel, onOpen, onEdit, onToggle, onDup, onSavePrice, onDragStart, onDragOver, onDrop }: {
  r: EffectAdminRow; kind: EffectKind; selected: boolean; reorderable: boolean; over: boolean;
  onSel: () => void; onOpen: () => void; onEdit: () => void; onToggle: () => void; onDup: () => void;
  onSavePrice: (price: number) => void;
  onDragStart: () => void; onDragOver: () => void; onDrop: () => void;
}) {
  const m = getMeta(r.default_params);
  return (
    <div className={"fx-card" + (r.enabled ? "" : " off") + (over ? " over" : "")} draggable={reorderable}
      onDragStart={onDragStart} onDragOver={(e) => { if (reorderable) { e.preventDefault(); onDragOver(); } }} onDrop={onDrop}>
      <div className="fx-media" onClick={onOpen}>
        {r.preview_url ? (isVideo(r.preview_url) ? <video src={r.preview_url} muted loop playsInline onMouseEnter={(e) => e.currentTarget.play()} onMouseLeave={(e) => e.currentTarget.pause()} /> : <ImgFallback src={r.preview_url} />) : <span className="ms fx-noimg">image</span>}
        <input type="checkbox" className="fx-check fx-sel" aria-label="Выбрать эффект" checked={selected} onClick={(e) => e.stopPropagation()} onChange={onSel} />
        <div className="fx-badges">
          {r.is_trending && <span className="fx-badge trend">🔥 Trend</span>}
          {m.premium && <span className="fx-badge premium">💎 Premium</span>}
          {m.is_new && <span className="fx-badge new">NEW</span>}
          {m.featured && <span className="fx-badge feat">★ Featured</span>}
        </div>
        <div className="fx-actions">
          <button className="btn ghost sm" title="Редактировать" onClick={(e) => { e.stopPropagation(); onEdit(); }}><span className="ms sm">edit</span></button>
          <button className="btn ghost sm" title="Дублировать" onClick={(e) => { e.stopPropagation(); onDup(); }}><span className="ms sm">content_copy</span></button>
        </div>
      </div>
      <div className="fx-body" onClick={onOpen}>
        <div className="fx-name">{r.name_ru || "Без названия"}</div>
        <div className="muted" style={{ fontSize: 11 }}>{catLabel(kind, r.category)} · {modelLabel(r.recommended_model || "")}{r.author ? ` · by ${r.author}` : ""}</div>
        <div className="fx-meta">
          <span onClick={(e) => e.stopPropagation()}><PriceEdit r={r} onSave={onSavePrice} compact /></span>
          <span className="form-row" style={{ gap: 8 }}>
            <span className="fx-gens"><span className="ms sm" style={{ fontSize: 13 }}>bolt</span>{r.gen_count.toLocaleString("ru")}</span>
            <Switch ariaLabel="Эффект включён" checked={r.enabled} onChange={() => onToggle()} />
          </span>
        </div>
      </div>
    </div>
  );
}

// ---------- Pager ----------
function Pager({ page, pageCount, pageSize, total, setPage, setPageSize }: {
  page: number; pageCount: number; pageSize: number; total: number; setPage: (n: number) => void; setPageSize: (n: number) => void;
}) {
  if (total === 0) return null;
  return (
    <div className="pager">
      <span className="cfg-hint" style={{ margin: 0 }}>Всего: {total} · стр. {page + 1} из {pageCount}</span>
      <div className="form-row" style={{ gap: "var(--sp-2)" }}>
        <Select width={120} ariaLabel="На странице" value={String(pageSize)} onChange={(v) => setPageSize(Number(v))}
          options={[12, 24, 48, 96].map((n) => ({ value: String(n), label: `${n} / стр.` }))} />
        <div className="pg-nums">
          <button className="btn ghost sm" disabled={page === 0} onClick={() => setPage(page - 1)}><span className="ms sm">chevron_left</span></button>
          <button className="btn ghost sm" disabled={page >= pageCount - 1} onClick={() => setPage(page + 1)}><span className="ms sm">chevron_right</span></button>
        </div>
      </div>
    </div>
  );
}

// ---------- Detail modal ----------
function DetailModal({ r, kind, onClose, onEdit, onDup, onDelete }: {
  r: EffectAdminRow; kind: EffectKind; onClose: () => void; onEdit: () => void; onDup: () => void; onDelete: () => void;
}) {
  const m = getMeta(r.default_params);
  const media = [r.preview_url, ...(m.gallery || []), m.video_url, m.gif_url].filter(Boolean) as string[];
  const [hero, setHero] = useState(media[0] || "");
  return (
    <Modal title={r.name_ru} icon="auto_awesome" onClose={onClose} wide
      footer={<>
        <button className="btn ghost spacer" onClick={onDup}><span className="ms sm">content_copy</span> Дублировать</button>
        <button className="btn danger" onClick={onDelete}><span className="ms sm">delete</span> Удалить</button>
        <button className="btn" onClick={onEdit}><span className="ms sm">edit</span> Редактировать</button>
      </>}>
      <div className="bc-grid" style={{ gridTemplateColumns: "minmax(0,1fr) minmax(0,1fr)", gap: "var(--sp-5)" }}>
        <div>
          <div className="fx-hero">{hero ? (isVideo(hero) ? <video src={hero} controls muted /> : <ImgFallback src={hero} />) : <span className="ms fx-noimg">image</span>}</div>
          {media.length > 1 && <div className="fx-gallery" style={{ marginTop: "var(--sp-2)" }}>{media.map((u) => isVideo(u) ? null : <img key={u} src={u} alt="" className={hero === u ? "on" : ""} onClick={() => setHero(u)} />)}</div>}
        </div>
        <div style={{ display: "flex", flexDirection: "column", gap: "var(--sp-3)", minWidth: 0 }}>
          <div className="form-row" style={{ gap: 6, flexWrap: "wrap" }}>
            <span className={"pill " + (r.enabled ? "ok" : "muted")}>{r.enabled ? "Активен" : "Скрыт"}</span>
            {r.is_trending && <span className="pill danger">🔥 Тренд</span>}
            {m.premium && <span className="pill pro">💎 Premium</span>}
            {m.is_new && <span className="pill warn">NEW</span>}
            {m.version && <span className="pill muted">v{m.version}</span>}
          </div>
          {m.description && <p className="cfg-hint" style={{ margin: 0 }}>{m.description}</p>}
          <div className="metrics" style={{ margin: 0, gridTemplateColumns: "1fr 1fr" }}>
            <Metric icon="bolt" label="Генераций" value={r.gen_count} small />
            <Metric icon="toll" label="Цена" value={r.price || "авто"} small />
          </div>
          <Field label="Категория">{catLabel(kind, r.category)}{m.subcategory ? ` · ${m.subcategory}` : ""}</Field>
          <Field label="Автор">{r.author || "—"}</Field>
          <Field label="Совместимые модели"><div className="mchips">{(r.compatible_models.length ? r.compatible_models : [r.recommended_model || ""]).filter(Boolean).map((mm) => <span key={mm} className="mchip on">{modelLabel(mm)}</span>)}</div></Field>
          {m.tags?.length ? <Field label="Теги"><div className="chip-row">{m.tags.map((t) => <span className="chip" key={t}>{t}</span>)}</div></Field> : null}
        </div>
      </div>

      <div style={{ marginTop: "var(--sp-5)", display: "flex", flexDirection: "column", gap: "var(--sp-3)" }}>
        {r.prompt_template && <Field label="Prompt-шаблон"><code className="code-key" style={{ whiteSpace: "pre-wrap" }}>{r.prompt_template}</code></Field>}
        {m.negative_prompt && <Field label="Negative Prompt"><code className="code-key" style={{ whiteSpace: "pre-wrap" }}>{m.negative_prompt}</code></Field>}
        {(() => { const chips = paramChips(genOnly(r.default_params)); return chips.length ? (
          <Field label="Параметры генерации"><div className="chip-row">{chips.map((c) => <span className="chip" key={c}>{c}</span>)}</div></Field>
        ) : <Field label="Параметры генерации"><span className="muted">Дефолты модели</span></Field>; })()}
      </div>
      <p className="cfg-hint" style={{ marginTop: "var(--sp-4)" }}>
        <span className="ms sm" style={{ verticalAlign: "-3px" }}>history</span>{" "}
        Журнал изменений (кто/когда/что, rollback) ведётся в общем «Аудит-логе» (действия <code className="code-key">effect.*</code>). CTR, рейтинг, выручка и избранное требуют таблиц событий на бэкенде; реальная метрика — «Генераций» ({r.gen_count}).
      </p>
    </Modal>
  );
}
function Field({ label, children }: { label: string; children: React.ReactNode }) {
  return <div className="cfg-field"><span className="cfg-cap">{label}</span><div>{children}</div></div>;
}

// ---------- Editor modal ----------
function EffectEditor({ kind, init, specs, onClose, onSaved, toast }: {
  kind: EffectKind; init: { id: number | "new"; row: EffectAdminRow | null }; specs: Record<string, ModelSpec>;
  onClose: () => void; onSaved: (reopenId?: number) => void; toast: (m: string) => void;
}) {
  const [id, setId] = useState<number | "new">(init.id);
  const r = init.row;
  const [d, setD] = useState<EffectPayload>(() => r ? rowToPayload(r) : { ...EMPTY, recommended_model: MODELS[kind][0].key, compatible_models: [MODELS[kind][0].key] });
  const [meta, setMeta] = useState<Meta>(() => r ? getMeta(r.default_params) : {});
  // Generation params as a structured object (no raw JSON); _meta lives in `meta`.
  const [genParams, setGenParams] = useState<Record<string, unknown>>(() => genOnly(r?.default_params || {}));
  const [tagInput, setTagInput] = useState("");
  const [busy, setBusy] = useState(false);  // FIX: AUDIT12-L2 - disable save while in-flight
  const fileRef = useRef<HTMLInputElement>(null);
  const promptRef = useRef<HTMLTextAreaElement>(null);

  const set = <K extends keyof EffectPayload>(k: K, v: EffectPayload[K]) => setD((p) => ({ ...p, [k]: v }));
  const setM = <K extends keyof Meta>(k: K, v: Meta[K]) => setMeta((p) => ({ ...p, [k]: v }));

  const toggleModel = (mk: string) => set("compatible_models", d.compatible_models.includes(mk) ? d.compatible_models.filter((x) => x !== mk) : [...d.compatible_models, mk]);
  const insertVar = (v: string) => {
    const el = promptRef.current; const cur = d.prompt_template || "";
    if (!el) { set("prompt_template", cur + v); return; }
    const s = el.selectionStart, e = el.selectionEnd;
    set("prompt_template", cur.slice(0, s) + v + cur.slice(e));
    requestAnimationFrame(() => { el.focus(); el.selectionStart = el.selectionEnd = s + v.length; });
  };
  const addTag = (raw: string) => { const t = raw.trim().replace(/,$/, ""); if (!t) return; setM("tags", Array.from(new Set([...(meta.tags || []), t]))); setTagInput(""); };

  async function save() {
    const body: EffectPayload = { ...d, default_params: withMeta(genParams, meta) };
    setBusy(true);
    try {
      if (id === "new") {
        const created = await api.effectCreate(kind, body);
        setId(created.id); onSaved(created.id);
        toast("✅ Эффект создан — теперь можно загрузить превью");
      } else {
        await api.effectUpdate(kind, id, body); onSaved();
        toast("✅ Сохранено");
      }
    } catch (e) { toast(String(e)); }
    finally { setBusy(false); }
  }
  async function uploadPreview(file: File) {
    if (typeof id !== "number") { toast("Сначала сохраните эффект, затем загрузите превью"); return; }
    try { const { preview_url } = await api.effectPreview(kind, id, file); set("preview_url", preview_url); onSaved(); toast("✅ Превью загружено"); }
    catch (e) { toast(String(e)); }
  }
  // Ctrl+S inside the editor
  useEffect(() => {
    const h = (e: KeyboardEvent) => { if ((e.ctrlKey || e.metaKey) && e.key.toLowerCase() === "s") { e.preventDefault(); save(); } };
    window.addEventListener("keydown", h); return () => window.removeEventListener("keydown", h);
  }, [save]);  // FIX: AUDIT-41 - add deps array to prevent listener thrash

  return (
    <Modal title={id === "new" ? "Новый эффект" : `Редактирование #${id}`} icon="auto_awesome" onClose={onClose} wide
      footer={<>
        <span className="cfg-hint" style={{ marginRight: "auto" }}>Ctrl+S — сохранить</span>
        <button className="btn ghost" onClick={onClose}>Закрыть</button>
        <button className="btn" disabled={busy} onClick={save}><span className="ms sm">save</span> Сохранить</button>
      </>}>
      <div style={{ display: "flex", flexDirection: "column", gap: "var(--sp-5)" }}>
        <Group title="Основное">
          <div className="form-grid">
            <F label="Название"><input value={d.name_ru} onChange={(e) => set("name_ru", e.target.value)} /></F>
            <F label="Slug"><input className="mono" value={meta.slug ?? ""} onChange={(e) => setM("slug", e.target.value)} placeholder="auto-effect" /></F>
            <F label="Автор"><input value={d.author ?? ""} onChange={(e) => set("author", e.target.value || null)} /></F>
            <F label="Категория"><Select width="100%" ariaLabel="Категория" value={d.category} onChange={(v) => set("category", v)} options={CATS[kind].map((c) => ({ value: c.key, label: c.label }))} /></F>
            <F label="Подкатегория"><input value={meta.subcategory ?? ""} onChange={(e) => setM("subcategory", e.target.value)} /></F>
            <F label="Версия"><input value={meta.version ?? ""} onChange={(e) => setM("version", e.target.value)} placeholder="1.0" /></F>
          </div>
          <F label="Краткое описание"><input value={meta.description ?? ""} onChange={(e) => setM("description", e.target.value)} /></F>
          <F label="Полное описание"><textarea style={{ minHeight: 60 }} value={meta.full_description ?? ""} onChange={(e) => setM("full_description", e.target.value)} /></F>
          <F label="Теги">
            <div className="chip-row" style={{ marginBottom: 6 }}>{(meta.tags || []).map((t) => <span className="chip" key={t}>{t}<button onClick={() => setM("tags", (meta.tags || []).filter((x) => x !== t))}><span className="ms sm">close</span></button></span>)}</div>
            <input value={tagInput} onChange={(e) => setTagInput(e.target.value)} placeholder="тег + Enter"
              onKeyDown={(e) => { if (e.key === "Enter" || e.key === ",") { e.preventDefault(); addTag(tagInput); } }} onBlur={() => addTag(tagInput)} />
          </F>
        </Group>

        <Group title="Цена, статус и флаги">
          <div className="form-grid">
            <F label="Цена, ✨ (0 = авто)"><input type="number" min={0} value={d.price} onChange={(e) => set("price", Math.max(0, Number(e.target.value) || 0))} /></F>
            <F label="Макс. фото"><input type="number" min={1} value={d.max_photos} onChange={(e) => set("max_photos", Math.max(1, Number(e.target.value) || 1))} /></F>
            <F label="Порядок"><input type="number" value={d.sort_order} onChange={(e) => set("sort_order", Number(e.target.value) || 0)} /></F>
            {kind === "photo" && <F label="Бейдж (new/top/pro)"><input value={d.badge ?? ""} onChange={(e) => set("badge", e.target.value || null)} /></F>}
          </div>
          <div className="form-grid">
            <Switch checked={d.enabled} onChange={(v) => set("enabled", v)} label="Включён" />
            <Switch checked={d.is_trending} onChange={(v) => set("is_trending", v)} label="В тренде 🔥" />
            <Switch checked={!!meta.premium} onChange={(v) => setM("premium", v)} label="Premium 💎" />
            <Switch checked={!!meta.featured} onChange={(v) => setM("featured", v)} label="Featured ★" />
            <Switch checked={!!meta.is_new} onChange={(v) => setM("is_new", v)} label="Новинка" />
            <Switch checked={!!meta.is_popular} onChange={(v) => setM("is_popular", v)} label="Популярный" />
            <Switch checked={d.is_ad} onChange={(v) => set("is_ad", v)} label="Спонсорский (AD)" />
          </div>
        </Group>

        <Group title="Совместимые модели" hint="Mini App покажет карточки только для известных моделей. Рекомендуемая выбирается по умолчанию.">
          <div className="mchips">
            {MODELS[kind].map((m) => (
              <span key={m.key} className={"mchip" + (d.compatible_models.includes(m.key) ? " on" : "")} onClick={() => toggleModel(m.key)}>
                {d.compatible_models.includes(m.key) && <span className="ms">check</span>}{m.label}
              </span>
            ))}
          </div>
          <F label="Рекомендуемая модель">
            <Select width={260} ariaLabel="Рекомендуемая модель" value={d.recommended_model ?? ""} onChange={(v) => set("recommended_model", v)}
              options={(d.compatible_models.length ? d.compatible_models : MODELS[kind].map((m) => m.key)).map((k) => ({ value: k, label: modelLabel(k) }))} />
          </F>
        </Group>

        <Group title="Промпт" hint="Переменные подставляются движком генерации при сборке запроса.">
          <div className="var-row">{PROMPT_VARS.map((v) => <button key={v} type="button" className="var-chip" onClick={() => insertVar(v)}>{v}</button>)}</div>
          <F label="Prompt-шаблон"><textarea ref={promptRef} style={{ minHeight: 70 }} value={d.prompt_template ?? ""} onChange={(e) => set("prompt_template", e.target.value)} /></F>
          <F label="Поле промпта в Mini App">
            <Select width={260} ariaLabel="Режим промпта" value={d.prompt_mode ?? "optional"}
              onChange={(v) => set("prompt_mode", v as "hidden" | "optional" | "required")}
              options={[
                { value: "optional", label: "Опционально (можно пусто)" },
                { value: "required", label: "Обязательно" },
                { value: "hidden", label: "Скрыто (чистый стиль)" },
              ]} />
          </F>
          <div className="form-grid">
            <F label="Negative Prompt"><textarea style={{ minHeight: 50 }} value={meta.negative_prompt ?? ""} onChange={(e) => setM("negative_prompt", e.target.value)} /></F>
            <F label="System Prompt"><textarea style={{ minHeight: 50 }} value={meta.system_prompt ?? ""} onChange={(e) => setM("system_prompt", e.target.value)} /></F>
          </div>
        </Group>

        <Group title="Параметры генерации" hint="Параметры по умолчанию для рекомендуемой модели: качество, формат, длительность, разрешение и т.п. Пустое поле = дефолт модели.">
          <SmartParams spec={specs[d.recommended_model || ""]} params={genParams} onChange={setGenParams} />
        </Group>

        <Group title="Медиа" hint="Превью загружается на сервер (jpg/png/webp/gif/mp4/webm, ≤30 МБ). Галерея/видео/GIF — по URL (можно вставить ссылку загруженного файла).">
          <div className="form-row" style={{ gap: "var(--sp-3)", alignItems: "center" }}>
            <div className="fx-media" style={{ width: 90, height: 112, borderRadius: "var(--r-sm)", flex: "0 0 auto" }}>
              {d.preview_url ? (isVideo(d.preview_url) ? <video src={d.preview_url} muted /> : <ImgFallback src={d.preview_url} />) : <span className="ms fx-noimg">image</span>}
            </div>
            <div>
              <button className="btn ghost" onClick={() => fileRef.current?.click()} disabled={id === "new"}><span className="ms sm">upload</span> Загрузить превью</button>
              <input ref={fileRef} type="file" accept="image/*,video/mp4,video/webm" hidden onChange={(e) => { const f = e.target.files?.[0]; if (!f) return; if (f.size > 30 * 1024 * 1024) { toast("Файл больше 30 МБ"); return; } uploadPreview(f); }} />
              {id === "new" && <p className="cfg-hint" style={{ margin: "6px 0 0" }}>Сохраните эффект, затем загрузите превью.</p>}
            </div>
          </div>
          <div className="form-grid">
            <F label="Thumbnail URL"><input className="mono" value={d.thumbnail_url ?? ""} onChange={(e) => set("thumbnail_url", e.target.value || null)} /></F>
            <F label="Video URL"><input className="mono" value={meta.video_url ?? ""} onChange={(e) => setM("video_url", e.target.value)} /></F>
            <F label="GIF URL"><input className="mono" value={meta.gif_url ?? ""} onChange={(e) => setM("gif_url", e.target.value)} /></F>
            <F label="Галерея (URL через запятую)"><input className="mono" value={(meta.gallery || []).join(", ")} onChange={(e) => setM("gallery", e.target.value.split(",").map((s) => s.trim()).filter(Boolean))} /></F>
          </div>
        </Group>
      </div>
    </Modal>
  );
}

// Friendly per-model parameter form (replaces the raw default_params JSON). Renders
// only the controls the selected model actually supports, from its spec schema.
function SmartParams({ spec, params, onChange }: { spec?: ModelSpec; params: Record<string, unknown>; onChange: (p: Record<string, unknown>) => void }) {
  if (!spec) return <p className="cfg-hint">Параметры появятся после выбора рекомендуемой модели.</p>;
  const set = (k: string, v: unknown) => onChange({ ...params, [k]: v });
  const sval = (k: string): string => { const v = params[k] ?? spec.default[k]; return v == null ? "" : String(v); };
  const bval = (k: string): boolean => Boolean(params[k] ?? spec.default[k]);
  return (
    <div style={{ display: "flex", flexDirection: "column", gap: "var(--sp-3)" }}>
      <div className="form-grid">
        {spec.models && <F label="Вариант модели"><Select width="100%" ariaLabel="Вариант" value={sval("model")}
          options={spec.models.map(([v, l]) => ({ value: v, label: l }))} onChange={(v) => set("model", v)} /></F>}
        {spec.qualities && <F label="Качество"><Select width="100%" ariaLabel="Качество" value={sval("quality")}
          options={spec.qualities.map((q) => ({ value: q, label: q.toUpperCase() }))} onChange={(v) => set("quality", v)} /></F>}
        {spec.ratios && <F label="Формат (соотношение)"><Select width="100%" ariaLabel="Формат" value={sval("ratio")}
          options={spec.ratios.map((rt) => ({ value: rt, label: rt }))} onChange={(v) => set("ratio", v)} /></F>}
        {spec.durations && <F label="Длительность"><Select width="100%" ariaLabel="Длительность" value={sval("duration")}
          options={spec.durations.map((s) => ({ value: String(s), label: `${s} сек` }))} onChange={(v) => set("duration", Number(v))} /></F>}
        {spec.resolutions && <F label="Разрешение"><Select width="100%" ariaLabel="Разрешение" value={sval("res")}
          options={spec.resolutions.map((rs) => ({ value: rs, label: rs }))} onChange={(v) => set("res", v)} /></F>}
        {spec.modes && <F label="Режим"><Select width="100%" ariaLabel="Режим" value={sval("mode")}
          options={spec.modes.map(([v, l]) => ({ value: v, label: l }))} onChange={(v) => set("mode", v)} /></F>}
        {("count" in spec.default) && <F label="Количество"><input type="number" min={1}
          value={Number(params.count ?? spec.default.count ?? 1)} onChange={(e) => set("count", Math.max(1, Number(e.target.value) || 1))} /></F>}
      </div>
      {(spec.fourk || spec.audio || spec.seed || spec.prompt_enhance) && (
        <div className="form-grid">
          {spec.fourk && <Switch checked={bval("fourk")} onChange={(v) => set("fourk", v)} label="4K" />}
          {spec.audio && <Switch checked={bval("audio")} onChange={(v) => set("audio", v)} label="Звук" />}
          {spec.seed && <Switch checked={bval("seed")} onChange={(v) => set("seed", v)} label="Фиксированный сид" />}
          {spec.prompt_enhance && <Switch checked={bval("prompt_enhance")} onChange={(v) => set("prompt_enhance", v)} label="Улучшение промпта" />}
        </div>
      )}
      <p className="cfg-hint" style={{ margin: 0 }}>
        <span className="ms sm" style={{ verticalAlign: "-3px" }}>info</span>{" "}
        Поля под рекомендуемую модель «{spec.title}». Сохраняются только заданные значения — остальное берётся из дефолтов модели.
      </p>
    </div>
  );
}

function Group({ title, hint, children }: { title: string; hint?: string; children: React.ReactNode }) {
  return (
    <div>
      <div className="panel-title sm" style={{ margin: "0 0 var(--sp-3)", display: "flex", alignItems: "center", gap: 6, paddingBottom: "var(--sp-2)", borderBottom: "1px solid var(--border)" }}>
        {title}{hint && <span className="ms sm" title={hint} style={{ color: "var(--hint)", cursor: "help", fontSize: 15 }}>info</span>}
      </div>
      <div style={{ display: "flex", flexDirection: "column", gap: "var(--sp-3)" }}>{children}</div>
    </div>
  );
}
function F({ label, children }: { label: string; children: React.ReactNode }) {
  return <div className="cfg-field"><span className="cfg-cap">{label}</span>{children}</div>;
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
