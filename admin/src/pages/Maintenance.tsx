import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import {
  maintenanceApi,
  type MaintAuditRow,
  type MaintCache,
  type MaintDatabase,
  type MaintDbOpResult,
  type MaintOverview,
  type MaintQueue,
  type MaintStorage,
} from "../api";
import { Select } from "../components/Select";
import { DateField } from "../components/DateField";
import { Switch } from "../components/Switch";

// Maintenance Center (ТЗ §8). Grounded in the REAL backend — every metric and
// action below is wired to a live endpoint:
//   • overview/database/storage/cache → read-only telemetry (PRAGMA / shutil /
//     Redis INFO / COUNT), no migration;
//   • DB maintenance (VACUUM/ANALYZE/REINDEX/OPTIMIZE/Integrity) and app-cache
//     flush → safe, audited, superadmin-only writes;
//   • queue → /health-ops with real retry/cancel over GenerationJob;
//   • logs → /maintenance/logs tail with client-side severity parsing/search;
//   • audit → /audit.
// Capabilities that need tables/services we don't have yet (backup history &
// scheduling, error grouping with stack traces, cron scheduler, per-provider
// latency, timeseries charts, maintenance mode, system notifications) are honestly
// gated with a "requires backend" note and a cross-reference — never faked.

type Tab = "overview" | "database" | "storage" | "cache" | "queue" | "logs" | "audit";
const TABS: { id: Tab; label: string; icon: string }[] = [
  { id: "overview", label: "Обзор", icon: "monitoring" },
  { id: "database", label: "База данных", icon: "database" },
  { id: "storage", label: "Хранилище", icon: "folder" },
  { id: "cache", label: "Кэш", icon: "bolt" },
  { id: "queue", label: "Очередь", icon: "queue" },
  { id: "logs", label: "Логи", icon: "terminal" },
  { id: "audit", label: "Аудит", icon: "history" },
];

const role = () => localStorage.getItem("admin_role") || "";
const isSuper = () => role() === "superadmin";

// ---------- formatting helpers ----------
function fmtBytes(n: number | undefined): string {
  if (!n || n < 0) return "0 B";
  const u = ["B", "KB", "MB", "GB", "TB"]; let i = 0; let v = n;
  while (v >= 1024 && i < u.length - 1) { v /= 1024; i++; }
  return `${v.toFixed(v >= 100 || i === 0 ? 0 : 1)} ${u[i]}`;
}
const fmtInt = (n: number | undefined) => (n ?? 0).toLocaleString("ru");
function fmtUptime(s: number | undefined): string {
  if (!s || s < 0) return "—";
  const d = Math.floor(s / 86400); const h = Math.floor((s % 86400) / 3600); const m = Math.floor((s % 3600) / 60);
  if (d > 0) return `${d}д ${h}ч`;
  if (h > 0) return `${h}ч ${m}м`;
  return `${m}м`;
}
function ago(s: string | null | undefined): string {
  if (!s) return "—";
  const ms = Date.now() - new Date(s).getTime();
  const m = Math.floor(ms / 60000); const h = Math.floor(m / 60); const d = Math.floor(h / 24);
  if (m < 1) return "только что"; if (m < 60) return `${m} мин назад`;
  if (h < 24) return `${h} ч назад`; if (d < 30) return `${d} дн назад`;
  return new Date(s).toLocaleDateString("ru");
}
function fmtDate(s: string): string {
  return new Date(s).toLocaleString("ru", { day: "2-digit", month: "short", hour: "2-digit", minute: "2-digit", second: "2-digit" });
}

export function Maintenance() {
  const [tab, setTab] = useState<Tab>("overview");
  const [msg, setMsg] = useState(""); const [err, setErr] = useState("");
  const notify = useCallback((m: string, isErr = false) => {
    if (isErr) { setErr(m); setMsg(""); } else { setMsg(m); setErr(""); }
  }, []);

  return (
    <div>
      <div className="section-head">
        <div>
          <h1 className="page-title">Центр обслуживания</h1>
          <p className="page-sub">Бэкапы, база данных, хранилище, кэш, очереди, логи и аудит — единый production-grade пульт эксплуатации. Все метрики и действия работают на реальных данных.</p>
        </div>
      </div>

      {(msg || err) && (
        <p className={err ? "note-err" : "note-ok"}>
          <span className="ms sm">{err ? "error" : "check_circle"}</span>{err || msg}
          <button className="btn ghost sm" onClick={() => { setMsg(""); setErr(""); }} aria-label="Скрыть" style={{ marginLeft: "auto" }}>×</button>
        </p>
      )}

      <div className="panel" style={{ padding: "var(--sp-2) var(--sp-3)", position: "sticky", top: 0, zIndex: 6, marginBottom: "var(--sp-4)" }}>
        <div className="seg-tabs" style={{ marginBottom: 0, flexWrap: "wrap" }}>
          {TABS.map((t) => (
            <button key={t.id} className={tab === t.id ? "on" : ""} onClick={() => setTab(t.id)}>
              <span className="ms sm" style={{ verticalAlign: "-3px", marginRight: 4 }}>{t.icon}</span>{t.label}
            </button>
          ))}
        </div>
      </div>

      {tab === "overview" && <OverviewTab notify={notify} go={setTab} />}
      {tab === "database" && <DatabaseTab notify={notify} />}
      {tab === "storage" && <StorageTab notify={notify} />}
      {tab === "cache" && <CacheTab notify={notify} />}
      {tab === "queue" && <QueueTab notify={notify} />}
      {tab === "logs" && <LogsTab notify={notify} />}
      {tab === "audit" && <AuditTab notify={notify} />}
    </div>
  );
}

type Notify = (m: string, isErr?: boolean) => void;

