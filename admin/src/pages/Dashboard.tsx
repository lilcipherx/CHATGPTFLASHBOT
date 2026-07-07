import { useEffect, useState } from "react";
import { adminFetch, api, Dashboard as DashboardT, DashboardPeriod, RevenueCurrency, logout } from "../api";  // FIX: F43 - logout() on 401

interface Attention {
  stuck_jobs: number;
  open_complaints: number;
  pending_gallery: number;
  open_support: number;
  failed_channel_posts: number;
  total: number;
}

// Uses the shared `adminFetch` so the /attention poll gets the same auto-refresh on
// 401 as the rest of the dashboard (no stray "session expired" every 60s).
async function fetchAttention(): Promise<Attention> {
  const res = await adminFetch("/attention/", {
    headers: { "Content-Type": "application/json" },
  });
  if (res.status === 401) { logout(); window.dispatchEvent(new CustomEvent("admin:unauth")); throw new Error("session expired"); }  // FIX: F43 + AUDIT-H8
  if (!res.ok) throw new Error(`API ${res.status}`);
  return res.json() as Promise<Attention>;
}

// Each attention bucket links to the page where the admin actually resolves it,
// so the panel is a one-click triage list rather than a passive counter.
const ATTENTION_ITEMS: { key: keyof Attention; label: string; to: string }[] = [
  { key: "stuck_jobs", label: "Зависшие задачи", to: "/health" },
  { key: "open_complaints", label: "Жалобы", to: "/feedback" },
  { key: "pending_gallery", label: "Галерея на модерации", to: "/gallery" },
  { key: "open_support", label: "Обращения в поддержку", to: "/feedback" },
  { key: "failed_channel_posts", label: "Ошибки автопостинга", to: "/autoposting" },
];

const PERIODS: { id: DashboardPeriod; label: string }[] = [
  { id: "day", label: "День" },
  { id: "week", label: "Неделя" },
  { id: "month", label: "Месяц" },
  { id: "all", label: "Всё время" },
];

const GATEWAY_LABEL: Record<string, string> = {
  stars: "Telegram Stars", sbp_tribute: "СБП (Tribute)", yookassa: "ЮКасса", stripe: "Stripe",
  crypto: "🪙 Крипта (CryptoBot)",
};
// Currency → display symbol + human label. Native amounts are never converted
// between currencies; each gets its own tab so totals stay honest.
const CURRENCY_META: Record<string, { sym: string; label: string }> = {
  stars: { sym: "⭐", label: "Stars" },
  xtr: { sym: "⭐", label: "Stars" },
  rub: { sym: "₽", label: "Рубли" },
  usd: { sym: "$", label: "USD" },
  eur: { sym: "€", label: "EUR" },
  usdt: { sym: "₮", label: "USDT" },
};
function curMeta(c: string) {
  return CURRENCY_META[c.toLowerCase()] ?? { sym: "", label: c.toUpperCase() };
}

const JOB_CLASS: Record<string, string> = {
  complete: "ok", processing: "info", pending: "warn", failed: "danger",
};
const JOB_LABEL: Record<string, string> = {
  complete: "Готово", processing: "В работе", pending: "В очереди", failed: "Ошибка",
};

