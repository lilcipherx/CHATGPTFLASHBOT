import { useEffect, useMemo, useState } from "react";
import { adminFetch, logout } from "../api";  // FIX: F42 - logout() on 401
import { Select } from "../components/Select";
import { Modal } from "../components/Modal";

// JSON wrapper over the shared `adminFetch` — inherits credential handling plus the
// transparent token refresh on 401 (no premature "session expired" mid-session).
async function gReq<T>(path: string, init: RequestInit = {}): Promise<T> {
  const res = await adminFetch(path, {
    ...init,
    headers: { ...(init.headers ?? {}), "Content-Type": "application/json" },
  });
  if (res.status === 401) { logout(); window.dispatchEvent(new CustomEvent("admin:unauth")); throw new Error("session expired"); }  // FIX: F42 + AUDIT-H8
  if (!res.ok) throw new Error(`API ${res.status}`);
  return res.json() as Promise<T>;
}

interface Contest {
  id: number; title: string; description: string | null; status: string;
  winners_count: number; prize_type: string; prize_amount: number;
  entrants: number; created_at: string | null; drawn_at: string | null;
}

interface EntrantRow { user_id: number; entered_at: string | null }

type ContestBody = {
  title: string; description: string | null; winners_count: number;
  prize_type: string; prize_amount: number;
};

const contestsApi = {
  list: () => gReq<Contest[]>("/contests"),
  create: (body: ContestBody) =>
    gReq<Contest>("/contests", { method: "POST", body: JSON.stringify(body) }),
  update: (id: number, body: ContestBody) =>
    gReq<Contest>(`/contests/${id}`, { method: "PUT", body: JSON.stringify(body) }),
  draw: (id: number) => gReq<{ ok: boolean; id: number; winners: number[] }>(`/contests/${id}/draw`, { method: "POST" }),
  close: (id: number) => gReq<{ ok: boolean; id: number; status: string }>(`/contests/${id}/close`, { method: "POST" }),
  entrants: (id: number) => gReq<{ entrants: EntrantRow[] }>(`/contests/${id}/entrants`),
  winners: (id: number) => gReq<{ winners: number[]; drawn_at: string | null }>(`/contests/${id}/winners`),
};

const STATUS_META: Record<string, { label: string; cls: string }> = {
  open: { label: "Приём заявок", cls: "ok" },
  closed: { label: "Закрыт", cls: "muted" },
  drawn: { label: "Разыгран", cls: "pro" },
};
const fmtDate = (s: string | null) => (s ? s.slice(0, 19).replace("T", " ") : "—");

// Auto-prize vocabulary — must mirror core.services.contests.PRIZE_TYPES. The unit
// label is what appears in the amount field's suffix; "0" amount = notify-only.
const PRIZE_OPTS = [
  { value: "credits", label: "Кредиты ✨", unit: "✨" },
  { value: "image", label: "Пакет фото 🖼", unit: "🖼" },
  { value: "video", label: "Пакет видео 🎬", unit: "🎬" },
  { value: "music", label: "Пакет музыки 🎵", unit: "🎵" },
];
const prizeUnit = (t: string) => PRIZE_OPTS.find((o) => o.value === t)?.unit ?? "✨";

// Shared prize editor — auto-grant on draw. Amount 0 means no auto-prize (the bot
// only notifies winners and the admin grants manually).
function PrizeFields({ type, amount, onType, onAmount }: {
  type: string; amount: number; onType: (v: string) => void; onAmount: (v: number) => void;
}) {
  return (
    <div className="row" style={{ gap: "var(--sp-3)", alignItems: "flex-end", marginBottom: "var(--sp-4)" }}>
      <div className="cfg-field" style={{ minWidth: 180 }}>
        <span className="cfg-cap">Приз победителю</span>
        <Select ariaLabel="Тип приза" value={type} onChange={onType}
          options={PRIZE_OPTS.map((o) => ({ value: o.value, label: o.label }))} />
      </div>
      <div className="cfg-field" style={{ maxWidth: 160 }}>
        <span className="cfg-cap">Сколько ({prizeUnit(type)})</span>
        {/* FIX: AUDIT12-M13/M14 - max 10_000_000 ceiling on contest prize amount. */}
        <input type="number" min={0} max={10_000_000} value={amount}
          aria-label="Количество приза"
          onChange={(e) => onAmount(Math.max(0, Number(e.target.value) || 0))} />
      </div>
    </div>
  );
}