// ================= Overview =================
function OverviewTab({ notify, go }: { notify: Notify; go: (t: Tab) => void }) {
  const [ov, setOv] = useState<MaintOverview | null>(null);
  const [busy, setBusy] = useState("");
  const [auto, setAuto] = useState(false);

  const load = useCallback(async () => {
    try { setOv(await maintenanceApi.overview()); }
    catch (e) { notify("Не удалось загрузить обзор: " + msgOf(e), true); }
  }, [notify]);
  useEffect(() => { load(); }, [load]);  // FIX: AUDIT13-L19 - removed a duplicate mount-load effect (double-fetched on first render)
  useEffect(() => { if (!auto) return; const id = setInterval(load, 10000); return () => clearInterval(id); }, [auto, load]);

  async function backup() {
    setBusy("backup");
    try { await maintenanceApi.downloadBackup(); notify("Резервная копия скачана"); load(); }
    catch (e) {
      const m = msgOf(e);
      notify(m === "postgres_use_pgdump" ? "На Postgres используйте pg_dump на сервере"
        : m === "forbidden" ? "Доступно только суперадмину" : "Не удалось создать бэкап: " + m, true);
    } finally { setBusy(""); }
  }
  async function optimize() {
    if (!confirm("Запустить VACUUM (дефрагментация + сжатие базы)? Может занять время на большой БД.")) return;
    setBusy("opt");
    try { const r = await maintenanceApi.dbOp("vacuum"); notify(`VACUUM выполнен за ${r.duration_ms} мс · освобождено ${fmtBytes(r.reclaimed_bytes)}`); load(); }
    catch (e) { notify("VACUUM не выполнен: " + msgOf(e), true); } finally { setBusy(""); }
  }
  async function flush() {
    if (!confirm("Сбросить перестраиваемые кэши приложения (cache:* / dashboard)? Рабочие данные не затрагиваются.")) return;
    setBusy("flush");
    try { const r = await maintenanceApi.cacheFlush(); notify(`Кэш сброшен · удалено ключей: ${r.deleted}`); load(); }
    catch (e) { notify("Не удалось сбросить кэш: " + msgOf(e), true); } finally { setBusy(""); }
  }

  if (!ov) return <SkeletonGrid />;
  const jobs = ov.counts.jobs_by_status || {};
  // FIX: UI-7 - guard the disk percent so a missing value never renders as
  // "undefined%" in the metric card (other metrics already fall back to 0/"—").
  const diskPct = ov.disk.percent ?? 0;
  const diskTone = diskPct >= 90 ? "danger" : diskPct >= 75 ? "warn" : "ok";
  const frag = ov.db.fragmentation_pct ?? 0;

  return (
    <div className="page-stack">
      <div className="metrics">
        <Metric icon="group" label="Пользователи" value={fmtInt(ov.counts.users)} />
        <Metric icon="bolt" label="Задачи всего" value={fmtInt(ov.counts.jobs_total)} />
        <Metric icon="database" label="Размер БД" value={fmtBytes(ov.db.size_bytes)} tone="purple" />
        <Metric icon="hard_drive" label="Диск занят" value={`${diskPct}%`} tone={diskTone === "danger" ? "danger" : undefined} small />
        <Metric icon="memory" label="Память Redis" value={ov.redis.ok ? fmtBytes(ov.redis.used_memory_bytes) : "н/д"} small />
        <Metric icon="payments" label="Транзакции" value={fmtInt(ov.counts.transactions)} small />
        <Metric icon="receipt_long" label="Записей аудита" value={fmtInt(ov.counts.audit_entries)} small />
        <Metric icon="schedule" label="Аптайм процесса" value={fmtUptime(ov.uptime_seconds)} small />
        <Metric icon="backup" label="Последний бэкап" value={ago(ov.backup.last_backup_at)} small />
      </div>

      <div className="form-row" style={{ justifyContent: "flex-end", margin: 0, gap: "var(--sp-2)" }}>
        <Switch checked={auto} onChange={setAuto} label="Авто-обновление (10с)" />
        <button className="btn ghost sm" onClick={load}><span className="ms sm">refresh</span> Обновить</button>
      </div>

      {/* System health */}
      <div className="prov-grid">
        <HealthCard title="База данных" icon="database" ok dim={ov.engine}>
          <KV k="Движок" v={ov.engine} />
          <KV k="Размер файла" v={fmtBytes(ov.db.size_bytes)} />
          {ov.db.page_count != null && <KV k="Страниц" v={fmtInt(ov.db.page_count)} />}
          <Bar label="Фрагментация" pct={frag} tone={frag >= 25 ? "danger" : frag >= 10 ? "warn" : "ok"} right={`${frag}%`} />
        </HealthCard>

        <HealthCard title="Redis / кэш" icon="bolt" ok={ov.redis.ok} dim={ov.redis.ok ? ov.redis.version || "online" : "недоступен"}>
          {ov.redis.ok ? <>
            <KV k="Память" v={fmtBytes(ov.redis.used_memory_bytes)} />
            <KV k="Ключей" v={fmtInt(ov.redis.keys)} />
            <KV k="Hit-rate" v={ov.redis.hit_rate_pct != null ? `${ov.redis.hit_rate_pct}%` : "—"} />
            <KV k="Аптайм" v={fmtUptime(ov.redis.uptime_seconds)} />
          </> : <p className="cfg-hint">INFO недоступен на этом Redis (или соединение потеряно). Кэш-операции работают по мере доступности.</p>}
        </HealthCard>

        <HealthCard title="Диск" icon="hard_drive" ok={diskTone !== "danger"} dim={ov.disk.path}>
          <Bar label="Использовано" pct={diskPct} tone={diskTone} right={`${fmtBytes(ov.disk.used_bytes)} / ${fmtBytes(ov.disk.total_bytes)}`} />
          <KV k="Свободно" v={fmtBytes(ov.disk.free_bytes)} />
          <KV k="Хранилище медиа" v={ov.storage_backend === "s3" ? "S3 / MinIO" : "Локальный диск"} />
        </HealthCard>

        <HealthCard title="Очередь задач" icon="queue" ok dim={`${fmtInt(ov.counts.jobs_total)} всего`}>
          <KV k="В ожидании" v={fmtInt((jobs.pending || 0) + (jobs.processing || 0))} />
          <KV k="Завершено" v={fmtInt(jobs.complete || 0)} />
          <KV k="Ошибки" v={fmtInt(jobs.failed || 0)} />
          <button className="btn ghost sm" style={{ marginTop: 6 }} onClick={() => go("queue")}><span className="ms sm">open_in_new</span> К очереди</button>
        </HealthCard>
      </div>

      {/* Backup + quick mass actions */}
      <div className="prov-grid">
        <div className="panel">
          <div className="panel-title sm"><span className="ms sm">backup</span> Резервное копирование</div>
          <p className="cfg-hint">{ov.backup.note}</p>
          <KV k="Последний бэкап" v={ov.backup.last_backup_at ? `${fmtDate(ov.backup.last_backup_at)} (${ago(ov.backup.last_backup_at)})` : "не выполнялся"} />
          <div className="form-row" style={{ gap: "var(--sp-2)", marginTop: "var(--sp-3)" }}>
            <button className="btn" disabled={!ov.backup.supported || busy === "backup"} onClick={backup}>
              <span className="ms sm">download</span> {busy === "backup" ? "Готовим…" : "Скачать бэкап сейчас"}
            </button>
          </div>
          <GatedNote>История бэкапов, расписание (hourly/daily/cron), retention-политика, шифрование и автоверификация требуют таблицы <code className="code-key">backups</code> и воркера-планировщика. Сейчас доступен консистентный снимок SQLite по запросу (на Postgres — <code className="code-key">pg_dump</code>).</GatedNote>
        </div>

        <div className="panel">
          <div className="panel-title sm"><span className="ms sm">bolt</span> Массовые действия</div>
          <p className="cfg-hint">Безопасные обслуживающие операции. Дефрагментация и сброс кэша доступны суперадмину и фиксируются в аудите.</p>
          <div className="form-row" style={{ gap: "var(--sp-2)", flexWrap: "wrap", marginTop: "var(--sp-3)" }}>
            <button className="btn ghost" disabled={!!busy} onClick={backup}><span className="ms sm">backup</span> Бэкап</button>
            <button className="btn ghost" disabled={!isSuper() || !!busy} onClick={optimize} title={isSuper() ? "" : "Только суперадмин"}><span className="ms sm">cleaning_services</span> Оптимизировать БД</button>
            <button className="btn ghost" disabled={!isSuper() || !!busy} onClick={flush} title={isSuper() ? "" : "Только суперадмин"}><span className="ms sm">mop</span> Сбросить кэш</button>
            <button className="btn ghost" onClick={() => go("database")}><span className="ms sm">database</span> Обслуживание БД</button>
            <button className="btn ghost" onClick={() => go("queue")}><span className="ms sm">queue</span> Очередь</button>
          </div>
        </div>
      </div>

      <div className="prov-grid">
        <GatedCard icon="show_chart" title="Графики мониторинга" text="Временные ряды CPU/RAM/latency/RPS требуют сбора метрик (Prometheus/timeseries). Сейчас доступны live-снимки выше; исторические графики — на стороне Grafana/Datadog." />
        <GatedCard icon="notifications" title="Системные уведомления" text="Алерты «диск почти полон / провайдер offline / БД заблокирована / переполнение очереди» требуют event-шины и порогов. Пороговые индикаторы (диск/фрагментация) уже подсвечиваются в карточках выше." />
        <GatedCard icon="engineering" title="Режим обслуживания" text="Включение Maintenance Mode (whitelist админов, кастомное сообщение, ETA, redirect) требует middleware в боте/Mini App. Кандидат на отдельный флаг + проверку на входе." />
      </div>
    </div>
  );
}

