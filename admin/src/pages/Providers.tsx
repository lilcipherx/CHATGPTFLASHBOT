import { useEffect, useMemo, useState } from "react";
import { api } from "../api";
import { Select } from "../components/Select";
import { Switch } from "../components/Switch";
import { Modal } from "../components/Modal";

// The /providers endpoint is the kill-switch registry for MEDIA (video) generation
// providers (core.ai_router.video_adapters._PROVIDERS). Each row: key, available
// (its API key is configured) and disabled (admin kill-switch). Per-provider
// telemetry (requests/latency/health/logs/cost) is NOT tracked for these media
// gateways — it lives at the account level on the AI-routing page. Native provider
// API keys + OpenAI base URL are managed on the «Ключи API» page, not here.
interface Row { key: string; available: boolean; disabled: boolean; modality?: string }

const MODALITY_LABEL: Record<string, string> = { video: "Видео", image: "Изображение", music: "Аудио" };
const modalityOf = (r: Row) => MODALITY_LABEL[r.modality || ""] || "Медиа";

// Curated catalogue metadata (static, honest — these are well-known vendors). Keyed
// by the routing service key; several Kling-powered keys are distinct route entries.
const META: Record<string, { label: string; vendor: string; icon: string; desc: string; docs: string }> = {
  seedance: { label: "Seedance", vendor: "ByteDance", icon: "🎬", desc: "Генерация видео Seedance (ByteDance) — текст/изображение → видео.", docs: "https://www.volcengine.com/" },
  veo: { label: "Google Veo", vendor: "Google DeepMind", icon: "🟦", desc: "Veo — модель генерации видео от Google DeepMind.", docs: "https://deepmind.google/technologies/veo/" },
  grok: { label: "Grok Video", vendor: "xAI", icon: "✖️", desc: "Видео-генерация на стеке xAI Grok.", docs: "https://x.ai/" },
  kling_ai: { label: "Kling AI", vendor: "Kuaishou", icon: "🟧", desc: "Kling — флагманская видео-модель Kuaishou. Базовый маршрут.", docs: "https://klingai.com/" },
  kling_effects: { label: "Kling · Effects", vendor: "Kuaishou", icon: "✨", desc: "Маршрут Kling для эффект-пресетов Mini App.", docs: "https://klingai.com/" },
  kling_motion: { label: "Kling · Motion", vendor: "Kuaishou", icon: "🌀", desc: "Маршрут Kling для motion/анимации.", docs: "https://klingai.com/" },
  videoeffect: { label: "Video Effects", vendor: "Kuaishou (Kling)", icon: "🎞️", desc: "Видео-эффекты Mini App (на базе Kling, §13.4).", docs: "https://klingai.com/" },
  hailuo: { label: "Hailuo", vendor: "MiniMax", icon: "🌊", desc: "Hailuo (MiniMax) — генерация видео.", docs: "https://hailuoai.video/" },
  pika: { label: "Pika", vendor: "Pika Labs", icon: "⚡", desc: "Pika Labs — генерация и редактирование видео.", docs: "https://pika.art/" },
  mj_video: { label: "Midjourney Video", vendor: "Midjourney", icon: "🛥️", desc: "Видео-режим Midjourney.", docs: "https://www.midjourney.com/" },
  // image providers
  nano_banana: { label: "Nano Banana", vendor: "Google", icon: "🍌", desc: "Быстрая генерация изображений Nano Banana.", docs: "" },
  seedream: { label: "Seedream", vendor: "ByteDance", icon: "🌱", desc: "Seedream — генерация изображений (ByteDance).", docs: "" },
  flux2: { label: "Flux", vendor: "Black Forest Labs", icon: "🟪", desc: "FLUX — генерация изображений (Black Forest Labs).", docs: "https://blackforestlabs.ai/" },
  gpt_image2: { label: "GPT Image", vendor: "OpenAI", icon: "🟢", desc: "GPT Image — генерация изображений OpenAI.", docs: "https://platform.openai.com/" },
  midjourney: { label: "Midjourney", vendor: "Midjourney", icon: "⛵", desc: "Midjourney — генерация изображений.", docs: "https://www.midjourney.com/" },
  recraft: { label: "Recraft", vendor: "Recraft", icon: "🎨", desc: "Recraft — генерация изображений/векторов.", docs: "https://www.recraft.ai/" },
  // music providers
  suno: { label: "Suno", vendor: "Suno", icon: "🎵", desc: "Suno — генерация музыки и вокала.", docs: "https://suno.com/" },
  lyria: { label: "Lyria", vendor: "Google DeepMind", icon: "🎼", desc: "Lyria — музыкальная модель Google DeepMind.", docs: "https://deepmind.google/" },
};
const metaOf = (k: string) => META[k] || { label: k, vendor: "—", icon: "🧩", desc: "Медиа-провайдер генерации.", docs: "" };