export function Contests() {
  const [rows, setRows] = useState<Contest[] | null>(null);
  const [msg, setMsg] = useState("");
  const [busy, setBusy] = useState<number | null>(null);
  const [q, setQ] = useState("");
  const [stFilter, setStFilter] = useState("");
  const [createOpen, setCreateOpen] = useState(false);
  const [result, setResult] = useState<{ contest: Contest; winners: number[] } | null>(null);
  const [editContest, setEditContest] = useState<Contest | null>(null);
  const [entrantsFor, setEntrantsFor] = useState<Contest | null>(null);

  async function viewWinners(c: Contest) {
    setBusy(c.id);
    try {
      const r = await contestsApi.winners(c.id);
      setResult({ contest: c, winners: r.winners });
    } catch (e) { setMsg(String(e)); }
    finally { setBusy(null); }
  }

  const load = () => contestsApi.list().then(setRows).catch((e) => { setRows([]); setMsg(String(e)); });
  useEffect(() => { load(); /* eslint-disable-next-line */ }, []);

  const filtered = useMemo(() => {
    const term = q.trim().toLowerCase();
    return (rows ?? []).filter((r) => {
      if (term && !(r.title.toLowerCase().includes(term) || String(r.id).includes(term))) return false;
      if (stFilter && r.status !== stFilter) return false;
      return true;
    });
  }, [rows, q, stFilter]);

  const kpi = useMemo(() => {
    const all = rows ?? [];
    const participants = all.reduce((s, c) => s + c.entrants, 0);
    return {
      total: all.length,
      active: all.filter((c) => c.status === "open").length,
      finished: all.filter((c) => c.status === "drawn" || c.status === "closed").length,
      participants,
      avg: all.length ? Math.round(participants / all.length) : 0,
    };
  }, [rows]);

  async function onDraw(c: Contest) {
    if (!confirm(`Провести розыгрыш «${c.title}»?\nУчастников: ${c.entrants}. Будет выбрано до ${c.winners_count} случайных победителей. Действие необратимо.`)) return;
    setBusy(c.id);
    try {
      const r = await contestsApi.draw(c.id);
      setResult({ contest: c, winners: r.winners });
      setMsg(`✅ Розыгрыш «${c.title}» проведён: ${r.winners.length} победителей`);
      await load();
    } catch (e) { setMsg(String(e)); }
    finally { setBusy(null); }
  }
  async function onClose(c: Contest) {
    if (!confirm(`Закрыть приём заявок для «${c.title}»? Новые участники не смогут присоединиться.`)) return;
    setBusy(c.id);
    try { await contestsApi.close(c.id); setMsg(`✅ Конкурс «${c.title}» закрыт`); await load(); }
    catch (e) { setMsg(String(e)); }
    finally { setBusy(null); }
  }

  return (
    <div>
      <h1 className="page-title">Конкурсы</h1>
      <p className="page-sub">Создавайте розыгрыши, следите за участниками и выбирайте случайных победителей.</p>

      {msg && (
        <p className={msg.startsWith("✅") ? "note-ok" : "note-err"}>
          <span className="ms sm">{msg.startsWith("✅") ? "check_circle" : "error"}</span>{msg}
          <button className="btn ghost sm" onClick={() => setMsg("")}>×</button>
        </p>
      )}

      <div className="page-stack">
        <div className="metrics">
          <Metric icon="emoji_events" label="Всего конкурсов" value={kpi.total} />
          <Metric icon="play_circle" label="Активных" value={kpi.active} tone="purple" />
          <Metric icon="check_circle" label="Завершённых" value={kpi.finished} />
          <Metric icon="group" label="Участников (Σ)" value={kpi.participants} />
          <Metric icon="leaderboard" label="Ср. участников" value={kpi.avg} />
        </div>

        <div className="panel">
          <div className="toolbar">
            {/* FIX: AUDIT12-M13/M14 - aria-label + maxLength 255 on contest search. */}
            <input className="grow" placeholder="Поиск по названию или ID" value={q} onChange={(e) => setQ(e.target.value)} maxLength={255} aria-label="Поиск конкурса" />
            <Select ariaLabel="Статус" value={stFilter} onChange={setStFilter}
              options={[{ value: "", label: "Все статусы" }, { value: "open", label: "Приём заявок" },
                { value: "closed", label: "Закрытые" }, { value: "drawn", label: "Разыгранные" }]} />
            <button className="btn spacer" onClick={() => setCreateOpen(true)}>
              <span className="ms sm">add</span> Создать конкурс
            </button>
          </div>

          {rows === null ? (
            <div className="table-wrap" tabIndex={0} style={{ border: "none" }}>
              <table className="tbl"><tbody>
                {Array.from({ length: 4 }).map((_, i) => (
                  <tr key={i}><td><div className="skeleton-row" style={{ minHeight: 48 }} /></td></tr>
                ))}
              </tbody></table>
            </div>
          ) : filtered.length === 0 ? (
            rows.length === 0 ? (
              <div className="empty-state">
                <div className="es-icon"><span className="ms">emoji_events</span></div>
                <p className="es-title">Конкурсов пока нет</p>
                <p className="es-desc">Создайте первый розыгрыш — задайте название и число победителей, а когда наберутся участники, проведите случайный розыгрыш в один клик.</p>
                <button className="btn" style={{ marginTop: "var(--sp-2)" }} onClick={() => setCreateOpen(true)}>
                  <span className="ms sm">add</span> Создать первый конкурс
                </button>
              </div>
            ) : <div className="empty">Под фильтры ничего не подходит.</div>
          ) : (
            <div className="table-wrap" tabIndex={0} style={{ border: "none" }}>
              <table className="tbl">
                <thead>
                  <tr><th>Название</th><th>Статус</th><th>Участников</th><th>Победителей</th><th>Приз</th><th>Создан</th><th>Разыгран</th><th></th></tr>
                </thead>
                <tbody>
                  {filtered.map((c) => {
                    const st = STATUS_META[c.status] ?? { label: c.status, cls: "muted" };
                    return (
                      <tr key={c.id}>
                        <td>
                          <div style={{ fontWeight: 600 }}>{c.title}</div>
                          {c.description && <div className="muted clamp-2" style={{ fontSize: 12, maxWidth: 320 }}>{c.description}</div>}
                        </td>
                        <td><span className={"pill " + st.cls}>{st.label}</span></td>
                        <td><b style={{ fontVariantNumeric: "tabular-nums" }}>{c.entrants.toLocaleString("ru")}</b></td>
                        <td className="muted">{c.winners_count}</td>
                        <td className="muted" style={{ whiteSpace: "nowrap" }}>
                          {c.prize_amount > 0 ? `${c.prize_amount} ${prizeUnit(c.prize_type)}` : "—"}
                        </td>
                        <td className="muted" style={{ whiteSpace: "nowrap" }}>{fmtDate(c.created_at)}</td>
                        <td className="muted" style={{ whiteSpace: "nowrap" }}>{fmtDate(c.drawn_at)}</td>
                        <td>
                          <div className="cell-actions">
                            {c.status === "drawn" ? (
                              <button className="btn sm" disabled={busy === c.id} title="Показать победителей" onClick={() => viewWinners(c)}>
                                <span className="ms sm">workspace_premium</span> Победители
                              </button>
                            ) : (
                              <button className="btn sm" disabled={busy === c.id}
                                title="Случайный розыгрыш" onClick={() => onDraw(c)}>
                                <span className="ms sm">casino</span> Розыгрыш
                              </button>
                            )}
                            <button className="btn ghost sm" disabled={busy === c.id} title="Участники" onClick={() => setEntrantsFor(c)}>
                              <span className="ms sm">group</span>
                            </button>
                            {c.status !== "drawn" && (
                              <button className="btn ghost sm" disabled={busy === c.id} title="Редактировать" onClick={() => setEditContest(c)}>
                                <span className="ms sm">edit</span>
                              </button>
                            )}
                            <button className="btn ghost sm danger" disabled={busy === c.id || c.status !== "open"}
                              title={c.status !== "open" ? "Доступно только для активных" : "Закрыть приём заявок"} onClick={() => onClose(c)}>
                              <span className="ms sm">lock</span>
                            </button>
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
      </div>

      {createOpen && (
        <CreateContestModal onClose={() => setCreateOpen(false)}
          onDone={(m) => { setMsg(m); setCreateOpen(false); load(); }} />
      )}
      {editContest && (
        <EditContestModal contest={editContest} onClose={() => setEditContest(null)}
          onDone={(m) => { setMsg(m); setEditContest(null); load(); }} />
      )}
      {entrantsFor && <EntrantsModal contest={entrantsFor} onClose={() => setEntrantsFor(null)} />}
      {result && <ResultModal contest={result.contest} winners={result.winners} onClose={() => setResult(null)} />}
    </div>
  );
}

// ---- Edit an existing (not-yet-drawn) contest ------------------------------
function EditContestModal({ contest, onClose, onDone }: {
  contest: Contest; onClose: () => void; onDone: (msg: string) => void;
}) {
  const [title, setTitle] = useState(contest.title);
  const [description, setDescription] = useState(contest.description ?? "");
  const [winners, setWinners] = useState(contest.winners_count);
  const [prizeType, setPrizeType] = useState(contest.prize_type ?? "credits");
  const [prizeAmount, setPrizeAmount] = useState(contest.prize_amount ?? 0);
  const [busy, setBusy] = useState(false);
  const [err, setErr] = useState("");
  const dirty = title !== contest.title || description !== (contest.description ?? "")
    || winners !== contest.winners_count || prizeType !== contest.prize_type
    || prizeAmount !== contest.prize_amount;

  async function submit() {
    if (!title.trim()) { setErr("Введите название конкурса."); return; }
    setBusy(true); setErr("");
    try {
      await contestsApi.update(contest.id, {
        title: title.trim(), description: description.trim() || null,
        winners_count: Math.max(1, winners), prize_type: prizeType, prize_amount: prizeAmount,
      });
      onDone(`✅ Конкурс «${title.trim()}» обновлён`);
    } catch (e) { setErr(e instanceof Error ? e.message : String(e)); }
    finally { setBusy(false); }
  }

  return (
    <Modal title={`Редактировать · ${contest.title}`} icon="edit" onClose={onClose}
      footer={<button className="btn" onClick={submit} disabled={busy || !dirty}>
        <span className="ms sm">save</span> {busy ? "Сохранение…" : "Сохранить"}
      </button>}>
      {err && <p className="note-err"><span className="ms sm">error</span>{err}</p>}
      <div className="cfg-field" style={{ marginBottom: "var(--sp-4)" }}>
        <span className="cfg-cap">Название</span>
        {/* FIX: AUDIT12-M13 - aria-label on contest title input (maxLength already 120). */}
        <input autoFocus maxLength={120} value={title} onChange={(e) => setTitle(e.target.value)} aria-label="Название конкурса" />
      </div>
      <div className="cfg-field" style={{ marginBottom: "var(--sp-4)" }}>
        <span className="cfg-cap">Описание</span>
        {/* FIX: AUDIT12-M13 - aria-label on contest description (maxLength already 2000). */}
        <textarea style={{ minHeight: 90, resize: "vertical" }} maxLength={2000} value={description} onChange={(e) => setDescription(e.target.value)} aria-label="Описание конкурса" />
      </div>
      <div className="cfg-field" style={{ maxWidth: 200, marginBottom: "var(--sp-4)" }}>
        <span className="cfg-cap">Количество победителей</span>
        <input type="number" min={1} value={winners} onChange={(e) => setWinners(Math.max(1, Number(e.target.value) || 1))} />
      </div>
      <PrizeFields type={prizeType} amount={prizeAmount} onType={setPrizeType} onAmount={setPrizeAmount} />
      <p className="cfg-hint" style={{ marginTop: 0 }}>Приз начисляется каждому победителю автоматически при розыгрыше. 0 — без авто-приза (только уведомление).</p>
    </Modal>
  );
}

// ---- Entrants (who joined) -------------------------------------------------
function EntrantsModal({ contest, onClose }: { contest: Contest; onClose: () => void }) {
  const [rows, setRows] = useState<EntrantRow[] | null>(null);
  const [err, setErr] = useState("");
  useEffect(() => {
    contestsApi.entrants(contest.id).then((r) => setRows(r.entrants)).catch((e) => { setRows([]); setErr(String(e)); });
  }, [contest.id]);

  return (
    <Modal wide title={`Участники · ${contest.title}`} icon="group" onClose={onClose}>
      {err && <p className="note-err"><span className="ms sm">error</span>{err}</p>}
      {rows === null ? <div className="loading">Загрузка…</div>
        : rows.length === 0 ? <div className="empty">В конкурсе пока нет участников.</div>
        : (
          <>
            <p className="cfg-hint" style={{ marginTop: 0 }}>Всего участников: {rows.length}.</p>
            <div className="table-wrap" tabIndex={0} style={{ border: "none" }}>
              <table className="tbl">
                <thead><tr><th>Пользователь</th><th>Вступил</th></tr></thead>
                <tbody>
                  {rows.map((e, i) => (
                    <tr key={i}>
                      <td><a className="user-link code-key" href={`#/users?focus=${e.user_id}`}>#{e.user_id}</a></td>
                      <td className="muted">{e.entered_at ? new Date(e.entered_at).toLocaleString("ru") : "—"}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          </>
        )}
    </Modal>
  );
}

function Metric({ icon, label, value, tone }: {
  icon: string; label: string; value: number; tone?: "purple" | "danger";
}) {
  return (
    <div className={"metric" + (tone ? " " + tone : "")}>
      <span className="glow" />
      <div className="top"><span className="lbl">{label}</span><span className="ms sm">{icon}</span></div>
      <div><div className="num">{value.toLocaleString("ru")}</div></div>
    </div>
  );
}

function CreateContestModal({ onClose, onDone }: { onClose: () => void; onDone: (msg: string) => void }) {
  const [title, setTitle] = useState("");
  const [description, setDescription] = useState("");
  const [winners, setWinners] = useState(1);
  const [prizeType, setPrizeType] = useState("credits");
  const [prizeAmount, setPrizeAmount] = useState(0);
  const [busy, setBusy] = useState(false);
  const [err, setErr] = useState("");

  async function submit() {
    if (!title.trim()) { setErr("Введите название конкурса."); return; }
    setBusy(true); setErr("");
    try {
      await contestsApi.create({
        title: title.trim(), description: description.trim() || null,
        winners_count: Math.max(1, winners), prize_type: prizeType, prize_amount: prizeAmount,
      });
      onDone(`✅ Конкурс «${title.trim()}» создан`);
    } catch (e) { setErr(e instanceof Error ? e.message : String(e)); }
    finally { setBusy(false); }
  }

  return (
    <Modal title="Новый конкурс" icon="emoji_events" onClose={onClose}
      footer={<button className="btn" onClick={submit} disabled={busy}>
        <span className="ms sm">add</span> {busy ? "Создание…" : "Создать конкурс"}
      </button>}>
      {err && <p className="note-err"><span className="ms sm">error</span>{err}</p>}
      <div className="cfg-field" style={{ marginBottom: "var(--sp-4)" }}>
        <span className="cfg-cap">Название</span>
        {/* FIX: AUDIT12-M13/M14 - aria-label + maxLength 255 on contest title. */}
        <input autoFocus placeholder="Розыгрыш Premium на месяц" value={title} onChange={(e) => setTitle(e.target.value)} maxLength={255} aria-label="Название конкурса" />
      </div>
      <div className="cfg-field" style={{ marginBottom: "var(--sp-4)" }}>
        <span className="cfg-cap">Описание (необязательно)</span>
        {/* FIX: AUDIT12-M13/M14 - aria-label + maxLength 10000 on contest description. */}
        <textarea style={{ minHeight: 90, resize: "vertical" }} placeholder="Условия и призы конкурса для участников"
          value={description} onChange={(e) => setDescription(e.target.value)} maxLength={10000} aria-label="Описание конкурса" />
        <p className="cfg-hint">Текст показывается участникам.</p>
      </div>
      <div className="cfg-field" style={{ maxWidth: 200, marginBottom: "var(--sp-4)" }}>
        <span className="cfg-cap">Количество победителей</span>
        {/* FIX: AUDIT12-M14 - max 1000 ceiling on winners count. */}
        <input type="number" min={1} max={1000} value={winners} onChange={(e) => setWinners(Math.max(1, Number(e.target.value) || 1))} aria-label="Количество победителей" />
      </div>
      <PrizeFields type={prizeType} amount={prizeAmount} onType={setPrizeType} onAmount={setPrizeAmount} />
      <p className="cfg-hint" style={{ marginTop: 0 }}>Приз начисляется каждому победителю автоматически при розыгрыше. 0 — без авто-приза (только уведомление).</p>
    </Modal>
  );
}

function ResultModal({ contest, winners, onClose }: { contest: Contest; winners: number[]; onClose: () => void }) {
  function copy() { navigator.clipboard.writeText(winners.join("\n")).catch(() => {}); }
  function exportCsv() {
    const blob = new Blob(["user_id\n" + winners.join("\n")], { type: "text/csv;charset=utf-8" });
    const a = document.createElement("a"); a.href = URL.createObjectURL(blob);
    a.download = `contest_${contest.id}_winners.csv`; a.click(); URL.revokeObjectURL(a.href);
  }
  return (
    <Modal title={`Победители · ${contest.title}`} icon="workspace_premium" onClose={onClose}
      footer={winners.length > 0 ? <>
        <button className="btn" onClick={copy}><span className="ms sm">content_copy</span> Копировать ID</button>
        <button className="btn ghost" onClick={exportCsv}><span className="ms sm">download</span> Экспорт CSV</button>
      </> : undefined}>
      {winners.length === 0 ? (
        <div className="empty-state">
          <div className="es-icon"><span className="ms">sentiment_dissatisfied</span></div>
          <p className="es-title">Нет участников</p>
          <p className="es-desc">В конкурсе не было участников, поэтому победители не выбраны.</p>
        </div>
      ) : (
        <>
          <p className="cfg-hint" style={{ marginBottom: "var(--sp-3)" }}>Выбрано случайно {winners.length} победителей. Каждому отправлено уведомление в боте.</p>
          <div className="row">
            {winners.map((id, i) => (
              <a key={id} href={`#/users?focus=${id}`} className="pill pro user-link" style={{ fontSize: 12, textDecoration: "none" }}>
                <span className="ms sm">workspace_premium</span> #{i + 1} · {id}
              </a>
            ))}
          </div>
        </>
      )}
    </Modal>
  );
}