// ================= Database =================
function DatabaseTab({ notify }: { notify: Notify }) {
  const [db, setDb] = useState<MaintDatabase | null>(null);
  const [q, setQ] = useState("");
  const [busy, setBusy] = useState("");
  const [last, setLast] = useState<MaintDbOpResult | null>(null);

  const load = useCallback(async () => {
    try { setDb(await maintenanceApi.database()); }
    catch (e) { notify("Не удалось загрузить статистику БД: " + msgOf(e), true); }
  }, [notify]);
  useEffect(() => { load(); }, [load]);

  async function op(name: string, confirmText: string) {
    if (!confirm(confirmText)) return;
    setBusy(name); setLast(null);
    try {
      const r = await maintenanceApi.dbOp(name);
      setLast(r);
      notify(`${name.toUpperCase()} выполнен за ${r.duration_ms} мс${r.reclaimed_bytes ? ` · освобождено ${fmtBytes(r.reclaimed_bytes)}` : ""}`);
      load();
    } catch (e) { notify(`${name} не выполнен: ` + msgOf(e), true); } finally { setBusy(""); }
  }

  const tables = useMemo(() => {
    const list = db?.tables || [];
    const s = q.trim().toLowerCase();
    return s ? list.filter((t) => t.name.toLowerCase().includes(s)) : list;
  }, [db, q]);

  if (!db) return <SkeletonGrid />;
  const sup = isSuper();
  const page = db.page;
  const OPS: { id: string; label: string; icon: string; confirm: string }[] = [
    { id: "vacuum", label: "VACUUM", icon: "cleaning_services", confirm: "Запустить VACUUM (дефрагментация + сжатие)? Может занять время." },
    { id: "analyze", label: "ANALYZE", icon: "analytics", confirm: "Пересобрать статистику планировщика (ANALYZE)?" },
    { id: "reindex", label: "REINDEX", icon: "reorder", confirm: "Перестроить все индексы (REINDEX)?" },
    { id: "optimize", label: "OPTIMIZE", icon: "tune", confirm: "Выполнить PRAGMA optimize?" },
    { id: "integrity_check", label: "Проверка целостности", icon: "verified", confirm: "Запустить проверку целостности БД?" },
  ];

  return (
    <div className="page-stack">
      <div className="metrics">
        <Metric icon="table_rows" label="Таблиц" value={fmtInt(db.tables.length)} />
        <Metric icon="data_usage" label="Всего записей" value={fmtInt(db.total_rows)} tone="purple" />
        {page && <Metric icon="database" label="Размер БД" value={fmtBytes(page.size_bytes)} small />}
        {page && <Metric icon="grid_on" label="Страниц" value={fmtInt(page.page_count)} small />}
        {page && <Metric icon="broken_image" label="Свободно (freelist)" value={fmtBytes(page.free_bytes)} small />}
        {page && <Metric icon="healing" label="Фрагментация" value={`${page.fragmentation_pct}%`} tone={page.fragmentation_pct >= 25 ? "danger" : undefined} small />}
      </div>

      <div className="panel">
        <div className="panel-title sm"><span className="ms sm">build_circle</span> Обслуживание базы данных {db.engine !== "sqlite" && <span className="pill warn" style={{ marginLeft: 8 }}>{db.engine}</span>}</div>
        <p className="cfg-hint">{sup ? "Операции выполняются на живой БД и фиксируются в аудите." : "Доступно только суперадмину."}{db.engine !== "sqlite" && " На Postgres операции выполняются на стороне сервера (pg)."}</p>
        <div className="form-row" style={{ gap: "var(--sp-2)", flexWrap: "wrap", marginTop: "var(--sp-3)" }}>
          {OPS.map((o) => (
            <button key={o.id} className="btn ghost" disabled={!sup || db.engine !== "sqlite" || !!busy} onClick={() => op(o.id, o.confirm)}>
              <span className="ms sm">{o.icon}</span> {busy === o.id ? "…" : o.label}
            </button>
          ))}
        </div>
        {last && (
          <div className="note-ok" style={{ marginTop: "var(--sp-3)" }}>
            <span className="ms sm">task_alt</span>
            <span><b>{last.op}</b> · {last.duration_ms} мс · результат: <code className="code-key">{last.result}</code>{last.reclaimed_bytes ? ` · освобождено ${fmtBytes(last.reclaimed_bytes)}` : ""}</span>
          </div>
        )}
        <GatedNote>История операций VACUUM/ANALYZE и журнал миграций (последний применённый revision) требуют отдельного хранения. Текущая фрагментация и размеры считаются вживую через PRAGMA.</GatedNote>
      </div>

      <div className="panel">
        <div className="section-head" style={{ margin: 0, marginBottom: "var(--sp-3)" }}>
          <div className="panel-title sm" style={{ margin: 0 }}><span className="ms sm">table_chart</span> Таблицы ({tables.length})</div>
          {/* FIX: AUDIT12-M13/M14 - aria-label + maxLength 255 on table search. */}
          <input style={{ width: 220 }} placeholder="Поиск таблицы…" value={q} onChange={(e) => setQ(e.target.value)} maxLength={255} aria-label="Поиск таблицы" />
        </div>
        <div className="table-wrap sticky" tabIndex={0} style={{ border: "none" }}>
          <table className="tbl">
            <thead><tr><th>Таблица</th><th style={{ textAlign: "right" }}>Записей</th><th style={{ textAlign: "right" }}>Индексов</th><th style={{ width: "40%" }}>Доля</th></tr></thead>
            <tbody>
              {tables.map((t) => {
                const pct = db.total_rows > 0 && t.rows > 0 ? Math.round(t.rows / db.total_rows * 100) : 0;
                return (
                  <tr key={t.name}>
                    <td><span className="code-key" style={{ fontSize: 12.5 }}>{t.name}</span></td>
                    <td style={{ textAlign: "right" }}>{t.rows < 0 ? <span className="pill danger">н/д</span> : fmtInt(t.rows)}</td>
                    <td style={{ textAlign: "right" }} className="muted">{t.indexes}</td>
                    <td>
                      <div className="form-row" style={{ gap: 8, margin: 0, alignItems: "center" }}>
                        <div style={{ flex: 1, height: 6, borderRadius: 3, background: "var(--panel-2)", overflow: "hidden" }}>
                          <div style={{ width: `${pct}%`, height: "100%", background: "var(--accent)" }} />
                        </div>
                        <span className="muted" style={{ fontSize: 11, width: 34 }}>{pct}%</span>
                      </div>
                    </td>
                  </tr>
                );
              })}
            </tbody>
          </table>
        </div>
      </div>
    </div>
  );
}