export function Dashboard() {
  const [d, setD] = useState<DashboardT | null>(null);
  const [err, setErr] = useState("");
  const [att, setAtt] = useState<Attention | null>(null);
  const [period, setPeriod] = useState<DashboardPeriod>("all");
  const [busy, setBusy] = useState(false);
  const [updatedAt, setUpdatedAt] = useState<Date | null>(null);

  // Refresh on an interval so the "в реальном времени" overview actually stays live.
  // The backend caches each period's payload for 60s, so a 60s poll is ~1 DB scan/min.
  // `alive` guards setState-after-unmount; clearInterval stops the timer. A transient
  // error shows as a banner ABOVE the last good data rather than blanking the panel,
  // and the next successful poll clears it. Re-runs when the period changes.
  useEffect(() => {
    let alive = true;
    const load = () => {
      setBusy(true);
      Promise.allSettled([
        api.dashboard(period)
          .then((v) => { if (alive) { setD(v); setErr(""); } })
          .catch((e) => { if (alive) setErr(String(e)); }),
        fetchAttention()
          .then((v) => { if (alive) setAtt(v); })
          .catch(() => { if (alive) setAtt(null); }),
      ]).finally(() => { if (alive) { setBusy(false); setUpdatedAt(new Date()); } });
    };
    load();
    const id = window.setInterval(load, 60_000);
    return () => { alive = false; window.clearInterval(id); };
  }, [period]);

  const periodWord = period === "all" ? "всё время"
    : period === "day" ? "сутки" : period === "week" ? "неделю" : "месяц";

  return (
    <div>
      <div className="page-head">
        <div>
          <h1 className="page-title">Обзор системы</h1>
          <p className="page-sub">Метрики продукта и состояние очереди в реальном времени.</p>
        </div>
        <div style={{ display: "flex", flexDirection: "column", alignItems: "flex-end", gap: 6 }}>
          <div className="seg-tabs">
            {PERIODS.map((p) => (
              <button key={p.id} className={period === p.id ? "on" : ""}
                aria-pressed={period === p.id} onClick={() => setPeriod(p.id)}>
                {p.label}
              </button>
            ))}
          </div>
          <span className="health-updated" aria-live="polite">
            {busy
              ? <><span className="ms sm spin">progress_activity</span> обновление…</>
              : updatedAt && <><span className="live-dot" /> обновлено {updatedAt.toLocaleTimeString("ru")}</>}
          </span>
        </div>
      </div>

      {err && (
        <p className="note-err">
          <span className="ms sm">error</span>{err}
          <button className="btn ghost sm" onClick={() => setErr("")}>×</button>
        </p>
      )}

      {att && <AttentionPanel data={att} />}

      {!d ? (
        <div className="metrics">
          {Array.from({ length: 9 }).map((_, i) => <div key={i} className="skeleton-row" />)}
        </div>
      ) : (
        <>
          <div className="metrics">
            <Metric icon="group" label="Всего пользователей" value={d.total_users}
              delta={d.new_users > 0 ? `+${d.new_users.toLocaleString("ru")} за ${periodWord}` : undefined} />
            <Metric icon="bolt" label="Активны сегодня (DAU)" value={d.dau} tone="purple" />
            <Metric icon="calendar_month" label="Активны за 30 дней (MAU)" value={d.mau} />
            <Metric icon="stars" label="Активные подписки" value={d.active_subscriptions} tone="purple" />
            <Metric icon="conversion_path" label="Конверсия в оплату" value={d.conversion_pct} suffix="%"
              delta={d.paying_users > 0 ? `${d.paying_users.toLocaleString("ru")} платящих` : undefined} />
            <Metric icon="payments" label={`Оплат за ${periodWord}`} value={d.paid_transactions} />
            <Metric icon="toll" label="Кредитов в обороте" value={d.credits_total} suffix="✨" />
            <Metric icon="auto_awesome" label="Генераций готово" value={d.completed_generations} tone="purple" />
            <Metric icon="block" label="Заблокировано" value={d.banned_users}
              tone={d.banned_users > 0 ? "danger" : undefined} />
          </div>

          <div className="grid-2">
            <RevenuePanel data={d.revenue_by_currency} />
            <JobsPanel data={d.jobs_by_status} pending={d.pending_jobs} />
          </div>
        </>
      )}
    </div>
  );
}

function AttentionPanel({ data }: { data: Attention }) {
  return (
    <div className="panel">
      <div className="panel-title">
        Требует внимания{" "}
        {data.total > 0 && <span className="pill danger">{data.total}</span>}
      </div>
      {data.total === 0 ? (
        <div className="empty">Всё спокойно — нет задач, требующих внимания.</div>
      ) : (
        <div style={{ display: "flex", flexWrap: "wrap", gap: 8 }}>
          {ATTENTION_ITEMS.filter((it) => data[it.key] > 0).map((it) => (
            // HashRouter app → a plain hash anchor navigates without needing Router
            // context (keeps this panel renderable/testable in isolation).
            <a key={it.key} href={`#${it.to}`} className="pill warn pill-link">
              {it.label}: {data[it.key].toLocaleString("ru")}
              <span className="ms sm">chevron_right</span>
            </a>
          ))}
        </div>
      )}
    </div>
  );
}

