import { useCallback, useEffect, useState } from "react";
import { useLatestGuard } from "../lib/latestGuard";
import { api, type GatewayStatus, type Payment, type PaymentsStats } from "../api";
import { Select } from "../components/Select";
import { DateField } from "../components/DateField";
import { Modal } from "../components/Modal";

// Payments / billing control center (ТЗ §8). Grounded in the REAL backend:
//   • KPIs, the revenue trend and the gateway breakdown come from /payments/stats —
//     accurate, currency-aware aggregates computed in the DB across the WHOLE window
//     (not just one page), so they're correct at any volume;
//   • the transactions table uses /payments with indexed server-side filters
//     (status/gateway/user_id/date range) + pagination and an enriched detail drawer;
//   • refunds use the real two-phase /payments/{id}/refund (revoke → gateway refund,
//     retryable).
// Revenue is never cross-summed across currencies — it's always shown per-currency.

const STATUSES = ["", "paid", "refund_pending", "refunded", "pending", "failed"];
const GATEWAYS = ["", "stars", "yookassa", "stripe", "sbp_tribute", "crypto"];
const STATUS_CLASS: Record<string, string> = {
  paid: "ok", refund_pending: "warn", refunded: "muted", pending: "warn", failed: "danger",
};
const STATUS_LABEL: Record<string, string> = {
  paid: "оплачен", refund_pending: "возврат…", refunded: "возвращён", pending: "ожидание", failed: "ошибка",
};
const GATEWAY_LABEL: Record<string, string> = {
  stars: "Telegram Stars", sbp_tribute: "СБП (Tribute)", yookassa: "ЮКасса",
  stripe: "Stripe", crypto: "Крипта (CryptoBot)",
};
const WINDOWS = [
  { value: "7", label: "7 дней" }, { value: "30", label: "30 дней" },
  { value: "90", label: "90 дней" }, { value: "365", label: "Год" },
];
const PAGE = 50;
const CURRENCY_SUFFIX: Record<string, string> = { rub: "₽", usd: "$", eur: "€", stars: "⭐", xtr: "⭐" };
// Fiat amounts are stored in MINOR units (kopecks/cents — see core.payments.service
// stars_to_minor, which multiplies by 100). Stars are whole units. Divide the minor
// currencies by 100 for display so a 499 ₽ charge shows as "499 ₽", not "49 900 ₽".
const MINOR_UNIT = new Set(["rub", "usd", "eur"]);

function fmtMoney(amount: number, currency: string): string {
  const c = currency.toLowerCase();
  const suf = CURRENCY_SUFFIX[c] ?? currency.toUpperCase();
  const isStars = c === "stars" || c === "xtr";
  const major = MINOR_UNIT.has(c) ? amount / 100 : amount;
  const n = major.toLocaleString("ru", isStars || Number.isInteger(major)
    ? {} : { minimumFractionDigits: 2, maximumFractionDigits: 2 });
  return isStars ? `${suf} ${n}` : `${n} ${suf}`;
}
const fmtInt = (n: number | undefined) => (n ?? 0).toLocaleString("ru");
const ymd = (d: Date) => `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, "0")}-${String(d.getDate()).padStart(2, "0")}`;
function fmtDate(s: string): string {
  return new Date(s).toLocaleString("ru", { day: "2-digit", month: "short", year: "numeric", hour: "2-digit", minute: "2-digit" });
}
function ago(s: string | null): string {
  if (!s) return "—";
  const d = Math.floor((Date.now() - new Date(s).getTime()) / 86400000);
  if (d <= 0) return "сегодня"; if (d === 1) return "вчера"; if (d < 30) return `${d} дн назад`;
  return new Date(s).toLocaleDateString("ru");
}

