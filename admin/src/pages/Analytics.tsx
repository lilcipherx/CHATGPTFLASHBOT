import { useEffect, useMemo, useState } from "react";
import { adminFetch, logout } from "../api";  // FIX: F40 - logout() on 401
import { DateField } from "../components/DateField";
import { countryLabel } from "../lib/countries";
import { languageLabel } from "../lib/languages";
import { useLatestGuard } from "../lib/latestGuard";

// Thin JSON wrapper over the shared `adminFetch` so this page inherits the same
// credential handling AND transparent token refresh on 401 (no premature
// "session expired" when the 30-min access token rolls over mid-session).
async function aReq<T>(path: string, init: RequestInit = {}): Promise<T> {
  const res = await adminFetch(path, {
    ...init,
    headers: { ...(init.headers ?? {}), "Content-Type": "application/json" },
  });
  if (res.status === 401) { logout(); window.dispatchEvent(new CustomEvent("admin:unauth")); throw new Error("session expired"); }  // FIX: F40 + AUDIT-H8 (dispatch admin:unauth so App swaps to Login)
  if (!res.ok) throw new Error(`API ${res.status}`);
  return res.json() as Promise<T>;
}

interface CurrencyStat { revenue: number; paid_users: number; arpu: number; arppu: number; }
interface Summary {
  days: number;
  start: string;
  end: string;
  currencies: Record<string, CurrencyStat>;
  revenue_total: number;
  revenue_by_currency: Record<string, number>;
  revenue_by_day: { date: string; amount: number }[];
  new_users_by_day: { date: string; count: number }[];
  paid_users: number;
  total_users: number;
  arpu: number;
  arppu: number;
  conversion_pct: number;
}

interface Funnel {
  stages: { stage: string; count: number }[];
}
interface Retention {
  d1: number; d7: number; d30: number;
  eligible_d1: number; eligible_d7: number; eligible_d30: number;
}
interface Content {
  top_services: { name: string; count: number }[];
  top_models: { name: string; count: number }[];
}
interface Geo {
  top_languages: { code: string; count: number }[];
  top_countries: { code: string; count: number }[];
}

const STAGE_LABELS: Record<string, string> = {
  registered: "Регистрация",
  activated: "Первая генерация",
  purchased: "Первая покупка",
  repeat: "Повторная покупка",
};

// Currency → symbol + label. Native amounts are never converted between currencies.
const CURRENCY_META: Record<string, { sym: string; label: string }> = {
  stars: { sym: "⭐", label: "Stars" }, xtr: { sym: "⭐", label: "Stars" },
  rub: { sym: "₽", label: "Рубли" }, usd: { sym: "$", label: "USD" },
  eur: { sym: "€", label: "EUR" }, usdt: { sym: "₮", label: "USDT" },
};
function curMeta(c: string) {
  return CURRENCY_META[c.toLowerCase()] ?? { sym: "", label: c.toUpperCase() };
}

const PRESETS = [7, 14, 30, 90, 365];

