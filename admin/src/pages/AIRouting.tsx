import { useEffect, useMemo, useRef, useState } from "react";
import { AIAccount, AIModelRow, RouterPanel, api } from "../api";
import { Select, opts } from "../components/Select";
import { Switch } from "../components/Switch";
import { Modal } from "../components/Modal";

// Backend kinds: text gateways + media aggregators + direct provider keys.
const ACCOUNT_KINDS = ["omniroute", "openrouter", "openai", "custom", "kie", "muapi", "apimart", "direct"];
const MODALITIES = ["text", "image", "video", "music"];
const BACKENDS = ["", "omniroute", "openrouter", "kie", "muapi", "apimart", "direct"];
const MODALITY_LABEL: Record<string, string> = { text: "Текст", image: "Изображение", video: "Видео", music: "Аудио" };

const EMPTY_ACC = { name: "", kind: "omniroute", base_url: "", api_key: "", modality: "text", tier: 0, priority: 100, weight: 1, spend_limit_usd: 0, enabled: true };
type AccForm = typeof EMPTY_ACC;
const EMPTY_MODEL: Omit<AIModelRow, "key"> & { key: string } = { key: "", title: "", upstream_model: "", modality: "text", account_kind: null, premium: false, search: false, cost: 1, cost_micros: 0, price_in_micros: 0, price_out_micros: 0, enabled: true, sort_order: 100 };
// micro-USD (1e-6 $) per 1M tokens <-> $ per 1M tokens, for the editor inputs.
const perMtokUsd = (micros?: number) => ((micros ?? 0) / 1_000_000).toFixed(2);

const usd = (micros?: number) => `$${((micros ?? 0) / 1_000_000).toFixed(4)}`;
const statusMeta = (a: AIAccount): { dot: string; pill: string; label: string } => {
  if (!a.enabled) return { dot: "off", pill: "muted", label: "Выключен" };
  if (a.over_budget) return { dot: "off", pill: "danger", label: "Лимит" };
  if (a.status === "active") return { dot: "on", pill: "ok", label: "Активен" };
  if (a.status === "cooldown") return { dot: "cool", pill: "warn", label: "Cooldown" };
  return { dot: "off", pill: "danger", label: "Ошибка" };
};
const latTone = (ms?: number | null) => (!ms ? "" : ms < 800 ? "var(--accent)" : ms < 2500 ? "var(--warn)" : "var(--danger)");

function useDebounced<T>(v: T, ms = 200): T {
  const [d, setD] = useState(v);
  useEffect(() => { const t = setTimeout(() => setD(v), ms); return () => clearTimeout(t); }, [v, ms]);
  return d;
}

type Tab = "overview" | "accounts" | "models" | "tools";

export function AIRouting() {
  const [tab, setTab] = useState<Tab>("overview");
  const [accounts, setAccounts] = useState<AIAccount[] | null>(null);
  const [models, setModels] = useState<AIModelRow[] | null>(null);
  const [msg, setMsg] = useState("");

  const load = () =>
    Promise.all([api.aiAccounts(), api.aiModels()])
      .then(([a, m]) => { setAccounts(a); setModels(m); })
      .catch((e) => { setMsg(String(e)); setAccounts([]); setModels([]); });
  useEffect(() => { load(); }, []);
  const toast = (m: string) => setMsg(m);
  const guard = (p: Promise<unknown>) => p.then(load).catch((e) => setMsg(String(e)));

  async function exportConfig() {
    try {
      const cfg = await api.aiExportConfig();
      const blob = new Blob([JSON.stringify(cfg, null, 2)], { type: "application/json" });
      const a = document.createElement("a"); a.href = URL.createObjectURL(blob);
      a.download = `ai-routing-${new Date().toISOString().slice(0, 10)}.json`; a.click();
      URL.revokeObjectURL(a.href);  // FIX: AUDIT-92 - immediate revoke;  // FIX: F58 - release the blob URL after the download starts
    } catch (e) { setMsg(String(e)); }
  }
  async function importConfig(file: File) {
    try {
      const cfg = JSON.parse(await file.text());
      const r = await api.aiImportConfig({ accounts: cfg.accounts ?? [], models: cfg.models ?? [] });
      setMsg(`✅ Импортировано: моделей ${r.models}, аккаунтов ${r.accounts}`); load();
    } catch (e) { setMsg(`Импорт не удался: ${String(e)}`); }
  }

  const kpi = useMemo(() => {
    const a = accounts || [], m = models || [];
    const lat = a.filter((x) => x.avg_latency_ms).map((x) => x.avg_latency_ms as number);
    const req = a.reduce((s, x) => s + x.total_requests, 0);
    const err = a.reduce((s, x) => s + x.total_errors, 0);
    const cm = m.filter((x) => x.cost_micros);
    return {
      models: m.length, enabled: m.filter((x) => x.enabled).length, disabled: m.filter((x) => !x.enabled).length,
      backends: new Set(a.map((x) => x.kind)).size, accounts: a.length,
      avgLat: lat.length ? Math.round(lat.reduce((s, x) => s + x, 0) / lat.length) : 0,
      avgCost: cm.length ? Math.round(cm.reduce((s, x) => s + (x.cost_micros || 0), 0) / cm.length) : 0,
      errors: err, requests: req, success: req ? Math.round(((req - err) / req) * 100) : 100,
      spend: a.reduce((s, x) => s + (x.spend_micros || 0), 0),
    };
  }, [accounts, models]);

  const TABS: { id: Tab; label: string; icon: string }[] = [
    { id: "overview", label: "Обзор", icon: "monitoring" },
    { id: "accounts", label: "Аккаунты", icon: "vpn_key" },
    { id: "models", label: "Модели", icon: "grid_view" },
    { id: "tools", label: "Тест · Стоимость · Контейнеры", icon: "science" },
  ];

  return (
    <div>
      <div className="section-head">
        <div>
          <h1 className="page-title">AI-роутинг</h1>
          <p className="page-sub">Управление AI-шлюзом: пул аккаунтов, каталог моделей, маршрутизация, здоровье и стоимость.</p>
        </div>
        <div className="form-row">
          <button className="btn ghost sm" onClick={exportConfig}><span className="ms sm">download</span> Экспорт</button>
          <label className="btn ghost sm" style={{ cursor: "pointer" }}>
            <span className="ms sm">upload</span> Импорт
            <input type="file" accept="application/json" hidden onChange={(e) => { const f = e.target.files?.[0]; if (f) importConfig(f); e.target.value = ""; }} />
          </label>
        </div>
      </div>

      {msg && (
        <p className={msg.startsWith("✅") || msg.startsWith("✓") ? "note-ok" : "note-err"}>
          <span className="ms sm">{msg.startsWith("✅") || msg.startsWith("✓") ? "check_circle" : "error"}</span>
          {msg}<button className="btn ghost sm" onClick={() => setMsg("")} aria-label="Скрыть">×</button>
        </p>
      )}

      <div className="metrics">
        <Metric icon="grid_view" label="Моделей" value={kpi.models} />
        <Metric icon="check_circle" label="Активных" value={kpi.enabled} />
        <Metric icon="block" label="Выключено" value={kpi.disabled} tone={kpi.disabled ? "purple" : undefined} />
        <Metric icon="lan" label="Backends" value={kpi.backends} />
        <Metric icon="vpn_key" label="Аккаунтов" value={kpi.accounts} />
        <Metric icon="speed" label="Сред. latency" value={kpi.avgLat ? kpi.avgLat + " мс" : "—"} small />
        <Metric icon="bolt" label="Запросов" value={kpi.requests} />
        <Metric icon="percent" label="Успешность" value={kpi.success} suffix="%" tone={kpi.success < 90 ? "danger" : undefined} />
        <Metric icon="error" label="Ошибок" value={kpi.errors} tone={kpi.errors ? "danger" : undefined} />
        <Metric icon="payments" label="Расход" value={usd(kpi.spend)} small />
      </div>

      <div className="seg-tabs wrap" style={{ marginBottom: "var(--sp-5)" }}>
        {TABS.map((t) => (
          <button key={t.id} className={tab === t.id ? "on" : ""} onClick={() => setTab(t.id)}>
            <span className="ms sm" style={{ verticalAlign: "-3px", marginRight: 4 }}>{t.icon}</span>{t.label}
          </button>
        ))}
      </div>

      {accounts === null || models === null ? (
        <div className="panel"><div className="loading">Загрузка…</div></div>
      ) : tab === "overview" ? (
        <Overview accounts={accounts} />
      ) : tab === "accounts" ? (
        <AccountsTab accounts={accounts} guard={guard} toast={toast} />
      ) : tab === "models" ? (
        <ModelsTab models={models} guard={guard} toast={toast} />
      ) : (
        <ToolsTab accounts={accounts} models={models} toast={toast} />
      )}
    </div>
  );
}

