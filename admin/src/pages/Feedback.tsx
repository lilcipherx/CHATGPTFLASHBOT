import { useEffect, useRef, useState } from "react";
import { api, ComplaintRow, RatingRow } from "../api";
import { Select } from "../components/Select";
import { useLatestGuard } from "../lib/latestGuard";  // FIX: F46

const REFRESH_MS = 30_000;
type Status = "open" | "resolved" | "all";

const STATUS_OPTS = [
  { value: "open", label: "Открытые" },
  { value: "resolved", label: "Закрытые" },
  { value: "all", label: "Все" },
];

// Link a user id to their card on the Users page (deep link → opens the card).
function UserLink({ id }: { id: number }) {
  return <a className="code-key user-link" href={`#/users?focus=${id}`}>#{id}</a>;
}

export function Feedback() {
  const [stats, setStats] = useState<{ up: number; down: number; complaints_open: number } | null>(null);
  const [complaints, setComplaints] = useState<ComplaintRow[] | null>(null);
  const [dislikes, setDislikes] = useState<RatingRow[] | null>(null);
  const [status, setStatus] = useState<Status>("open");
  const [updatedAt, setUpdatedAt] = useState<Date | null>(null);
  const [msg, setMsg] = useState("");
  const [resolving, setResolving] = useState<number | null>(null);  // FIX: per-complaint in-flight guard (mirror Gallery/Contests)
  const aliveRef = useRef(true);
  const guard = useLatestGuard();  // FIX: F46

  const load = () => {
    const isLatest = guard();  // FIX: F46 - capture before fetch so a stale in-flight request can't overwrite
    api.feedbackStats().then((v) => { if (aliveRef.current && isLatest()) { setStats(v); setUpdatedAt(new Date()); } })
      .catch((e) => { if (aliveRef.current) setMsg(String(e)); });
    api.feedbackComplaints(status).then((v) => { if (aliveRef.current && isLatest()) setComplaints(v); })
      .catch((e) => { if (aliveRef.current) setMsg(String(e)); });
    api.feedbackRatings("down", 30).then((v) => { if (aliveRef.current && isLatest()) setDislikes(v); })
      .catch(() => { if (aliveRef.current) setDislikes(null); });
  };

  // Live triage queue: poll every 30s; reload immediately when the status changes.
  useEffect(() => {
    aliveRef.current = true;
    load();
    const id = window.setInterval(load, REFRESH_MS);
    return () => { aliveRef.current = false; window.clearInterval(id); };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [status]);

  async function resolve(id: number) {
    if (resolving !== null) return;  // FIX: block re-entrancy / double-submit
    if (!confirm("Закрыть жалобу? Она уйдёт из очереди открытых.")) return;
    setResolving(id);
    try { await api.resolveComplaint(id); setMsg("✅ Жалоба закрыта"); load(); }
    catch (e) { setMsg(String(e)); }
    finally { setResolving(null); }
  }

  const ratioPct = stats && stats.up + stats.down > 0
    ? Math.round((stats.up / (stats.up + stats.down)) * 100) : null;

  return (
    <div>
      <div className="page-head">
        <div>
          <h1 className="page-title">Оценки и жалобы</h1>
          <p className="page-sub">Реакции на ответы ассистента и обращения пользователей (§7).</p>
        </div>
        <div className="health-refresh">
          {updatedAt && (
            <span className="health-updated">
              <span className="live-dot" /> обновлено {updatedAt.toLocaleTimeString("ru")}
            </span>
          )}
          <button className="btn sm ghost" onClick={load}>
            <span className="ms sm">refresh</span> Обновить
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
          <Metric icon="thumb_up" label="Лайки" value={stats?.up} />
          <Metric icon="thumb_down" label="Дизлайки" value={stats?.down}
            tone={stats && stats.down > stats.up ? "danger" : undefined} />
          <Metric icon="sentiment_satisfied" label="Доля 👍"
            value={ratioPct ?? undefined} suffix="%" />
          <Metric icon="report" label="Открытых жалоб" value={stats?.complaints_open}
            tone={stats && stats.complaints_open > 0 ? "danger" : undefined} />
        </div>

        <div className="panel">
          <div className="panel-title"><span className="ms sm">thumb_down</span> Дизлайкнутые ответы</div>
          {dislikes === null ? <div className="loading">Загрузка…</div>
            : dislikes.length === 0 ? <div className="empty">Дизлайков нет — ассистент молодец.</div>
            : (
              <table className="tbl">
                <thead><tr><th>Время</th><th>Пользователь</th><th>Отрывок ответа</th></tr></thead>
                <tbody>
                  {dislikes.map((r) => (
                    <tr key={r.id}>
                      <td className="muted" style={{ whiteSpace: "nowrap" }}>
                        {r.created_at ? new Date(r.created_at).toLocaleString("ru") : "—"}
                      </td>
                      <td><UserLink id={r.user_id} /></td>
                      <td style={{ whiteSpace: "pre-wrap" }} className="muted">{r.snippet || "—"}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            )}
        </div>

        <div className="panel">
          <div className="panel-title">
            <span className="ms sm">report</span> Жалобы
            <label className="spacer" style={{ marginLeft: "auto" }}>
              <Select ariaLabel="Статус жалоб" value={status} onChange={(v) => setStatus(v as Status)}
                options={STATUS_OPTS} />
            </label>
          </div>
          {complaints === null ? <div className="loading">Загрузка…</div>
            : complaints.length === 0 ? <div className="empty">Жалоб нет — всё спокойно.</div>
            : (
              <table className="tbl">
                <thead><tr><th>Время</th><th>Пользователь</th><th>Текст</th><th>Статус</th><th></th></tr></thead>
                <tbody>
                  {complaints.map((c) => (
                    <tr key={c.id}>
                      <td className="muted" style={{ whiteSpace: "nowrap" }}>
                        {c.created_at ? new Date(c.created_at).toLocaleString("ru") : "—"}
                      </td>
                      <td><UserLink id={c.user_id} /></td>
                      <td style={{ whiteSpace: "pre-wrap" }}>{c.content}</td>
                      <td>
                        {c.resolved
                          ? <span className="pill ok">закрыта</span>
                          : <span className="pill warn">открыта</span>}
                      </td>
                      <td style={{ width: 1 }}>
                        {!c.resolved && (
                          <button className="btn sm ghost" disabled={resolving === c.id} onClick={() => resolve(c.id)}>{resolving === c.id ? "…" : "Закрыть"}</button>
                        )}
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            )}
        </div>
      </div>
    </div>
  );
}

function Metric({ icon, label, value, tone, suffix }: {
  icon: string; label: string; value: number | undefined; tone?: "danger"; suffix?: string;
}) {
  return (
    <div className={"metric" + (tone ? " " + tone : "")}>
      <span className="glow" />
      <div className="top">
        <span className="lbl">{label}</span>
        <span className="ms sm">{icon}</span>
      </div>
      <div>
        <div className="num">{value === undefined ? "—" : value.toLocaleString("ru")}{value !== undefined && suffix}</div>
      </div>
    </div>
  );
}
