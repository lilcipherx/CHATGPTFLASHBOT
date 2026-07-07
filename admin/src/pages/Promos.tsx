import { useEffect, useMemo, useRef, useState } from "react";
import QRCode from "qrcode";
import { api, PromoRow } from "../api";
import { Select } from "../components/Select";
import { DateField } from "../components/DateField";
import { Switch } from "../components/Switch";
import { Modal } from "../components/Modal";

const REFRESH_MS = 30_000;
const promoLink = (username: string, code: string) =>
  `https://t.me/${username}?start=promo_${code}`;

const REWARDS = ["credits", "image", "video", "music", "premium", "discount"];
const REWARD_LABEL: Record<string, string> = {
  credits: "✨ Кредиты", image: "image-pack", video: "video-pack", music: "music-pack",
  premium: "⭐ Premium (дней)", discount: "🏷 Скидка (%)",
};
const rewardOptions = REWARDS.map((r) => ({ value: r, label: REWARD_LABEL[r] }));

type Status = "active" | "disabled" | "expired" | "usedup";
function statusOf(p: PromoRow): Status {
  if (!p.is_active) return "disabled";
  if (p.expires_at && new Date(p.expires_at).getTime() < Date.now()) return "expired";
  if (p.used >= p.max_uses) return "usedup";
  return "active";
}
const STATUS_META: Record<Status, { label: string; cls: string }> = {
  active: { label: "Активен", cls: "ok" },
  disabled: { label: "Отключён", cls: "muted" },
  expired: { label: "Истёк", cls: "danger" },
  usedup: { label: "Исчерпан", cls: "warn" },
};

const DAY = 86400000;
const expiringSoon = (iso: string | null) =>
  !!iso && new Date(iso).getTime() - Date.now() > 0 && new Date(iso).getTime() - Date.now() < 3 * DAY;

function genCode(len: number, o: { digits: boolean; letters: boolean; prefix: string; suffix: string }): string {
  const D = "0123456789";
  const L = "ABCDEFGHIJKLMNPQRSTUVWXYZ"; // no O — avoids 0/O confusion
  let pool = (o.letters ? L : "") + (o.digits ? D : "");
  if (!pool) pool = L + D;
  let core = "";
  // FIX: AUDIT12-F5 - body of the for loop must be wrapped in { } (was: a single-statement
  // for with `const arr = ...` which is a declaration and not allowed in single-statement
  // context — Vite/tsc refuses to build).
  for (let i = 0; i < len; i++) {
    const arr = new Uint32Array(1);
    crypto.getRandomValues(arr);
    core += pool[arr[0] % pool.length];
  }
  return (o.prefix + core + o.suffix).toUpperCase();
}

