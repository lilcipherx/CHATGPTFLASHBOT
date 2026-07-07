import { useCallback, useEffect, useState } from "react";
import { useLocation } from "react-router-dom";
import { api, CrmData, UserCard, UserFilters, UserRow, UserSort } from "../api";
import { Modal } from "../components/Modal";
import { Select } from "../components/Select";
import { countryLabel } from "../lib/countries";
import { languageLabel } from "../lib/languages";
import { useLatestGuard } from "../lib/latestGuard";

type Tri = "any" | "yes" | "no";
const tri = (v: Tri): boolean | undefined => (v === "any" ? undefined : v === "yes");

const SORT_OPTS = [
  { value: "created_desc", label: "Новые сверху" },
  { value: "created_asc", label: "Старые сверху" },
  { value: "credits_desc", label: "Больше ✨" },
  { value: "credits_asc", label: "Меньше ✨" },
];

export function Users() {
  const [q, setQ] = useState("");
  const [premium, setPremium] = useState<Tri>("any");
  const [banned, setBanned] = useState<Tri>("any");
  const [country, setCountry] = useState("");
  const [language, setLanguage] = useState("");
  const [hasPhone, setHasPhone] = useState<Tri>("any");
  const [sort, setSort] = useState<UserSort>("created_desc");
  const [countries, setCountries] = useState<{ code: string; count: number }[]>([]);
  const [languages, setLanguages] = useState<{ code: string; count: number }[]>([]);
  const [rows, setRows] = useState<UserRow[]>([]);
  const [total, setTotal] = useState(0);
  const [card, setCard] = useState<UserCard | null>(null);
  const [msg, setMsg] = useState("");
  const [searched, setSearched] = useState(false);
  const [actBusy, setActBusy] = useState(false);  // FIX: F45 - prevent double-submit on user actions
  const PAGE = 50;
  const [hasMore, setHasMore] = useState(false);

  const filters = useCallback((offset: number): UserFilters => {
    return { q, premium: tri(premium), banned: tri(banned),
      country: country.trim() || undefined, language: language || undefined,
      has_phone: tri(hasPhone), sort, limit: PAGE, offset };
  }, [q, premium, banned, country, language, hasPhone, sort]);

  // FIX: AUDIT-M17 - race guard so a slower earlier response can't overwrite the
  // newer filtered list (search fires from the button, Enter, and the sort/country/
  // language effect, so several requests are easily in flight at once).
  const guardSearch = useLatestGuard();

  const search = useCallback(async () => {
    setMsg(""); setCard(null);
    const isLatest = guardSearch();
    try {
      const page = await api.searchUsers(filters(0));
      if (!isLatest()) return;
      setRows(page.items); setTotal(page.total);
      setHasMore(page.items.length < page.total); setSearched(true);
    } catch (e) { if (isLatest()) setMsg(String(e)); }
  }, [filters, guardSearch]);

  // Auto-load the newest users on open (and whenever the sort changes), so the table
  // is never blank — the admin can browse straight away without first hitting Search.
  // Deliberately NOT keyed on `search`/filters so typing in the query box doesn't
  // fire a request per keystroke — text filters apply on Enter / the Search button.
  // eslint-disable-next-line react-hooks/exhaustive-deps
  useEffect(() => { search(); }, [sort, country, language]);

  // Load the country + language lists once for the filter dropdowns (real data + counts).
  useEffect(() => {
    api.userCountries().then(setCountries).catch(() => setCountries([]));
    api.userLanguages().then(setLanguages).catch(() => setLanguages([]));
  }, []);

  // Deep link: another page (e.g. Feedback) can link to #/users?focus=<id> to open
  // that user's card directly.
  const location = useLocation();
  useEffect(() => {
    const focus = new URLSearchParams(location.search).get("focus");
    if (focus) open(Number(focus));
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [location.search]);

  const countryOpts = [
    { value: "", label: "🌍 Все страны" },
    ...countries.map((c) => ({ value: c.code, label: `${countryLabel(c.code)} · ${c.count.toLocaleString("ru")}` })),
  ];
  const languageOpts = [
    { value: "", label: "🗣 Все языки" },
    ...languages.map((l) => ({ value: l.code, label: `${languageLabel(l.code)} · ${l.count.toLocaleString("ru")}` })),
  ];

  async function loadMore() {
    // FIX: AUDIT-M17 - share the search guard so a fresh search supersedes an
    // in-flight page append (and vice versa) instead of mixing result sets.
    const isLatest = guardSearch();
    try {
      const page = await api.searchUsers(filters(rows.length));
      if (!isLatest()) return;
      setRows((prev) => {
        const next = [...prev, ...page.items];
        setHasMore(next.length < page.total);
        return next;
      });
    } catch (e) { if (isLatest()) setMsg(String(e)); }
  }

  async function open(id: number) {
    setMsg("");
    try { setCard(await api.userCard(id)); }
    catch (e) {
      // A deep link (e.g. from a complaint) can target a user_id with no User row —
      // surface that plainly instead of a raw "Error: not found".
      setMsg(/not found/i.test(String(e)) ? `Пользователь #${id} не найден` : String(e));
    }
  }

  async function act(fn: () => Promise<unknown>, ok = "✅ Готово") {
    // FIX: F45 - guard against double-clicks firing a second mutation (double credit
    // grant, double ban toggle, etc.) while the first is still in flight.
    if (actBusy) return;
    setActBusy(true);
    // Capture which card is open BEFORE search() (which clears card + msg), then
    // refresh the list and re-open the same user with fresh data, and finally show
    // the confirmation last so search()/open()'s setMsg("") can't wipe it.
    const openId = card?.user_id;
    try {
      await fn();
      await search();
      if (openId) await open(openId);
      setMsg(ok);
    } catch (e) { setMsg(String(e)); }
    finally { setActBusy(false); }
  }

  return (
    <div>
      <h1 className="page-title">Пользователи</h1>
      <p className="page-sub">Поиск, баланс, Premium, блокировка — полное управление аккаунтом.</p>

      {msg && (
        <p className={msg.startsWith("✅") || msg.startsWith("🎁") ? "note-ok" : "note-err"}>
          <span className="ms sm">{msg.startsWith("✅") || msg.startsWith("🎁") ? "check_circle" : "error"}</span>{msg}
          <button className="btn ghost sm" onClick={() => setMsg("")}>×</button>
        </p>
      )}

      <div className="toolbar">
        <input className="grow" placeholder="ID, username или телефон" value={q}
          onChange={(e) => setQ(e.target.value)}
          onKeyDown={(e) => e.key === "Enter" && search()} />
        <button className="btn" onClick={search}><span className="ms sm">search</span> Поиск</button>
      </div>

      <div className="toolbar">
        <label>Premium
          <Select ariaLabel="Premium" value={premium} onChange={(v) => setPremium(v as Tri)}
            options={[{ value: "any", label: "все" }, { value: "yes", label: "есть" }, { value: "no", label: "нет" }]} />
        </label>
        <label>Бан
          <Select ariaLabel="Бан" value={banned} onChange={(v) => setBanned(v as Tri)}
            options={[{ value: "any", label: "все" }, { value: "yes", label: "забанены" }, { value: "no", label: "активны" }]} />
        </label>
        <label>Телефон
          <Select ariaLabel="Телефон" value={hasPhone} onChange={(v) => setHasPhone(v as Tri)}
            options={[{ value: "any", label: "все" }, { value: "yes", label: "есть" }, { value: "no", label: "нет" }]} />
        </label>
        <label>Страна
          <Select ariaLabel="Страна" value={country} onChange={setCountry}
            options={countryOpts} />
        </label>
        <label>Язык
          <Select ariaLabel="Язык" value={language} onChange={setLanguage}
            options={languageOpts} />
        </label>
        <label>Сортировка
          <Select ariaLabel="Сортировка" value={sort} onChange={(v) => setSort(v as UserSort)}
            options={SORT_OPTS} />
        </label>
        <button className="btn ghost" onClick={search}>Применить фильтры</button>
        <button className="btn ghost" onClick={() => api.exportUsersCsv()}>
          <span className="ms sm">download</span> CSV
        </button>
      </div>

      {searched && (
        <div className="list-meta">
          Найдено: <b>{total.toLocaleString("ru")}</b>
          {rows.length < total && <span className="muted"> · показано {rows.length.toLocaleString("ru")}</span>}
        </div>
      )}

      <div className="table-wrap" tabIndex={0}>
        <table className="tbl">
          <thead><tr><th>ID</th><th>Username</th><th>Телефон</th><th>Страна</th><th>Подписка</th><th>Баланс</th><th>Статус</th><th>Регистрация</th><th></th></tr></thead>
          <tbody>
            {rows.length === 0 ? (
              <tr><td colSpan={9}><div className="empty">
                {searched ? "Ничего не найдено по заданным фильтрам." : "Загрузка…"}
              </div></td></tr>
            ) : rows.map((u) => (
              <tr key={u.user_id} style={{ cursor: "pointer" }} onClick={() => open(u.user_id)}>
                <td>{u.user_id}</td>
                <td>{u.username ? "@" + u.username : "—"}</td>
                <td className="muted">{u.phone || "—"}</td>
                <td>{u.country ? countryLabel(u.country) : "—"}</td>
                <td>{u.is_premium ? <span className="pill pro">{u.sub_tier}</span> : <span className="pill muted">free</span>}</td>
                <td><b>{u.credits.toLocaleString("ru")}</b> ✨</td>
                <td>{u.is_banned ? <span className="pill danger">бан</span> : <span className="pill ok">активен</span>}</td>
                <td className="muted">{u.created_at ? new Date(u.created_at).toLocaleDateString("ru") : "—"}</td>
                <td><button className="btn sm ghost"><span className="ms sm">tune</span> Управление</button></td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>

      {hasMore && (
        <div className="toolbar" style={{ justifyContent: "center" }}>
          <button className="btn ghost" onClick={loadMore}>
            <span className="ms sm">expand_more</span> Загрузить ещё
          </button>
        </div>
      )}

      {card && <UserDetail key={card.user_id} card={card} act={act} actBusy={actBusy} onClose={() => setCard(null)} />}
    </div>
  );
}

function UserDetail({ card, act, actBusy, onClose }: {
  // FIX: UI-9 - actBusy is owned by <Users>; it MUST be passed in. The button
  // `disabled={actBusy}` guards referenced it without the prop → "actBusy is not
  // defined" ReferenceError crashed the card on open (esbuild build skips type-check).
  card: UserCard; act: (fn: () => Promise<unknown>, ok?: string) => void; actBusy: boolean; onClose: () => void;
}) {
  const [pack, setPack] = useState("credits");
  const [amount, setAmount] = useState(10);
  const [months, setMonths] = useState(1);
  const [tier, setTier] = useState("premium");
  const id = card.user_id;

  return (
    <Modal
      title={`${card.username ? "@" + card.username : "ID " + id} · ${id}`}
      icon="account_circle"
      onClose={onClose}
      wide
    >
      <div className="info-row muted" style={{ marginBottom: "var(--sp-4)", fontSize: 13 }}>
        <span>📞 {card.phone || "не указан"}</span>
        <span>🌍 {card.country ? countryLabel(card.country) : "неизвестно"}</span>
        <span>📅 {card.created_at ? new Date(card.created_at).toLocaleString("ru") : "—"}</span>
        <span>🗣 {card.language_code ? languageLabel(card.language_code) : "неизвестно"}</span>
        <span>👥 рефералов: {card.referrals_count}</span>
        <span>🛒 покупок Premium: {card.premium_purchase_count}</span>
      </div>

      <div className="metrics">
        <Mini label="✨ Кредиты" value={card.credits} />
        <Mini label="💸 Потрачено" value={card.credits_used} />
        <Mini label="image-pack" value={card.balances.image} />
        <Mini label="video-pack" value={card.balances.video} />
        <Mini label="music-pack" value={card.balances.music} />
      </div>

      <div className="form-grid">
        <div className="panel" style={{ margin: 0 }}>
          <div className="panel-title sm">Начислить / списать</div>
          <div className="toolbar" style={{ marginBottom: 0 }}>
            <Select ariaLabel="Тип начисления" value={pack} onChange={setPack}
              options={[
                { value: "credits", label: "✨ Кредиты" },
                { value: "image", label: "image-pack" },
                { value: "video", label: "video-pack" },
                { value: "music", label: "music-pack" },
              ]} />
            <input type="number" style={{ width: 110 }} value={amount} onChange={(e) => { const v = Number(e.target.value); setAmount(Number.isFinite(v) ? v : 0); }} />
            {/* FIX: AUDIT-LOW - disable while an action is in flight (was: second click
                silently dropped by act()'s guard, no feedback) and block a zero no-op grant. */}
            <button className="btn" disabled={actBusy || amount === 0} onClick={() => act(() => api.grantCredits(id, pack, Math.abs(amount)))}>+ Начислить</button>
            <button className="btn danger" disabled={actBusy || amount === 0} onClick={() => act(() => api.grantCredits(id, pack, -Math.abs(amount)))}>− Списать</button>
          </div>
        </div>

        <div className="panel" style={{ margin: 0 }}>
          <div className="panel-title sm">Premium</div>
          <div className="toolbar" style={{ marginBottom: 0 }}>
            <Select ariaLabel="Тариф Premium" value={tier} onChange={setTier}
              options={[{ value: "premium", label: "premium" }, { value: "premium_x2", label: "premium_x2" }]} />
            {/* FIX: AUDIT-LOW - clamp months to a positive integer (was: clearing the
                field gave Number("")===0 → grantPremium(0); a typed "-1" also passed through). */}
            <input type="number" min={1} step={1} style={{ width: 80 }} value={months}
              onChange={(e) => { const v = Math.floor(Number(e.target.value)); setMonths(Number.isFinite(v) && v > 0 ? v : 1); }} />
            <span className="muted">мес</span>
            <button className="btn" disabled={actBusy} onClick={() => act(() => api.grantPremium(id, months, tier), "🎁 Premium выдан (юзер уведомлён)")}>Подарить</button>
            {card.is_premium && (
              <button className="btn danger" disabled={actBusy} onClick={() => {
                if (confirm("Отобрать Premium у пользователя? Ему придёт уведомление.")) {
                  act(() => api.revokePremium(id), "✅ Premium отозван (юзер уведомлён)");
                }
              }}>Отобрать</button>
            )}
          </div>
          <div className="muted" style={{ fontSize: 12, marginTop: 8 }}>
            До: {card.sub_expires ? new Date(card.sub_expires).toLocaleString("ru") : "—"}
          </div>
        </div>
      </div>

      <div className="toolbar" style={{ marginTop: 16, marginBottom: 0 }}>
        <button className={"btn " + (card.is_banned ? "ghost" : "danger")} disabled={actBusy}
          onClick={() => {
            // FIX: AUDIT-M18 - confirm before banning (destructive, user is notified
            // server-side). Unban is non-destructive, so it needs no prompt.
            if (card.is_banned || confirm("Забанить пользователя? Ему придёт уведомление.")) {
              act(() => api.ban(id, !card.is_banned));
            }
          }}>
          <span className="ms sm">block</span> {card.is_banned ? "Разбанить" : "Забанить"}
        </button>
        <button className="btn ghost" onClick={() => act(() => api.resetQuota(id))}>
          <span className="ms sm">restart_alt</span> Сбросить квоту
        </button>
        <button className="btn ghost" onClick={() => act(() => api.clearContext(id))}>
          <span className="ms sm">mop</span> Очистить контекст
        </button>
      </div>

      <CrmSection userId={id} />

      {card.premium_purchases.length > 0 && (
        <>
          <div className="panel-title sm" style={{ marginTop: "var(--sp-5)" }}>История покупок Premium</div>
          <table className="tbl">
            <tbody>
              {card.premium_purchases.map((p, i) => (
                <tr key={i}>
                  <td><span className="pill pro">{p.product}</span></td>
                  <td className="muted">{p.months ? p.months + " мес" : "—"}</td>
                  <td className="muted">{p.amount} {p.gateway}</td>
                  <td className="muted">{new Date(p.at).toLocaleString("ru")}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </>
      )}

      {card.transactions.length > 0 && (
        <>
          <div className="panel-title sm" style={{ marginTop: "var(--sp-5)" }}>Последние транзакции</div>
          <table className="tbl">
            <tbody>
              {card.transactions.slice(0, 8).map((t, i) => (
                <tr key={i}>
                  <td>{t.product}</td>
                  <td className="muted">{t.amount} {t.gateway}</td>
                  <td><span className={"pill " + (t.status === "paid" ? "ok" : "muted")}>{t.status}</span></td>
                  <td className="muted">{new Date(t.created_at).toLocaleDateString("ru")}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </>
      )}
    </Modal>
  );
}

function CrmSection({ userId }: { userId: number }) {
  const [data, setData] = useState<CrmData>({ notes: [], tags: [] });
  const [tag, setTag] = useState("");
  const [note, setNote] = useState("");
  const [err, setErr] = useState("");

  async function load() {
    try { setData(await api.crmGet(userId)); }
    catch (e) { setErr(String(e)); }
  }

  useEffect(() => { load(); /* eslint-disable-next-line react-hooks/exhaustive-deps */ }, [userId]);

  async function run(fn: () => Promise<unknown>) {
    setErr("");
    try { await fn(); await load(); }
    catch (e) { setErr(String(e)); }
  }

  async function addTag() {
    const t = tag.trim();
    if (!t) return;
    setTag("");
    await run(() => api.crmAddTag(userId, t));
  }

  async function addNote() {
    const t = note.trim();
    if (!t) return;
    setNote("");
    await run(() => api.crmAddNote(userId, t));
  }

  return (
    <div className="panel" style={{ margin: 0, marginTop: "var(--sp-5)" }}>
      <div className="panel-title sm">
        <span className="ms sm">sell</span> Заметки и теги
        {err && <span className="muted spacer">{err}</span>}
      </div>

      <div className="row" style={{ marginBottom: "var(--sp-3)" }}>
        {data.tags.map((t) => (
          <span key={t} className="pill" style={{ display: "inline-flex", alignItems: "center", gap: 4 }}>
            {t}
            <button className="btn ghost sm" style={{ padding: "0 4px", lineHeight: 1 }}
              title="Удалить тег"
              onClick={() => { if (!confirm(`Удалить тег «${t}»?`)) return; run(() => api.crmDeleteTag(userId, t)); }}>×
            </button>
          </span>
        ))}
        {data.tags.length === 0 && <span className="muted">тегов нет</span>}
      </div>

      <div className="toolbar" style={{ marginBottom: "var(--sp-4)" }}>
        <input className="grow" placeholder="Новый тег" value={tag} maxLength={40}
          onChange={(e) => setTag(e.target.value)}
          onKeyDown={(e) => e.key === "Enter" && addTag()} />
        <button className="btn ghost" onClick={addTag}>+ Тег</button>
      </div>

      <div className="toolbar" style={{ marginBottom: "var(--sp-3)", alignItems: "flex-start" }}>
        <textarea className="grow" placeholder="Новая заметка" value={note} rows={2}
          style={{ resize: "vertical" }}
          onChange={(e) => setNote(e.target.value)} />
        <button className="btn" onClick={addNote}>Добавить</button>
      </div>

      {data.notes.length === 0 ? (
        <div className="muted">заметок нет</div>
      ) : (
        <table className="tbl">
          <tbody>
            {data.notes.map((n) => (
              <tr key={n.id}>
                <td style={{ whiteSpace: "pre-wrap" }}>{n.text}</td>
                <td className="muted" style={{ whiteSpace: "nowrap" }}>
                  {n.created_at ? new Date(n.created_at).toLocaleString("ru") : "—"}
                </td>
                <td style={{ width: 1 }}>
                  <button className="btn ghost sm" title="Удалить заметку"
                    onClick={() => { if (confirm("Удалить заметку?")) run(() => api.crmDeleteNote(n.id)); }}>
                    <span className="ms sm">delete</span>
                  </button>
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      )}
    </div>
  );
}

function Mini({ label, value }: { label: string; value: number }) {
  return (
    <div className="metric">
      <span className="glow" />
      <div className="top"><span className="lbl">{label}</span></div>
      <div className="num">{value.toLocaleString("ru")}</div>
    </div>
  );
}
