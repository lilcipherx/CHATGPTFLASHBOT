import { useEffect, useMemo, useRef, useState } from "react";
import { api, BannerPayload, BannerRow, CarouselBehavior } from "../api";
import { Select } from "../components/Select";
import { Switch } from "../components/Switch";
import { Modal } from "../components/Modal";

const EMPTY: BannerPayload = {
  image_url: "", title: null, subtitle: null, link_url: null, locale: null, sort_order: 0, enabled: true,
};
// Locale options for the per-slide targeting dropdown ("" = all languages).
const LOCALES: { value: string; label: string }[] = [
  { value: "", label: "🌐 Все языки" },
  { value: "ru", label: "🇷🇺 Русский" }, { value: "en", label: "🇬🇧 English" },
  { value: "uz", label: "🇺🇿 Oʻzbekcha" }, { value: "es", label: "🇪🇸 Español" },
  { value: "fr", label: "🇫🇷 Français" }, { value: "ar", label: "🇸🇦 العربية" },
  { value: "pt", label: "🇧🇷 Português" }, { value: "zh", label: "🇨🇳 简体中文" },
];
const localeLabel = (code: string | null) => LOCALES.find((l) => l.value === (code ?? ""))?.label ?? code;
const DEFAULT_BEHAVIOR: CarouselBehavior = {
  animation: "slide", speed_ms: 400, autoplay: true, pause_on_interaction: true,
  loop: true, show_indicators: true, show_arrows: false, manual_swipe: true,
};
const payloadOf = (r: BannerRow): BannerPayload => ({
  image_url: r.image_url, title: r.title, subtitle: r.subtitle,
  link_url: r.link_url, locale: r.locale, sort_order: r.sort_order, enabled: r.enabled,
});