export function Promos() {
  const [rows, setRows] = useState<PromoRow[] | null>(null);
  const [msg, setMsg] = useState("");
  const [q, setQ] = useState("");
  const [stFilter, setStFilter] = useState("");
  const [tyFilter, setTyFilter] = useState("");
  const [createOpen, setCreateOpen] = useState(false);
  const [massOpen, setMassOpen] = useState(false);
  const [dupInit, setDupInit] = useState<PromoRow | null>(null);
  const [shareFor, setShareFor] = useState<PromoRow | null>(null);
  const [historyFor, setHistoryFor] = useState<PromoRow | null>(null);
  const [botUsername, setBotUsername] = useState<string | null>(null);
  const aliveRef = useRef(true);

  const load = () => api.promos()
    .then((r) => { if (aliveRef.current) setRows(r); })
    .catch((e) => { if (aliveRef.current) { setRows([]); setMsg(String(e)); } });

  // Live activation counters: poll every 30s. Also fetch the bot @username once for
  // building share/redeem links.
  useEffect(() => {
    aliveRef.current = true;
    load();
    api.promoBotUsername().then((r) => { if (aliveRef.current) setBotUsername(r.username); }).catch(() => {});
    const id = window.setInterval(load, REFRESH_MS);
    return () => { aliveRef.current = false; window.clearInterval(id); };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  const filtered = useMemo(() => {
    const term = q.trim().toLowerCase();
    return (rows ?? []).filter((p) => {
      if (term && !p.code.toLowerCase().includes(term)) return false;
      if (stFilter && statusOf(p) !== stFilter) return false;
      if (tyFilter && p.reward_type !== tyFilter) return false;
      return true;
    });
  }, [rows, q, stFilter, tyFilter]);

  const kpi = useMemo(() => {
    const all = rows ?? [];
    return {
      total: all.length,
      active: all.filter((p) => statusOf(p) === "active").length,
      expired: all.filter((p) => statusOf(p) === "expired").length,
      usedup: all.filter((p) => statusOf(p) === "usedup").length,
      activations: all.reduce((s, p) => s + p.used, 0),
      credits: all.filter((p) => p.reward_type === "credits").reduce((s, p) => s + p.used * p.reward_amount, 0),
    };
  }, [rows]);

  const [busyCode, setBusyCode] = useState<string | null>(null);  // FIX: AUDIT-88 - per-row busy state
  async function toggle(p: PromoRow) {
    setBusyCode(p.code);
    try { await api.togglePromo(p.code); load(); } catch (e) { setMsg(String(e)); }
    finally { setBusyCode(null); }
  }
  async function del(p: PromoRow) {
    if (!confirm(`Удалить промокод ${p.code}? Действие необратимо.`)) return;
    try { await api.deletePromo(p.code); setMsg(`✅ Промокод ${p.code} удалён`); load(); }
    catch (e) { setMsg(String(e)); }
  }
  async function setExpiry(p: PromoRow, val: string) {
    try { await api.setPromoExpiry(p.code, val ? new Date(val).toISOString() : null); load(); }
    catch (e) { setMsg(String(e)); }
  }
  function exportCsv() {
    const all = rows ?? [];
    if (!all.length) return;
    const head = "code,reward_type,reward_amount,max_uses,used,is_active,status,expires_at";
    const body = all.map((p) =>
      [p.code, p.reward_type, p.reward_amount, p.max_uses, p.used, p.is_active, statusOf(p), p.expires_at ?? ""].join(","));
    const blob = new Blob([head + "\n" + body.join("\n")], { type: "text/csv;charset=utf-8" });
    const a = document.createElement("a");
    a.href = URL.createObjectURL(blob);
    a.download = "promo_codes.csv";
    a.click();
    URL.revokeObjectURL(a.href);
  }
  function openDuplicate(p: PromoRow) { setDupInit(p); setCreateOpen(true); }

  return (
    <div>
      <h1 className="page-title">Промокоды</h1>
      <p className="page-sub">Создание, массовая генерация, фильтрация и управление промокодами.</p>

      {msg && (
        <p className={msg.startsWith("✅") ? "note-ok" : "note-err"}>
          <span className="ms sm">{msg.startsWith("✅") ? "check_circle" : "error"}</span>{msg}
          <button className="btn ghost sm" onClick={() => setMsg("")}>×</button>
        </p>
      )}

      <div className="page-stack">
        <div className="metrics">
          <Metric icon="confirmation_number" label="Всего промокодов" value={kpi.total} />
          <Metric icon="check_circle" label="Активных" value={kpi.active} tone="purple" />
          <Metric icon="schedule" label="Истёкших" value={kpi.expired} tone={kpi.expired > 0 ? "danger" : undefined} />
          <Metric icon="block" label="Исчерпано" value={kpi.usedup} />
          <Metric icon="bolt" label="Активаций" value={kpi.activations} />
          <Metric icon="toll" label="Выдано ✨" value={kpi.credits} />
        </div>

        <div className="panel">
          <div className="toolbar">
            <input className="grow" placeholder="Поиск по коду" value={q} onChange={(e) => setQ(e.target.value)} />
            <Select ariaLabel="Статус" value={stFilter} onChange={setStFilter}
              options={[{ value: "", label: "Все статусы" }, { value: "active", label: "Активные" },
                { value: "disabled", label: "Отключённые" }, { value: "expired", label: "Истёкшие" },
                { value: "usedup", label: "Исчерпанные" }]} />
            <Select ariaLabel="Тип награды" value={tyFilter} onChange={setTyFilter}
              options={[{ value: "", label: "Все типы" }, ...rewardOptions]} />
            <button className="btn ghost spacer" onClick={exportCsv} disabled={!rows?.length}>
              <span className="ms sm">download</span> Экспорт CSV
            </button>
            <button className="btn ghost" onClick={() => setMassOpen(true)}>
              <span className="ms sm">auto_awesome_motion</span> Массовая генерация
            </button>
            <button className="btn" onClick={() => { setDupInit(null); setCreateOpen(true); }}>
              <span className="ms sm">add</span> Создать промокод
            </button>
          </div>

          {rows === null ? (
            <div className="table-wrap" tabIndex={0} style={{ border: "none" }}>
              <table className="tbl"><tbody>
                {Array.from({ length: 5 }).map((_, i) => (
                  <tr key={i}><td><div className="skeleton-row" style={{ minHeight: 44 }} /></td></tr>
                ))}
              </tbody></table>
            </div>
          ) : filtered.length === 0 ? (
            rows.length === 0 ? (
              <div className="empty-state">
                <div className="es-icon"><span className="ms">confirmation_number</span></div>
                <p className="es-title">Промокодов пока нет</p>
                <p className="es-desc">Создайте первый промокод для выдачи кредитов или пакетов — или сгенерируйте сразу партию для кампании.</p>
                <button className="btn" style={{ marginTop: "var(--sp-2)" }} onClick={() => { setDupInit(null); setCreateOpen(true); }}>
                  <span className="ms sm">add</span> Создать первый промокод
                </button>
              </div>
            ) : (
              <div className="empty">Под фильтры ничего не подходит.</div>
            )
          ) : (
            <div className="table-wrap" tabIndex={0} style={{ border: "none" }}>
              <table className="tbl">
                <thead>
                  <tr><th>Код</th><th>Награда</th><th>Использовано</th><th>Осталось</th><th>Статус</th><th>Истекает</th><th></th></tr>
                </thead>
                <tbody>
                  {filtered.map((p) => {
                    const st = statusOf(p);
                    const remaining = Math.max(0, p.max_uses - p.used);
                    const pct = p.max_uses ? Math.min(100, (p.used / p.max_uses) * 100) : 0;
                    return (
                      <tr key={p.code}>
                        <td className="code-key" style={{ whiteSpace: "nowrap" }}>{p.code}</td>
                        <td style={{ whiteSpace: "nowrap" }}>{p.reward_amount} <span className="muted">{REWARD_LABEL[p.reward_type] ?? p.reward_type}</span></td>
                        <td>
                          <div style={{ display: "flex", flexDirection: "column", gap: 4, minWidth: 96 }}>
                            <span className="muted" style={{ fontSize: 12 }}>{p.used} / {p.max_uses}</span>
                            <div style={{ height: 6, borderRadius: 999, background: "var(--panel-2)", overflow: "hidden" }}>
                              <div style={{ height: "100%", width: pct + "%", background: pct >= 100 ? "var(--warn)" : "var(--accent)" }} />
                            </div>
                          </div>
                        </td>
                        <td><span className={remaining === 0 ? "pill warn" : "muted"}>{remaining}</span></td>
                        <td><span className={"pill " + STATUS_META[st].cls}>{STATUS_META[st].label}</span></td>
                        <td>
                          <div style={{ display: "flex", alignItems: "center", gap: 6 }}>
                            <DateField style={{ width: 180 }}
                              value={p.expires_at ? p.expires_at.slice(0, 10) : ""}
                              onChange={(v) => setExpiry(p, v)} />
                            {expiringSoon(p.expires_at) && <span className="pill warn" title="Скоро истекает">скоро</span>}
                          </div>
                        </td>
                        <td>
                          <div className="cell-actions">
                            <button className="btn ghost sm" title="Поделиться (QR + ссылка)" onClick={() => setShareFor(p)}>
                              <span className="ms sm">qr_code_2</span>
                            </button>
                            <button className="btn ghost sm" title="Кто активировал" onClick={() => setHistoryFor(p)}>
                              <span className="ms sm">history</span>{p.used > 0 ? ` ${p.used}` : ""}
                            </button>
                            <button className={"btn sm " + (p.is_active ? "ghost" : "")} title={p.is_active ? "Отключить" : "Включить"}
                              disabled={busyCode === p.code} onClick={() => toggle(p)}>{/* FIX: AUDIT-88 - per-row busy guard */}
                              {p.is_active ? "Выключить" : "Включить"}
                            </button>
                            <button className="btn ghost sm" title="Дублировать" onClick={() => openDuplicate(p)}>
                              <span className="ms sm">library_add</span>
                            </button>
                            <button className="btn danger sm" title="Удалить" onClick={() => del(p)}>
                              <span className="ms sm">delete</span>
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
        <CreateModal init={dupInit} onClose={() => setCreateOpen(false)}
          onDone={(m) => { setMsg(m); setCreateOpen(false); load(); }} />
      )}
      {massOpen && (
        <MassModal onClose={() => setMassOpen(false)}
          onDone={(m) => { setMsg(m); setMassOpen(false); load(); }} />
      )}
      {shareFor && (
        <ShareModal promo={shareFor} username={botUsername}
          onClose={() => setShareFor(null)} onMsg={setMsg} />
      )}
      {historyFor && (
        <RedemptionsModal promo={historyFor} onClose={() => setHistoryFor(null)} />
      )}
    </div>
  );
}

// ---- Share: activation link + QR ------------------------------------------
function ShareModal({ promo, username, onClose, onMsg }: {
  promo: PromoRow; username: string | null; onClose: () => void; onMsg: (m: string) => void;
}) {
  const [qr, setQr] = useState("");
  const link = username ? promoLink(username, promo.code) : "";

  useEffect(() => {
    if (!link) { setQr(""); return; }
    QRCode.toDataURL(link, { width: 240, margin: 1, color: { dark: "#0a0a0a", light: "#ffffff" } })
      .then(setQr).catch(() => setQr(""));
  }, [link]);

  async function copyText(text: string, label: string) {
    try { await navigator.clipboard.writeText(text); onMsg(`✅ ${label} скопирован`); }
    catch { onMsg("Не удалось скопировать"); }
  }
  function downloadQr() {
    if (!qr) return;
    const a = document.createElement("a");
    a.href = qr; a.download = `promo_${promo.code}.png`; a.click();
  }

  return (
    <Modal title={`Поделиться · ${promo.code}`} icon="qr_code_2" onClose={onClose}>
      <div className="cfg-field" style={{ marginBottom: "var(--sp-4)" }}>
        <span className="cfg-cap">Код</span>
        <div className="toolbar" style={{ marginBottom: 0 }}>
          <input className="grow code-key" readOnly value={promo.code} />
          <button className="btn ghost" onClick={() => copyText(promo.code, "Код")}>
            <span className="ms sm">content_copy</span> Код
          </button>
        </div>
      </div>

      {link ? (
        <>
          <div className="cfg-field" style={{ marginBottom: "var(--sp-4)" }}>
            <span className="cfg-cap">Ссылка-активация (авто-погашение при /start)</span>
            <div className="toolbar" style={{ marginBottom: 0 }}>
              <input className="grow" readOnly value={link} />
              <button className="btn ghost" onClick={() => copyText(link, "Ссылка")}>
                <span className="ms sm">link</span> Ссылка
              </button>
            </div>
          </div>
          <div style={{ display: "flex", flexDirection: "column", alignItems: "center", gap: "var(--sp-3)" }}>
            {qr ? <img src={qr} alt="QR" width={240} height={240} style={{ borderRadius: 12, border: "1px solid var(--border)" }} />
              : <div className="loading">Генерация QR…</div>}
            <button className="btn ghost" onClick={downloadQr} disabled={!qr}>
              <span className="ms sm">download</span> Скачать QR
            </button>
          </div>
        </>
      ) : (
        <p className="cfg-hint">
          <span className="ms sm" style={{ verticalAlign: "-3px" }}>info</span>{" "}
          Ссылка и QR станут доступны после первого запуска бота (тогда определяется его @username).
          Сейчас можно скопировать сам код.
        </p>
      )}
    </Modal>
  );
}

// ---- Redemptions history (who activated) -----------------------------------
function RedemptionsModal({ promo, onClose }: { promo: PromoRow; onClose: () => void }) {
  const [rows, setRows] = useState<{ user_id: number; redeemed_at: string | null }[] | null>(null);
  const [err, setErr] = useState("");

  useEffect(() => {
    api.promoRedemptions(promo.code).then(setRows).catch((e) => { setRows([]); setErr(String(e)); });
  }, [promo.code]);

  return (
    <Modal title={`Активации · ${promo.code}`} icon="history" onClose={onClose} wide>
      {err && <p className="note-err"><span className="ms sm">error</span>{err}</p>}
      <p className="cfg-hint" style={{ marginTop: 0 }}>
        Использовано {promo.used} из {promo.max_uses}. Каждый пользователь может активировать код один раз.
      </p>
      {rows === null ? <div className="loading">Загрузка…</div>
        : rows.length === 0 ? <div className="empty">Этот промокод ещё никто не активировал.</div>
        : (
          <div className="table-wrap" tabIndex={0} style={{ border: "none" }}>
            <table className="tbl">
              <thead><tr><th>Пользователь</th><th>Когда</th></tr></thead>
              <tbody>
                {rows.map((r, i) => (
                  <tr key={i}>
                    <td><a className="user-link code-key" href={`#/users?focus=${r.user_id}`}>#{r.user_id}</a></td>
                    <td className="muted">{r.redeemed_at ? new Date(r.redeemed_at).toLocaleString("ru") : "—"}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
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

// ---- Reward fields shared by create + mass ---------------------------------
const amountCap = (type: string) =>
  type === "credits" ? "Кол-во ✨" : type === "premium" ? "Дней Premium"
    : type === "discount" ? "Скидка, %" : "Кол-во пакет-кредитов";

function RewardFields({ type, setType, amount, setAmount, maxUses, setMaxUses, expires, setExpires,
  newUserDays, setNewUserDays }: {
  type: string; setType: (v: string) => void;
  amount: number; setAmount: (v: number) => void;
  maxUses: number; setMaxUses: (v: number) => void;
  expires: string; setExpires: (v: string) => void;
  newUserDays: number; setNewUserDays: (v: number) => void;
}) {
  return (
    <div className="form-grid">
      <div className="cfg-field">
        <span className="cfg-cap">Тип награды</span>
        <Select ariaLabel="Тип награды" width="100%" value={type} onChange={setType} options={rewardOptions} />
      </div>
      <div className="cfg-field">
        <span className="cfg-cap">{amountCap(type)}</span>
        <input type="number" aria-label="Размер награды" min={0} value={amount} onChange={(e) => setAmount(Math.max(0, Number(e.target.value) || 0))} />
      </div>
      <div className="cfg-field">
        <span className="cfg-cap">Макс. активаций</span>
        <input type="number" aria-label="Макс. использований" min={1} value={maxUses} onChange={(e) => setMaxUses(Math.max(1, Number(e.target.value) || 1))} />
      </div>
      <div className="cfg-field">
        <span className="cfg-cap">Действует до (необязательно)</span>
        <DateField value={expires} onChange={setExpires} />
      </div>
      <div className="cfg-field">
        <span className="cfg-cap">Только новички, дней (0 — все)</span>
        <input type="number" aria-label="Только для новых, дней" min={0} value={newUserDays}
          onChange={(e) => setNewUserDays(Math.max(0, Number(e.target.value) || 0))} />
      </div>
    </div>
  );
}

// ---- Create / duplicate ----------------------------------------------------
function CreateModal({ init, onClose, onDone }: {
  init: PromoRow | null; onClose: () => void; onDone: (msg: string) => void;
}) {
  const [code, setCode] = useState("");
  const [type, setType] = useState(init?.reward_type ?? "credits");
  const [amount, setAmount] = useState(init?.reward_amount ?? 10);
  const [maxUses, setMaxUses] = useState(init?.max_uses ?? 100);
  const [expires, setExpires] = useState("");
  const [newUserDays, setNewUserDays] = useState(init?.new_user_days ?? 0);
  const [busy, setBusy] = useState(false);
  const [err, setErr] = useState("");

  async function submit() {
    const c = code.trim().toUpperCase();
    if (!c) { setErr("Введите код или сгенерируйте случайный."); return; }
    setBusy(true); setErr("");
    try {
      await api.createPromo({
        code: c, reward_type: type, reward_amount: amount, max_uses: maxUses,
        // FIX: AUDIT-2 - treat YYYY-MM-DD as local end-of-day to avoid early expiry
        expires_at: expires ? new Date(expires + "T23:59:59").toISOString() : null,
        new_user_days: newUserDays,
      });
      onDone(`✅ Промокод ${c} создан`);
    } catch (e) {
      const m = e instanceof Error ? e.message : String(e);
      setErr(m.includes("409") ? "Промокод с таким кодом уже существует." : m);
    } finally { setBusy(false); }
  }

  return (
    <Modal title={init ? "Дублировать промокод" : "Новый промокод"} icon="confirmation_number" onClose={onClose}
      footer={<button className="btn" onClick={submit} disabled={busy || !code.trim() || amount < 1}>
        {/* FIX: AUDIT13-L20 - block creating a no-op promo (empty code or 0 reward). */}
        <span className="ms sm">add</span> {busy ? "Создание…" : "Создать"}
      </button>}>
      {err && <p className="note-err"><span className="ms sm">error</span>{err}</p>}
      <div className="cfg-field" style={{ marginBottom: "var(--sp-4)" }}>
        <span className="cfg-cap">Код</span>
        <div className="toolbar" style={{ marginBottom: 0 }}>
          <input className="grow" placeholder="WELCOME2026" value={code}
            onChange={(e) => setCode(e.target.value.toUpperCase().replace(/[^A-Z0-9_-]/g, ""))} maxLength={32} />
          <button className="btn ghost" title="Сгенерировать случайный"
            onClick={() => setCode(genCode(8, { digits: true, letters: true, prefix: "", suffix: "" }))}>
            <span className="ms sm">casino</span> Случайный
          </button>
        </div>
      </div>
      <RewardFields type={type} setType={setType} amount={amount} setAmount={setAmount}
        maxUses={maxUses} setMaxUses={setMaxUses} expires={expires} setExpires={setExpires}
        newUserDays={newUserDays} setNewUserDays={setNewUserDays} />
    </Modal>
  );
}

// ---- Mass generation -------------------------------------------------------
const COUNT_PRESETS = [10, 25, 50, 100];
const MAX_BATCH = 200;

function MassModal({ onClose, onDone }: { onClose: () => void; onDone: (msg: string) => void }) {
  const [count, setCount] = useState(10);
  const [len, setLen] = useState(8);
  const [prefix, setPrefix] = useState("");
  const [suffix, setSuffix] = useState("");
  const [digits, setDigits] = useState(true);
  const [letters, setLetters] = useState(true);
  const [type, setType] = useState("credits");
  const [amount, setAmount] = useState(10);
  const [maxUses, setMaxUses] = useState(1);
  const [expires, setExpires] = useState("");
  const [newUserDays, setNewUserDays] = useState(0);
  const [running, setRunning] = useState(false);
  const [progress, setProgress] = useState(0);
  const [err, setErr] = useState("");

  async function run() {
    const n = Math.max(1, Math.min(MAX_BATCH, count));
    if (!digits && !letters) { setErr("Выберите хотя бы цифры или буквы для кода."); return; }
    setRunning(true); setErr(""); setProgress(0);
    // unique codes within the batch
    const codes = new Set<string>();
    let guard = 0;
    while (codes.size < n && guard < n * 20) { codes.add(genCode(len, { digits, letters, prefix, suffix })); guard++; }
    const exp = expires ? new Date(expires).toISOString() : null;
    let created = 0, dupes = 0, failed = 0, done = 0;
    for (const code of codes) {
      try { await api.createPromo({ code, reward_type: type, reward_amount: amount, max_uses: maxUses, expires_at: exp, new_user_days: newUserDays }); created++; }
      catch (e) { (e instanceof Error && e.message.includes("409")) ? dupes++ : failed++; }
      setProgress(++done);
    }
    setRunning(false);
    onDone(`✅ Создано ${created} из ${codes.size}` + (dupes ? ` · ${dupes} дублей пропущено` : "") + (failed ? ` · ${failed} ошибок` : ""));
  }

  return (
    <Modal wide title="Массовая генерация промокодов" icon="auto_awesome_motion" onClose={onClose}
      footer={<button className="btn" onClick={run} disabled={running}>
        <span className="ms sm">bolt</span> {running ? `Генерация… ${progress}/${Math.min(MAX_BATCH, count)}` : `Сгенерировать ${Math.min(MAX_BATCH, count)}`}
      </button>}>
      {err && <p className="note-err"><span className="ms sm">error</span>{err}</p>}

      <div className="cfg-field" style={{ marginBottom: "var(--sp-4)" }}>
        <span className="cfg-cap">Количество (макс. {MAX_BATCH})</span>
        <div className="toolbar" style={{ marginBottom: 0 }}>
          {COUNT_PRESETS.map((n) => (
            <button key={n} className={"btn sm " + (count === n ? "" : "ghost")} onClick={() => setCount(n)}>{n}</button>
          ))}
          <input type="number" min={1} max={MAX_BATCH} style={{ width: 110 }} value={count}
            onChange={(e) => setCount(Math.max(1, Math.min(MAX_BATCH, Number(e.target.value) || 1)))} />
        </div>
      </div>

      <div className="form-grid">
        <div className="cfg-field">
          <span className="cfg-cap">Длина кода</span>
          <input type="number" min={4} max={20} value={len} onChange={(e) => setLen(Math.max(4, Math.min(20, Number(e.target.value) || 8)))} />
        </div>
        <div className="cfg-field">
          <span className="cfg-cap">Префикс</span>
          <input value={prefix} placeholder="SALE-" onChange={(e) => setPrefix(e.target.value.toUpperCase())} />
        </div>
        <div className="cfg-field">
          <span className="cfg-cap">Суффикс</span>
          <input value={suffix} placeholder="-26" onChange={(e) => setSuffix(e.target.value.toUpperCase())} />
        </div>
        <div className="cfg-field">
          <span className="cfg-cap">Состав кода</span>
          <div className="form-row" style={{ minHeight: 42 }}>
            <Switch checked={digits} onChange={setDigits} label="Цифры" />
            <Switch checked={letters} onChange={setLetters} label="Буквы" />
          </div>
        </div>
      </div>

      <div className="panel-title sm" style={{ margin: "var(--sp-4) 0 var(--sp-2)" }}>Награда для всей партии</div>
      <RewardFields type={type} setType={setType} amount={amount} setAmount={setAmount}
        maxUses={maxUses} setMaxUses={setMaxUses} expires={expires} setExpires={setExpires}
        newUserDays={newUserDays} setNewUserDays={setNewUserDays} />

      <p className="cfg-hint" style={{ marginTop: "var(--sp-3)" }}>
        Пример кода: <span className="code-key">{genCode(len, { digits, letters, prefix, suffix })}</span>.
        Коды создаются по одному через стандартный API; дубликаты автоматически пропускаются.
      </p>
    </Modal>
  );
}