export function Analytics() {
  const [days, setDays] = useState(30);
  const [custom, setCustom] = useState(false);
  const [since, setSince] = useState("");
  const [until, setUntil] = useState("");
  const [d, setD] = useState<Summary | null>(null);
  const [funnel, setFunnel] = useState<Funnel | null>(null);
  const [ret, setRet] = useState<Retention | null>(null);
  const [content, setContent] = useState<Content | null>(null);
  const [geo, setGeo] = useState<Geo | null>(null);
  const [err, setErr] = useState("");
  const guard = useLatestGuard();

  // Build the query: a complete custom range (both ends) overrides the preset.
  const qs = useMemo(() => {
    if (custom && since && until) return `since=${since}&until=${until}`;
    return `days=${days}`;
  }, [custom, since, until, days]);
  const customIncomplete = custom && (!since || !until);

  useEffect(() => {
    if (customIncomplete) return;   // wait for both dates before firing
    // Guard against out-of-order responses: switching the range fires four fetches;
    // a stale (slower) batch must not overwrite the freshly-selected one.
    const isLatest = guard();
    setD(null);
    setFunnel(null);
    setRet(null);
    setContent(null);
    setGeo(null);
    setErr("");
    const fail = (e: unknown) => { if (isLatest()) setErr(String(e)); };
    aReq<Summary>(`/analytics/summary?${qs}`).then((x) => { if (isLatest()) setD(x); }).catch(fail);
    aReq<Funnel>(`/analytics/funnel?${qs}`).then((x) => { if (isLatest()) setFunnel(x); }).catch(fail);
    aReq<Retention>(`/analytics/retention?${qs}`).then((x) => { if (isLatest()) setRet(x); }).catch(fail);
    aReq<Content>(`/analytics/content?${qs}`).then((x) => { if (isLatest()) setContent(x); }).catch(fail);
    aReq<Geo>(`/analytics/geo?${qs}`).then((x) => { if (isLatest()) setGeo(x); }).catch(fail);
  }, [qs, customIncomplete, guard]);

  const currencies = d ? Object.entries(d.currencies).sort((a, b) => b[1].paid_users - a[1].paid_users) : [];
  const newUsersTotal = d ? d.new_users_by_day.reduce((s, r) => s + r.count, 0) : 0;

  return (
    <div>
      <h1 className="page-title">Аналитика</h1>
      <p className="page-sub">Выручка, рост аудитории и конверсия за выбранный период.</p>

      <div className="analytics-range">
        <div className="seg-tabs wrap">
          {PRESETS.map((r) => (
            <button key={r} className={!custom && days === r ? "on" : ""}
              onClick={() => { setCustom(false); setDays(r); }}>
              {r === 365 ? "Год" : `${r} дн.`}
            </button>
          ))}
          <button className={custom ? "on" : ""} onClick={() => setCustom(true)}>Период…</button>
        </div>
        {/* Only for a custom range — for a preset the active button already says it.
            ISO → ДД.ММ.ГГГГ so it reads like a date, not a database value. */}
        {custom && d && (
          <span className="range-note">
            {d.start.split("-").reverse().join(".")} → {d.end.split("-").reverse().join(".")} · {d.days} дн.
          </span>
        )}
      </div>

      {custom && (
        <div className="range-card">
          <label className="range-field">
            <span className="range-lbl">С</span>
            <DateField value={since} onChange={setSince} ariaLabel="С даты" />
          </label>
          <label className="range-field">
            <span className="range-lbl">По</span>
            <DateField value={until} onChange={setUntil} ariaLabel="По дату" />
          </label>
        </div>
      )}

      {err && (
        <p className="note-err">
          <span className="ms sm">error</span>{err}
          <button className="btn ghost sm" onClick={() => setErr("")}>×</button>
        </p>
      )}

      {customIncomplete ? (
        <div className="empty">Выберите обе даты диапазона.</div>
      ) : !d ? (
        <div className="metrics">
          {Array.from({ length: 4 }).map((_, i) => <div key={i} className="skeleton-row" />)}
        </div>
      ) : (
        <div className="page-stack">
          <div className="metrics">
            <Metric icon="percent" label="Конверсия в оплату" value={d.conversion_pct} suffix="%"
              delta={`${d.paid_users.toLocaleString("ru")} из ${d.total_users.toLocaleString("ru")}`} tone="purple" />
            <Metric icon="person_add" label="Новых пользователей" value={newUsersTotal} />
            <Metric icon="paid" label="Платящих за период" value={d.paid_users} tone="purple" />
          </div>

          <div className="panel">
            <div className="panel-title">Выручка по валютам</div>
            {currencies.length === 0 ? (
              <div className="empty">Платежей за период нет.</div>
            ) : (
              <div className="cur-cards">
                {currencies.map(([cur, s]) => {
                  const m = curMeta(cur);
                  return (
                    <div key={cur} className="cur-card">
                      <div className="cur-top">{m.sym} {m.label}</div>
                      <div className="cur-rev">{m.sym}{s.revenue.toLocaleString("ru")}</div>
                      <div className="cur-meta">
                        ARPPU {m.sym}{s.arppu.toLocaleString("ru")} · ARPU {m.sym}{s.arpu.toLocaleString("ru")}
                        <br />{s.paid_users.toLocaleString("ru")} платящих
                      </div>
                    </div>
                  );
                })}
              </div>
            )}
          </div>

          <div className="grid-2">
            <ColumnPanel
              title="Выручка по дням"
              rows={d.revenue_by_day.map((r) => ({ date: r.date, value: r.amount }))}
              empty="Платежей за период нет."
            />
            <ColumnPanel
              title="Новые пользователи по дням"
              rows={d.new_users_by_day.map((r) => ({ date: r.date, value: r.count }))}
              empty="Новых пользователей за период нет."
              tone="purple"
            />
          </div>

          {ret && (
            <div className="metrics">
              <Metric icon="event_repeat" label="Retention D1" value={ret.d1} suffix="%" tone="purple"
                delta={`когорта ${ret.eligible_d1.toLocaleString("ru")}`} />
              <Metric icon="event_repeat" label="Retention D7" value={ret.d7} suffix="%" tone="purple"
                delta={`когорта ${ret.eligible_d7.toLocaleString("ru")}`} />
              <Metric icon="event_repeat" label="Retention D30" value={ret.d30} suffix="%" tone="purple"
                delta={`когорта ${ret.eligible_d30.toLocaleString("ru")}`} />
            </div>
          )}

          <div className="grid-2">
            {funnel && (
              <BarPanel
                title="Воронка (когорта периода)"
                rows={funnel.stages.map((s) => ({ name: STAGE_LABELS[s.stage] ?? s.stage, value: s.count }))}
                empty="Нет данных по воронке."
              />
            )}
            {content && (
              <BarPanel
                title="Топ сервисов"
                rows={content.top_services.map((r) => ({ name: r.name, value: r.count }))}
                empty="Генераций за период нет."
              />
            )}
          </div>

          {content && content.top_models.length > 0 && (
            <BarPanel
              title="Топ моделей"
              rows={content.top_models.map((r) => ({ name: r.name, value: r.count }))}
              empty="Нет данных."
            />
          )}

          {geo && (
            <div className="grid-2">
              <BarPanel
                title="Языки аудитории"
                rows={geo.top_languages.map((r) => ({ name: languageLabel(r.code), value: r.count }))}
                empty="Нет данных по языкам."
              />
              <BarPanel
                title="Страны (по телефону)"
                rows={geo.top_countries.map((r) => ({ name: countryLabel(r.code), value: r.count }))}
                empty="Страна заполняется только при шаринге телефона — данных пока нет."
              />
            </div>
          )}
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
        {delta && <div className="delta"><span className="ms">info</span>{delta}</div>}
      </div>
    </div>
  );
}

// Vertical-column chart for a daily time series. Each day is a column whose height
// is proportional to its value; the date + value show on hover (title). Scrolls
// horizontally when the window is long (90/365 days) so columns stay readable.
function ColumnPanel({ title, rows, empty, tone }: {
  title: string; rows: { date: string; value: number }[]; empty: string;
  tone?: "purple";
}) {
  const max = Math.max(1, ...rows.map((r) => r.value));
  // Show a sparse date axis: ~8 labels max, otherwise they collide.
  const step = Math.max(1, Math.ceil(rows.length / 8));
  return (
    <div className="panel">
      <div className="panel-title">{title}</div>
      {rows.length === 0 ? (
        <div className="empty">{empty}</div>
      ) : (
        <div className="col-chart-wrap">
          <div className="col-chart">
            {rows.map((r, i) => (
              <div key={r.date} className="col" title={`${r.date}: ${r.value.toLocaleString("ru")}`}>
                <div className={"col-bar" + (tone ? " " + tone : "")}
                  style={{ height: `${Math.max(2, (r.value / max) * 100)}%` }} />
                <span className="col-lbl">{i % step === 0 ? r.date.slice(5) : ""}</span>
              </div>
            ))}
          </div>
        </div>
      )}
    </div>
  );
}

function BarPanel({ title, rows, empty }: {
  title: string; rows: { name: string; value: number }[]; empty: string;
}) {
  const max = Math.max(1, ...rows.map((r) => r.value));
  return (
    <div className="panel">
      <div className="panel-title">{title}</div>
      {rows.length === 0 ? (
        <div className="empty">{empty}</div>
      ) : (
        rows.map((r) => (
          <div key={r.name} className="barrow">
            <span className="name" title={r.name}>{r.name}</span>
            <span className="track"><span className="fill" style={{ width: `${(r.value / max) * 100}%` }} /></span>
            <span className="val">{r.value.toLocaleString("ru")}</span>
          </div>
        ))
      )}
    </div>
  );
}