// ================= Storage =================
function StorageTab({ notify }: { notify: Notify }) {
  const [st, setSt] = useState<MaintStorage | null>(null);
  const load = useCallback(async () => {
    try { setSt(await maintenanceApi.storage()); }
    catch (e) { notify("Не удалось загрузить хранилище: " + msgOf(e), true); }
  }, [notify]);
  useEffect(() => { load(); }, [load]);

  if (!st) return <SkeletonGrid />;
  const max = Math.max(1, ...st.categories.map((c) => c.bytes));

  return (
    <div className="page-stack">
      <div className="metrics">
        <Metric icon="folder" label="Бэкенд" value={st.backend === "s3" ? "S3/MinIO" : "Локальный"} />
        <Metric icon="data_usage" label="Объём" value={fmtBytes(st.total_bytes)} tone="purple" />
        <Metric icon="description" label="Файлов" value={fmtInt(st.total_files)} small />
        <Metric icon="category" label="Категорий" value={fmtInt(st.categories.length)} small />
      </div>

      {st.backend === "s3" ? (
        <div className="panel"><EmptyState icon="cloud" title="Хранилище в объектном сторе"
          desc={`Файлы в бакете «${st.bucket}». Размеры по категориям считаются на стороне S3/MinIO (lifecycle-политики, метрики бакета), а не через API.`} /></div>
      ) : st.categories.length === 0 ? (
        <div className="panel"><EmptyState icon="folder_open" title="Медиа-файлов нет"
          desc={st.exists ? "Каталог media/ пуст — загрузок ещё не было." : "Каталог media/ не создан (локальные загрузки ещё не выполнялись)."} /></div>
      ) : (
        <div className="panel">
          <div className="panel-title sm"><span className="ms sm">folder</span> Категории медиа · <span className="code-key">{st.path}</span></div>
          <div className="page-stack" style={{ gap: "var(--sp-3)", marginTop: "var(--sp-3)" }}>
            {st.categories.map((c) => (
              <div key={c.name}>
                <div className="form-row" style={{ justifyContent: "space-between", margin: "0 0 4px" }}>
                  <span><span className="ms sm" style={{ verticalAlign: "-3px", marginRight: 4 }}>{iconForCat(c.name)}</span><b>{c.name}</b> <span className="muted" style={{ fontSize: 11 }}>· {fmtInt(c.files)} файл.</span></span>
                  <span className="muted">{fmtBytes(c.bytes)}</span>
                </div>
                <div style={{ height: 8, borderRadius: 4, background: "var(--panel-2)", overflow: "hidden" }}>
                  <div style={{ width: `${Math.round(c.bytes / max * 100)}%`, height: "100%", background: "var(--accent)" }} />
                </div>
              </div>
            ))}
          </div>
        </div>
      )}

      <GatedCard icon="auto_delete" title="Действия с файлами"
        text="Очистка cache/temp, удаление старых изображений/видео, voice-cache и orphan-файлов (медиа без ссылок из generation_jobs) требуют отдельных эндпоинтов с безопасной выборкой и подтверждением. Сейчас раздел только показывает фактические объёмы по категориям." />
    </div>
  );
}