export function Payments() {
  const [days, setDays] = useState("30");
  const [stats, setStats] = useState<PaymentsStats | null>(null);
  const [trend, setTrend] = useState<"count" | "amount">("count");
  const [statsErr, setStatsErr] = useState(false);

  // transactions table (independent server-side filters + pagination)
  const [rows, setRows] = useState<Payment[] | null>(null);
  const [total, setTotal] = useState(0);
  const [page, setPage] = useState(0);
  const [status, setStatus] = useState("");
  const [gateway, setGateway] = useState("");
  const [userId, setUserId] = useState("");
  const [from, setFrom] = useState("");
  const [to, setTo] = useState("");

  const [busy, setBusy] = useState("");
  const [err, setErr] = useState("");
  const [note, setNote] = useState("");
  const [detail, setDetail] = useState<Payment | null>(null);

  const guardStats = useLatestGuard();
  const loadStats = useCallback(() => {
    const isLatest = guardStats();
    setStats(null); setStatsErr(false);
    api.paymentsStats(Number(days))
      .then((s) => { if (isLatest()) setStats(s); })
      .catch(() => { if (isLatest()) setStatsErr(true); });
  }, [days, guardStats]);
  useEffect(loadStats, [loadStats]);

  const guardRows = useLatestGuard();
  const loadRows = useCallback(() => {
    const isLatest = guardRows();
    setRows(null); setErr("");
    api.payments({
      status: status || undefined, gateway: gateway || undefined,
      user_id: userId.trim() ? Number(userId.trim()) : undefined,
      since: from ? new Date(from + "T00:00:00").toISOString() : undefined,
      until: to ? new Date(to + "T23:59:59").toISOString() : undefined,
      limit: PAGE, offset: page * PAGE,
    }).then((r) => { if (isLatest()) { setRows(r.items); setTotal(r.total); } })
      .catch((e) => { if (isLatest()) { setRows([]); setErr(String(e)); } });
  }, [status, gateway, userId, from, to, page, guardRows]);
  useEffect(loadRows, [loadRows]);
  // Reset to first page whenever a filter changes.
  useEffect(() => { setPage(0); }, [status, gateway, userId, from, to]);

  async function refund(tx: Payment) {
    const retry = tx.status === "refund_pending";
    const ask = retry
      ? `Повторить возврат денег для ${tx.product} (${fmtMoney(tx.amount, tx.currency)})? Доступ уже отозван.`
      : `Вернуть платёж ${tx.product} (${fmtMoney(tx.amount, tx.currency)})? Списанное будет отозвано.`;
    if (!confirm(ask)) return;
    setBusy(tx.tx_id); setNote("");
    try {
      const r = await api.refund(tx.tx_id);
      if (r.ok) {
        const g = r.gateway_refund ?? "";
        const money = g.startsWith("refunded") ? "деньги возвращены в шлюзе"
          : g === "stars" ? "Stars возвращены" : g === "skip" ? "в шлюзе возвращать нечего" : g;
        setNote(`✅ Возврат завершён · доступ отозван · ${money}`);
      } else {
        setNote(`⚠️ Доступ отозван, но возврат денег НЕ прошёл (${r.gateway_refund}). Статус: ${r.status}. Нажмите «Повторить», когда устраните причину.`);
      }
      loadRows(); loadStats();
      setDetail((d) => (d && d.tx_id === tx.tx_id ? { ...d, status: r.status ?? d.status } : d));
    } catch (e) { setNote(`⚠️ ${e instanceof Error ? e.message : String(e)}`); }
    finally { setBusy(""); }
  }

  const pageCount = Math.max(1, Math.ceil(total / PAGE));
  const t = stats?.totals;
  const conv = t && t.count ? Math.round(t.paid / t.count * 100) : 0;
  const refundsTotal = (t?.refunded ?? 0) + (t?.refund_pending ?? 0);
  const revCurrencies = stats ? Object.entries(stats.revenue_by_currency).sort((a, b) => b[1] - a[1]) : [];
  const trendMax = Math.max(1, ...(stats?.revenue_by_day ?? []).map((d) => trend === "count" ? d.count : d.amount));
  const gwMaxPaid = Math.max(1, ...(stats?.by_gateway ?? []).map((g) => g.paid));
  const filtersOn = !!(status || gateway || userId || from || to);

  return (
    <div>
      <div className="section-head">
        <div>
          <h1 className="page-title">Платежи</h1>
          <p className="page-sub">Транзакции, выручка по шлюзам и валютам, конверсия и возвраты. Все метрики считаются на стороне БД по всему окну — точны при любом объёме.</p>
        </div>
        <div className="form-row" style={{ gap: "var(--sp-2)", margin: 0 }}>
          <Select width={140} ariaLabel="Период" value={days} onChange={setDays} options={WINDOWS} />
          <button className="btn ghost sm" onClick={() => { loadStats(); loadRows(); }}><span className="ms sm">refresh</span> Обновить</button>
        </div>
      </div>

      {note && (
        <p className={note.startsWith("✅") ? "note-ok" : "note-err"}>
          <span className="ms sm">{note.startsWith("✅") ? "check_circle" : "warning"}</span>{note}
          <button className="btn ghost sm" onClick={() => setNote("")} style={{ marginLeft: "auto" }}>×</button>
        </p>
      )}
      {err && (<p className="note-err"><span className="ms sm">error</span>{err}<button className="btn ghost sm" onClick={() => setErr("")} style={{ marginLeft: "auto" }}>×</button></p>)}

      <div className="page-stack">
        {/* KPIs */}
        <div className="metrics">
          <Metric icon="receipt_long" label="Транзакций" value={statsErr ? "н/д" : fmtInt(t?.count)} />
          <Metric icon="check_circle" label="Оплачено" value={fmtInt(t?.paid)} tone="purple" />
          <Metric icon="percent" label="Конверсия" value={conv} suffix="%" />
          <Metric icon="group" label="Платящих" value={fmtInt(stats?.paid_users)} small />
          <Metric icon="error" label="Ошибки" value={fmtInt(t?.failed)} tone={t?.failed ? "danger" : undefined} small />
          <Metric icon="undo" label="Возвраты" value={fmtInt(refundsTotal)} tone={refundsTotal ? "danger" : undefined} small />
          <Metric icon="hourglass_top" label="В ожидании" value={fmtInt(t?.pending)} small />
          <Metric icon="account_balance" label="Шлюзов" value={fmtInt(stats?.by_gateway.length)} small />
        </div>

        {/* Revenue: per-currency totals + daily trend */}
        <div className="panel">
          <div className="section-head" style={{ margin: 0, marginBottom: "var(--sp-3)" }}>
            <div className="panel-title sm" style={{ margin: 0 }}><span className="ms sm">payments</span> Выручка за период</div>
            <div className="chip-row" style={{ margin: 0 }}>
              <button className="chip" style={{ cursor: "pointer", borderColor: trend === "count" ? "var(--accent)" : undefined }} onClick={() => setTrend("count")}>Оплаты, шт</button>
              <button className="chip" style={{ cursor: "pointer", borderColor: trend === "amount" ? "var(--accent)" : undefined }} onClick={() => setTrend("amount")}>Сумма (смешанные валюты)</button>
            </div>
          </div>

          {revCurrencies.length === 0 ? (
            <p className="cfg-hint">За выбранный период оплат не было.</p>
          ) : (
            <div className="chip-row" style={{ marginBottom: "var(--sp-3)" }}>
              {revCurrencies.map(([cur, sum]) => (
                <span key={cur} className="chip">
                  <span className="muted">выручка</span><b>{fmtMoney(sum, cur)}</b>
                  {stats?.avg_check_by_currency[cur] != null && (
                    <span className="muted" style={{ marginLeft: 6 }}>· чек {fmtMoney(stats.avg_check_by_currency[cur], cur)}</span>
                  )}
                </span>
              ))}
            </div>
          )}

          {stats && stats.revenue_by_day.length > 0 ? (
            <div style={{ display: "flex", alignItems: "flex-end", gap: 3, height: 120, padding: "8px 0" }}>
              {stats.revenue_by_day.map((d) => {
                const v = trend === "count" ? d.count : d.amount;
                const h = Math.max(2, Math.round(v / trendMax * 100));
                return (
                  <div key={d.date} title={`${d.date}: ${trend === "count" ? `${d.count} оплат` : fmtInt(d.amount)}`}
                    style={{ flex: 1, minWidth: 2, height: `${h}%`, background: "var(--accent)", borderRadius: "3px 3px 0 0", opacity: 0.85 }} />
                );
              })}
            </div>
          ) : <SkeletonBar />}
          {trend === "amount" && <p className="cfg-hint" style={{ marginTop: 6 }}><span className="ms sm" style={{ verticalAlign: "-3px" }}>info</span> Сумма складывается из разных валют (Stars + минорные единицы карт/СБП) — для точной картины смотрите разбивку по валютам выше.</p>}
        </div>

        {/* Gateway breakdown — accurate over the window */}
        <div className="panel">
          <div className="panel-title sm"><span className="ms sm">hub</span> Платёжные шлюзы</div>
          {!stats ? <SkeletonRows /> : stats.by_gateway.length === 0 ? (
            <EmptyState icon="account_balance" title="Нет операций" desc="За выбранный период ни один шлюз не использовался." />
          ) : (
            <div className="table-wrap" tabIndex={0} style={{ border: "none" }}>
              <table className="tbl">
                <thead><tr><th>Шлюз</th><th style={{ textAlign: "right" }}>Транзакций</th><th>Success</th><th style={{ width: "32%" }}>Оплачено</th><th>Выручка</th><th>Последняя</th></tr></thead>
                <tbody>
                  {stats.by_gateway.map((g) => (
                    <tr key={g.gateway} style={{ cursor: "pointer" }} onClick={() => { setGateway(g.gateway); document.querySelector(".tx-panel")?.scrollIntoView({ behavior: "smooth" }); }}>
                      <td><b>{GATEWAY_LABEL[g.gateway] ?? g.gateway}</b></td>
                      <td className="muted" style={{ textAlign: "right" }}>{fmtInt(g.count)}</td>
                      <td><span className={"pill " + (g.success_pct >= 80 ? "ok" : g.success_pct >= 50 ? "warn" : "danger")}>{g.success_pct}%</span></td>
                      <td>
                        <div className="barrow" style={{ margin: 0 }}>
                          <span className="track"><span className="fill" style={{ width: `${g.paid / gwMaxPaid * 100}%` }} /></span>
                          <span className="val">{fmtInt(g.paid)}</span>
                        </div>
                      </td>
                      <td style={{ whiteSpace: "nowrap" }}>
                        {Object.keys(g.revenue_by_currency).length === 0 ? <span className="muted">—</span>
                          : Object.entries(g.revenue_by_currency).map(([c, s]) => <div key={c} style={{ fontSize: 12.5 }}>{fmtMoney(s, c)}</div>)}
                      </td>
                      <td className="muted" style={{ whiteSpace: "nowrap" }}>{ago(g.last_at)}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          )}
        </div>

        {/* Payment systems configuration (credentials) */}
        <GatewayConfig />

        {/* Transactions */}
        <div className="panel tx-panel">
          <div className="section-head" style={{ margin: 0, marginBottom: "var(--sp-3)" }}>
            <div className="panel-title sm" style={{ margin: 0 }}><span className="ms sm">format_list_bulleted</span> Транзакции {rows && <span className="pill muted">{fmtInt(total)}</span>}</div>
            <button className="btn ghost sm" onClick={() => api.exportPaymentsCsv().catch((e) => setErr(String(e)))}><span className="ms sm">download</span> Экспорт CSV</button>
          </div>

          <div className="chip-row" style={{ marginBottom: "var(--sp-3)" }}>
            <span className="muted" style={{ fontSize: 12, alignSelf: "center" }}>Быстро:</span>
            <button className="chip" style={{ cursor: "pointer" }}
              onClick={() => { const d = ymd(new Date()); setFrom(d); setTo(d); }}>Сегодня</button>
            <button className="chip" style={{ cursor: "pointer" }}
              onClick={() => { setFrom(ymd(new Date(Date.now() - 6 * 86400000))); setTo(ymd(new Date())); }}>7 дней</button>
            <button className="chip" style={{ cursor: "pointer" }}
              onClick={() => setStatus("refunded")}>Возвраты</button>
            <button className="chip" style={{ cursor: "pointer" }}
              onClick={() => setStatus("failed")}>Ошибки</button>
            <button className="chip" style={{ cursor: "pointer" }}
              onClick={() => setStatus("refund_pending")}>Возврат завис</button>
          </div>

          <div className="toolbar">
            {/* FIX: AUDIT12-M13/M14 - aria-label + maxLength 32 on user id lookup. */}
            <input className="grow" type="number" placeholder="ID пользователя" value={userId} onChange={(e) => setUserId(e.target.value)} style={{ maxWidth: 200 }} min={0} max={10_000_000} aria-label="ID пользователя" />
            <Select ariaLabel="Статус" value={status} onChange={setStatus} options={STATUSES.map((s) => ({ value: s, label: s ? (STATUS_LABEL[s] ?? s) : "Все статусы" }))} />
            <Select ariaLabel="Шлюз" value={gateway} onChange={setGateway} options={GATEWAYS.map((g) => ({ value: g, label: g ? (GATEWAY_LABEL[g] ?? g) : "Все шлюзы" }))} />
            <DateField style={{ width: 160 }} value={from} onChange={setFrom} title="С даты" />
            <DateField style={{ width: 160 }} value={to} onChange={setTo} title="По дату" />
            {filtersOn && <button className="btn ghost sm" onClick={() => { setStatus(""); setGateway(""); setUserId(""); setFrom(""); setTo(""); }}><span className="ms sm">close</span> Сбросить</button>}
          </div>

          {rows === null ? <SkeletonRows />
            : rows.length === 0 ? (
              <EmptyState icon="receipt_long" title="Платежей не найдено"
                desc={filtersOn ? "Под выбранные фильтры транзакций нет. Измените или сбросьте фильтры." : "Транзакций пока нет."} />
            ) : (
              <>
                <div className="table-wrap sticky" tabIndex={0} style={{ border: "none" }}>
                  <table className="tbl">
                    <thead><tr><th>Дата</th><th>User</th><th>Продукт</th><th style={{ textAlign: "right" }}>Сумма</th><th>Шлюз</th><th>Статус</th><th style={{ width: 130 }}></th></tr></thead>
                    <tbody>
                      {rows.map((tx) => (
                        <tr key={tx.tx_id} style={{ cursor: "pointer" }} onClick={() => setDetail(tx)}>
                          <td className="muted" style={{ whiteSpace: "nowrap" }}>{fmtDate(tx.created_at)}</td>
                          <td onClick={(e) => e.stopPropagation()}>
                            <a className="user-link code-key" href={`#/users?focus=${tx.user_id}`}>{tx.user_id}</a>
                          </td>
                          <td>{tx.product}{tx.duration_months ? <span className="muted"> · {tx.duration_months} мес</span> : tx.qty ? <span className="muted"> · ×{tx.qty}</span> : ""}</td>
                          <td style={{ whiteSpace: "nowrap", textAlign: "right" }}>{fmtMoney(tx.amount, tx.currency)}</td>
                          <td className="muted">{GATEWAY_LABEL[tx.gateway] ?? tx.gateway}</td>
                          <td><span className={"pill " + (STATUS_CLASS[tx.status] ?? "muted")}>{STATUS_LABEL[tx.status] ?? tx.status}</span></td>
                          <td onClick={(e) => e.stopPropagation()}>
                            {(tx.status === "paid" || tx.status === "refund_pending") && (
                              <button className="btn danger sm" disabled={busy === tx.tx_id} onClick={() => refund(tx)}>
                                {busy === tx.tx_id ? "…" : tx.status === "refund_pending" ? "Повторить" : "Возврат"}
                              </button>
                            )}
                          </td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                </div>
                {pageCount > 1 && (
                  <div className="pager">
                    <span className="muted">{fmtInt(total)} транзакций · стр. {page + 1} из {pageCount}</span>
                    <div className="pg-nums">
                      <button className="btn ghost sm" disabled={page === 0} onClick={() => setPage((p) => p - 1)}>←</button>
                      <button className="btn ghost sm" disabled={page >= pageCount - 1} onClick={() => setPage((p) => p + 1)}>→</button>
                    </div>
                  </div>
                )}
              </>
            )}
        </div>
      </div>

      {detail && (
        <TxDetail tx={detail} onClose={() => setDetail(null)} onRefund={() => refund(detail)} busy={busy === detail.tx_id}
          onUser={() => { setUserId(String(detail.user_id)); setDetail(null); document.querySelector(".tx-panel")?.scrollIntoView({ behavior: "smooth" }); }} />
      )}
    </div>
  );
}

// ---------- transaction detail drawer ----------
function TxDetail({ tx, onClose, onRefund, onUser, busy }: {
  tx: Payment; onClose: () => void; onRefund: () => void; onUser: () => void; busy: boolean;
}) {
  const refundable = tx.status === "paid" || tx.status === "refund_pending";
  return (
    <Modal title={`Транзакция · ${tx.product}`} icon="receipt_long" onClose={onClose} wide
      footer={<>
        <button className="btn ghost" onClick={onUser}><span className="ms sm">person</span> Платежи пользователя</button>
        {refundable && (
          <button className="btn danger spacer" disabled={busy} onClick={onRefund}>
            <span className="ms sm">undo</span> {busy ? "…" : tx.status === "refund_pending" ? "Повторить возврат" : "Вернуть платёж"}
          </button>
        )}
      </>}>
      <div className="form-grid">
        <KV k="Статус"><span className={"pill " + (STATUS_CLASS[tx.status] ?? "muted")}>{STATUS_LABEL[tx.status] ?? tx.status}</span></KV>
        <KV k="Сумма"><b>{fmtMoney(tx.amount, tx.currency)}</b></KV>
        <KV k="Шлюз">{GATEWAY_LABEL[tx.gateway] ?? tx.gateway}</KV>
        <KV k="Пользователь"><a className="user-link code-key" href={`#/users?focus=${tx.user_id}`}>{tx.user_id}</a></KV>
        <KV k="Продукт">{tx.product}</KV>
        {tx.duration_months != null && <KV k="Длительность">{tx.duration_months} мес</KV>}
        {tx.qty != null && <KV k="Количество">×{tx.qty}</KV>}
        {tx.credits_added != null && <KV k="Начислено ✨">{fmtInt(tx.credits_added)}</KV>}
        <KV k="Создана">{fmtDate(tx.created_at)}</KV>
        {tx.paid_at && <KV k="Оплачена">{fmtDate(tx.paid_at)}</KV>}
        <KV k="ID транзакции"><span className="code-key" style={{ fontSize: 11 }}>{tx.tx_id}</span></KV>
        {tx.gateway_tx_id && <KV k="Ссылка шлюза (сверка)"><span className="code-key" style={{ fontSize: 11 }}>{tx.gateway_tx_id}</span></KV>}
      </div>
      <p className="cfg-hint" style={{ marginTop: "var(--sp-4)" }}>
        <span className="ms sm" style={{ verticalAlign: "-3px" }}>info</span>{" "}
        Возврат двухфазный: сначала отзывается доступ (идемпотентно, без двойного отзыва), затем выполняется возврат денег в шлюзе. Если шлюз недоступен, статус остаётся «возврат…» и операцию можно повторить.
      </p>
    </Modal>
  );
}

// ---------- payment-gateway credentials ----------
function GatewayConfig() {
  const [gws, setGws] = useState<GatewayStatus[] | null>(null);
  const [open, setOpen] = useState(false);
  const [drafts, setDrafts] = useState<Record<string, string>>({});
  const [msg, setMsg] = useState("");
  const [busy, setBusy] = useState(false);

  const load = useCallback(() => {
    api.paymentGateways().then(setGws).catch((e) => setMsg(String(e)));
  }, []);
  useEffect(() => { if (open && gws === null) load(); }, [open, gws, load]);

  async function save() {
    const fields = Object.fromEntries(Object.entries(drafts).filter(([, v]) => v.trim()));
    if (Object.keys(fields).length === 0) { setMsg("Нечего сохранять — заполните поля."); return; }
    setBusy(true); setMsg("");
    try {
      const r = await api.setPaymentGateways(fields);
      setMsg(`✅ Сохранено: ${r.changed.length} полей`);
      setDrafts({}); setGws(null); load();
    } catch (e) { setMsg(`⚠️ ${e instanceof Error ? e.message : String(e)}`); }
    finally { setBusy(false); }
  }

  async function clearField(field: string) {
    if (!confirm("Сбросить значение к .env по умолчанию?")) return;
    setBusy(true); setMsg("");
    try {
      await api.clearPaymentGateway(field);
      setMsg("✅ Сброшено к .env");
      setGws(null); load();
    } catch (e) { setMsg(`⚠️ ${e instanceof Error ? e.message : String(e)}`); }
    finally { setBusy(false); }
  }

  const SRC_LABEL: Record<string, string> = { db: "из админки", env: "из .env", none: "не задано" };

  return (
    <div className="panel">
      <div className="section-head" style={{ margin: 0 }}>
        <div className="panel-title sm" style={{ margin: 0 }}>
          <span className="ms sm">tune</span> Платёжные системы
          <span className="muted" style={{ fontWeight: 400, fontSize: 12, marginLeft: 8 }}>
            API-ключи Stripe, ЮКассы, CryptoBot, СБП
          </span>
        </div>
        <button className="btn ghost sm" onClick={() => setOpen((o) => !o)}>
          <span className="ms sm">{open ? "expand_less" : "expand_more"}</span>
          {open ? "Свернуть" : "Настроить"}
        </button>
      </div>

      {open && (
        <>
          {msg && (
            <p className={msg.startsWith("✅") ? "note-ok" : "note-err"} style={{ marginTop: "var(--sp-3)" }}>
              <span className="ms sm">{msg.startsWith("✅") ? "check_circle" : "warning"}</span>{msg}
              <button className="btn ghost sm" onClick={() => setMsg("")} style={{ marginLeft: "auto" }}>×</button>
            </p>
          )}
          <p className="cfg-hint" style={{ marginTop: "var(--sp-3)" }}>
            <span className="ms sm" style={{ verticalAlign: "-3px" }}>lock</span>{" "}
            Секреты хранятся в БД в зашифрованном виде и применяются без перезапуска. Значение из админки переопределяет .env; «Сбросить» возвращает к .env. Telegram Stars настраивается через токен бота и не требует ключей здесь.
          </p>

          {gws === null ? <SkeletonRows /> : (
            <div className="page-stack" style={{ marginTop: "var(--sp-3)" }}>
              {gws.map((g) => (
                <div key={g.id} className="panel" style={{ margin: 0, background: "var(--panel-2)" }}>
                  <div className="panel-title sm" style={{ margin: "0 0 var(--sp-3)" }}>
                    {g.label}
                    <span className={"pill " + (g.ready ? "ok" : "muted")} style={{ marginLeft: 8 }}>
                      {g.ready ? "настроен" : "не настроен"}
                    </span>
                  </div>
                  {g.fields.map((f) => (
                    <div key={f.field} className="gw-field">
                      <div className="gw-field-head">
                        <span>{f.label}</span>
                        <span className="muted" style={{ fontSize: 11 }}>
                          {SRC_LABEL[f.source]}{f.configured && f.secret ? ` · ${f.value}` : f.configured && !f.secret ? ` · ${f.value}` : ""}
                        </span>
                      </div>
                      <div className="form-row" style={{ margin: 0, gap: "var(--sp-2)" }}>
                        {/* FIX: AUDIT12-M13/M14 - aria-label + maxLength 512 on gateway secret. */}
                        <input className="grow" type={f.secret ? "password" : "text"} autoComplete="off"
                          maxLength={512} aria-label={`Секрет для ${f.label}`}
                          placeholder={f.configured ? "Заменить значение…" : "Ввести значение…"}
                          value={drafts[f.field] ?? ""}
                          onChange={(e) => setDrafts((d) => ({ ...d, [f.field]: e.target.value }))} />
                        {f.source === "db" && (
                          <button className="btn ghost sm" disabled={busy} onClick={() => clearField(f.field)}
                            title="Сбросить к .env"><span className="ms sm">restart_alt</span></button>
                        )}
                      </div>
                    </div>
                  ))}
                </div>
              ))}
              <div className="form-row" style={{ margin: 0, justifyContent: "flex-end" }}>
                <button className="btn" disabled={busy} onClick={save}>
                  <span className="ms sm">save</span> Сохранить
                </button>
              </div>
            </div>
          )}
        </>
      )}
    </div>
  );
}

// ---------- shared ----------
function KV({ k, children }: { k: string; children: React.ReactNode }) {
  return <div className="form-row" style={{ justifyContent: "space-between", margin: 0, fontSize: 13, padding: "6px 0", borderBottom: "1px solid var(--border)" }}><span className="muted">{k}</span><span style={{ fontWeight: 600, textAlign: "right" }}>{children}</span></div>;
}
function Metric({ icon, label, value, suffix, tone, small }: { icon: string; label: string; value: number | string; suffix?: string; tone?: "purple" | "danger"; small?: boolean }) {
  return (
    <div className={"metric" + (tone ? " " + tone : "")}>
      <span className="glow" />
      <div className="top"><span className="lbl">{label}</span><span className="ms sm">{icon}</span></div>
      <div><div className="num" style={small ? { fontSize: 16 } : undefined}>{typeof value === "number" ? value.toLocaleString("ru") : value}{suffix && <small>{suffix}</small>}</div></div>
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
function SkeletonRows() {
  return <div className="page-stack" style={{ marginTop: "var(--sp-2)" }}>{Array.from({ length: 5 }).map((_, i) => <div key={i} className="skeleton" style={{ height: 44 }} />)}</div>;
}
function SkeletonBar() {
  return <div style={{ display: "flex", alignItems: "flex-end", gap: 3, height: 120 }}>{Array.from({ length: 24 }).map((_, i) => <div key={i} className="skeleton" style={{ flex: 1, height: `${20 + (i * 37) % 70}%` }} />)}</div>;
}
