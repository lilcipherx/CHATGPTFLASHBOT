import { useEffect, useRef, useState } from "react";
import { api, ProviderStatus, QueueHealth, SystemHealth } from "../api";

const JOB_LABEL: Record<string, string> = {
  complete: "Готово", processing: "В работе", pending: "В очереди", failed: "Ошибка",
};

function fmtAge(seconds: number): string {
  if (seconds <= 0) return "—";
  const m = Math.floor(seconds / 60);
  if (m < 60) return `${m} мин`;
  const h = Math.floor(m / 60);
  return `${h} ч ${m % 60} мин`;
}

function fmtDuration(seconds: number): string {
  if (!seconds || seconds <= 0) return "—";
  if (seconds < 60) return `${seconds.toFixed(seconds < 10 ? 1 : 0)} с`;
  const m = Math.floor(seconds / 60);
  const s = Math.round(seconds % 60);
  return `${m} м ${s} с`;
}

function fmtUptime(seconds: number): string {
  if (!seconds || seconds <= 0) return "—";
  const d = Math.floor(seconds / 86400);
  const h = Math.floor((seconds % 86400) / 3600);
  const m = Math.floor((seconds % 3600) / 60);
  if (d > 0) return `${d} д ${h} ч`;
  if (h > 0) return `${h} ч ${m} мин`;
  return `${m} мин`;
}

const REFRESH_MS = 15_000;

