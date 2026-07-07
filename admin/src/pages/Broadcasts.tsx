import { useEffect, useMemo, useRef, useState } from "react";
import { api, BroadcastRow } from "../api";
import { Select } from "../components/Select";
import { Modal } from "../components/Modal";
import { sanitizeTelegramHtml } from "../lib/telegramHtml";

// Audience dimensions backed by workers/broadcast_tasks._segment_filter:
//   {} = все (кроме забаненных) · {tier:"premium"|"free"} · {language:"<code>"}.
// Anything else (страна, активность, VIP, теги…) is NOT yet filtered server-side
// and is surfaced as a backend-gated note rather than a fake control.
const TIERS = [
  { value: "all", label: "Все пользователи" },
  { value: "premium", label: "Только Premium" },
  { value: "free", label: "Только Free" },
];
const LANGS = [
  { value: "", label: "Все языки" },
  { value: "ru", label: "Русский (ru)" },
  { value: "en", label: "English (en)" },
  { value: "uk", label: "Українська (uk)" },
  { value: "uz", label: "Oʻzbek (uz)" },
  { value: "kk", label: "Қазақ (kk)" },
  { value: "es", label: "Español (es)" },
  { value: "de", label: "Deutsch (de)" },
  { value: "fr", label: "Français (fr)" },
  { value: "tr", label: "Türkçe (tr)" },
  { value: "ar", label: "العربية (ar)" },
  { value: "zh", label: "中文 (zh)" },
];

type Draft = {
  title: string; comment: string; description: string;
  text: string; photoUrl: string; btnText: string; btnUrl: string;
  tier: string; language: string; sendMode: "now" | "schedule"; schedule: string;
};
const EMPTY: Draft = {
  title: "", comment: "", description: "", text: "", photoUrl: "",
  btnText: "", btnUrl: "", tier: "all", language: "", sendMode: "now", schedule: "",
};
const DRAFT_KEY = "bc_draft_v1";
const TPL_KEY = "bc_templates_v1";

type Template = { id: string; name: string; d: Partial<Draft> };

// --- status → badge mapping (replaces the old 3-way ok/warn/danger pill) ---
const STATUS: Record<string, { cls: string; label: string }> = {
  draft: { cls: "muted", label: "Черновик" },
  scheduled: { cls: "warn", label: "Запланирована" },
  queued: { cls: "pro", label: "В очереди" },
  sending: { cls: "live", label: "Отправляется" },
  done: { cls: "ok", label: "Завершена" },
  failed: { cls: "danger", label: "Ошибка" },
  cancelled: { cls: "muted", label: "Отменена" },
};
function StatusBadge({ status }: { status: string }) {
  const s = STATUS[status] ?? { cls: "muted", label: status };
  return (
    <span className={"pill " + s.cls}>
      {status === "sending" && <span className="dot" />}
      {s.label}
    </span>
  );
}

function segLabel(seg: Record<string, unknown> | undefined): string {
  const s = seg || {};
  const parts: string[] = [];
  const t = s.tier;
  if (t === "premium") parts.push("Premium");
  else if (t === "free") parts.push("Free");
  else parts.push("Все");
  if (s.language) parts.push(String(s.language).toUpperCase());
  return parts.join(" · ");
}

const reached = (b: BroadcastRow) => (b.sent || 0) + (b.failed || 0);
const deliveryRate = (b: BroadcastRow) => {
  const r = reached(b);
  return r ? Math.round(((b.sent || 0) / r) * 100) : null;
};
const cFloat = (c: Record<string, unknown> | null | undefined, k: string) =>
  (c && typeof c[k] === "string" ? (c[k] as string) : "");

