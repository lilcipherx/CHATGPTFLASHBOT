import { useCallback, useEffect, useState } from "react";
import { api, CronJobRow } from "../api";
import { Select } from "../components/Select";
import { useLatestGuard } from "../lib/latestGuard";

// Friendly interval presets (seconds). The backend clamps to [30, 604800].
const INTERVALS: { value: number; label: string }[] = [
  { value: 30, label: "30 сек" },
  { value: 60, label: "1 мин" },
  { value: 300, label: "5 мин" },
  { value: 900, label: "15 мин" },
  { value: 1800, label: "30 мин" },
  { value: 3600, label: "1 час" },
  { value: 21600, label: "6 часов" },
  { value: 43200, label: "12 часов" },
  { value: 86400, label: "1 день" },
  { value: 604800, label: "1 неделя" },
];

function intervalLabel(sec: number): string {
  const hit = INTERVALS.find((i) => i.value === sec);
  return hit ? hit.label : `${sec} сек`;
}

function fmtWhen(iso: string | null): string {
  if (!iso) return "—";
  const d = new Date(iso);
  return isNaN(d.getTime()) ? "—" : d.toLocaleString("ru");
}

/**
 * Планировщик (cron): включение/отключение каждой фоновой задачи и настройка,
 * как часто она запускается — прямо во время работы, без перезапуска. Управляет
 * таблицей cron_jobs; beat читает её на каждом тике. Изменения — только superadmin.
 */
export function Scheduler() {
  const [rows, setRows] = useState<CronJobRow[] | null>(null);
  const [err, setErr] = useState(false);
  const [busy, setBusy] = useState<string | null>(null);   // name currently saving
  const [msg, setMsg] = useState("");
  const guard = useLatestGuard();

  const load = useCallback(async () => {
    setErr(false);
    const isLatest = guard();
    try {
      const r = await api.cronList();
      if (isLatest()) setRows(r.jobs);
    } catch {
      if (isLatest()) setErr(true);
    }
  }, [guard]);

  useEffect(() => { load(); }, [load]);

  async function save(name: string, patch: { enabled?: boolean; interval_seconds?: number }) {
    if (busy) return;
    setBusy(name);
    setMsg("");
    // Optimistic update so the switch/select feels instant; rolled back on failure.
    const prev = rows;
    setRows((rs) => rs?.map((r) => (r.name === name ? { ...r, ...patch } : r)) ?? rs);
    try {
      const r = await api.cronUpdate(name, patch);
      setRows((rs) => rs?.map((x) => (x.name === name ? r.job : x)) ?? rs);
      setMsg("✅ Сохранено");
    } catch (e) {
      setRows(prev ?? null);  // rollback
      setMsg(`Ошибка: ${e instanceof Error ? e.message : String(e)}`);
    } finally {
      setBusy(null);
    }
  }

  if (err) {
    return (
      <div className="empty-state">
        <div className="es-icon"><span className="ms">error</span></div>
        <h3 className="es-title">Не удалось загрузить планировщик</h3>
        <button className="btn" onClick={() => load()}>Повторить</button>
      </div>
    );
  }
  if (rows === null) return <div className="loading">Загрузка…</div>;

  return (
    <div>
      <div className="panel-title" style={{ marginTop: 0 }}>
        <span className="ms sm">schedule</span> Планировщик задач
      </div>
      <p className="muted" style={{ marginTop: 0 }}>
        Включайте/отключайте фоновые задачи и задавайте, как часто они запускаются.
        Изменения применяются на лету (в течение минуты). Требуется роль superadmin.
      </p>
      {msg && <div className="muted" style={{ margin: "8px 0" }}>{msg}</div>}

      <div className="panel" style={{ overflowX: "auto" }}>
        <table className="table">
          <thead>
            <tr>
              <th>Задача</th>
              <th>Статус</th>
              <th>Как часто</th>
              <th style={{ minWidth: 140, whiteSpace: "nowrap" }}>Последний запуск</th>
              <th style={{ minWidth: 80, whiteSpace: "nowrap" }}>Итог</th>
            </tr>
          </thead>
          <tbody>
            {rows.map((r) => (
              <tr key={r.name}>
                <td>
                  <div>{r.label}</div>
                  <div className="muted" style={{ fontSize: 12 }}>{r.name}</div>
                </td>
                <td>
                  <button
                    className={"btn sm " + (r.enabled ? "" : "ghost")}
                    disabled={busy === r.name}
                    onClick={() => save(r.name, { enabled: !r.enabled })}
                    title={r.enabled ? "Отключить" : "Включить"}
                  >
                    <span className="ms sm">{r.enabled ? "toggle_on" : "toggle_off"}</span>
                    {r.enabled ? "Включена" : "Выключена"}
                  </button>
                </td>
                <td>
                  {/* FIX: UI-2 - use the design-system Select (portalled dark menu)
                      instead of a native <select> whose OPEN dropdown was browser-
                      native (light) and broke the dark theme. */}
                  <Select
                    ariaLabel="Интервал запуска"
                    value={String(r.interval_seconds)}
                    onChange={(v) => save(r.name, { interval_seconds: Number(v) })}
                    options={[
                      // Keep the current value visible even if it isn't a preset.
                      ...(!INTERVALS.some((i) => i.value === r.interval_seconds)
                        ? [{ value: String(r.interval_seconds), label: intervalLabel(r.interval_seconds) }]
                        : []),
                      ...INTERVALS.map((i) => ({ value: String(i.value), label: i.label })),
                    ]}
                  />
                </td>
                <td className="muted">{fmtWhen(r.last_run_at)}</td>
                <td className="muted" style={{ maxWidth: 240, whiteSpace: "pre-wrap" }}>
                  {r.last_status ?? "—"}
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </div>
  );
}