export function Banners() {
  const [rows, setRows] = useState<BannerRow[] | null>(null);
  const [intervalMs, setIntervalMs] = useState(5000);
  const [behavior, setBehavior] = useState<CarouselBehavior>(DEFAULT_BEHAVIOR);
  const [saved, setSaved] = useState({ intervalMs: 5000, behavior: DEFAULT_BEHAVIOR });
  const [busy, setBusy] = useState(false);  // FIX: AUDIT12-L2 - slide editor save in-flight guard
  const [editId, setEditId] = useState<number | "new" | null>(null);
  const [draft, setDraft] = useState<BannerPayload>({ ...EMPTY });
  const [pendingFile, setPendingFile] = useState<File | null>(null);
  const [pendingPreview, setPendingPreview] = useState<string>("");
  const [msg, setMsg] = useState("");
  const [savingSettings, setSavingSettings] = useState(false);
  const [reordering, setReordering] = useState(false);

  const load = () =>
    api.banners()
      .then((d) => {
        setRows(d.banners);
        // FIX: UI-8 - fall back to 5000ms if interval_ms is missing so the input and
        // the live-preview label never render "NaN" (e.g. "интервал NaN с").
        const ivl = Number.isFinite(d.interval_ms) ? d.interval_ms : 5000;
        setIntervalMs(ivl);
        setBehavior(d.behavior || DEFAULT_BEHAVIOR);
        setSaved({ intervalMs: ivl, behavior: d.behavior || DEFAULT_BEHAVIOR });
      })
      .catch((e) => { setMsg(String(e)); setRows([]); });
  useEffect(() => { load(); /* eslint-disable-next-line */ }, []);

  const settingsDirty = useMemo(
    () => intervalMs !== saved.intervalMs || JSON.stringify(behavior) !== JSON.stringify(saved.behavior),
    [intervalMs, behavior, saved],
  );
  const setB = <K extends keyof CarouselBehavior>(k: K, v: CarouselBehavior[K]) =>
    setBehavior((b) => ({ ...b, [k]: v }));

  async function saveSettings() {
    setSavingSettings(true);
    try {
      const r = await api.setCarouselSettings(intervalMs, behavior);
      setIntervalMs(r.interval_ms); setBehavior(r.behavior);
      setSaved({ intervalMs: r.interval_ms, behavior: r.behavior });
      setMsg("✅ Настройки карусели сохранены");
    } catch (e) { setMsg(String(e)); }
    finally { setSavingSettings(false); }
  }

  // ---- editor ----
  function startNew() {
    if (pendingPreview) URL.revokeObjectURL(pendingPreview);  // FIX: F63 - revoke previous blob URL
    setDraft({ ...EMPTY, sort_order: (rows?.length ?? 0) });
    setPendingFile(null); setPendingPreview(""); setEditId("new");
  }
  function startEdit(r: BannerRow) {
    if (pendingPreview) URL.revokeObjectURL(pendingPreview);  // FIX: F63
    setDraft(payloadOf(r)); setPendingFile(null); setPendingPreview(""); setEditId(r.id);
  }
  const setField = <K extends keyof BannerPayload>(k: K, v: BannerPayload[K]) =>
    setDraft((d) => ({ ...d, [k]: v }));

  async function pickImage(file: File) {
    // FIX: AUDIT-21 - client-side size limit (30 MB) before upload
    if (file.size > 30 * 1024 * 1024) { setMsg("Файл больше 30 МБ"); return; }
    if (!file.type.startsWith("image/")) { setMsg("Только изображения"); return; }
    if (typeof editId === "number") {
      try { const { image_url } = await api.bannerImage(editId, file); setField("image_url", image_url); await load(); }
      catch (e) { setMsg(String(e)); }
    } else {
      // FIX: FRONTEND - revoke the previous preview URL before creating a new one so
      // repeatedly picking different files doesn't leak blob URLs (each holds a
      // reference to the File in memory until the document unloads).
      if (pendingPreview) URL.revokeObjectURL(pendingPreview);
      setPendingFile(file); setPendingPreview(URL.createObjectURL(file));
    }
  }

  async function save() {
    // A slide with no image is invisible in the Mini App (the feed filters on
    // image_url), so require one up front instead of creating a dead blank slide.
    if (editId === "new" && !pendingFile && !draft.image_url) {
      setMsg("Добавьте изображение слайда перед сохранением"); return;
    }
    setBusy(true);
    try {
      if (editId === "new") {
        const created = await api.bannerCreate(draft);
        if (pendingFile) {
          try {
            await api.bannerImage(created.id, pendingFile);
          } catch (e) {
            // Image rejected (bad format / too large): roll back the just-created
            // empty slide so no broken placeholder is left behind, then surface why.
            await api.bannerDelete(created.id).catch(() => {});
            throw e;
          }
        }
      } else if (typeof editId === "number") {
        await api.bannerUpdate(editId, draft);
      }
      setEditId(null); setPendingFile(null);
      // FIX: FRONTEND - release the blob URL on save.
      if (pendingPreview) URL.revokeObjectURL(pendingPreview);
      setPendingPreview("");
      setMsg(""); await load();
    } catch (e) { setMsg(String(e)); }
    finally { setBusy(false); }
  }

  async function remove(r: BannerRow) {
    if (!confirm(`Удалить слайд${r.title ? ` «${r.title}»` : ` #${r.id}`}? Действие необратимо.`)) return;
    try { await api.bannerDelete(r.id); if (editId === r.id) setEditId(null); await load(); }
    catch (e) { setMsg(String(e)); }
  }
  async function toggleEnabled(r: BannerRow) {
    try { await api.bannerUpdate(r.id, { ...payloadOf(r), enabled: !r.enabled }); await load(); }
    catch (e) { setMsg(String(e)); }
  }
  async function duplicate(r: BannerRow) {
    try {
      await api.bannerCreate({ ...payloadOf(r), title: r.title ? `${r.title} (копия)` : null, sort_order: (rows?.length ?? 0) });
      setMsg("📋 Слайд продублирован"); await load();
    } catch (e) { setMsg(String(e)); }
  }

  // ---- multi-upload (drop several images → create+upload a slide each) ----
  async function quickUpload(files: FileList) {
    // FIX: AUDIT-21 - filter files by size/type before upload
    const list = Array.from(files).filter((f) => f.size <= 30 * 1024 * 1024 && f.type.startsWith("image/"));
    if (list.length !== files.length) setMsg("Некоторые файлы пропущены (размер >30МБ или не изображение)");
    let base = rows?.length ?? 0; const failed: string[] = [];
    for (const f of list) {
      try { const created = await api.bannerCreate({ ...EMPTY, sort_order: base++ }); await api.bannerImage(created.id, f); }
      catch { failed.push(f.name); }
    }
    setMsg(failed.length ? `⚠ Не загружены: ${failed.join(", ")}` : `✅ Создано слайдов: ${list.length}`);
    await load();
  }

  // ---- drag reorder (persists sort_order via PUT) ----
  const dragId = useRef<number | null>(null);
  const [overId, setOverId] = useState<number | null>(null);
  async function reorder(targetId: number) {
    const src = dragId.current; dragId.current = null; setOverId(null);
    if (src == null || src === targetId || !rows) return;
    const ordered = [...rows].sort((a, b) => a.sort_order - b.sort_order || a.id - b.id);
    const from = ordered.findIndex((r) => r.id === src);
    const to = ordered.findIndex((r) => r.id === targetId);
    if (from < 0 || to < 0) return;
    const [moved] = ordered.splice(from, 1);
    ordered.splice(to, 0, moved);
    const next = ordered.map((r, i) => ({ ...r, sort_order: i }));
    setRows(next); // optimistic
    setReordering(true);
    try {
      // Persist the new sort_order for every slide whose position changed.
      for (const r of next) {
        if (rows.find((o) => o.id === r.id)?.sort_order !== r.sort_order)
          await api.bannerUpdate(r.id, payloadOf(r));
      }
    } catch (e) { setMsg(String(e)); }
    finally { setReordering(false); await load(); }
  }

  const sorted = useMemo(
    () => (rows ? [...rows].sort((a, b) => a.sort_order - b.sort_order || a.id - b.id) : []),
    [rows],
  );
  const kpi = useMemo(() => {
    const r = rows || [];
    const last = r.map((x) => (x.created_at ? new Date(x.created_at).getTime() : 0)).sort((a, b) => b - a)[0];
    const impressions = r.reduce((a, x) => a + (x.impressions || 0), 0);
    const clicks = r.reduce((a, x) => a + (x.clicks || 0), 0);
    return {
      total: r.length, active: r.filter((x) => x.enabled).length,
      hidden: r.filter((x) => !x.enabled).length, withImg: r.filter((x) => x.image_url).length,
      impressions, clicks, ctr: impressions ? (clicks / impressions) * 100 : null,
      last: last ? new Date(last) : null,
    };
  }, [rows]);
  const ctrOf = (r: BannerRow) =>
    r.impressions ? Math.round(((r.clicks || 0) / r.impressions) * 1000) / 10 : null;

  return (
    <div>
      <h1 className="page-title">Карусель Mini App</h1>
      <p className="page-sub">CMS баннеров: слайды, загрузка изображений, порядок, поведение карусели и живой предпросмотр.</p>

      {msg && (
        <p className={msg.startsWith("✅") || msg.startsWith("📋") ? "note-ok" : "note-err"}>
          <span className="ms sm">{msg.startsWith("✅") ? "check_circle" : msg.startsWith("📋") ? "content_copy" : "error"}</span>
          {msg}
          <button className="btn ghost sm" onClick={() => setMsg("")} aria-label="Скрыть">×</button>
        </p>
      )}

      <div className="page-stack">
        {/* KPI */}
        <div className="metrics">
          <Metric icon="view_carousel" label="Всего слайдов" value={kpi.total} />
          <Metric icon="visibility" label="Активных" value={kpi.active} />
          <Metric icon="visibility_off" label="Скрытых" value={kpi.hidden} tone={kpi.hidden ? "purple" : undefined} />
          <Metric icon="visibility" label="Показы" value={kpi.impressions} />
          <Metric icon="ads_click" label="Клики / CTR"
            value={kpi.ctr == null ? "—" : `${kpi.clicks} · ${kpi.ctr.toFixed(1)}%`}
            hint="Показ засчитывается при первом отображении слайда, клик — при нажатии." small />
          <Metric icon="update" label="Обновлено" value={kpi.last ? kpi.last.toLocaleDateString("ru") : "—"} small />
        </div>

        <div className="bc-grid">
          <div style={{ display: "flex", flexDirection: "column", gap: "var(--sp-6)", minWidth: 0 }}>
            {/* Carousel behaviour */}
            <div className="panel" style={{ margin: 0 }}>
              <div className="section-head">
                <div className="panel-title" style={{ margin: 0 }}><span className="ms sm">tune</span> Настройки карусели</div>
                <div className="form-row">
                  {settingsDirty && <span className="pill warn">● не сохранено</span>}
                  <button className="btn" disabled={!settingsDirty || savingSettings} onClick={saveSettings}>
                    <span className="ms sm">save</span> {savingSettings ? "Сохранение…" : "Сохранить"}
                  </button>
                </div>
              </div>
              <div className="form-grid">
                <div className="cfg-field">
                  <span className="cfg-cap">Интервал смены, сек</span>
                  <input type="number" aria-label="Интервал смены, сек" min={1.5} max={60} step={0.5} value={intervalMs / 1000}
                    onChange={(e) => { const v = Number(e.target.value); setIntervalMs(Math.round(Math.max(1.5, Math.min(60, Number.isFinite(v) ? v : 5)) * 1000)); }} />
                </div>
                <div className="cfg-field">
                  <span className="cfg-cap">Тип анимации</span>
                  <Select width="100%" ariaLabel="Анимация" value={behavior.animation}
                    onChange={(v) => setB("animation", v as CarouselBehavior["animation"])}
                    options={[{ value: "slide", label: "Сдвиг (slide)" }, { value: "fade", label: "Затухание (fade)" }]} />
                </div>
                <div className="cfg-field">
                  <span className="cfg-cap">Скорость анимации, мс</span>
                  <input type="number" aria-label="Скорость анимации, мс" min={100} max={2000} step={50} value={behavior.speed_ms}
                    onChange={(e) => setB("speed_ms", Math.max(100, Math.min(2000, Number(e.target.value) || 0)))} />
                </div>
              </div>
              <div className="form-grid" style={{ marginTop: "var(--sp-4)" }}>
                <Switch checked={behavior.autoplay} onChange={(v) => setB("autoplay", v)} label="Автопрокрутка" />
                <Switch checked={behavior.pause_on_interaction} onChange={(v) => setB("pause_on_interaction", v)} label="Пауза при наведении" />
                <Switch checked={behavior.loop} onChange={(v) => setB("loop", v)} label="Бесконечная прокрутка" />
                <Switch checked={behavior.manual_swipe} onChange={(v) => setB("manual_swipe", v)} label="Ручное перелистывание" />
                <Switch checked={behavior.show_indicators} onChange={(v) => setB("show_indicators", v)} label="Индикаторы страниц" />
                <Switch checked={behavior.show_arrows} onChange={(v) => setB("show_arrows", v)} label="Стрелки навигации" />
              </div>
              <p className="cfg-hint" style={{ marginTop: "var(--sp-3)" }}>
                <span className="ms sm" style={{ verticalAlign: "-3px" }}>info</span>{" "}
                Все параметры применяются в Mini App: интервал и скорость, тип анимации (сдвиг/затухание), автопрокрутка, пауза при касании, бесконечная прокрутка, индикаторы, стрелки и ручной свайп.
              </p>
            </div>

            {/* Slides */}
            <div className="panel" style={{ margin: 0 }}>
              <div className="section-head">
                <div className="panel-title" style={{ margin: 0 }}>
                  <span className="ms sm">collections</span> Слайды
                  {reordering && <span className="pill muted">сохранение порядка…</span>}
                </div>
                <button className="btn" onClick={startNew}><span className="ms sm">add</span> Новый слайд</button>
              </div>

              {rows === null ? (
                <div className="loading">Загрузка…</div>
              ) : sorted.length === 0 ? (
                <>
                  <div className="empty-state">
                    <div className="es-icon"><span className="ms">view_carousel</span></div>
                    <p className="es-title">Слайдов пока нет</p>
                    <p className="es-desc">Создайте первый слайд вручную или перетащите изображения в зону загрузки ниже — каждый файл станет отдельным слайдом.</p>
                    <button className="btn" onClick={startNew}><span className="ms sm">add</span> Создать первый слайд</button>
                  </div>
                  <Dropzone onFiles={quickUpload} multi />
                </>
              ) : (
                <>
                  <div className="slide-grid">
                    {sorted.map((r) => (
                      <div key={r.id}
                        className={"slide-card" + (overId === r.id ? " over" : "")}
                        draggable
                        onDragStart={() => { dragId.current = r.id; }}
                        onDragOver={(e) => { e.preventDefault(); if (overId !== r.id) setOverId(r.id); }}
                        onDragLeave={() => overId === r.id && setOverId(null)}
                        onDrop={(e) => { e.preventDefault(); reorder(r.id); }}>
                        <div className="sc-thumb">
                          {r.image_url ? <img src={r.image_url} alt="" loading="eager" /> : <span className="ms sc-empty">image</span>}
                          <span className="sc-handle" title="Перетащите для изменения порядка"><span className="ms sm">drag_indicator</span></span>
                          <span className="sc-order">#{r.sort_order}</span>
                        </div>
                        <div className="sc-body">
                          <span className="sc-title clamp-2">
                            {r.title || <span className="muted">Без заголовка</span>}
                            <span className={"pill " + (r.locale ? "pro" : "muted")} style={{ marginLeft: 6, fontSize: 10 }}>{localeLabel(r.locale)}</span>
                          </span>
                          {r.subtitle && <span className="sc-sub clamp-2">{r.subtitle}</span>}
                          <div className="sc-stats" title="Показы · Клики · CTR">
                            <span><span className="ms sm">visibility</span> {(r.impressions || 0).toLocaleString("ru")}</span>
                            <span><span className="ms sm">ads_click</span> {(r.clicks || 0).toLocaleString("ru")}</span>
                            <span className={ctrOf(r) != null && ctrOf(r)! >= 1 ? "ok" : "muted"}>
                              CTR {ctrOf(r) == null ? "—" : `${ctrOf(r)}%`}
                            </span>
                          </div>
                          <div className="sc-foot">
                            <span className={"pill " + (r.enabled ? "ok" : "muted")}>{r.enabled ? "Активен" : "Скрыт"}</span>
                            <div className="form-row" style={{ gap: 2, flexWrap: "nowrap" }}>
                              <Switch ariaLabel="Слайд активен" checked={r.enabled} onChange={() => toggleEnabled(r)} />
                              <button className="btn ghost sm" title="Редактировать" onClick={() => startEdit(r)}><span className="ms sm">edit</span></button>
                              <button className="btn ghost sm" title="Дублировать" onClick={() => duplicate(r)}><span className="ms sm">content_copy</span></button>
                              <button className="btn ghost sm" title="Удалить" onClick={() => remove(r)}><span className="ms sm" style={{ color: "var(--danger)" }}>delete</span></button>
                            </div>
                          </div>
                        </div>
                      </div>
                    ))}
                  </div>
                  <div style={{ marginTop: "var(--sp-4)" }}><Dropzone onFiles={quickUpload} multi /></div>
                </>
              )}
            </div>

            {/* Analytics — real per-slide engagement (impressions/clicks/CTR) */}
            <div className="panel" style={{ margin: 0 }}>
              <div className="panel-title"><span className="ms sm">insights</span> Аналитика слайдов</div>
              {kpi.impressions === 0 ? (
                <p className="cfg-hint" style={{ margin: 0 }}>
                  <span className="ms sm" style={{ verticalAlign: "-3px" }}>info</span>{" "}
                  Пока нет показов. Как только Mini App покажет карусель пользователям, здесь появятся показы, клики и CTR по каждому слайду.
                </p>
              ) : (
                <div className="table-wrap" tabIndex={0} style={{ border: "none" }}>
                  <table className="tbl">
                    <thead><tr>
                      <th>Слайд</th>
                      <th style={{ textAlign: "right" }}>Показы</th>
                      <th style={{ textAlign: "right" }}>Клики</th>
                      <th style={{ textAlign: "right" }}>CTR</th>
                    </tr></thead>
                    <tbody>
                      {[...sorted].sort((a, b) => (b.impressions || 0) - (a.impressions || 0)).map((r) => (
                        <tr key={r.id}>
                          <td className="clamp-2" style={{ maxWidth: 220 }}>{r.title || <span className="muted">#{r.id} без заголовка</span>}</td>
                          <td style={{ textAlign: "right", fontVariantNumeric: "tabular-nums" }}>{(r.impressions || 0).toLocaleString("ru")}</td>
                          <td style={{ textAlign: "right", fontVariantNumeric: "tabular-nums" }}>{(r.clicks || 0).toLocaleString("ru")}</td>
                          <td style={{ textAlign: "right", fontVariantNumeric: "tabular-nums" }}>
                            <b className={ctrOf(r) != null && ctrOf(r)! >= 1 ? "ok" : "muted"}>{ctrOf(r) == null ? "—" : `${ctrOf(r)}%`}</b>
                          </td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                  <p className="cfg-hint" style={{ marginTop: "var(--sp-3)" }}>
                    <span className="ms sm" style={{ verticalAlign: "-3px" }}>info</span>{" "}
                    Показ засчитывается один раз за сессию при первом отображении слайда; клик — при нажатии. История изменений — в журнале аудита (действия <code className="code-key">banner.*</code>).
                  </p>
                </div>
              )}
            </div>
          </div>

          {/* Live Mini App preview */}
          <div className="bc-preview">
            <div className="panel-title sm" style={{ marginBottom: "var(--sp-3)" }}>
              <span className="ms sm">smartphone</span> Предпросмотр Mini App
            </div>
            <MiniPreview slides={sorted.filter((s) => s.enabled)} intervalMs={intervalMs} behavior={behavior} />
            <p className="cfg-hint" style={{ marginTop: "var(--sp-3)", textAlign: "center" }}>
              Живая карусель: интервал {(intervalMs / 1000).toFixed(1)} с · {behavior.animation === "fade" ? "затухание" : "сдвиг"}
            </p>
          </div>
        </div>
      </div>

      {/* Editor modal */}
      {editId !== null && (
        <Modal title={editId === "new" ? "Новый слайд" : `Слайд #${editId}`} icon="view_carousel"
          onClose={() => setEditId(null)} wide
          footer={<>
            <button className="btn ghost spacer" onClick={() => setEditId(null)}>Отмена</button>
            <button className="btn" disabled={busy} onClick={save}><span className="ms sm">save</span> Сохранить</button>
          </>}>
          <div className="bc-grid" style={{ gridTemplateColumns: "minmax(0,1fr) 220px", gap: "var(--sp-5)" }}>
            <div style={{ display: "flex", flexDirection: "column", gap: "var(--sp-4)", minWidth: 0 }}>
              <Dropzone
                onFiles={(fl) => fl[0] && pickImage(fl[0])}
                preview={editId === "new" ? pendingPreview || draft.image_url : draft.image_url}
              />
              <div className="form-grid">
                <div className="cfg-field"><span className="cfg-cap">Заголовок</span>
                  <input aria-label="Заголовок" value={draft.title ?? ""} onChange={(e) => setField("title", e.target.value || null)} /></div>
                <div className="cfg-field"><span className="cfg-cap">Подзаголовок</span>
                  <input aria-label="Подзаголовок" value={draft.subtitle ?? ""} onChange={(e) => setField("subtitle", e.target.value || null)} /></div>
              </div>
              <div className="form-grid">
                <div className="cfg-field"><span className="cfg-cap">Ссылка при нажатии</span>
                  <input placeholder="deep-link / URL" value={draft.link_url ?? ""} onChange={(e) => setField("link_url", e.target.value || null)} /></div>
                <div className="cfg-field"><span className="cfg-cap">Порядок (sort)</span>
                  <input type="number" aria-label="Порядок (sort)" value={draft.sort_order} onChange={(e) => setField("sort_order", Number(e.target.value) || 0)} /></div>
                <div className="cfg-field"><span className="cfg-cap">Язык показа</span>
                  <Select ariaLabel="Язык показа" value={draft.locale ?? ""} onChange={(v) => setField("locale", v || null)} options={LOCALES} />
                  <span className="cfg-hint">Картинка несёт текст — сделайте слайд под язык. «Все языки» — показывается всем.</span>
                </div>
              </div>
              <Switch checked={draft.enabled} onChange={(v) => setField("enabled", v)} label="Слайд активен (виден в Mini App)" />
              <p className="cfg-hint" style={{ margin: 0 }}>
                JPG, PNG, WEBP, GIF, BMP, AVIF · до 30 МБ. HEIC (фото с iPhone) — сначала сохраните как JPG.
                {editId === "new" && " Изображение загрузится при сохранении."}
              </p>
            </div>
            <div>
              <span className="cfg-cap" style={{ display: "block", marginBottom: "var(--sp-2)" }}>Предпросмотр слайда</span>
              <div className="slide-card" style={{ maxWidth: 220 }}>
                <div className="sc-thumb">
                  {(editId === "new" ? pendingPreview || draft.image_url : draft.image_url)
                    ? <img src={editId === "new" ? pendingPreview || draft.image_url : draft.image_url} alt="" />
                    : <span className="ms sc-empty">image</span>}
                </div>
                <div className="sc-body">
                  <span className="sc-title clamp-2">{draft.title || <span className="muted">Без заголовка</span>}</span>
                  {draft.subtitle && <span className="sc-sub clamp-2">{draft.subtitle}</span>}
                </div>
              </div>
            </div>
          </div>
        </Modal>
      )}
    </div>
  );
}

// ---------- subcomponents ----------

function Dropzone({ onFiles, preview, multi }: { onFiles: (f: FileList) => void; preview?: string; multi?: boolean }) {
  const [over, setOver] = useState(false);
  const ref = useRef<HTMLInputElement>(null);
  return (
    <div className={"dropzone" + (over ? " over" : "")}
      onClick={() => ref.current?.click()}
      onDragOver={(e) => { e.preventDefault(); setOver(true); }}
      onDragLeave={() => setOver(false)}
      onDrop={(e) => { e.preventDefault(); setOver(false); if (e.dataTransfer.files?.length) onFiles(e.dataTransfer.files); }}
      onPaste={(e) => { if (e.clipboardData.files?.length) onFiles(e.clipboardData.files); }}
      tabIndex={0} role="button" aria-label="Загрузить изображение">
      {preview ? (
        <img src={preview} alt="" style={{ maxHeight: 140, maxWidth: "100%", borderRadius: "var(--r-sm)", objectFit: "cover" }} />
      ) : (
        <span className="ms">cloud_upload</span>
      )}
      <span className="dz-hint">
        {preview ? "Нажмите, чтобы заменить" : <>Перетащите{multi ? " изображения" : " изображение"}, вставьте из буфера или нажмите для выбора<br />JPG · PNG · WEBP · GIF · BMP · AVIF · до 30 МБ{multi && " · можно несколько"}</>}
      </span>
      <input ref={ref} type="file" accept="image/*" hidden multiple={multi}
        onChange={(e) => { if (e.target.files?.length) onFiles(e.target.files); e.target.value = ""; }} />
    </div>
  );
}

function MiniPreview({ slides, intervalMs, behavior }: { slides: BannerRow[]; intervalMs: number; behavior: CarouselBehavior }) {
  const [idx, setIdx] = useState(0);
  const [paused, setPaused] = useState(false);
  const n = slides.length;
  useEffect(() => { if (idx >= n) setIdx(0); }, [n, idx]);
  useEffect(() => {
    if (!behavior.autoplay || paused || n < 2) return;
    const t = setTimeout(() => setIdx((i) => (i + 1) % n), Math.max(1500, intervalMs));
    return () => clearTimeout(t);
  }, [idx, behavior.autoplay, paused, intervalMs, n]);

  // FIX: POLISH-15 - resolve relative image URLs (e.g. "/media/banners/abc.jpg")
  // against the API base. Without this, the admin Banners page tried to load
  // images from "/media/..." which 404s on the admin origin (served at /admin/).
  // Mirror the miniapp's mediaUrl() helper.
  const API_BASE = (import.meta.env.VITE_API_BASE ?? "").trim().replace(/\/$/, "");
  const img = (u: string | null | undefined): string => {
    if (!u) return "";
    if (/^(https?:|data:|blob:)/i.test(u)) return u;
    return u.startsWith("/") ? `${API_BASE}${u}` : u;
  };

  const go = (d: number) => setIdx((i) => {
    const next = i + d;
    if (behavior.loop) return (next + n) % n;
    return Math.max(0, Math.min(n - 1, next));
  });

  return (
    <div className="mini-frame">
      <div className="mini-notch" />
      <div className={"mini-carousel " + behavior.animation}
        style={{ ["--mc-speed" as string]: `${behavior.speed_ms / 1000}s` }}
        onMouseEnter={() => behavior.pause_on_interaction && setPaused(true)}
        onMouseLeave={() => setPaused(false)}>
        {n === 0 ? (
          <div style={{ position: "absolute", inset: 0, display: "grid", placeItems: "center", color: "var(--hint)", fontSize: 12, gap: 6, gridAutoFlow: "row" }}>
            <span className="ms">image</span>Нет активных слайдов
          </div>
        ) : slides.map((s, i) => (
          <div key={s.id} className={"mini-slide" + (i === idx ? " show" : "")}
            style={behavior.animation === "slide" ? { transform: `translateX(${(i - idx) * 100}%)`, opacity: 1 } : { opacity: i === idx ? 1 : 0 }}>
            {s.image_url ? <img src={img(s.image_url)} alt="" /> : <div style={{ width: "100%", height: "100%", display: "grid", placeItems: "center", color: "var(--hint)" }}><span className="ms">image</span></div>}
            {(s.title || s.subtitle) && (
              <div className="mini-cap">{s.title && <b>{s.title}</b>}{s.subtitle && <span>{s.subtitle}</span>}</div>
            )}
          </div>
        ))}
        {behavior.show_arrows && n > 1 && (<>
          <button className="mini-arrow l" onClick={() => go(-1)} aria-label="Назад"><span className="ms sm">chevron_left</span></button>
          <button className="mini-arrow r" onClick={() => go(1)} aria-label="Вперёд"><span className="ms sm">chevron_right</span></button>
        </>)}
        {behavior.show_indicators && n > 1 && (
          <div className="mini-dots">{slides.map((s, i) => <i key={s.id} className={i === idx ? "on" : ""} onClick={() => setIdx(i)} />)}</div>
        )}
      </div>
      <div className="mini-body">
        <div className="mb-row" /><div className="mb-row s" /><div className="mb-row" />
      </div>
    </div>
  );
}

function Metric({ icon, label, value, tone, small, hint }: {
  icon: string; label: string; value: number | string; tone?: "purple" | "danger"; small?: boolean; hint?: string;
}) {
  return (
    <div className={"metric" + (tone ? " " + tone : "")} title={hint}>
      <span className="glow" />
      <div className="top"><span className="lbl">{label}</span><span className="ms sm">{icon}</span></div>
      <div><div className="num" style={small ? { fontSize: 16 } : undefined}>
        {typeof value === "number" ? value.toLocaleString("ru") : value}
      </div></div>
    </div>
  );
}