export function Broadcasts() {
  const [rows, setRows] = useState<BroadcastRow[] | null>(null);
  const [d, setD] = useState<Draft>(EMPTY);
  const [templates, setTemplates] = useState<Template[]>([]);
  const [sending, setSending] = useState(false);
  const [msg, setMsg] = useState("");
  const [view, setView] = useState<BroadcastRow | null>(null);
  const [audCount, setAudCount] = useState<number | null>(null);
  const [refreshing, setRefreshing] = useState(false);
  const builderRef = useRef<HTMLDivElement>(null);

  const set = <K extends keyof Draft>(k: K, v: Draft[K]) => setD((p) => ({ ...p, [k]: v }));

  const load = () =>
    api.broadcasts().then((r) => setRows(r)).catch((e) => { setMsg(String(e)); setRows([]); });
  useEffect(() => { load(); }, []);

  async function refresh() {
    setRefreshing(true);
    try { await load(); } finally { setRefreshing(false); }
  }

  // Live progress: a broadcast that is queued/sending/scheduled is still moving, so
  // poll every 10s ONLY while at least one is active (an all-idle history makes no
  // request — no needless server load).
  const hasActive = (rows || []).some(
    (b) => b.status === "queued" || b.status === "sending" || b.status === "scheduled",
  );
  useEffect(() => {
    if (!hasActive) return;
    const t = setInterval(() => { load(); }, 10000);
    return () => clearInterval(t);
  }, [hasActive]);

  // Audience-size preview: count how many users the current segment reaches (debounced),
  // using the exact server-side predicate so the number matches the real send.
  useEffect(() => {
    let cancelled = false;
    const seg: Record<string, unknown> = {};
    if (d.tier === "premium" || d.tier === "free") seg.tier = d.tier;
    if (d.language) seg.language = d.language;
    setAudCount(null);
    const t = setTimeout(() => {
      api.estimateBroadcast(seg)
        .then((r) => { if (!cancelled) setAudCount(r.count); })
        .catch(() => { if (!cancelled) setAudCount(null); });
    }, 350);
    return () => { cancelled = true; clearTimeout(t); };
  }, [d.tier, d.language]);

  // Restore autosaved draft + templates once.
  useEffect(() => {
    try {
      const raw = localStorage.getItem(DRAFT_KEY);
      if (raw) setD({ ...EMPTY, ...JSON.parse(raw) });
      const t = localStorage.getItem(TPL_KEY);
      if (t) setTemplates(JSON.parse(t));
    } catch { /* ignore corrupt storage */ }
  }, []);
  // Autosave draft on every change (skip the pristine empty state).
  useEffect(() => {
    if (JSON.stringify(d) === JSON.stringify(EMPTY)) localStorage.removeItem(DRAFT_KEY);
    else localStorage.setItem(DRAFT_KEY, JSON.stringify(d));
  }, [d]);

  const buildSegment = (): Record<string, unknown> => {
    const seg: Record<string, unknown> = {};
    if (d.tier === "premium" || d.tier === "free") seg.tier = d.tier;
    if (d.language) seg.language = d.language;
    return seg;
  };

  async function send() {
    if (!d.text.trim() && !d.photoUrl.trim()) { setMsg("Введите текст или ссылку на фото"); return; }
    if ((d.btnText.trim() ? 1 : 0) + (d.btnUrl.trim() ? 1 : 0) === 1) {
      setMsg("Для кнопки нужны и текст, и ссылка"); return;
    }
    let when: Date | null = null;
    if (d.sendMode === "schedule") {
      if (!d.schedule) { setMsg("Укажите дату и время запланированной отправки"); return; }
      when = new Date(d.schedule);
      if (when.getTime() <= Date.now()) { setMsg("Время отправки должно быть в будущем"); return; }
    }
    const seg = buildSegment();
    const audience = Object.keys(seg).length === 0 ? "ВСЕМ пользователям" : `сегменту «${segLabel(seg)}»`;
    const sizeNote = audCount != null ? ` (≈ ${audCount.toLocaleString("ru")} получателей)` : "";
    const action = when ? `запланировать на ${when.toLocaleString("ru")}` : "отправить СЕЙЧАС";
    if (!confirm(`Рассылка будет отправлена ${audience}${sizeNote}.\n\n${action}?\n\nЭто действие затронет много пользователей и не может быть отменено после старта.`)) return;

    setSending(true);
    try {
      await api.createBroadcast({
        segment: seg,
        text: d.text.trim(),
        photo_url: d.photoUrl.trim() || null,
        button_text: d.btnText.trim() || null,
        button_url: d.btnUrl.trim() || null,
        scheduled_at: when ? when.toISOString() : null,
        title: d.title.trim() || null,
        comment: d.comment.trim() || null,
        description: d.description.trim() || null,
      });
      setD(EMPTY);
      localStorage.removeItem(DRAFT_KEY);
      setMsg(when ? "✅ Рассылка запланирована" : "✅ Рассылка поставлена в очередь");
      await load();
    } catch (e) { setMsg(String(e)); }
    finally { setSending(false); }
  }

  async function cancel(b: BroadcastRow) {
    if (!confirm(`Отменить запланированную рассылку #${b.id}? Она не будет отправлена.`)) return;
    try {
      await api.cancelBroadcast(b.id);
      setMsg(`✅ Рассылка #${b.id} отменена`);
      await load();
    } catch (e) { setMsg(String(e)); }
  }

  function duplicate(b: BroadcastRow) {
    const c = b.content || {};
    const seg = b.segment || {};
    setD({
      ...EMPTY,
      title: cFloat(c, "title"), comment: cFloat(c, "comment"), description: cFloat(c, "description"),
      text: cFloat(c, "text"), photoUrl: cFloat(c, "photo_url"),
      btnText: cFloat(c, "button_text"), btnUrl: cFloat(c, "button_url"),
      tier: seg.tier === "premium" || seg.tier === "free" ? String(seg.tier) : "all",
      language: seg.language ? String(seg.language) : "",
      // FIX: AUDIT-2 - restore sendMode + schedule from source
      sendMode: b.scheduled_at ? "schedule" : "now",
      schedule: b.scheduled_at ? new Date(b.scheduled_at).toISOString().slice(0,16) : "",
    });
    setMsg("📋 Кампания скопирована в конструктор — отредактируйте и отправьте");
    builderRef.current?.scrollIntoView({ behavior: "smooth", block: "start" });
  }

  function saveTemplate() {
    if (!d.text.trim() && !d.photoUrl.trim()) { setMsg("Нечего сохранять — заполните сообщение"); return; }
    const name = prompt("Название шаблона:", d.title.trim() || "Шаблон");
    if (!name) return;
    const t: Template = {
      id: String(Date.now()), name,
      d: { title: d.title, text: d.text, photoUrl: d.photoUrl, btnText: d.btnText, btnUrl: d.btnUrl },
    };
    const next = [t, ...templates].slice(0, 20);
    setTemplates(next);
    localStorage.setItem(TPL_KEY, JSON.stringify(next));
    setMsg(`✅ Шаблон «${name}» сохранён`);
  }
  function applyTemplate(id: string) {
    const t = templates.find((x) => x.id === id);
    if (t) setD((p) => ({ ...p, ...t.d }));
  }

  const kpi = useMemo(() => {
    const r = rows || [];
    const today = new Date(); today.setHours(0, 0, 0, 0);
    const isToday = (iso: string) => new Date(iso) >= today;
    const done = r.filter((b) => b.status === "done");
    const sumSent = done.reduce((a, b) => a + (b.sent || 0), 0);
    const sumReached = done.reduce((a, b) => a + reached(b), 0);
    return {
      total: r.length,
      sentToday: r.filter((b) => b.status === "done" && isToday(b.created_at)).reduce((a, b) => a + (b.sent || 0), 0),
      scheduled: r.filter((b) => b.status === "scheduled").length,
      inProgress: r.filter((b) => b.status === "queued" || b.status === "sending").length,
      completed: done.length,
      errors: r.reduce((a, b) => a + (b.failed || 0), 0),
      delivery: sumReached ? Math.round((sumSent / sumReached) * 100) : null,
    };
  }, [rows]);

  const isEmpty = d.text.trim() === "" && d.photoUrl.trim() === "";
  const dirty = JSON.stringify(d) !== JSON.stringify(EMPTY);

  return (
    <div>
      <h1 className="page-title">Рассылки</h1>
      <p className="page-sub">Центр управления массовыми сообщениями: конструктор, сегментация, планирование и аналитика доставки.</p>

      {msg && (
        <p className={msg.startsWith("✅") || msg.startsWith("📋") ? "note-ok" : "note-err"}>
          <span className="ms sm">{msg.startsWith("✅") ? "check_circle" : msg.startsWith("📋") ? "content_copy" : "error"}</span>
          {msg}
          <button className="btn ghost sm" onClick={() => setMsg("")} aria-label="Скрыть">×</button>
        </p>
      )}

      <div className="page-stack">
        {/* ---------- KPI ---------- */}
        <div className="metrics">
          <Metric icon="campaign" label="Всего рассылок" value={kpi.total} />
          <Metric icon="send" label="Отправлено сегодня" value={kpi.sentToday} />
          <Metric icon="schedule" label="Запланировано" value={kpi.scheduled} tone={kpi.scheduled ? "purple" : undefined} />
          <Metric icon="autorenew" label="В процессе" value={kpi.inProgress} tone={kpi.inProgress ? "purple" : undefined} />
          <Metric icon="task_alt" label="Завершено" value={kpi.completed} />
          <Metric icon="error" label="Ошибок доставки" value={kpi.errors} tone={kpi.errors ? "danger" : undefined} />
          <Metric icon="done_all" label="Avg Delivery Rate" value={kpi.delivery ?? "—"} suffix={kpi.delivery != null ? "%" : undefined} />
        </div>

        {/* ---------- Constructor ---------- */}
        <div className="panel" ref={builderRef}>
          <div className="section-head">
            <div className="panel-title" style={{ margin: 0 }}>
              <span className="ms sm">edit_note</span> Новая рассылка
              {dirty && <span className="pill warn">● черновик</span>}
            </div>
            <div className="form-row">
              {templates.length > 0 && (
                <Select ariaLabel="Применить шаблон" width={190} value=""
                  onChange={applyTemplate}
                  options={[{ value: "", label: "Шаблоны…" }, ...templates.map((t) => ({ value: t.id, label: t.name }))]} />
              )}
              <button className="btn ghost sm" onClick={saveTemplate} title="Сохранить текущее сообщение как шаблон">
                <span className="ms sm">bookmark_add</span> Шаблон
              </button>
              {dirty && (
                <button className="btn ghost sm" onClick={() => { setD(EMPTY); localStorage.removeItem(DRAFT_KEY); }}
                  title="Очистить конструктор">
                  <span className="ms sm">restart_alt</span> Очистить
                </button>
              )}
            </div>
          </div>

          <div className="bc-grid">
            {/* left: form */}
            <div style={{ display: "flex", flexDirection: "column", gap: "var(--sp-4)" }}>
              <Group title="Основная информация" hint="Внутренние поля для вашей команды — пользователям не показываются.">
                <div className="form-grid">
                  <div className="cfg-field">
                    <span className="cfg-cap">Название кампании</span>
                    <input placeholder="Напр. «Летняя акция -30%»" value={d.title} onChange={(e) => set("title", e.target.value)} />
                  </div>
                  <div className="cfg-field">
                    <span className="cfg-cap">Внутренний комментарий</span>
                    <input placeholder="Заметка для команды" value={d.comment} onChange={(e) => set("comment", e.target.value)} />
                  </div>
                </div>
                <div className="cfg-field">
                  <span className="cfg-cap">Описание</span>
                  <input placeholder="Цель и контекст кампании" value={d.description} onChange={(e) => set("description", e.target.value)} />
                </div>
              </Group>

              <Group title="Сообщение"
                hint="Telegram-разметка HTML: <b>жирный</b>, <i>курсив</i>, <a href='…'>ссылка</a>, <code>код</code>. Эмодзи — как обычный текст.">
                <textarea style={{ minHeight: 120 }} maxLength={4096} placeholder="Текст сообщения…"
                  value={d.text} onChange={(e) => set("text", e.target.value)} />
              </Group>

              <Group title="Медиа"
                hint="Сейчас поддерживается одно изображение по URL. Загрузка файлов и несколько медиа (видео, GIF, документы, аудио) требуют файлового бэкенда — в разработке.">
                <div className="cfg-field">
                  <span className="cfg-cap">Изображение (URL)</span>
                  <input placeholder="https://…/banner.jpg" value={d.photoUrl} onChange={(e) => set("photoUrl", e.target.value)} />
                </div>
              </Group>

              <Group title="Inline-кнопка"
                hint="Поддерживается одна URL-кнопка под сообщением. Callback / WebApp / Login-кнопки и многострочные клавиатуры требуют доработки воркера.">
                <div className="form-grid">
                  <div className="cfg-field">
                    <span className="cfg-cap">Текст кнопки</span>
                    <input placeholder="Открыть" value={d.btnText} onChange={(e) => set("btnText", e.target.value)} />
                  </div>
                  <div className="cfg-field">
                    <span className="cfg-cap">Ссылка кнопки</span>
                    <input placeholder="https://t.me/…" value={d.btnUrl} onChange={(e) => set("btnUrl", e.target.value)} />
                  </div>
                </div>
              </Group>

              <Group title="Сегментация аудитории"
                hint="Серверная фильтрация по тарифу и языку (забаненные исключаются всегда). Доп. условия (страна, активность, баланс, VIP, теги) пока не фильтруются на бэкенде.">
                <div className="form-grid">
                  <div className="cfg-field">
                    <span className="cfg-cap">Тариф</span>
                    <Select width="100%" ariaLabel="Тариф" value={d.tier} onChange={(v) => set("tier", v)} options={TIERS} />
                  </div>
                  <div className="cfg-field">
                    <span className="cfg-cap">Язык интерфейса</span>
                    <Select width="100%" ariaLabel="Язык" value={d.language} onChange={(v) => set("language", v)} options={LANGS} />
                  </div>
                </div>
                <p className="cfg-hint" style={{ display: "flex", alignItems: "center", gap: 6 }}>
                  <span className="ms sm">groups</span>
                  Целевой сегмент: <b style={{ color: "var(--text)" }}>{segLabel(buildSegment())}</b>
                  <span style={{ color: "var(--hint)" }}>·</span>
                  {audCount == null
                    ? <span className="muted">подсчёт…</span>
                    : <b style={{ color: "var(--accent)" }}>≈ {audCount.toLocaleString("ru")} получателей</b>}
                </p>
              </Group>

              <Group title="Планирование"
                hint="Время указывается в вашем часовом поясе и сохраняется в UTC. Повторение (ежедневно/еженедельно), таймзона получателя и авто-остановка требуют доработки планировщика.">
                <div className="seg-tabs" style={{ marginBottom: "var(--sp-3)" }}>
                  <button className={d.sendMode === "now" ? "on" : ""} onClick={() => set("sendMode", "now")}>Отправить сейчас</button>
                  <button className={d.sendMode === "schedule" ? "on" : ""} onClick={() => set("sendMode", "schedule")}>Запланировать</button>
                </div>
                {d.sendMode === "schedule" && (
                  <div className="cfg-field">
                    <span className="cfg-cap">Дата и время отправки</span>
                    <input type="datetime-local" aria-label="Дата и время отправки" value={d.schedule} onChange={(e) => set("schedule", e.target.value)} />
              <span className="cfg-hint">Время — в вашем часовом поясе: {Intl.DateTimeFormat().resolvedOptions().timeZone}</span>
                  </div>
                )}
              </Group>

              <Group title="Тестовая отправка"
                hint="Предпросмотр справа показывает, как сообщение увидит пользователь. Реальная тест-отправка себе/администраторам появится после добавления тест-эндпоинта воркера.">
                <p className="cfg-hint" style={{ margin: 0 }}>
                  <span className="ms sm" style={{ verticalAlign: "-3px" }}>visibility</span>{" "}
                  Используйте живой предпросмотр для проверки вёрстки, эмодзи и кнопки перед массовой отправкой.
                </p>
              </Group>

              <div className="toolbar" style={{ marginTop: "var(--sp-2)", marginBottom: 0 }}>
                <button className="btn spacer" onClick={send} disabled={sending || isEmpty}>
                  <span className="ms sm">{d.sendMode === "schedule" ? "schedule_send" : "send"}</span>
                  {sending ? "Отправка…" : d.sendMode === "schedule" ? "Запланировать" : "Отправить"}
                </button>
              </div>
            </div>

            {/* right: live Telegram preview */}
            <div className="bc-preview">
              <div className="panel-title sm" style={{ marginBottom: "var(--sp-3)" }}>
                <span className="ms sm">smartphone</span> Предпросмотр Telegram
              </div>
              <TgPreview text={d.text} photo={d.photoUrl} btnText={d.btnText} btnUrl={d.btnUrl} />
            </div>
          </div>
        </div>

        {/* ---------- History ---------- */}
        <div className="panel">
          <div className="section-head">
            <div className="panel-title" style={{ margin: 0 }}>
              <span className="ms sm">history</span> История рассылок
              {hasActive && <span className="pill live"><span className="dot" /> live</span>}
            </div>
            <button className="btn ghost sm" onClick={refresh} disabled={refreshing} title="Обновить">
              <span className={"ms sm" + (refreshing ? " spin" : "")}>refresh</span> Обновить
            </button>
          </div>
          {rows === null ? (
            <div className="loading">Загрузка…</div>
          ) : rows.length === 0 ? (
            <div className="empty-state">
              <div className="es-icon"><span className="ms">campaign</span></div>
              <p className="es-title">Рассылок ещё не было</p>
              <p className="es-desc">Создайте первую кампанию: соберите сообщение в конструкторе, выберите сегмент аудитории и отправьте сразу или по расписанию.</p>
              <button className="btn" onClick={() => builderRef.current?.scrollIntoView({ behavior: "smooth" })}>
                <span className="ms sm">add</span> Создать первую рассылку
              </button>
            </div>
          ) : (
            <div className="table-wrap" tabIndex={0} style={{ border: "none" }}>
              <table className="tbl">
                <thead>
                  <tr>
                    <th style={{ width: 48 }}>ID</th>
                    <th>Название</th>
                    <th>Статус</th>
                    <th>Сегмент</th>
                    <th style={{ textAlign: "right" }}>Получателей</th>
                    <th style={{ textAlign: "right" }}>Доставлено</th>
                    <th style={{ textAlign: "right" }}>Ошибок</th>
                    <th style={{ width: 150 }}>Delivery</th>
                    <th>Создана</th>
                    <th>Запланирована</th>
                    <th>Автор</th>
                    <th style={{ width: 130 }}>Действия</th>
                  </tr>
                </thead>
                <tbody>
                  {rows.map((b) => {
                    const dr = deliveryRate(b);
                    const done = b.status === "done";
                    const live = done || b.status === "sending";  // sending shows running counts
                    return (
                      <tr key={b.id}>
                        <td className="code-key">{b.id}</td>
                        <td>
                          <div className="clamp-2" style={{ maxWidth: 220, fontWeight: 600 }}>
                            {cFloat(b.content, "title") || <span className="muted">Без названия</span>}
                          </div>
                          {cFloat(b.content, "text") && (
                            <div className="clamp-2 muted" style={{ maxWidth: 220, fontSize: 12 }}>
                              {cFloat(b.content, "text").replace(/<[^>]+>/g, "")}
                            </div>
                          )}
                        </td>
                        <td><StatusBadge status={b.status} /></td>
                        <td className="muted">{segLabel(b.segment)}</td>
                        <td style={{ textAlign: "right", fontVariantNumeric: "tabular-nums" }}>
                          {done || b.status === "sending" ? reached(b).toLocaleString("ru") : <span className="muted">—</span>}
                        </td>
                        <td style={{ textAlign: "right", fontVariantNumeric: "tabular-nums" }}>
                          {live ? (b.sent || 0).toLocaleString("ru") : <span className="muted">—</span>}
                        </td>
                        <td style={{ textAlign: "right", fontVariantNumeric: "tabular-nums" }}>
                          {live ? <span className={b.failed ? "danger" : ""}>{(b.failed || 0).toLocaleString("ru")}</span> : <span className="muted">—</span>}
                        </td>
                        <td>
                          {dr == null ? <span className="muted">—</span> : (
                            <div style={{ display: "flex", alignItems: "center", gap: 8 }}>
                              <div className={"bcbar" + (dr < 80 ? " warn" : "") + (dr < 50 ? " danger" : "")}>
                                <span style={{ width: dr + "%" }} />
                              </div>
                              <b style={{ fontVariantNumeric: "tabular-nums", fontSize: 12 }}>{dr}%</b>
                            </div>
                          )}
                        </td>
                        <td className="muted" style={{ whiteSpace: "nowrap" }}>{new Date(b.created_at).toLocaleString("ru")}</td>
                        <td className="muted" style={{ whiteSpace: "nowrap" }}>
                          {b.scheduled_at ? new Date(b.scheduled_at).toLocaleString("ru") : "—"}
                        </td>
                        <td className="muted">{b.author || (b.admin_id ? "#" + b.admin_id : "—")}</td>
                        <td>
                          <div className="form-row" style={{ gap: 4, flexWrap: "nowrap" }}>
                            <button className="btn ghost sm" onClick={() => setView(b)} title="Просмотр">
                              <span className="ms sm">visibility</span>
                            </button>
                            <button className="btn ghost sm" onClick={() => duplicate(b)} title="Дублировать">
                              <span className="ms sm">content_copy</span>
                            </button>
                            {b.status === "scheduled" && (
                              <button className="btn ghost sm" onClick={() => cancel(b)} title="Отменить">
                                <span className="ms sm" style={{ color: "var(--danger)" }}>cancel</span>
                              </button>
                            )}
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

      {view && <ViewModal b={view} onClose={() => setView(null)} onDuplicate={() => { duplicate(view); setView(null); }} />}
    </div>
  );
}

// ---------- subcomponents ----------

function Group({ title, hint, children }: { title: string; hint?: string; children: React.ReactNode }) {
  return (
    <div>
      <div className="panel-title sm" style={{ margin: "0 0 var(--sp-2)", display: "flex", alignItems: "center", gap: 6 }}>
        {title}
        {hint && <span className="ms sm" title={hint} style={{ color: "var(--hint)", cursor: "help", fontSize: 15 }}>info</span>}
      </div>
      <div style={{ display: "flex", flexDirection: "column", gap: "var(--sp-3)" }}>{children}</div>
    </div>
  );
}

function TgPreview({ text, photo, btnText, btnUrl }: { text: string; photo: string; btnText: string; btnUrl: string }) {
  return (
    <div className="tg-preview">
      <div className="tg-bubble">
        {photo.trim() && (
          <img src={photo} alt="" onError={(e) => { (e.currentTarget.style.display = "none"); }} />
        )}
        <div className="tg-text" dangerouslySetInnerHTML={{ __html: sanitizeTelegramHtml(text) }} />
        {btnText.trim() && btnUrl.trim() && (
          <div className="tg-kbd">
            <div className="tg-btn"><span className="ms">open_in_new</span> {btnText}</div>
          </div>
        )}
      </div>
    </div>
  );
}

function ViewModal({ b, onClose, onDuplicate }: { b: BroadcastRow; onClose: () => void; onDuplicate: () => void }) {
  const c = b.content || {};
  const dr = deliveryRate(b);
  const done = b.status === "done";
  return (
    <Modal title={cFloat(c, "title") || `Рассылка #${b.id}`} icon="campaign" onClose={onClose} wide
      footer={<>
        <button className="btn ghost spacer" onClick={onDuplicate}><span className="ms sm">content_copy</span> Дублировать</button>
        <button className="btn ghost" onClick={onClose}>Закрыть</button>
      </>}>
      <div style={{ display: "flex", alignItems: "center", gap: 10, marginBottom: "var(--sp-4)" }}>
        <StatusBadge status={b.status} />
        <span className="muted" style={{ fontSize: 13 }}>Сегмент: {segLabel(b.segment)}</span>
      </div>

      {cFloat(c, "comment") && <p className="cfg-hint" style={{ margin: "0 0 var(--sp-2)" }}>💬 {cFloat(c, "comment")}</p>}
      {cFloat(c, "description") && <p className="cfg-hint" style={{ margin: "0 0 var(--sp-4)" }}>{cFloat(c, "description")}</p>}

      <div className="panel-title sm" style={{ margin: "0 0 var(--sp-2)" }}>Сообщение</div>
      <TgPreview text={cFloat(c, "text")} photo={cFloat(c, "photo_url")} btnText={cFloat(c, "button_text")} btnUrl={cFloat(c, "button_url")} />

      <div className="metrics" style={{ margin: "var(--sp-4) 0 0" }}>
        <Metric icon="group" label="Получателей" value={done || b.status === "sending" ? reached(b) : "—"} />
        <Metric icon="done_all" label="Доставлено" value={done ? (b.sent || 0) : "—"} />
        <Metric icon="error" label="Ошибок" value={done ? (b.failed || 0) : "—"} tone={b.failed ? "danger" : undefined} />
        <Metric icon="percent" label="Delivery Rate" value={dr ?? "—"} suffix={dr != null ? "%" : undefined} />
      </div>

      <div className="form-grid" style={{ marginTop: "var(--sp-4)" }}>
        <div className="cfg-field"><span className="cfg-cap">Создана</span><span>{new Date(b.created_at).toLocaleString("ru")}</span></div>
        <div className="cfg-field"><span className="cfg-cap">Запланирована</span><span>{b.scheduled_at ? new Date(b.scheduled_at).toLocaleString("ru") : "—"}</span></div>
        <div className="cfg-field"><span className="cfg-cap">Автор</span><span>{b.author || (b.admin_id ? "#" + b.admin_id : "—")}</span></div>
        <div className="cfg-field"><span className="cfg-cap">ID</span><span className="code-key">{b.id}</span></div>
      </div>

      <p className="cfg-hint" style={{ marginTop: "var(--sp-4)" }}>
        <span className="ms sm" style={{ verticalAlign: "-3px" }}>info</span>{" "}
        Пофамильный список получателей и журнал Telegram API будут доступны после добавления
        таблицы доставок (per-recipient delivery log) на бэкенде.
      </p>
    </Modal>
  );
}

function Metric({ icon, label, value, suffix, tone }: {
  icon: string; label: string; value: number | string; suffix?: string; tone?: "purple" | "danger";
}) {
  return (
    <div className={"metric" + (tone ? " " + tone : "")}>
      <span className="glow" />
      <div className="top"><span className="lbl">{label}</span><span className="ms sm">{icon}</span></div>
      <div><div className="num">{typeof value === "number" ? value.toLocaleString("ru") : value}{suffix && <small>{suffix}</small>}</div></div>
    </div>
  );
}