// ================= Cache =================
function CacheTab({ notify }: { notify: Notify }) {
  const [c, setC] = useState<MaintCache | null>(null);
  const [busy, setBusy] = useState(false);
  const load = useCallback(async () => {
    try { setC(await maintenanceApi.cache()); }
    catch (e) { notify("Не удалось загрузить кэш: " + msgOf(e), true); }
  }, [notify]);
  useEffect(() => { load(); }, [load]);

  async function flush() {
    if (!confirm("Сбросить перестраиваемые кэши приложения (cache:* / admin:dashboard:*)? FSM/контекст/лимиты не трогаются.")) return;
    setBusy(true);
    try { const r = await maintenanceApi.cacheFlush(); notify(`Кэш сброшен · удалено ключей: ${r.deleted}`); load(); }
    catch (e) { notify("Не удалось сбросить кэш: " + msgOf(e), true); } finally { setBusy(false); }
  }

  if (!c) return <SkeletonGrid />;
  const r = c.redis;

  return (
    <div className="page-stack">
      <div className="metrics">
        <Metric icon="bolt" label="Redis" value={r.ok ? "online" : "н/д"} tone={r.ok ? undefined : "danger"} />
        <Metric icon="memory" label="Память" value={r.ok ? fmtBytes(r.used_memory_bytes) : "—"} tone="purple" />
        <Metric icon="key" label="Всего ключей" value={r.ok ? fmtInt(r.keys) : "—"} small />
        <Metric icon="recycling" label="App-кэш ключей" value={c.app_cache_keys < 0 ? "н/д" : fmtInt(c.app_cache_keys)} small />
        <Metric icon="percent" label="Hit-rate" value={r.hit_rate_pct != null ? `${r.hit_rate_pct}%` : "—"} small />
        <Metric icon="schedule" label="Аптайм" value={fmtUptime(r.uptime_seconds)} small />
      </div>

      <div className="prov-grid">
        <HealthCard title="Redis" icon="bolt" ok={r.ok} dim={r.ok ? r.version || "online" : "недоступен"}>
          {r.ok ? <>
            <KV k="Память" v={fmtBytes(r.used_memory_bytes)} />
            <KV k="Попаданий" v={fmtInt(r.hits)} />
            <KV k="Промахов" v={fmtInt(r.misses)} />
            <KV k="Hit-rate" v={r.hit_rate_pct != null ? `${r.hit_rate_pct}%` : "—"} />
            <KV k="Версия" v={r.version || "—"} />
          </> : <p className="cfg-hint">INFO недоступен на этом Redis-сервере. Сброс app-кэша всё равно работает (по префиксам ключей).</p>}
        </HealthCard>

        <div className="panel">
          <div className="panel-title sm"><span className="ms sm">mop</span> Управление кэшем</div>
          <p className="cfg-hint">Сбрасываются только перестраиваемые кэши приложения по префиксам: {c.prefixes.map((p) => <code key={p} className="code-key" style={{ marginRight: 6 }}>{p}*</code>)}. Данные восстановятся из БД при следующем запросе.</p>
          <div className="form-row" style={{ marginTop: "var(--sp-3)" }}>
            <button className="btn" disabled={!isSuper() || busy} onClick={flush} title={isSuper() ? "" : "Только суперадмин"}>
              <span className="ms sm">delete_sweep</span> {busy ? "Сбрасываем…" : "Сбросить app-кэш"}
            </button>
            <button className="btn ghost" onClick={load}><span className="ms sm">refresh</span> Обновить</button>
          </div>
          <GatedNote>Точечная инвалидация по доменам (изображения / модели / voice / documents), прогрев (warmup) и CDN/Image-cache требуют именованных кэш-пространств. Сейчас кэши приложения живут под общими префиксами выше.</GatedNote>
        </div>
      </div>
    </div>
  );
}