// ---------------- Overview: health + routing strategy + by-backend analytics ----------------
function Overview({ accounts }: { accounts: AIAccount[] }) {
  const pool = accounts.filter((a) => a.tier === 0);
  const fallback = accounts.filter((a) => a.tier !== 0);
  const byBackend = useMemo(() => {
    const m = new Map<string, { req: number; err: number; spend: number; n: number }>();
    for (const a of accounts) {
      const x = m.get(a.kind) || { req: 0, err: 0, spend: 0, n: 0 };
      x.req += a.total_requests; x.err += a.total_errors; x.spend += a.spend_micros || 0; x.n++;
      m.set(a.kind, x);
    }
    return [...m.entries()].sort((a, b) => b[1].req - a[1].req);
  }, [accounts]);
  const maxReq = Math.max(1, ...byBackend.map(([, v]) => v.req));

  if (accounts.length === 0) return <EmptyState icon="vpn_key" title="Аккаунтов пока нет" desc="Добавьте первый backend-аккаунт во вкладке «Аккаунты», чтобы маршрутизатор начал обслуживать запросы." />;

  return (
    <div className="page-stack">
      <div className="bc-grid" style={{ gridTemplateColumns: "minmax(0,1.4fr) minmax(0,1fr)" }}>
        {/* Health monitor */}
        <div className="panel" style={{ margin: 0 }}>
          <div className="panel-title"><span className="ms sm">monitor_heart</span> Health Monitor</div>
          <HealthTable rows={pool} title="Пул" />
          {fallback.length > 0 && <div style={{ marginTop: "var(--sp-4)" }}><HealthTable rows={fallback} title="Fallback" /></div>}
        </div>
        {/* Routing strategy: selectable intra-tier mode + explainer */}
        <div className="panel" style={{ margin: 0 }}>
          <div className="panel-title"><span className="ms sm">alt_route</span> Стратегия маршрутизации</div>
          <StrategyPicker />
          <ol style={{ margin: "var(--sp-3) 0 0", paddingLeft: 18, display: "flex", flexDirection: "column", gap: "var(--sp-2)", fontSize: 13, lineHeight: 1.5 }}>
            <li><b>Fallback-цепочка по tier:</b> сначала пул (tier 0, {pool.length}), затем fallback (tier 1, {fallback.length}), потом прямой API.</li>
            <li><b>Внутри tier — выбранная стратегия</b> (приоритет/вес · быстрейший · поровну).</li>
            <li><b>Cooldown:</b> аккаунт с ошибками/исчерпанным лимитом уводится в cooldown и временно исключается → пробуется следующий.</li>
            <li><b>Spend-cap:</b> при достижении лимита трат аккаунт выводится из ротации автоматически.</li>
          </ol>
          <p className="cfg-hint" style={{ marginTop: "var(--sp-3)" }}>
            <span className="ms sm" style={{ verticalAlign: "-3px" }}>info</span>{" "}
            Tier-fallback всегда первичен (гарантия авто-перехода). Стратегия меняет лишь порядок аккаунтов внутри одного tier.
          </p>
        </div>
      </div>

      {/* Cumulative analytics by backend */}
      <div className="panel">
        <div className="panel-title"><span className="ms sm">bar_chart</span> Использование по backend (накопительно)</div>
        <div className="table-wrap" tabIndex={0} style={{ border: "none" }}>
          <table className="tbl">
            <thead><tr><th>Backend</th><th>Аккаунтов</th><th style={{ width: "40%" }}>Запросов</th><th>Ошибок</th><th>Успешность</th><th>Расход</th></tr></thead>
            <tbody>
              {byBackend.map(([kind, v]) => (
                <tr key={kind}>
                  <td><span className="pill muted">{kind}</span></td>
                  <td className="muted" style={{ fontVariantNumeric: "tabular-nums" }}>{v.n}</td>
                  <td>
                    <div style={{ display: "flex", alignItems: "center", gap: 8 }}>
                      <div className="bcbar"><span style={{ width: (v.req / maxReq) * 100 + "%" }} /></div>
                      <b style={{ fontVariantNumeric: "tabular-nums", fontSize: 12 }}>{v.req.toLocaleString("ru")}</b>
                    </div>
                  </td>
                  <td className={v.err ? "danger" : "muted"} style={{ fontVariantNumeric: "tabular-nums" }}>{v.err}</td>
                  <td style={{ fontVariantNumeric: "tabular-nums" }}>{v.req ? Math.round(((v.req - v.err) / v.req) * 100) : 100}%</td>
                  <td className="muted">{usd(v.spend)}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
        <p className="cfg-hint" style={{ marginTop: "var(--sp-3)" }}>
          <span className="ms sm" style={{ verticalAlign: "-3px" }}>info</span>{" "}
          Метрики накопительные (счётчики на аккаунтах). Разбивка по дням/неделям/месяцам и покнопочный лог запросов (пользователь, модель, ответ) потребуют таблицы событий запросов — здесь не выдумываются.
        </p>
      </div>
    </div>
  );
}

function HealthTable({ rows, title }: { rows: AIAccount[]; title: string }) {
  if (!rows.length) return <div className="cfg-hint">{title}: пусто</div>;
  return (
    <div>
      <div className="panel-title sm" style={{ marginBottom: "var(--sp-2)" }}>{title} · {rows.length}</div>
      <div className="table-wrap" tabIndex={0} style={{ border: "none" }}>
        <table className="tbl">
          <thead><tr><th>Статус</th><th>Аккаунт</th><th>Backend</th><th>Успешность</th><th>Latency</th><th>Посл. запрос</th></tr></thead>
          <tbody>
            {rows.map((a) => {
              const s = statusMeta(a); const sr = Math.round((a.success_rate ?? 1) * 100);
              return (
                <tr key={a.id}>
                  <td><span className={"status-dot " + s.dot} />{s.label}</td>
                  <td>{a.name}</td>
                  <td><span className="pill muted">{a.kind}</span></td>
                  <td><div style={{ display: "flex", alignItems: "center", gap: 8 }}>
                    <div className={"bcbar" + (sr < 90 ? " warn" : "") + (sr < 70 ? " danger" : "")}><span style={{ width: sr + "%" }} /></div>
                    <b style={{ fontSize: 12, fontVariantNumeric: "tabular-nums" }}>{sr}%</b>
                  </div></td>
                  <td style={{ color: latTone(a.avg_latency_ms), fontVariantNumeric: "tabular-nums" }}>{a.avg_latency_ms ? a.avg_latency_ms + " мс" : "—"}</td>
                  <td className="muted" style={{ fontSize: 12 }}>{a.last_used_at ? new Date(a.last_used_at).toLocaleString("ru") : "—"}</td>
                </tr>
              );
            })}
          </tbody>
        </table>
      </div>
    </div>
  );
}

// ---------------- Accounts tab ----------------
function AccountsTab({ accounts, guard, toast }: {
  accounts: AIAccount[]; guard: (p: Promise<unknown>) => void; toast: (m: string) => void;
}) {
  const [q, setQ] = useState(""); const dq = useDebounced(q);
  const [fTier, setFTier] = useState("all"); const [fKind, setFKind] = useState("all"); const [fStatus, setFStatus] = useState("all");
  const [card, setCard] = useState<AIAccount | null>(null);
  const [adding, setAdding] = useState(false);

  const filtered = useMemo(() => accounts.filter((a) => {
    if (fTier === "pool" && a.tier !== 0) return false;
    if (fTier === "fallback" && a.tier === 0) return false;
    if (fKind !== "all" && a.kind !== fKind) return false;
    if (fStatus !== "all") { const ok = fStatus === "active" ? a.enabled && a.status === "active" : fStatus === "off" ? !a.enabled : a.status === fStatus; if (!ok) return false; }
    if (dq.trim()) { const s = dq.toLowerCase(); if (![a.name, a.kind, a.base_url, String(a.id)].some((f) => String(f).toLowerCase().includes(s))) return false; }
    return true;
  }), [accounts, dq, fTier, fKind, fStatus]);

  return (
    <div className="page-stack">
      <div className="panel" style={{ padding: "var(--sp-3) var(--sp-4)" }}>
        <div className="section-head" style={{ margin: 0 }}>
          <div className="form-row" style={{ gap: "var(--sp-2)", flexWrap: "wrap" }}>
            <input style={{ width: 200 }} placeholder="Поиск: имя, backend, URL, ID" value={q} onChange={(e) => setQ(e.target.value)} />
            <Select width={150} ariaLabel="Tier" value={fTier} onChange={setFTier} options={[{ value: "all", label: "Все tier" }, { value: "pool", label: "Пул (0)" }, { value: "fallback", label: "Fallback (1)" }]} />
            <Select width={150} ariaLabel="Backend" value={fKind} onChange={setFKind} options={[{ value: "all", label: "Все backends" }, ...ACCOUNT_KINDS.map((k) => ({ value: k, label: k }))]} />
            <Select width={150} ariaLabel="Статус" value={fStatus} onChange={setFStatus} options={[{ value: "all", label: "Все статусы" }, { value: "active", label: "Активные" }, { value: "cooldown", label: "Cooldown" }, { value: "off", label: "Выключенные" }]} />
          </div>
          <button className="btn" onClick={() => setAdding(true)}><span className="ms sm">add</span> Аккаунт</button>
        </div>
      </div>

      <div className="panel">
        {filtered.length === 0 ? (
          accounts.length === 0
            ? <EmptyState icon="vpn_key" title="Аккаунтов пока нет" desc="Добавьте первый backend-аккаунт — gateway, агрегатор или прямой провайдерский ключ." action={{ label: "Добавить аккаунт", onClick: () => setAdding(true) }} />
            : <EmptyState icon="search_off" title="Ничего не найдено" desc="Измените поиск или фильтры." />
        ) : (
          <div className="table-wrap sticky" tabIndex={0} style={{ border: "none" }}>
            <table className="tbl">
              <thead><tr>
                <th>Статус</th><th>Название</th><th>Backend</th><th>Base URL</th><th>Tier</th><th>Prio</th><th>Вес</th>
                <th>Запр/Ош</th><th>Успех</th><th>Latency</th><th>Расход</th><th style={{ width: 180 }}>Действия</th>
              </tr></thead>
              <tbody>
                {filtered.map((a) => {
                  const s = statusMeta(a); const sr = Math.round((a.success_rate ?? 1) * 100);
                  return (
                    <tr key={a.id}>
                      <td><span className={"status-dot " + s.dot} /><span className={"pill " + s.pill}>{s.label}</span></td>
                      <td><b style={{ cursor: "pointer" }} onClick={() => setCard(a)}>{a.name}</b></td>
                      <td><span className="pill muted">{a.kind}</span></td>
                      <td className="code-key" style={{ maxWidth: 200, overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap" }} title={a.base_url}>{a.base_url}</td>
                      <td>{a.tier === 0 ? "пул" : "fb"}</td>
                      <td style={{ fontVariantNumeric: "tabular-nums" }}>{a.priority}</td>
                      <td style={{ fontVariantNumeric: "tabular-nums" }}>{a.weight}</td>
                      <td className="muted" style={{ fontVariantNumeric: "tabular-nums" }}>{a.total_requests}/<span className={a.total_errors ? "danger" : ""}>{a.total_errors}</span></td>
                      <td style={{ fontVariantNumeric: "tabular-nums" }}>{sr}%</td>
                      <td style={{ color: latTone(a.avg_latency_ms), fontVariantNumeric: "tabular-nums" }}>{a.avg_latency_ms ? a.avg_latency_ms + "мс" : "—"}</td>
                      <td className={a.over_budget ? "danger" : "muted"} title={a.spend_limit_usd ? `лимит $${a.spend_limit_usd}` : "без лимита"}>{a.spend_usd ? usd(a.spend_micros) : "—"}{a.over_budget ? " ⛔" : ""}</td>
                      <td>
                        <div className="form-row" style={{ gap: 2, flexWrap: "nowrap" }}>
                          <button className="btn ghost sm" title="Открыть" onClick={() => setCard(a)}><span className="ms sm">visibility</span></button>
                          <button className="btn ghost sm" title={a.enabled ? "Выключить" : "Включить"} onClick={() => { if (a.enabled && accounts.filter(x => x.enabled).length <= 1) { if (!confirm("Это последний активный аккаунт — все генерации остановятся. Выключить?")) return; } /* FIX: AUDIT-72 - confirm before disabling the last active account */ guard(api.aiUpdateAccount(a.id, { enabled: !a.enabled })); }}><span className="ms sm">{a.enabled ? "toggle_on" : "toggle_off"}</span></button>
                          <button className="btn ghost sm" title="Сброс health" onClick={() => guard(api.aiResetAccount(a.id))}><span className="ms sm">restart_alt</span></button>
                          <button className="btn ghost sm" title="Удалить" onClick={() => confirm(`Удалить «${a.name}»?`) && guard(api.aiDeleteAccount(a.id))}><span className="ms sm" style={{ color: "var(--danger)" }}>delete</span></button>
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

      {card && <AccountCard a={card} onClose={() => setCard(null)} guard={guard} toast={toast} />}
      {adding && <AccountEditor onClose={() => setAdding(false)} guard={guard} toast={toast} />}
    </div>
  );
}

function AccountCard({ a, onClose, guard, toast }: {
  a: AIAccount; onClose: () => void; guard: (p: Promise<unknown>) => void; toast: (m: string) => void;
}) {
  const [ping, setPing] = useState<{ ok: boolean; status_code: number; latency_ms: number; detail: string } | null>(null);
  const [busy, setBusy] = useState(false);
  const s = statusMeta(a);
  async function test() { setBusy(true); try { setPing(await api.aiTestAccount(a.id)); } catch (e) { toast(String(e)); } finally { setBusy(false); } }
  return (
    <Modal title={a.name} icon="vpn_key" onClose={onClose} wide
      footer={<>
        <button className="btn ghost spacer" onClick={() => { guard(api.aiResetAccount(a.id)); onClose(); }}><span className="ms sm">restart_alt</span> Сброс health</button>
        <button className="btn ghost" onClick={() => { if (confirm("Обнулить расход?")) { guard(api.aiResetSpend(a.id)); onClose(); } }}><span className="ms sm">payments</span> Обнулить расход</button>
        <button className="btn danger" onClick={() => { if (confirm(`Удалить «${a.name}»?`)) { guard(api.aiDeleteAccount(a.id)); onClose(); } }}><span className="ms sm">delete</span> Удалить</button>
      </>}>
      <div className="form-row" style={{ gap: 8, marginBottom: "var(--sp-4)" }}>
        <span className={"status-dot " + s.dot} /><span className={"pill " + s.pill}>{s.label}</span>
        <span className="pill muted">{a.kind}</span><span className="pill muted">{MODALITY_LABEL[a.modality] || a.modality}</span>
        <span className="pill muted">{a.tier === 0 ? "пул" : "fallback"}</span>
      </div>

      <div className="form-grid">
        <KV label="API Key (маскирован)"><span className="code-key">{a.api_key}</span></KV>
        <KV label="Base URL"><span className="code-key" style={{ wordBreak: "break-all" }}>{a.base_url}</span></KV>
        <KV label="Priority / Weight">{a.priority} / {a.weight}</KV>
        <KV label="Создан">{a.created_at ? new Date(a.created_at).toLocaleString("ru") : "—"}</KV>
      </div>

      <div className="metrics" style={{ margin: "var(--sp-4) 0", gridTemplateColumns: "repeat(4,1fr)" }}>
        <Metric icon="bolt" label="Запросов" value={a.total_requests} small />
        <Metric icon="error" label="Ошибок" value={a.total_errors} small tone={a.total_errors ? "danger" : undefined} />
        <Metric icon="percent" label="Успех" value={Math.round((a.success_rate ?? 1) * 100)} suffix="%" small />
        <Metric icon="speed" label="Avg latency" value={a.avg_latency_ms ? a.avg_latency_ms + "мс" : "—"} small />
      </div>

      <div className="form-grid">
        <KV label="Расход / Лимит">{usd(a.spend_micros)}{a.spend_limit_micros ? ` / ${usd(a.spend_limit_micros)}` : " / ∞"}{a.over_budget ? " ⛔" : ""}</KV>
        <KV label="Последняя задержка">{a.last_latency_ms ? a.last_latency_ms + " мс" : "—"}</KV>
        <KV label="Последний запрос">{a.last_used_at ? new Date(a.last_used_at).toLocaleString("ru") : "—"}</KV>
        <KV label="Cooldown до">{a.cooldown_until ? new Date(a.cooldown_until).toLocaleString("ru") : "—"}</KV>
      </div>
      {a.last_error && <div style={{ marginTop: "var(--sp-3)" }}><KV label="Последняя ошибка"><span className="danger" style={{ fontSize: 12 }}>{a.last_error}</span></KV></div>}

      <div style={{ marginTop: "var(--sp-4)", padding: "var(--sp-3)", background: "var(--surface-1)", border: "1px solid var(--border)", borderRadius: "var(--r-sm)" }}>
        <div className="form-row" style={{ justifyContent: "space-between" }}>
          <span className="panel-title sm" style={{ margin: 0 }}><span className="ms sm">network_check</span> Health Check</span>
          <button className="btn sm" onClick={test} disabled={busy}><span className="ms sm">{busy ? "hourglass_top" : "play_arrow"}</span> {busy ? "Проверка…" : "Ping"}</button>
        </div>
        {ping && (
          <p className={ping.ok ? "note-ok" : "note-err"} style={{ marginTop: "var(--sp-2)", marginBottom: 0 }}>
            <span className="ms sm">{ping.ok ? "check_circle" : "error"}</span>
            {ping.ok ? `Подключение OK · ${ping.latency_ms} мс (HTTP ${ping.status_code})` : `${ping.status_code || "нет ответа"} · ${ping.latency_ms} мс · ${ping.detail}`}
          </p>
        )}
      </div>
      <p className="cfg-hint" style={{ marginTop: "var(--sp-4)" }}>
        <span className="ms sm" style={{ verticalAlign: "-3px" }}>info</span>{" "}
        Headers, timeout, retry, organization/project, metadata и tags не хранятся в текущей модели аккаунта — потребуют доп. полей. История ошибок ведётся как последняя ошибка + общий счётчик; полный лог запросов требует таблицы событий.
      </p>
    </Modal>
  );
}

function AccountEditor({ onClose, guard, toast }: { onClose: () => void; guard: (p: Promise<unknown>) => void; toast: (m: string) => void }) {
  const [f, setF] = useState<AccForm>({ ...EMPTY_ACC });
  const set = <K extends keyof AccForm>(k: K, v: AccForm[K]) => setF((p) => ({ ...p, [k]: v }));
  function save() {
    if (!f.name || !f.base_url || !f.api_key) { toast("name, base_url, api_key обязательны"); return; }
        // FIX: AUDIT-2 - validate base_url scheme (SSRF defense)
        if (!/^https?:\/\//.test(f.base_url.trim())) { toast("Base URL должен начинаться с http(s)://"); return; }
    guard(api.aiCreateAccount({ name: f.name, kind: f.kind, base_url: f.base_url, api_key: f.api_key, modality: f.modality, tier: Number(f.tier), priority: Number(f.priority), weight: Number(f.weight), spend_limit_micros: Math.round(Number(f.spend_limit_usd) * 1_000_000), enabled: f.enabled }));
    onClose();
  }
  return (
    <Modal title="Новый аккаунт" icon="add_circle" onClose={onClose} wide
      footer={<><button className="btn ghost spacer" onClick={onClose}>Отмена</button><button className="btn" onClick={save}><span className="ms sm">add</span> Добавить</button></>}>
      <div className="form-grid">
        <KVF label="Название"><input value={f.name} onChange={(e) => set("name", e.target.value)} /></KVF>
        <KVF label="Backend"><Select width="100%" ariaLabel="Backend" value={f.kind} onChange={(v) => set("kind", v)} options={opts(ACCOUNT_KINDS)} /></KVF>
        <KVF label="Модальность"><Select width="100%" ariaLabel="Модальность" value={f.modality} onChange={(v) => set("modality", v)} options={MODALITIES.map((m) => ({ value: m, label: MODALITY_LABEL[m] }))} /></KVF>
        <KVF label="Tier"><Select width="100%" ariaLabel="Tier" value={String(f.tier)} onChange={(v) => set("tier", Number(v))} options={[{ value: "0", label: "пул (tier 0)" }, { value: "1", label: "fallback (tier 1)" }]} /></KVF>
      </div>
      <KVF label="Base URL (…/v1)"><input className="mono" value={f.base_url} onChange={(e) => set("base_url", e.target.value)} placeholder="https://gateway.example/v1" /></KVF>
      <KVF label="API Key"><input className="mono" value={f.api_key} onChange={(e) => set("api_key", e.target.value)} placeholder="sk-…" /></KVF>
      <div className="form-grid">
        <KVF label="Priority"><input type="number" value={f.priority} onChange={(e) => { const v = Number(e.target.value); set("priority", Number.isFinite(v) ? Math.max(0, Math.floor(v)) : 0); }}/></KVF>
        <KVF label="Weight (балансировка)"><input type="number" value={f.weight} onChange={(e) => { const v = Number(e.target.value); set("weight", Number.isFinite(v) ? Math.max(0, Math.floor(v)) : 0); }}/></KVF>
        <KVF label="Лимит трат, $ (0 = ∞)"><input type="number" step="0.01" min="0" value={f.spend_limit_usd} onChange={(e) => { const v = Number(e.target.value); set("spend_limit_usd", Number.isFinite(v) ? Math.max(0, v) : 0); }}/></KVF>
      </div>
      <div style={{ marginTop: "var(--sp-3)" }}><Switch checked={f.enabled} onChange={(v) => set("enabled", v)} label="Включён" /></div>
      <p className="cfg-hint" style={{ marginTop: "var(--sp-4)" }}>
        <span className="ms sm" style={{ verticalAlign: "-3px" }}>info</span>{" "}
        Org/project, timeout, retries, cooldown, health-URL, headers, metadata, tags, sticky и fallback-chain потребуют доп. полей модели аккаунта — пока хранятся обязательные поля маршрутизации.
      </p>
    </Modal>
  );
}

// ---------------- Models tab ----------------
type MSort = "sort_order" | "title" | "cost" | "cost_micros";
function ModelsTab({ models, guard, toast }: { models: AIModelRow[]; guard: (p: Promise<unknown>) => void; toast: (m: string) => void }) {
  const [q, setQ] = useState(""); const dq = useDebounced(q);
  const [fMod, setFMod] = useState("all"); const [fBackend, setFBackend] = useState("all"); const [fExtra, setFExtra] = useState("all");
  const [sortKey, setSortKey] = useState<MSort>("sort_order"); const [sortDir, setSortDir] = useState<1 | -1>(1);
  const [page, setPage] = useState(0); const [pageSize, setPageSize] = useState(24);
  const [sel, setSel] = useState<Set<string>>(new Set());
  const [editor, setEditor] = useState<{ row: AIModelRow | null } | null>(null);
  const drag = useRef<string | null>(null); const [over, setOver] = useState<string | null>(null);
  const reorderable = sortKey === "sort_order" && !dq && fMod === "all" && fBackend === "all" && fExtra === "all";

  const filtered = useMemo(() => {
    let r = models;
    if (fMod !== "all") r = r.filter((m) => m.modality === fMod);
    if (fBackend !== "all") r = r.filter((m) => (m.account_kind || "") === (fBackend === "any" ? "" : fBackend));
    if (fExtra === "premium") r = r.filter((m) => m.premium); else if (fExtra === "free") r = r.filter((m) => !m.premium);
    else if (fExtra === "on") r = r.filter((m) => m.enabled); else if (fExtra === "off") r = r.filter((m) => !m.enabled);
    if (dq.trim()) { const s = dq.toLowerCase(); r = r.filter((m) => [m.key, m.title, m.upstream_model, m.account_kind].some((f) => String(f ?? "").toLowerCase().includes(s))); }
    return [...r].sort((a, b) => {
      if (sortKey === "title") return a.title.localeCompare(b.title) * sortDir;
      if (sortKey === "cost") return (a.cost - b.cost) * sortDir;
      if (sortKey === "cost_micros") return ((a.cost_micros || 0) - (b.cost_micros || 0)) * sortDir;
      return (a.sort_order - b.sort_order || a.key.localeCompare(b.key)) * sortDir;
    });
  }, [models, dq, fMod, fBackend, fExtra, sortKey, sortDir]);
  const pageCount = Math.max(1, Math.ceil(filtered.length / pageSize));
  const paged = filtered.slice(page * pageSize, page * pageSize + pageSize);
  useEffect(() => { if (page >= pageCount) setPage(0); }, [page, pageCount]);

  async function reorder(targetKey: string) {
    const src = drag.current; drag.current = null; setOver(null);
    if (!src || src === targetKey || !reorderable) return;
    const ordered = [...models].sort((a, b) => a.sort_order - b.sort_order || a.key.localeCompare(b.key));
    const from = ordered.findIndex((m) => m.key === src), to = ordered.findIndex((m) => m.key === targetKey);
    const [m] = ordered.splice(from, 1); ordered.splice(to, 0, m);
    for (let i = 0; i < ordered.length; i++) if (ordered[i].sort_order !== i * 10) {
      const { key, ...rest } = ordered[i]; await api.aiUpsertModel(key, { ...rest, sort_order: i * 10 });
    }
    guard(Promise.resolve()); toast("✅ Порядок моделей сохранён");
  }
  const bulk = async (patch: Partial<AIModelRow> | "delete") => {
    const targets = models.filter((m) => sel.has(m.key));
    // FIX: AUDIT-2 - per-item try/catch + busy state
    let ok = 0, failed = 0;
    for (const m of targets) {
      try {
        if (patch === "delete") await api.aiDeleteModel(m.key);
        else { const { key, ...rest } = m; await api.aiUpsertModel(key, { ...rest, ...patch }); }
        ok++;
      } catch (e) { failed++; toast(`❌ ${m.key}: ${e}`); }
    }
    setSel(new Set()); guard(Promise.resolve());
    toast(`✅ Готово: ${ok}${failed ? `, ошибок: ${failed}` : ""}`);
  };
  const sortHead = (k: MSort, label: string) => (
    <th className="sortable" onClick={() => { if (sortKey === k) setSortDir((d) => (d === 1 ? -1 : 1)); else { setSortKey(k); setSortDir(1); } }}>
      {label}{sortKey === k && <span className="ms sort-ic">{sortDir === 1 ? "arrow_drop_up" : "arrow_drop_down"}</span>}
    </th>
  );

  return (
    <div className="page-stack">
      <div className="panel" style={{ padding: "var(--sp-3) var(--sp-4)" }}>
        <div className="section-head" style={{ margin: 0 }}>
          <div className="form-row" style={{ gap: "var(--sp-2)", flexWrap: "wrap" }}>
            <input style={{ width: 200 }} placeholder="Поиск: key, название, upstream" value={q} onChange={(e) => setQ(e.target.value)} />
            <Select width={140} ariaLabel="Модальность" value={fMod} onChange={setFMod} options={[{ value: "all", label: "Все типы" }, ...MODALITIES.map((m) => ({ value: m, label: MODALITY_LABEL[m] }))]} />
            <Select width={150} ariaLabel="Backend" value={fBackend} onChange={setFBackend} options={[{ value: "all", label: "Все backends" }, { value: "any", label: "(любой)" }, ...BACKENDS.filter(Boolean).map((b) => ({ value: b, label: b }))]} />
            <Select width={140} ariaLabel="Доп" value={fExtra} onChange={setFExtra} options={[{ value: "all", label: "Все" }, { value: "premium", label: "Premium" }, { value: "free", label: "Free" }, { value: "on", label: "Включённые" }, { value: "off", label: "Выключенные" }]} />
          </div>
          <button className="btn" onClick={() => setEditor({ row: null })}><span className="ms sm">add</span> Модель</button>
        </div>
        {sel.size > 0 && (
          <div className="form-row" style={{ gap: "var(--sp-2)", flexWrap: "wrap", marginTop: "var(--sp-3)", paddingTop: "var(--sp-3)", borderTop: "1px solid var(--border)" }}>
            <span className="pill pro">{sel.size} выбрано</span>
            <button className="btn ghost sm" onClick={() => bulk({ enabled: true })}><span className="ms sm">visibility</span> Вкл</button>
            <button className="btn ghost sm" onClick={() => bulk({ enabled: false })}><span className="ms sm">visibility_off</span> Выкл</button>
            <button className="btn ghost sm" onClick={() => { const v = prompt("Backend (omniroute/kie/… или пусто=любой):"); if (v !== null) bulk({ account_kind: v || null }); }}><span className="ms sm">lan</span> Backend</button>
            <button className="btn ghost sm" onClick={() => { const v = prompt("Стоимость пользователю (кредиты):"); if (v !== null) bulk({ cost: Math.max(0, Number(v) || 0) }); }}><span className="ms sm">toll</span> Стоимость</button>
            <button className="btn ghost sm" onClick={() => confirm(`Удалить ${sel.size} моделей?`) && bulk("delete")}><span className="ms sm" style={{ color: "var(--danger)" }}>delete</span> Удалить</button>
            <button className="btn ghost sm" onClick={() => setSel(new Set())}>Снять</button>
          </div>
        )}
      </div>

      <div className="panel">
        {filtered.length === 0 ? (
          models.length === 0
            ? <EmptyState icon="grid_view" title="Моделей пока нет" desc="Добавьте первую модель каталога: key, upstream-id, backend и стоимость." action={{ label: "Добавить модель", onClick: () => setEditor({ row: null }) }} />
            : <EmptyState icon="search_off" title="Ничего не найдено" desc="Измените поиск или фильтры." />
        ) : (
          <>
            <div className="table-wrap sticky" tabIndex={0} style={{ border: "none" }}>
              <table className="tbl">
                <thead><tr>
                  <th style={{ width: 32 }}><input type="checkbox" className="fx-check" aria-label="Выбрать" checked={paged.every((m) => sel.has(m.key))} onChange={(e) => setSel(e.target.checked ? new Set(paged.map((m) => m.key)) : new Set())} /></th>
                  <th>Key</th>{sortHead("title", "Название")}<th>Upstream</th><th>Тип</th><th>Backend</th><th>Premium</th>
                  {sortHead("cost", "Цена")}{sortHead("cost_micros", "Себест.")}<th>Статус</th>{sortHead("sort_order", "#")}<th style={{ width: 110 }}>Действия</th>
                </tr></thead>
                <tbody>
                  {paged.map((m) => (
                    <tr key={m.key} draggable={reorderable} onDragStart={() => (drag.current = m.key)}
                      onDragOver={(e) => { if (reorderable) { e.preventDefault(); setOver(m.key); } }} onDrop={() => reorder(m.key)}
                      style={over === m.key ? { outline: "1px solid var(--accent)" } : undefined}>
                      <td><input type="checkbox" className="fx-check" aria-label="Выбрать" checked={sel.has(m.key)} onChange={() => setSel((s) => { const n = new Set(s); n.has(m.key) ? n.delete(m.key) : n.add(m.key); return n; })} /></td>
                      <td className="code-key">{m.key}</td>
                      <td><b style={{ cursor: "pointer" }} onClick={() => setEditor({ row: m })}>{m.title}</b></td>
                      <td className="code-key" style={{ maxWidth: 160, overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap" }} title={m.upstream_model}>{m.upstream_model}</td>
                      <td><span className="pill muted">{MODALITY_LABEL[m.modality] || m.modality}</span></td>
                      <td>{m.account_kind ? <span className="pill muted">{m.account_kind}</span> : <span className="muted">любой</span>}</td>
                      <td>{m.premium ? <span className="pill pro">PRO</span> : <span className="muted">—</span>}</td>
                      <td style={{ fontVariantNumeric: "tabular-nums" }}>{m.cost}</td>
                      <td className="muted" style={{ fontVariantNumeric: "tabular-nums" }}>{m.cost_micros ? usd(m.cost_micros) : "—"}</td>
                      <td><button className="btn ghost sm" title={m.enabled ? "Выключить" : "Включить"} onClick={() => { const { key, ...rest } = m; guard(api.aiUpsertModel(key, { ...rest, enabled: !m.enabled })); }}><span className={"status-dot " + (m.enabled ? "on" : "off")} style={{ margin: 0 }} /></button></td>
                      <td className="muted">{m.sort_order}</td>
                      <td>
                        <div className="form-row" style={{ gap: 2, flexWrap: "nowrap" }}>
                          <button className="btn ghost sm" title="Редактировать" onClick={() => setEditor({ row: m })}><span className="ms sm">edit</span></button>
                          <button className="btn ghost sm" title="Удалить" onClick={() => confirm(`Удалить модель ${m.key}?`) && guard(api.aiDeleteModel(m.key))}><span className="ms sm" style={{ color: "var(--danger)" }}>delete</span></button>
                        </div>
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
            <Pager page={page} pageCount={pageCount} pageSize={pageSize} total={filtered.length} setPage={setPage} setPageSize={setPageSize} />
          </>
        )}
      </div>

      {editor && <ModelEditor row={editor.row} guard={guard} toast={toast} onClose={() => setEditor(null)} />}
    </div>
  );
}

function ModelEditor({ row, guard, toast, onClose }: { row: AIModelRow | null; guard: (p: Promise<unknown>) => void; toast: (m: string) => void; onClose: () => void }) {
  const [m, setM] = useState<AIModelRow & { key: string }>(() => row ? { ...row } : { ...EMPTY_MODEL });
  const set = <K extends keyof AIModelRow>(k: K, v: AIModelRow[K]) => setM((p) => ({ ...p, [k]: v }));
  function save() {
    if (!m.key || !m.title || !m.upstream_model) { toast("key, title, upstream_model обязательны"); return; }
    const { key, ...rest } = m;
    guard(api.aiUpsertModel(key, rest)); onClose();
  }
  return (
    <Modal title={row ? `Модель: ${row.key}` : "Новая модель"} icon="grid_view" onClose={onClose} wide
      footer={<><button className="btn ghost spacer" onClick={onClose}>Отмена</button><button className="btn" onClick={save}><span className="ms sm">save</span> Сохранить</button></>}>
      <div className="form-grid">
        <KVF label="Key (= job.service)"><input className="mono" value={m.key} disabled={!!row} onChange={(e) => set("key", e.target.value)} /></KVF>
        <KVF label="Название"><input value={m.title} onChange={(e) => set("title", e.target.value)} /></KVF>
      </div>
      <KVF label="Upstream model (id для API)"><input className="mono" value={m.upstream_model} onChange={(e) => set("upstream_model", e.target.value)} /></KVF>
      <div className="form-grid">
        <KVF label="Модальность"><Select width="100%" ariaLabel="Модальность" value={m.modality} onChange={(v) => set("modality", v)} options={MODALITIES.map((x) => ({ value: x, label: MODALITY_LABEL[x] }))} /></KVF>
        <KVF label="Backend (pin)"><Select width="100%" ariaLabel="Backend" value={m.account_kind ?? ""} onChange={(v) => set("account_kind", v || null)} options={BACKENDS.map((x) => ({ value: x, label: x || "(любой)" }))} /></KVF>
        <KVF label="Цена пользователю (кредиты)"><input type="number" min={0} value={m.cost} onChange={(e) => set("cost", Math.max(0, Number(e.target.value) || 0))} /></KVF>
        <KVF label="Себестоимость, $ за запрос"><input type="number" step="0.0001" min={0} value={(m.cost_micros || 0) / 1_000_000} onChange={(e) => set("cost_micros", Math.round(Number(e.target.value) * 1_000_000))} /></KVF>
        <KVF label="Порядок"><input type="number" value={m.sort_order} onChange={(e) => set("sort_order", Number(e.target.value) || 0)} /></KVF>
        <KVF label="Цена за 1M вход. токенов, $"><input type="number" step="0.01" min={0} value={perMtokUsd(m.price_in_micros)} onChange={(e) => set("price_in_micros", Math.round(Number(e.target.value) * 1_000_000))} /></KVF>
        <KVF label="Цена за 1M вых. токенов, $"><input type="number" step="0.01" min={0} value={perMtokUsd(m.price_out_micros)} onChange={(e) => set("price_out_micros", Math.round(Number(e.target.value) * 1_000_000))} /></KVF>
      </div>
      <div className="form-row" style={{ gap: "var(--sp-4)", marginTop: "var(--sp-3)" }}>
        <Switch checked={m.enabled} onChange={(v) => set("enabled", v)} label="Включена" />
        <Switch checked={m.premium} onChange={(v) => set("premium", v)} label="Premium" />
        <Switch checked={!!m.search} onChange={(v) => set("search", v)} label="Поиск (/s)" />
      </div>
      <p className="cfg-hint" style={{ marginTop: "var(--sp-4)" }}>
        <span className="ms sm" style={{ verticalAlign: "-3px" }}>info</span>{" "}
        Модальность ({MODALITY_LABEL[m.modality]}) — реальный признак возможностей. Гранулярные флаги (Vision/Function Calling/Streaming/Reasoning/JSON Mode), контекст, max-output и RPM/TPM потребуют доп. полей модели — пока не хранятся.
      </p>
    </Modal>
  );
}

// ---------------- Tools tab: test center + cost calculator + containers ----------------
function ToolsTab({ accounts, models, toast }: { accounts: AIAccount[]; models: AIModelRow[]; toast: (m: string) => void }) {
  const [accId, setAccId] = useState(accounts[0]?.id ? String(accounts[0].id) : "");
  const [res, setRes] = useState<Record<number, { ok: boolean; latency_ms: number; status_code: number; detail: string }>>({});
  const [busy, setBusy] = useState(false);
  async function testOne(id: number) { setBusy(true); try { const r = await api.aiTestAccount(id); setRes((p) => ({ ...p, [id]: r })); } catch (e) { toast(String(e)); } finally { setBusy(false); } }
  async function testAll() {
    setBusy(true);
    try {
      for (const a of accounts) {
        try { const r = await api.aiTestAccount(a.id); setRes((p) => ({ ...p, [a.id]: r })); }
        catch (e) { setRes((p) => ({ ...p, [a.id]: { ok: false, status_code: 0, latency_ms: 0, detail: String(e) } })); }  // FIX: AUDIT-2
      }
    } finally { setBusy(false); }  // FIX: AUDIT-2 - always clear busy
  }

  // cost calculator — per-request (cost_micros) or per-token (price_in/out per 1M).
  const [modelKey, setModelKey] = useState(models[0]?.key ?? "");
  const [reqs, setReqs] = useState(1000);
  const [inTok, setInTok] = useState(1000);
  const [outTok, setOutTok] = useState(500);
  const model = models.find((m) => m.key === modelKey);
  const tokenPriced = !!((model?.price_in_micros || 0) || (model?.price_out_micros || 0));
  // micro-USD: price_*_micros is per 1M tokens, so scale by tokens/1e6.
  const tokenCostPerReq = ((model?.price_in_micros || 0) * inTok + (model?.price_out_micros || 0) * outTok) / 1_000_000;
  const provider = (tokenPriced ? tokenCostPerReq : (model?.cost_micros || 0)) * reqs;
  const userCredits = (model?.cost || 0) * reqs;

  return (
    <div className="page-stack">
      <div className="bc-grid">
        {/* Test center */}
        <div className="panel" style={{ margin: 0 }}>
          <div className="section-head">
            <div className="panel-title" style={{ margin: 0 }}><span className="ms sm">network_check</span> Test Center</div>
            <button className="btn ghost sm" onClick={testAll} disabled={busy || !accounts.length}><span className="ms sm">checklist</span> Тест всех</button>
          </div>
          {accounts.length === 0 ? <EmptyState icon="vpn_key" title="Нет аккаунтов" desc="Добавьте аккаунт, чтобы запускать проверки подключения." /> : (
            <div className="form-row" style={{ gap: "var(--sp-2)" }}>
              <Select width={240} ariaLabel="Аккаунт" value={accId} onChange={setAccId} options={accounts.map((a) => ({ value: String(a.id), label: `${a.name} · ${a.kind}` }))} />
              <button className="btn" onClick={() => accId && testOne(Number(accId))} disabled={busy}><span className="ms sm">play_arrow</span> Ping</button>
            </div>
          )}
          <div style={{ marginTop: "var(--sp-3)", display: "flex", flexDirection: "column", gap: 6 }}>
            {accounts.filter((a) => res[a.id]).map((a) => { const r = res[a.id]; return (
              <p key={a.id} className={r.ok ? "note-ok" : "note-err"} style={{ margin: 0 }}>
                <span className="ms sm">{r.ok ? "check_circle" : "error"}</span>
                <b>{a.name}</b>: {r.ok ? `OK · ${r.latency_ms} мс (HTTP ${r.status_code})` : `${r.status_code || "нет ответа"} · ${r.latency_ms} мс · ${r.detail}`}
              </p>
            ); })}
          </div>
          <p className="cfg-hint" style={{ marginTop: "var(--sp-3)" }}>
            <span className="ms sm" style={{ verticalAlign: "-3px" }}>info</span>{" "}
            Реальная проверка подключения (GET /models с ключом аккаунта). Полный прогон промпта (system/temperature/top-p/max-tokens/streaming) потребует серверного completion-эндпоинта.
          </p>
        </div>

        {/* Cost calculator */}
        <div className="panel" style={{ margin: 0 }}>
          <div className="panel-title"><span className="ms sm">calculate</span> Калькулятор стоимости</div>
          <div className="form-grid">
            <KVF label="Модель"><Select width="100%" ariaLabel="Модель" value={modelKey} onChange={setModelKey} options={models.map((m) => ({ value: m.key, label: m.title }))} /></KVF>
            <KVF label="Количество запросов"><input type="number" min={0} value={reqs} onChange={(e) => setReqs(Math.max(0, Number(e.target.value) || 0))} /></KVF>
            {tokenPriced && <KVF label="Вход. токенов / запрос"><input type="number" min={0} value={inTok} onChange={(e) => setInTok(Math.max(0, Number(e.target.value) || 0))} /></KVF>}
            {tokenPriced && <KVF label="Вых. токенов / запрос"><input type="number" min={0} value={outTok} onChange={(e) => setOutTok(Math.max(0, Number(e.target.value) || 0))} /></KVF>}
          </div>
          <div className="metrics" style={{ margin: "var(--sp-4) 0 0", gridTemplateColumns: "1fr 1fr" }}>
            <Metric icon="payments" label={tokenPriced ? "Себестоимость (по токенам)" : "Себестоимость (за запрос)"} value={usd(provider)} small />
            <Metric icon="toll" label="Списано пользователям" value={userCredits.toLocaleString("ru") + " кр."} small />
          </div>
          <p className="cfg-hint" style={{ marginTop: "var(--sp-3)" }}>
            <span className="ms sm" style={{ verticalAlign: "-3px" }}>info</span>{" "}
            {tokenPriced
              ? <>Потокенный расчёт: цена за 1M входных/выходных токенов × токены × запросы. Кредиты пользователю — по <code className="code-key">cost</code>.</>
              : <>Расчёт за запрос (<code className="code-key">cost_micros</code>). Задайте цену за 1M токенов в модели — появится потокенный режим.</>}
          </p>
        </div>
      </div>

      <RouterPanels />
    </div>
  );
}

// Editable list of router web-UIs (OmniRoute / LiteLLM / custom) to open or embed.
// You log into your own accounts (Google/ChatGPT/…) inside each router's own UI.
function RouterPanels() {
  const [panels, setPanels] = useState<RouterPanel[] | null>(null);
  const [dirty, setDirty] = useState(false);
  const [active, setActive] = useState<string | null>(null);
  const [msg, setMsg] = useState("");
  const [busy, setBusy] = useState(false);  // FIX: AUDIT12-L2 - panels save in-flight guard
  useEffect(() => { api.routerPanels().then((r) => setPanels(r.panels)).catch(() => setPanels([])); }, []);

  const edit = (i: number, patch: Partial<RouterPanel>) => { setPanels((p) => p!.map((x, j) => (j === i ? { ...x, ...patch } : x))); setDirty(true); };
  const add = () => { setPanels((p) => [...(p || []), { id: `r${Date.now().toString(36)}`, name: "", url: "" }]); setDirty(true); };
  const remove = (i: number) => { setPanels((p) => p!.filter((_, j) => j !== i)); setDirty(true); if (panels?.[i]?.id === active) setActive(null); };
  async function save() {
    setBusy(true);
    try { const r = await api.setRouterPanels((panels || []).filter((p) => p.name.trim())); setPanels(r.panels); setDirty(false); setMsg("✅ Сохранено"); }
    catch (e) { setMsg(String(e)); }
    finally { setBusy(false); }
  }
  if (panels === null) return null;
  const embedded = panels.find((p) => p.id === active && p.url);
  const open = (url: string) => window.open(url, "_blank", "noopener,noreferrer");

  return (
    <div className="panel">
      <div className="section-head">
        <div className="panel-title" style={{ margin: 0 }}><span className="ms sm">open_in_browser</span> Панели роутеров (UI)</div>
        <div className="form-row" style={{ gap: "var(--sp-2)" }}>
          <button className="btn ghost sm" onClick={add}><span className="ms sm">add</span> Роутер</button>
          <button className="btn sm" onClick={save} disabled={!dirty || busy}><span className="ms sm">save</span> Сохранить</button>
        </div>
      </div>
      {msg && <p className={msg.startsWith("✅") ? "note-ok" : "note-err"}><span className="ms sm">{msg.startsWith("✅") ? "check_circle" : "error"}</span>{msg}<button className="btn ghost sm" onClick={() => setMsg("")}>×</button></p>}

      <div style={{ display: "flex", flexDirection: "column", gap: "var(--sp-2)" }}>
        {panels.map((p, i) => (
          <div key={p.id} className="form-row" style={{ gap: "var(--sp-2)", alignItems: "center", flexWrap: "wrap" }}>
            <input style={{ width: 150 }} placeholder="Название" value={p.name} onChange={(e) => edit(i, { name: e.target.value })} />
            <input className="mono" style={{ flex: 1, minWidth: 220 }} placeholder="https://…/ui — адрес веб-интерфейса роутера" value={p.url} onChange={(e) => edit(i, { url: e.target.value })} />
            <button className="btn ghost sm" disabled={!p.url} title="Встроить в страницу" onClick={() => setActive(active === p.id ? null : p.id)}>
              <span className="ms sm">{active === p.id ? "visibility_off" : "visibility"}</span> {active === p.id ? "Скрыть" : "Встроить"}
            </button>
            <button className="btn ghost sm" disabled={!p.url} title="Открыть в новой вкладке" onClick={() => p.url && open(p.url)}><span className="ms sm">open_in_new</span> Вкладка</button>
            <button className="btn ghost sm" title="Удалить" onClick={() => remove(i)}><span className="ms sm" style={{ color: "var(--danger)" }}>delete</span></button>
          </div>
        ))}
        {panels.length === 0 && <p className="cfg-hint">Роутеров нет. Нажмите «Роутер», чтобы добавить.</p>}
      </div>

      {embedded && (
        <div style={{ marginTop: "var(--sp-4)" }}>
          <div className="section-head" style={{ marginBottom: "var(--sp-2)" }}>
            <span className="cfg-hint" style={{ margin: 0 }}>{embedded.name} · <span className="code-key">{embedded.url}</span></span>
            <button className="btn ghost sm" onClick={() => open(embedded.url)}><span className="ms sm">open_in_new</span> Открыть в новой вкладке</button>
          </div>
          <iframe src={embedded.url} title={embedded.name} sandbox="allow-same-origin allow-scripts allow-forms allow-popups"
            style={{ width: "100%", height: 620, border: "1px solid var(--border)", borderRadius: "var(--r-sm)", background: "#fff" }} />
          <p className="cfg-hint" style={{ marginTop: "var(--sp-2)" }}>
            <span className="ms sm" style={{ verticalAlign: "-3px" }}>info</span>{" "}
            Если панель пустая — роутер запрещает встраивание (X-Frame-Options / CSP). Тогда откройте его в новой вкладке.
          </p>
        </div>
      )}

      <p className="cfg-hint" style={{ marginTop: "var(--sp-3)" }}>
        <span className="ms sm" style={{ verticalAlign: "-3px" }}>info</span>{" "}
        Укажите URL веб-интерфейса каждого роутера (OmniRoute / LiteLLM) — там вы входите своими аккаунтами (Google, ChatGPT…), через которые идут генерации. Пока роутеры не развёрнуты — оставьте URL пустым.
      </p>
    </div>
  );
}

// ---------------- routing strategy picker (Overview) ----------------
const STRATEGY_LABEL: Record<string, string> = {
  weighted: "Приоритет + вес (по умолчанию)",
  least_latency: "Минимальная задержка (быстрейший)",
  round_robin: "Round-robin (поровну)",
};
function StrategyPicker() {
  const [strategy, setStrategy] = useState("");
  const [options, setOptions] = useState<string[]>([]);
  const [saved, setSaved] = useState(false);
  // FIX: UI-10 - local error display. The catch referenced an undefined `toast`
  // (no such function in this component) → "toast is not defined" ReferenceError
  // crashed the whole AI-routing page whenever a strategy save failed.
  const [err, setErr] = useState("");
  useEffect(() => { api.aiStrategy().then((r) => { setStrategy(r.strategy); setOptions(r.options); }).catch(() => {}); }, []);
  async function change(v: string) {
    const prev = strategy;
    setStrategy(v); setErr("");
    try { await api.aiSetStrategy(v); setSaved(true); setTimeout(() => setSaved(false), 1500); }
    catch (e) { setStrategy(prev); setErr(String(e)); setTimeout(() => setErr(""), 3000); }  // FIX: AUDIT-40 - revert + show error on failure
  }
  if (!options.length) return null;
  return (
    <div className="form-row" style={{ gap: "var(--sp-2)", alignItems: "center" }}>
      <span className="cfg-cap" style={{ margin: 0 }}>Режим внутри tier:</span>
      <Select width={280} ariaLabel="Стратегия" value={strategy} onChange={change}
        options={options.map((o) => ({ value: o, label: STRATEGY_LABEL[o] || o }))} />
      {saved && <span className="pill ok">✓ сохранено</span>}
      {err && <span className="pill danger">{err}</span>}
    </div>
  );
}

// ---------------- shared bits ----------------
function Pager({ page, pageCount, pageSize, total, setPage, setPageSize }: {
  page: number; pageCount: number; pageSize: number; total: number; setPage: (n: number) => void; setPageSize: (n: number) => void;
}) {
  if (total === 0) return null;
  return (
    <div className="pager">
      <span className="cfg-hint" style={{ margin: 0 }}>Всего: {total} · стр. {page + 1} из {pageCount}</span>
      <div className="form-row" style={{ gap: "var(--sp-2)" }}>
        <Select width={120} ariaLabel="На странице" value={String(pageSize)} onChange={(v) => setPageSize(Number(v))} options={[24, 48, 96].map((n) => ({ value: String(n), label: `${n} / стр.` }))} />
        <button className="btn ghost sm" disabled={page === 0} onClick={() => setPage(page - 1)}><span className="ms sm">chevron_left</span></button>
        <button className="btn ghost sm" disabled={page >= pageCount - 1} onClick={() => setPage(page + 1)}><span className="ms sm">chevron_right</span></button>
      </div>
    </div>
  );
}
function EmptyState({ icon, title, desc, action }: { icon: string; title: string; desc: string; action?: { label: string; onClick: () => void } }) {
  return (
    <div className="empty-state">
      <div className="es-icon"><span className="ms">{icon}</span></div>
      <p className="es-title">{title}</p>
      <p className="es-desc">{desc}</p>
      {action && <button className="btn" onClick={action.onClick}><span className="ms sm">add</span> {action.label}</button>}
    </div>
  );
}
function KV({ label, children }: { label: string; children: React.ReactNode }) {
  return <div className="cfg-field"><span className="cfg-cap">{label}</span><div>{children}</div></div>;
}
function KVF({ label, children }: { label: string; children: React.ReactNode }) {
  return <div className="cfg-field"><span className="cfg-cap">{label}</span>{children}</div>;
}
function Metric({ icon, label, value, suffix, tone, small }: {
  icon: string; label: string; value: number | string; suffix?: string; tone?: "purple" | "danger"; small?: boolean;
}) {
  return (
    <div className={"metric" + (tone ? " " + tone : "")}>
      <span className="glow" />
      <div className="top"><span className="lbl">{label}</span><span className="ms sm">{icon}</span></div>
      <div><div className="num" style={small ? { fontSize: 16 } : undefined}>{typeof value === "number" ? value.toLocaleString("ru") : value}{suffix && <small>{suffix}</small>}</div></div>
    </div>
  );
}