export function Health() {
  const [sys, setSys] = useState<SystemHealth | null>(null);
  const [queue, setQueue] = useState<QueueHealth | null>(null);
  const [providers, setProviders] = useState<ProviderStatus[] | null>(null);
  const [updatedAt, setUpdatedAt] = useState<Date | null>(null);
  const [msg, setMsg] = useState("");
  const [busy, setBusy] = useState(false);
  const [retryBusy, setRetryBusy] = useState<string | null>(null);  // FIX: F44 - per-job retry busy state
  // FIX: AUDIT-FINAL-9 - cancelBusy was referenced in the JSX (disabled={cancelBusy === j.job_id})
  // but never declared. Clicking "Отмена" rendered ReferenceError → ErrorBoundary
  // crash, hiding the entire Health page until reload. Mirror the retryBusy pattern.
  const [cancelBusy, setCancelBusy] = useState<string | null>(null);
  const aliveRef = useRef(true);

  const load = () => {
    setBusy(true);
    Promise.allSettled([
      api.systemHealth().then((v) => { if (aliveRef.current) { setSys(v); setUpdatedAt(new Date()); } })
        .catch((e) => { if (aliveRef.current) setMsg(String(e)); }),
      api.queueHealth().then((v) => { if (aliveRef.current) setQueue(v); })
        .catch((e) => { if (aliveRef.current) setMsg(String(e)); }),
      api.providers().then((v) => { if (aliveRef.current) setProviders(v); })
        .catch(() => { if (aliveRef.current) setProviders(null); }),
    ]).finally(() => { if (aliveRef.current) setBusy(false); });
  };

  // Live health: poll every 15s and clean up the timer + guard setState-after-unmount.
  useEffect(() => {
    aliveRef.current = true;
    load();
    const id = window.setInterval(load, REFRESH_MS);
    return () => { aliveRef.current = false; window.clearInterval(id); };
  }, []);

  async function retry(id: string) {
    // FIX: F44 - guard against rapid double-clicks firing duplicate retryJob calls.
    if (retryBusy) return;
    setRetryBusy(id);
    try { await api.retryJob(id); setMsg("✅ Задача перезапущена"); load(); }
    catch (e) { setMsg(String(e)); }
    finally { setRetryBusy(null); }
  }
  async function cancel(id: string) {
    if (!confirm("Отменить задачу и вернуть средства пользователю?")) return;
    // FIX: AUDIT-FINAL-9 - guard against rapid double-clicks (mirror retry()).
    if (cancelBusy) return;
    setCancelBusy(id);
    try { await api.cancelJob(id); setMsg("✅ Задача отменена, средства возвращены"); load(); }
    catch (e) { setMsg(String(e)); }
    finally { setCancelBusy(null); }
  }

  const counts = queue?.counts ?? {};
  const order = ["complete", "processing", "pending", "failed"];
  const countKeys = [...new Set([...order, ...Object.keys(counts)])].filter((k) => counts[k]);

  return (
    <div>
      <div className="page-head">
        <div>
          <h1 className="page-title">Здоровье системы</h1>
          <p className="page-sub">Состояние сервисов, очередь генераций, ретрай и отмена зависших задач.</p>
        </div>
        <div className="health-refresh">
          {updatedAt && (
            <span className="health-updated">
              <span className="live-dot" /> обновлено {updatedAt.toLocaleTimeString("ru")}
            </span>
          )}
          <button className="btn sm ghost" onClick={load} disabled={busy}>
            <span className={"ms sm" + (busy ? " spin" : "")}>{busy ? "progress_activity" : "refresh"}</span>
            {busy ? " Обновление…" : " Обновить"}
          </button>
        </div>
      </div>

      {msg && (
        <p className={msg.startsWith("✅") ? "note-ok" : "note-err"}>
          <span className="ms sm">{msg.startsWith("✅") ? "check_circle" : "error"}</span>{msg}
          <button className="btn ghost sm" onClick={() => setMsg("")}>×</button>
        </p>
      )}

      <div className="page-stack">
        <div className="metrics">
          <Metric icon="database" label="База данных" value={sys?.db_ok ? "OK" : "Недоступна"}
            tone={sys?.db_ok ? undefined : "danger"} />
          <Metric icon="bolt" label="Redis / очередь" value={sys?.redis_ok ? "OK" : "Недоступна"}
            tone={sys?.redis_ok ? undefined : "danger"} />
          <Metric icon="group" label="Всего пользователей" value={(sys?.total_users ?? 0).toLocaleString("ru")} />
          <Metric icon="hourglass_top" label="Активных задач" value={(sys?.pending_jobs ?? 0).toLocaleString("ru")}
            tone={queue && queue.stuck_count > 0 ? "danger" : undefined} />
        </div>

        <div className="metrics">
          <Metric icon="timer" label="Среднее время генерации"
            value={fmtDuration(sys?.avg_job_seconds ?? 0)} sub="за 24 ч" />
          <Metric icon="error" label="Доля ошибок (24 ч)"
            value={`${(sys?.error_rate_pct ?? 0).toLocaleString("ru")}%`}
            sub={sys ? `${sys.failed_24h} из ${sys.completed_24h + sys.failed_24h}` : undefined}
            tone={(sys?.error_rate_pct ?? 0) >= 20 ? "danger" : undefined} />
          <Metric icon="schedule" label="Время работы" value={fmtUptime(sys?.uptime_seconds ?? 0)} />
          <Metric icon="tag" label="Версия" value={sys?.version ?? "—"} />
        </div>

        <div className="panel">
          <div className="panel-title">
            AI-провайдеры (видео)
            <a href="#/providers" className="panel-link">настроить <span className="ms sm">chevron_right</span></a>
          </div>
          {!providers || providers.length === 0 ? (
            <div className="empty">Провайдеры не настроены.</div>
          ) : (
            <div className="prov-grid">
              {providers.map((p) => {
                const state = p.disabled ? "off" : p.available ? "on" : "down";
                const label = p.disabled ? "Выключен" : p.available ? "Доступен" : "Недоступен";
                return (
                  <div key={p.key} className={"prov-chip " + state}>
                    <span className="prov-led" />
                    <span className="prov-key">{p.key}</span>
                    <span className="prov-state">{label}</span>
                  </div>
                );
              })}
            </div>
          )}
        </div>

        <div className="panel">
          <div className="panel-title">
            Очередь генераций
            {queue && queue.stuck_count > 0 &&
              <span className="pill warn">{queue.stuck_count} зависших</span>}
          </div>
          {countKeys.length === 0 ? (
            <div className="empty">Задач пока нет.</div>
          ) : (
            <div className="toolbar" style={{ marginBottom: 0, flexWrap: "wrap" }}>
              {countKeys.map((k) => (
                <span key={k} className="pill">{JOB_LABEL[k] ?? k}: {counts[k].toLocaleString("ru")}</span>
              ))}
              {queue && queue.oldest_pending_age_seconds > 0 && (
                <span className="pill">Старейшая активная: {fmtAge(queue.oldest_pending_age_seconds)}</span>
              )}
            </div>
          )}
        </div>

        <div className="table-wrap" tabIndex={0}>
          <table className="tbl">
            <thead>
              <tr><th>Job ID</th><th>Сервис</th><th>User</th><th>Статус</th><th>Создана</th><th></th></tr>
            </thead>
            <tbody>
              {!queue || queue.stuck_jobs.length === 0 ? (
                <tr><td colSpan={6}><div className="empty">Зависших задач нет.</div></td></tr>
              ) : queue.stuck_jobs.map((j) => (
                <tr key={j.job_id}>
                  <td className="code-key">{j.job_id.slice(0, 8)}…</td>
                  <td>{j.service}</td>
                  <td className="muted">{j.user_id}</td>
                  <td>{JOB_LABEL[j.status] ?? j.status}</td>
                  <td className="muted">{new Date(j.created_at).toLocaleString("ru")}</td>
                  <td>
                    <div className="cell-actions">
                      <button className="btn sm" disabled={retryBusy === j.job_id} onClick={() => retry(j.job_id)}>
                        <span className="ms sm">refresh</span> {retryBusy === j.job_id ? "…" : "Ретрай"}
                      </button>
                      <button className="btn sm danger" onClick={() => cancel(j.job_id)} disabled={cancelBusy === j.job_id}>
                        <span className="ms sm">cancel</span> Отмена
                      </button>
                    </div>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </div>
    </div>
  );
}

function Metric({ icon, label, value, tone, sub }: {
  icon: string; label: string; value: string | number; tone?: "danger"; sub?: string;
}) {
  return (
    <div className={"metric" + (tone ? " " + tone : "")}>
      <span className="glow" />
      <div className="top">
        <span className="lbl">{label}</span>
        <span className="ms sm">{icon}</span>
      </div>
      <div>
        <div className="num">{value}</div>
        {sub && <div className="delta"><span className="ms">info</span>{sub}</div>}
      </div>
    </div>
  );
}