// ================= Queue =================
function QueueTab({ notify }: { notify: Notify }) {
  const [q, setQ] = useState<MaintQueue | null>(null);
  const [auto, setAuto] = useState(false);
  const [busy, setBusy] = useState("");
  const load = useCallback(async () => {
    try { setQ(await maintenanceApi.queue()); }
    catch (e) { notify("Не удалось загрузить очередь: " + msgOf(e), true); }
  }, [notify]);
  useEffect(() => { load(); }, [load]);  // FIX: AUDIT13-L19 - removed a duplicate mount-load effect (double-fetched on first render)
  useEffect(() => { if (!auto) return; const id = setInterval(load, 8000); return () => clearInterval(id); }, [auto, load]);

  async function retry(id: string) {
    setBusy(id);
    try { const r = await maintenanceApi.jobRetry(id); notify(`Задача перезапущена${r.enqueued ? " и поставлена в очередь" : ""}`); load(); }
    catch (e) { notify("Retry не выполнен: " + msgOf(e), true); } finally { setBusy(""); }
  }
  async function cancel(id: string) {
    if (!confirm("Отменить задачу и вернуть списание пользователю?")) return;
    setBusy(id);
    try { const r = await maintenanceApi.jobCancel(id); notify(`Задача отменена${r.refunded ? " · средства возвращены" : ""}`); load(); }
    catch (e) { notify("Cancel не выполнен: " + msgOf(e), true); } finally { setBusy(""); }
  }

  if (!q) return <SkeletonGrid />;
  const counts = q.counts || {};
  const statuses = ["pending", "processing", "complete", "failed"];

  return (
    <div className="page-stack">
      <div className="metrics">
        <Metric icon="hourglass_top" label="В ожидании" value={fmtInt(counts.pending)} />
        <Metric icon="autorenew" label="Выполняется" value={fmtInt(counts.processing)} tone="purple" />
        <Metric icon="check_circle" label="Завершено" value={fmtInt(counts.complete)} small />
        <Metric icon="error" label="Ошибки" value={fmtInt(counts.failed)} tone={counts.failed ? "danger" : undefined} small />
        <Metric icon="warning" label="Зависшие" value={fmtInt(q.stuck_count)} tone={q.stuck_count ? "danger" : undefined} small />
        <Metric icon="timer" label="Старейшая в ожидании" value={q.oldest_pending_age_seconds ? fmtUptime(Math.round(q.oldest_pending_age_seconds)) : "—"} small />
      </div>

      <div className="form-row" style={{ justifyContent: "space-between", margin: 0 }}>
        <div className="chip-row">
          {statuses.map((s) => <span key={s} className="chip"><b>{s}</b><span className="muted">{fmtInt(counts[s])}</span></span>)}
          {Object.keys(counts).filter((s) => !statuses.includes(s)).map((s) => <span key={s} className="chip"><b>{s}</b><span className="muted">{fmtInt(counts[s])}</span></span>)}
        </div>
        <div className="form-row" style={{ gap: "var(--sp-2)", margin: 0 }}>
          <Switch checked={auto} onChange={setAuto} label="Авто (8с)" />
          <button className="btn ghost sm" onClick={load}><span className="ms sm">refresh</span> Обновить</button>
        </div>
      </div>

      <div className="panel">
        <div className="panel-title sm"><span className="ms sm">warning</span> Зависшие задачи (старше {Math.round(q.stuck_threshold_seconds / 60)} мин)</div>
        {q.stuck_jobs.length === 0 ? (
          <EmptyState icon="check_circle" title="Зависших задач нет" desc="Все активные задачи в пределах порога. Воркеры обрабатывают очередь штатно." />
        ) : (
          <div className="table-wrap sticky" tabIndex={0} style={{ border: "none", marginTop: "var(--sp-2)" }}>
            <table className="tbl">
              <thead><tr><th>Job ID</th><th>Сервис</th><th>User</th><th>Статус</th><th>Возраст</th><th style={{ width: 150 }}></th></tr></thead>
              <tbody>
                {q.stuck_jobs.map((j) => (
                  <tr key={j.job_id}>
                    <td><span className="code-key" style={{ fontSize: 11 }}>{j.job_id.slice(0, 8)}…</span></td>
                    <td>{j.service}</td>
                    <td className="muted">{j.user_id}</td>
                    <td><span className={"pill " + (j.status === "failed" ? "danger" : "warn")}>{j.status}</span></td>
                    <td className="muted">{ago(j.created_at)}</td>
                    <td>
                      <div className="form-row" style={{ gap: 4, margin: 0 }}>
                        <button className="btn ghost sm" disabled={busy === j.job_id} onClick={() => retry(j.job_id)}><span className="ms sm">restart_alt</span> Retry</button>
                        <button className="btn ghost sm" disabled={busy === j.job_id} onClick={() => cancel(j.job_id)}><span className="ms sm">cancel</span> Cancel</button>
                      </div>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </div>

      <GatedCard icon="schedule_send" title="Планировщик задач (cron)"
        text="Список периодических задач (название, cron, последний/следующий запуск, enable/disable, run-now) требует чтения beat-расписания. Управление воркерами/перезапуск пула — через инфраструктуру (supervisor/systemd/docker). Здесь доступны live-операции над зависшими задачами." />
    </div>
  );
}

// ================= Logs =================
const SEVERITIES = ["CRITICAL", "ERROR", "WARNING", "INFO", "DEBUG", "SUCCESS"] as const;
type Severity = (typeof SEVERITIES)[number];
function severityOf(line: string): Severity | null {
  const m = line.match(/\b(CRITICAL|ERROR|WARN(?:ING)?|INFO|DEBUG|SUCCESS|TRACE)\b/i);
  if (!m) return null;
  const s = m[1].toUpperCase();
  if (s === "WARN") return "WARNING";
  if (s === "TRACE") return "DEBUG";
  return s as Severity;
}
const SEV_CLASS: Record<Severity, string> = {
  CRITICAL: "danger", ERROR: "danger", WARNING: "warn", INFO: "muted", DEBUG: "muted", SUCCESS: "ok",
};
const RENDER_CAP = 1500; // windowing — render at most the newest N lines

function LogsTab({ notify }: { notify: Notify }) {
  const [lines, setLines] = useState<string[]>([]);
  const [path, setPath] = useState("");
  const [limit, setLimit] = useState(500);
  const [sev, setSev] = useState("all");
  const [q, setQ] = useState("");
  const [auto, setAuto] = useState(false);
  const [loading, setLoading] = useState(false);
  const [loaded, setLoaded] = useState(false);
  const boxRef = useRef<HTMLPreElement>(null);

  const load = useCallback(async () => {
    setLoading(true);
    try {
      const r = await maintenanceApi.logs(limit);
      setLines(r.lines); setPath(r.path); setLoaded(true);
      if (r.count === 0) notify("Лог пуст или файл не найден");
    } catch (e) { notify("Не удалось загрузить логи: " + msgOf(e), true); }
    finally { setLoading(false); }
  }, [limit, notify]);
  useEffect(() => { if (!auto) return; const id = setInterval(load, 5000); return () => clearInterval(id); }, [auto, load]);
  useEffect(() => { load(); }, [load]);  // FIX: AUDIT-85
  useEffect(() => { if (auto && boxRef.current) boxRef.current.scrollTop = boxRef.current.scrollHeight; }, [lines, auto]);

  const parsed = useMemo(() => lines.map((l) => ({ text: l, sev: severityOf(l) })), [lines]);
  const counts = useMemo(() => {
    const c: Record<string, number> = {};
    for (const p of parsed) if (p.sev) c[p.sev] = (c[p.sev] || 0) + 1;
    return c;
  }, [parsed]);
  const filtered = useMemo(() => {
    const s = q.trim().toLowerCase();
    return parsed.filter((p) => {
      if (sev !== "all" && p.sev !== sev) return false;
      if (s && !p.text.toLowerCase().includes(s)) return false;
      return true;
    });
  }, [parsed, sev, q]);
  const shown = filtered.length > RENDER_CAP ? filtered.slice(filtered.length - RENDER_CAP) : filtered;

  function download() {
    const blob = new Blob([lines.join("\n")], { type: "text/plain" });
    const a = document.createElement("a"); a.href = URL.createObjectURL(blob);
    a.download = `app-log-${new Date().toISOString().slice(0, 19).replace(/[:T]/g, "-")}.log`; a.click();
    URL.revokeObjectURL(a.href);  // FIX: AUDIT-92 - immediate revoke;  // FIX: F67 - release the blob URL after the download starts
  }

  return (
    <div className="page-stack">
      <div className="panel" style={{ padding: "var(--sp-3)", position: "sticky", top: 56, zIndex: 5 }}>
        <div className="section-head" style={{ margin: 0 }}>
          <div className="form-row" style={{ gap: "var(--sp-2)", flexWrap: "wrap", margin: 0 }}>
            {/* FIX: AUDIT12-M13/M14 - aria-label on SQL log limit input. */}
            <input type="number" min={1} max={5000} value={limit} onChange={(e) => setLimit(Math.max(1, Math.min(5000, Number(e.target.value) || 200)))} style={{ width: 100 }} title="Строк подгружать" aria-label="Лимит строк" />
            <Select width={170} ariaLabel="Severity" value={sev} onChange={setSev} options={[{ value: "all", label: "Все уровни" }, ...SEVERITIES.map((s) => ({ value: s, label: s }))]} />
            {/* FIX: AUDIT12-M13/M14 - aria-label + maxLength 255 on SQL log search. */}
            <input style={{ width: 240 }} placeholder="Поиск по тексту / модулю / ID…" value={q} onChange={(e) => setQ(e.target.value)} maxLength={255} aria-label="Поиск в логе" />
          </div>
          <div className="form-row" style={{ gap: "var(--sp-2)", margin: 0 }}>
            <Switch checked={auto} onChange={setAuto} label="Tail (5с)" />
            <button className="btn ghost sm" disabled={loading} onClick={load}><span className="ms sm">{loading ? "hourglass_top" : "refresh"}</span> Загрузить</button>
            <button className="btn ghost sm" title="Скачать лог" aria-label="Скачать лог" disabled={!lines.length} onClick={download}><span className="ms sm">download</span></button>
          </div>
        </div>
        {loaded && (
          <div className="chip-row" style={{ marginTop: "var(--sp-3)" }}>
            <span className="chip"><b>{fmtInt(filtered.length)}</b><span className="muted">показано</span></span>
            {SEVERITIES.filter((s) => counts[s]).map((s) => (
              <button key={s} className="chip" style={{ cursor: "pointer", borderColor: sev === s ? "var(--accent)" : undefined }} onClick={() => setSev(sev === s ? "all" : s)}>
                <span className={"pill " + SEV_CLASS[s]} style={{ fontSize: 10 }}>{s}</span><span className="muted">{counts[s]}</span>
              </button>
            ))}
            {path && <span className="muted" style={{ fontSize: 11, marginLeft: "auto" }}>{path}</span>}
          </div>
        )}
      </div>

      {!loaded ? (
        <div className="panel"><EmptyState icon="terminal" title="Логи не загружены"
          desc="Нажмите «Загрузить», чтобы получить хвост лог-файла приложения. Путь фиксирован конфигом (защита от path traversal)." /></div>
      ) : filtered.length === 0 ? (
        <div className="panel"><EmptyState icon="search_off" title="Ничего не найдено" desc="Измените уровень severity или строку поиска." /></div>
      ) : (
        <div className="panel" style={{ padding: 0, overflow: "hidden" }}>
          {filtered.length > RENDER_CAP && <p className="cfg-hint" style={{ padding: "8px 12px", margin: 0 }}>Показаны последние {RENDER_CAP} из {fmtInt(filtered.length)} строк (windowing). Уточните фильтр для остальных.</p>}
          <pre ref={boxRef} className="log-view" style={{ maxHeight: "62vh", margin: 0, border: "none", borderRadius: 0 }}>
            {shown.map((p, i) => (
              <div key={i} style={{ display: "flex", gap: 8 }}>
                {p.sev && <span className={"pill " + SEV_CLASS[p.sev]} style={{ fontSize: 9, flex: "0 0 auto", height: 16, alignSelf: "center" }}>{p.sev[0]}</span>}
                <span style={p.sev === "ERROR" || p.sev === "CRITICAL" ? { color: "var(--danger)" } : undefined}>{p.text}</span>
              </div>
            ))}
          </pre>
        </div>
      )}

      <GatedCard icon="bug_report" title="Error Center (группировка)"
        text="Группировка по exception со stack-trace, счётчиком, числом затронутых пользователей, resolve/ignore/archive требует структурированного хранения ошибок (Sentry уже подключаем через SENTRY_DSN, либо отдельная таблица). Здесь доступен быстрый фильтр «ERROR/CRITICAL» по живому логу." />
    </div>
  );
}

// ================= Audit =================
const AUDIT_PRESETS = [
  { value: "", label: "Все действия" },
  { value: "maintenance", label: "Обслуживание" },
  { value: "backup", label: "Бэкапы" },
  { value: "job", label: "Задачи (retry/cancel)" },
  { value: "provider", label: "Провайдеры" },
  { value: "pricing", label: "Цены" },
  { value: "flag", label: "Фич-флаги" },
];

function AuditTab({ notify }: { notify: Notify }) {
  const [rows, setRows] = useState<MaintAuditRow[] | null>(null);
  const [action, setAction] = useState("maintenance");
  const [since, setSince] = useState("");

  const load = useCallback(async () => {
    setRows(null);
    try { setRows(await maintenanceApi.audit({ action: action || undefined, since: since || undefined, limit: 200 })); }
    catch (e) { notify("Не удалось загрузить аудит: " + msgOf(e), true); setRows([]); }
  }, [action, since, notify]);
  useEffect(() => { load(); }, [load]);

  return (
    <div className="page-stack">
      <div className="panel" style={{ padding: "var(--sp-3)" }}>
        <div className="form-row" style={{ gap: "var(--sp-2)", flexWrap: "wrap", margin: 0 }}>
          <Select width={220} ariaLabel="Действие" value={action} onChange={setAction} options={AUDIT_PRESETS} />
          <DateField value={since} onChange={setSince} style={{ width: 170 }} title="С даты" />
          <button className="btn ghost sm" onClick={load}><span className="ms sm">refresh</span> Обновить</button>
          {since && <button className="btn ghost sm" onClick={() => setSince("")}>Сбросить дату</button>}
        </div>
      </div>

      <div className="panel">
        {rows === null ? <SkeletonGrid rows={5} />
          : rows.length === 0 ? <EmptyState icon="history" title="Записей нет" desc="Под выбранные фильтры аудит пуст. Измените действие или дату." />
            : (
              <div className="table-wrap sticky" tabIndex={0} style={{ border: "none" }}>
                <table className="tbl">
                  <thead><tr><th>Время</th><th>Действие</th><th>Объект</th><th>Admin</th><th>IP</th></tr></thead>
                  <tbody>
                    {rows.map((a) => (
                      <tr key={a.id}>
                        <td className="muted" style={{ whiteSpace: "nowrap" }}>{fmtDate(a.created_at)}</td>
                        <td><span className="code-key" style={{ fontSize: 12 }}>{a.action}</span></td>
                        <td className="muted">{a.target_type}{a.target_id ? ` · ${a.target_id}` : ""}</td>
                        <td className="muted">#{a.admin_id}</td>
                        <td className="muted" style={{ fontSize: 11 }}>{a.ip || "—"}</td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            )}
      </div>
      <GatedNote>Аудит хранит кто / когда / что / IP по каждому действию (бэкап, restore, optimize, cache, provider, settings, security). Поле «причина» и rollback конкретной операции требуют расширения схемы аудита (before/after-снимки уже пишутся для части действий).</GatedNote>
    </div>
  );
}

// ================= shared bits =================
function msgOf(e: unknown): string { return e instanceof Error ? e.message : String(e); }
function iconForCat(name: string): string {
  const n = name.toLowerCase();
  if (n.includes("upload") || n.includes("image") || n.includes("photo")) return "image";
  if (n.includes("video")) return "movie";
  if (n.includes("voice") || n.includes("audio")) return "graphic_eq";
  if (n.includes("doc")) return "description";
  if (n.includes("result")) return "auto_awesome";
  if (n.includes("avatar")) return "face";
  return "folder";
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
function HealthCard({ title, icon, ok, dim, children }: { title: string; icon: string; ok: boolean; dim?: string; children: React.ReactNode }) {
  return (
    <div className="prov-card">
      <div className="pc-head">
        <span className="prov-logo"><span className="ms">{icon}</span></span>
        <div style={{ minWidth: 0 }}>
          <div className="pc-name">{title}</div>
          <div className="pc-vendor" style={{ display: "flex", alignItems: "center", gap: 5 }}>
            <span className={`status-dot ${ok ? "on" : "off"}`} />{dim}
          </div>
        </div>
      </div>
      <div className="page-stack" style={{ gap: 6 }}>{children}</div>
    </div>
  );
}
function KV({ k, v }: { k: string; v: React.ReactNode }) {
  return <div className="form-row" style={{ justifyContent: "space-between", margin: 0, fontSize: 13 }}><span className="muted">{k}</span><span style={{ fontWeight: 600 }}>{v}</span></div>;
}
function Bar({ label, pct, tone, right }: { label: string; pct: number; tone: "ok" | "warn" | "danger"; right?: string }) {
  const color = tone === "danger" ? "var(--danger)" : tone === "warn" ? "var(--warn)" : "var(--accent)";
  return (
    <div>
      <div className="form-row" style={{ justifyContent: "space-between", margin: "0 0 4px", fontSize: 12 }}><span className="muted">{label}</span><span className="muted">{right ?? `${pct}%`}</span></div>
      <div style={{ height: 7, borderRadius: 4, background: "var(--panel-2)", overflow: "hidden" }}>
        <div style={{ width: `${Math.min(100, Math.max(0, pct))}%`, height: "100%", background: color }} />
      </div>
    </div>
  );
}
function GatedNote({ children }: { children: React.ReactNode }) {
  return <p className="cfg-hint" style={{ marginTop: "var(--sp-3)", display: "flex", gap: 6 }}><span className="ms sm" style={{ flex: "0 0 auto" }}>info</span><span>{children}</span></p>;
}
function GatedCard({ icon, title, text }: { icon: string; title: string; text: string }) {
  return (
    <div className="prov-card off">
      <div className="pc-head"><span className="prov-logo"><span className="ms">{icon}</span></span><div className="pc-name">{title} <span className="pill muted" style={{ marginLeft: 4, fontSize: 10 }}>требует бэкенда</span></div></div>
      <p className="pc-desc">{text}</p>
    </div>
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
function SkeletonGrid({ rows = 4 }: { rows?: number }) {
  return <div className="page-stack">{Array.from({ length: rows }).map((_, i) => <div key={i} className="skeleton" style={{ height: 64 }} />)}</div>;
}