function Metric({ icon, label, value, delta, suffix, tone }: {
  icon: string; label: string; value: number; delta?: string; suffix?: string;
  tone?: "purple" | "danger";
}) {
  return (
    <div className={"metric" + (tone ? " " + tone : "")}>
      <span className="glow" />
      <div className="top">
        <span className="lbl">{label}</span>
        <span className="ms sm">{icon}</span>
      </div>
      <div>
        <div className="num">{value.toLocaleString("ru")}{suffix && <small>{suffix}</small>}</div>
        {delta && <div className="delta"><span className="ms">trending_up</span>{delta}</div>}
      </div>
    </div>
  );
}

function RevenuePanel({ data }: { data: Record<string, RevenueCurrency> }) {
  // Sort currencies by tx count so the most-used payment currency is the default tab.
  const currencies = Object.keys(data).sort((a, b) => data[b].count - data[a].count);
  const [cur, setCur] = useState<string>("");
  const active = cur && data[cur] ? cur : currencies[0];
  const bucket: RevenueCurrency | undefined = active ? data[active] : undefined;
  const gateways = bucket ? Object.entries(bucket.by_gateway).sort((a, b) => b[1] - a[1]) : [];
  const max = Math.max(1, ...gateways.map(([, v]) => v));
  const m = active ? curMeta(active) : { sym: "", label: "" };

  return (
    <div className="panel">
      <div className="panel-title">Выручка по валютам</div>
      {currencies.length === 0 ? (
        <div className="empty">Платежей пока нет.</div>
      ) : (
        <>
          {currencies.length > 1 && (
            <div className="seg-tabs wrap" style={{ marginBottom: 14 }}>
              {currencies.map((c) => {
                const cm = curMeta(c);
                return (
                  <button key={c} className={c === active ? "on" : ""} onClick={() => setCur(c)}>
                    {cm.sym} {cm.label}
                  </button>
                );
              })}
            </div>
          )}
          {bucket && (
            <div className="rev-head">
              <span className="rev-total">{m.sym}{bucket.total.toLocaleString("ru")}</span>
              <span className="rev-meta">
                {bucket.count.toLocaleString("ru")} оплат · средний чек {m.sym}{bucket.avg_check.toLocaleString("ru")}
              </span>
            </div>
          )}
          {gateways.map(([g, v]) => (
            <div key={g} className="barrow">
              <span className="name">{GATEWAY_LABEL[g] ?? g}</span>
              <span className="track"><span className="fill" style={{ width: `${(v / max) * 100}%` }} /></span>
              <span className="val">{m.sym}{v.toLocaleString("ru")}</span>
            </div>
          ))}
        </>
      )}
    </div>
  );
}

function JobsPanel({ data, pending }: { data: Record<string, number>; pending: number }) {
  const order = ["complete", "processing", "pending", "failed"];
  const keys = [...new Set([...order, ...Object.keys(data)])].filter((k) => data[k]);
  const max = Math.max(1, ...keys.map((k) => data[k]));
  return (
    <div className="panel">
      <div className="panel-title">Очередь генераций {pending > 0 && <span className="pill warn">{pending} активных</span>}</div>
      {keys.length === 0 ? (
        <div className="empty">Задач пока нет.</div>
      ) : (
        keys.map((k) => (
          <div key={k} className="barrow">
            <span className="name">{JOB_LABEL[k] ?? k}</span>
            <span className="track"><span className={"fill " + (JOB_CLASS[k] ?? "")} style={{ width: `${(data[k] / max) * 100}%` }} /></span>
            <span className="val">{data[k].toLocaleString("ru")}</span>
          </div>
        ))
      )}
    </div>
  );
}