type Status = { dot: string; pill: string; label: string };
function statusOf(r: Row): Status {
  if (r.disabled) return { dot: "off", pill: "muted", label: "Выключен" };
  if (!r.available) return { dot: "cool", pill: "warn", label: "Нет ключа" };
  return { dot: "on", pill: "ok", label: "Активен" };
}

export function Providers() {
  const [rows, setRows] = useState<Row[] | null>(null);
  const [msg, setMsg] = useState("");
  const [q, setQ] = useState("");
  const [fStatus, setFStatus] = useState("all");
  const [fAvail, setFAvail] = useState("all");
  const [fMod, setFMod] = useState("all");
  const [view, setView] = useState<"grid" | "table">("grid");
  const [sel, setSel] = useState<Set<string>>(new Set());
  const [detail, setDetail] = useState<Row | null>(null);
  const [busy, setBusy] = useState(false);

  const load = () => api.providers().then((r) => setRows(r)).catch((e) => { setMsg(String(e)); setRows([]); });
  useEffect(() => { load(); }, []);
  const toast = (m: string) => setMsg(m);

  // Optimistic toggle: flip locally, then reconcile from the server.
  async function toggle(key: string, nextDisabled?: boolean) {
    setRows((rs) => rs && rs.map((r) => r.key === key ? { ...r, disabled: nextDisabled ?? !r.disabled } : r));
    try { await api.toggleProvider(key); await load(); }
    catch (e) { toast(String(e)); await load(); }
  }
  async function bulkToggle(disabled: boolean) {
    const targets = (rows || []).filter((r) => sel.has(r.key) && r.disabled !== disabled);
    if (!targets.length) { setSel(new Set()); return; }
    setBusy(true);
    try { for (const r of targets) await api.toggleProvider(r.key); setSel(new Set()); await load(); toast(`✅ ${disabled ? "Выключено" : "Включено"}: ${targets.length}`); }
    catch (e) { toast(String(e)); await load(); } finally { setBusy(false); }
  }
  function exportJson(only?: Set<string>) {
    const list = (rows || []).filter((r) => !only || only.has(r.key)).map((r) => ({ ...r, ...metaOf(r.key) }));
    const blob = new Blob([JSON.stringify(list, null, 2)], { type: "application/json" });
    const a = document.createElement("a"); a.href = URL.createObjectURL(blob);
    a.download = `providers-${new Date().toISOString().slice(0, 10)}.json`; a.click();
    setTimeout(() => URL.revokeObjectURL(a.href), 1000);  // FIX: F68 - release the blob URL after the download starts
  }

  const filtered = useMemo(() => (rows || []).filter((r) => {
    if (fStatus === "enabled" && r.disabled) return false;
    if (fStatus === "disabled" && !r.disabled) return false;
    if (fAvail === "configured" && !r.available) return false;
    if (fAvail === "missing" && r.available) return false;
    if (fMod !== "all" && (r.modality || "") !== fMod) return false;
    if (q.trim()) { const s = q.toLowerCase(); const m = metaOf(r.key); if (![r.key, m.label, m.vendor].some((f) => f.toLowerCase().includes(s))) return false; }
    return true;
  }), [rows, q, fStatus, fAvail, fMod]);

  const kpi = useMemo(() => {
    const r = rows || [];
    return {
      total: r.length, enabled: r.filter((x) => !x.disabled).length, disabled: r.filter((x) => x.disabled).length,
      active: r.filter((x) => !x.disabled && x.available).length, missing: r.filter((x) => !x.available).length,
      vendors: new Set(r.map((x) => metaOf(x.key).vendor)).size,
    };
  }, [rows]);

  const allVisibleSelected = filtered.length > 0 && filtered.every((r) => sel.has(r.key));

  return (
    <div>
      <div className="section-head">
        <div>
          <h1 className="page-title">Провайдеры</h1>
          <p className="page-sub">Центр управления медиа-провайдерами генерации: доступность, kill-switch и каталог.</p>
        </div>
        <div className="form-row">
          <div className="seg-tabs">
            <button className={view === "grid" ? "on" : ""} onClick={() => setView("grid")} title="Плитка"><span className="ms sm">grid_view</span></button>
            <button className={view === "table" ? "on" : ""} onClick={() => setView("table")} title="Таблица"><span className="ms sm">table_rows</span></button>
          </div>
          <button className="btn ghost sm" onClick={() => exportJson()}><span className="ms sm">download</span> Экспорт</button>
        </div>
      </div>

      {msg && (
        <p className={msg.startsWith("✅") ? "note-ok" : "note-err"}>
          <span className="ms sm">{msg.startsWith("✅") ? "check_circle" : "error"}</span>
          {msg}<button className="btn ghost sm" onClick={() => setMsg("")} aria-label="Скрыть">×</button>
        </p>
      )}

      <div className="page-stack">
        <div className="metrics">
          <Metric icon="dns" label="Всего провайдеров" value={kpi.total} />
          <Metric icon="check_circle" label="Включено" value={kpi.enabled} />
          <Metric icon="block" label="Выключено" value={kpi.disabled} tone={kpi.disabled ? "purple" : undefined} />
          <Metric icon="bolt" label="Активных" value={kpi.active} />
          <Metric icon="key_off" label="Без ключа" value={kpi.missing} tone={kpi.missing ? "danger" : undefined} />
          <Metric icon="apartment" label="Вендоров" value={kpi.vendors} />
        </div>

        {/* Toolbar */}
        <div className="panel" style={{ padding: "var(--sp-3) var(--sp-4)" }}>
          <div className="section-head" style={{ margin: 0 }}>
            <div className="form-row" style={{ gap: "var(--sp-2)", flexWrap: "wrap" }}>
              <input style={{ width: 220 }} placeholder="Поиск: провайдер, вендор, key" value={q} onChange={(e) => setQ(e.target.value)} />
              <Select width={150} ariaLabel="Статус" value={fStatus} onChange={setFStatus} options={[{ value: "all", label: "Все статусы" }, { value: "enabled", label: "Включённые" }, { value: "disabled", label: "Выключенные" }]} />
              <Select width={170} ariaLabel="Доступность" value={fAvail} onChange={setFAvail} options={[{ value: "all", label: "Любой ключ" }, { value: "configured", label: "Ключ настроен" }, { value: "missing", label: "Без ключа" }]} />
              <Select width={150} ariaLabel="Тип" value={fMod} onChange={setFMod} options={[{ value: "all", label: "Все типы" }, { value: "video", label: "Видео" }, { value: "image", label: "Изображение" }, { value: "music", label: "Аудио" }]} />
            </div>
            <a className="btn ghost sm" href="#" onClick={(e) => { e.preventDefault(); toast("Ключи провайдеров — на странице «Ключи API»; статистика аккаунтов — на «AI-роутинг»."); }}>
              <span className="ms sm">info</span> Где ключи и статистика?
            </a>
          </div>
          {sel.size > 0 && (
            <div className="form-row" style={{ gap: "var(--sp-2)", flexWrap: "wrap", marginTop: "var(--sp-3)", paddingTop: "var(--sp-3)", borderTop: "1px solid var(--border)" }}>
              <span className="pill pro">{sel.size} выбрано</span>
              <button className="btn ghost sm" disabled={busy} onClick={() => bulkToggle(false)}><span className="ms sm">check_circle</span> Включить</button>
              <button className="btn ghost sm" disabled={busy} onClick={() => bulkToggle(true)}><span className="ms sm">block</span> Выключить</button>
              <button className="btn ghost sm" onClick={() => exportJson(sel)}><span className="ms sm">download</span> Экспорт</button>
              <button className="btn ghost sm" onClick={() => setSel(new Set())}>Снять</button>
            </div>
          )}
        </div>

        {/* Content */}
        {rows === null ? (
          view === "grid" ? (
            <div className="prov-grid">{Array.from({ length: 6 }).map((_, i) => <div key={i} className="prov-card"><div className="skeleton" style={{ height: 42, width: 42, borderRadius: 11 }} /><div className="skeleton" style={{ height: 14, width: "70%" }} /><div className="skeleton" style={{ height: 30 }} /></div>)}</div>
          ) : <div className="panel"><div className="loading">Загрузка…</div></div>
        ) : filtered.length === 0 ? (
          <div className="panel">
            <EmptyState icon="dns" title={rows.length === 0 ? "Провайдеры не настроены" : "Ничего не найдено"}
              desc={rows.length === 0 ? "Медиа-провайдеры регистрируются в коде роутера. Как только провайдер появится, им можно будет управлять здесь." : "Измените поиск или фильтры."} />
          </div>
        ) : view === "grid" ? (
          <div className="prov-grid">
            {filtered.map((r) => {
              const m = metaOf(r.key); const s = statusOf(r);
              return (
                <div key={r.key} className={"prov-card" + (r.disabled ? " off" : "")}>
                  <input type="checkbox" className="fx-check pc-sel" aria-label="Выбрать" checked={sel.has(r.key)} onChange={() => setSel((p) => { const n = new Set(p); n.has(r.key) ? n.delete(r.key) : n.add(r.key); return n; })} />
                  <div className="pc-head">
                    <div className="prov-logo">{m.icon}</div>
                    <div style={{ minWidth: 0 }}>
                      <div className="pc-name">{m.label}</div>
                      <div className="pc-vendor">{m.vendor} · <span className="code-key">{r.key}</span></div>
                    </div>
                  </div>
                  <p className="pc-desc clamp-2">{m.desc}</p>
                  <div className="form-row" style={{ gap: 6 }}>
                    <span className={"status-dot " + s.dot} /><span className={"pill " + s.pill}>{s.label}</span>
                    <span className={"pill " + (r.available ? "ok" : "muted")}>{r.available ? "ключ есть" : "нет ключа"}</span>
                  </div>
                  <div className="pc-foot">
                    <button className="btn ghost sm" onClick={() => setDetail(r)}><span className="ms sm">visibility</span> Детали</button>
                    <Switch checked={!r.disabled} onChange={() => toggle(r.key)} label={r.disabled ? "Выкл" : "Вкл"} />
                  </div>
                </div>
              );
            })}
          </div>
        ) : (
          <div className="panel">
            <div className="table-wrap sticky" tabIndex={0} style={{ border: "none" }}>
              <table className="tbl">
                <thead><tr>
                  <th style={{ width: 32 }}><input type="checkbox" className="fx-check" aria-label="Выбрать" checked={allVisibleSelected} onChange={(e) => setSel(e.target.checked ? new Set(filtered.map((r) => r.key)) : new Set())} /></th>
                  <th>Провайдер</th><th>Вендор</th><th>Key</th><th>Тип</th><th>Ключ</th><th>Статус</th><th style={{ width: 150 }}>Действия</th>
                </tr></thead>
                <tbody>
                  {filtered.map((r) => {
                    const m = metaOf(r.key); const s = statusOf(r);
                    return (
                      <tr key={r.key}>
                        <td><input type="checkbox" className="fx-check" aria-label="Выбрать" checked={sel.has(r.key)} onChange={() => setSel((p) => { const n = new Set(p); n.has(r.key) ? n.delete(r.key) : n.add(r.key); return n; })} /></td>
                        <td><div className="form-row" style={{ gap: 8 }}><span style={{ fontSize: 18 }}>{m.icon}</span><b style={{ cursor: "pointer" }} onClick={() => setDetail(r)}>{m.label}</b></div></td>
                        <td className="muted">{m.vendor}</td>
                        <td className="code-key">{r.key}</td>
                        <td><span className="pill muted">{modalityOf(r)}</span></td>
                        <td>{r.available ? <span className="pill ok">есть</span> : <span className="pill muted">нет</span>}</td>
                        <td><span className={"status-dot " + s.dot} /><span className={"pill " + s.pill}>{s.label}</span></td>
                        <td>
                          <div className="form-row" style={{ gap: 2, flexWrap: "nowrap" }}>
                            <button className="btn ghost sm" title="Детали" onClick={() => setDetail(r)}><span className="ms sm">visibility</span></button>
                            <button className="btn ghost sm" title={r.disabled ? "Включить" : "Выключить"} onClick={() => toggle(r.key)}><span className="ms sm">{r.disabled ? "toggle_off" : "toggle_on"}</span></button>
                          </div>
                        </td>
                      </tr>
                    );
                  })}
                </tbody>
              </table>
            </div>
          </div>
        )}
      </div>

      {detail && <ProviderCard r={detail} onClose={() => setDetail(null)} onToggle={() => toggle(detail.key)} onExport={() => exportJson(new Set([detail.key]))} toast={toast} />}
    </div>
  );
}

function ProviderCard({ r, onClose, onToggle, onExport, toast }: {
  r: Row; onClose: () => void; onToggle: () => void; onExport: () => void; toast: (m: string) => void;
}) {
  const m = metaOf(r.key); const s = statusOf(r);
  return (
    <Modal title={m.label} icon="dns" onClose={onClose} wide
      footer={<>
        <button className="btn ghost spacer" onClick={onExport}><span className="ms sm">download</span> Экспорт</button>
        <button className={"btn " + (r.disabled ? "" : "ghost")} onClick={() => { onToggle(); onClose(); }}>
          <span className="ms sm">{r.disabled ? "check_circle" : "block"}</span> {r.disabled ? "Включить" : "Выключить"}
        </button>
      </>}>
      <div className="form-row" style={{ gap: 10, marginBottom: "var(--sp-4)" }}>
        <div className="prov-logo" style={{ width: 48, height: 48, fontSize: 26 }}>{m.icon}</div>
        <div>
          <div className="pc-name" style={{ fontSize: 16 }}>{m.label}</div>
          <div className="pc-vendor">{m.vendor}</div>
        </div>
        <div className="form-row" style={{ marginLeft: "auto", gap: 6 }}>
          <span className={"status-dot " + s.dot} /><span className={"pill " + s.pill}>{s.label}</span>
        </div>
      </div>

      <p className="cfg-hint" style={{ margin: "0 0 var(--sp-4)" }}>{m.desc}</p>

      <div className="form-grid">
        <KV label="Routing key"><span className="code-key">{r.key}</span></KV>
        <KV label="Тип / модальность"><span className="pill muted">{modalityOf(r)}</span></KV>
        <KV label="Ключ API">{r.available ? <span className="pill ok">настроен</span> : <span className="pill muted">не задан</span>}</KV>
        <KV label="Kill-switch">{r.disabled ? <span className="pill muted">выключен</span> : <span className="pill ok">включён</span>}</KV>
        <KV label="Документация">{m.docs ? <a className="code-key" href={m.docs} target="_blank" rel="noreferrer">{m.docs.replace(/^https?:\/\//, "")}</a> : "—"}</KV>
        <KV label="Управление ключом"><a href="#" className="code-key" onClick={(e) => { e.preventDefault(); toast("Ключи провайдеров задаются на странице «Ключи API»."); }}>Ключи API →</a></KV>
      </div>

      <div style={{ marginTop: "var(--sp-4)", padding: "var(--sp-3)", background: "var(--surface-1)", border: "1px solid var(--border)", borderRadius: "var(--r-sm)" }}>
        <span className="panel-title sm" style={{ margin: 0, display: "block", marginBottom: "var(--sp-2)" }}><span className="ms sm">insights</span> Телеметрия и health</span>
        <p className="cfg-hint" style={{ margin: 0 }}>
          Запросы, latency, ошибки (429/500/503), RPM/TPM, очередь и стоимость не отслеживаются на уровне медиа-провайдеров
          (они работают через долгий long-poll). Аккаунт-уровневые метрики, health-check и тест подключения доступны на странице
          <b> «AI-роутинг»</b>. Здесь — доступность ключа и kill-switch, которые применяются движком немедленно.
        </p>
      </div>
    </Modal>
  );
}

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
function Metric({ icon, label, value, tone }: { icon: string; label: string; value: number | string; tone?: "purple" | "danger" }) {
  return (
    <div className={"metric" + (tone ? " " + tone : "")}>
      <span className="glow" />
      <div className="top"><span className="lbl">{label}</span><span className="ms sm">{icon}</span></div>
      <div><div className="num">{typeof value === "number" ? value.toLocaleString("ru") : value}</div></div>
    </div>
  );
}
