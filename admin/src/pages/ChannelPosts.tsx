import { useEffect, useMemo, useRef, useState } from "react";
import { adminFetch, logout } from "../api";  // FIX: F41 - logout() on 401
import { Select } from "../components/Select";
import { Modal } from "../components/Modal";
import { sanitizeTelegramHtml } from "../lib/telegramHtml";

// JSON wrapper over the shared `adminFetch` — inherits credential handling plus the
// transparent token refresh on 401 (no premature "session expired" mid-session).
async function cReq<T>(path: string, init: RequestInit = {}): Promise<T> {
  const res = await adminFetch(path, {
    ...init,
    headers: { ...(init.headers ?? {}), "Content-Type": "application/json" },
  });
  if (res.status === 401) { logout(); window.dispatchEvent(new CustomEvent("admin:unauth")); throw new Error("session expired"); }  // FIX: F41 + AUDIT-H8
  if (!res.ok) throw new Error(`API ${res.status}`);
  return res.json() as Promise<T>;
}

interface ChannelPostRow {
  id: number;
  channel: string;
  text: string;
  photo_url: string | null;
  button_text: string | null;
  button_url: string | null;
  status: string;
  scheduled_at: string | null;
  sent_at: string | null;
  error: string | null;
  created_at: string | null;
  updated_at: string | null;
}

const posts = {
  list: () => cReq<ChannelPostRow[]>("/channel-posts/"),
  create: (body: Record<string, unknown>) =>
    cReq<ChannelPostRow>("/channel-posts/", { method: "POST", body: JSON.stringify(body) }),
  sendNow: (id: number) => cReq<ChannelPostRow>(`/channel-posts/${id}/send-now`, { method: "POST" }),
  remove: (id: number) => cReq<{ ok: boolean }>(`/channel-posts/${id}`, { method: "DELETE" }),
};

type Draft = {
  name: string; category: string; tags: string; comment: string;
  channels: string[]; channelInput: string;
  text: string; photoUrl: string; btnText: string; btnUrl: string;
  sendMode: "now" | "schedule"; schedule: string;
};
const EMPTY: Draft = {
  name: "", category: "", tags: "", comment: "",
  channels: [], channelInput: "", text: "", photoUrl: "",
  btnText: "", btnUrl: "", sendMode: "now", schedule: "",
};
const DRAFT_KEY = "cp_draft_v1";
const TPL_KEY = "cp_templates_v1";
type Template = { id: string; name: string; d: Partial<Draft> };

const CATEGORIES = ["", "Новости", "Акция", "Анонс", "Дайджест", "Гайд", "Развлечение"];

// pending+future = Scheduled · pending+due = Queued · sent = Published · failed.
function statusInfo(p: ChannelPostRow): { cls: string; label: string } {
  if (p.status === "sent") return { cls: "ok", label: "Опубликовано" };
  if (p.status === "failed") return { cls: "danger", label: "Ошибка" };
  if (p.scheduled_at && new Date(p.scheduled_at).getTime() > Date.now())
    return { cls: "warn", label: "Запланирована" };
  return { cls: "pro", label: "В очереди" };
}
function StatusBadge({ p }: { p: ChannelPostRow }) {
  const s = statusInfo(p);
  return <span className={"pill " + s.cls}>{s.label}</span>;
}
function contentType(p: { text: string; photo_url: string | null; button_url: string | null }): string {
  const out: string[] = [];
  if (p.photo_url) out.push("Фото");
  if (p.text) out.push("Текст");
  if (p.button_url) out.push("Кнопка");
  return out.join(" + ") || "—";
}
const dt = (iso: string | null) => (iso ? new Date(iso).toLocaleString("ru") : "—");
const dateOf = (p: ChannelPostRow) => p.scheduled_at || p.sent_at || p.created_at || null;
const dayKey = (d: Date) => `${d.getFullYear()}-${d.getMonth()}-${d.getDate()}`;
const WD = ["Пн", "Вт", "Ср", "Чт", "Пт", "Сб", "Вс"];
const MONTHS = ["Январь", "Февраль", "Март", "Апрель", "Май", "Июнь", "Июль", "Август", "Сентябрь", "Октябрь", "Ноябрь", "Декабрь"];

export function ChannelPosts() {
  const [rows, setRows] = useState<ChannelPostRow[] | null>(null);
  const [d, setD] = useState<Draft>(EMPTY);
  const [templates, setTemplates] = useState<Template[]>([]);
  const [msg, setMsg] = useState("");
  const [busy, setBusy] = useState<number | null>(null);
  const [creating, setCreating] = useState(false);
  const [view, setView] = useState<ChannelPostRow | null>(null);
  const [plan, setPlan] = useState<"list" | "calendar">("list");
  const [cal, setCal] = useState(() => { const n = new Date(); return { y: n.getFullYear(), m: n.getMonth() }; });
  const [selDay, setSelDay] = useState<string | null>(null);
  const [showBuilder, setShowBuilder] = useState(false);
  const [refreshing, setRefreshing] = useState(false);
  const builderRef = useRef<HTMLDivElement>(null);
  const textRef = useRef<HTMLTextAreaElement>(null);

  const set = <K extends keyof Draft>(k: K, v: Draft[K]) => setD((p) => ({ ...p, [k]: v }));

  const load = () => posts.list().then((r) => setRows(r)).catch((e) => { setMsg(String(e)); setRows([]); });
  useEffect(() => { load(); }, []);
  useEffect(() => {
    try {
      const raw = localStorage.getItem(DRAFT_KEY);
      if (raw) { setD({ ...EMPTY, ...JSON.parse(raw) }); setShowBuilder(true); }  // restore → open
      const t = localStorage.getItem(TPL_KEY); if (t) setTemplates(JSON.parse(t));
    } catch { /* ignore */ }
  }, []);

  async function refresh() {
    setRefreshing(true);
    try { await load(); } finally { setRefreshing(false); }
  }

  function openBuilder() {
    setShowBuilder(true);
    requestAnimationFrame(() => builderRef.current?.scrollIntoView({ behavior: "smooth", block: "start" }));
  }

  // Live status: a pending post is published by the every-minute cron, so poll while
  // any post is still pending (none → no request).
  const hasPending = (rows || []).some((p) => p.status === "pending");
  useEffect(() => {
    if (!hasPending) return;
    const t = setInterval(() => { load(); }, 15000);
    return () => clearInterval(t);
  }, [hasPending]);
  useEffect(() => {
    if (JSON.stringify(d) === JSON.stringify(EMPTY)) localStorage.removeItem(DRAFT_KEY);
    else localStorage.setItem(DRAFT_KEY, JSON.stringify(d));
  }, [d]);

  // --- channel chips ---
  function addChannels(raw: string) {
    const parts = raw.split(/[,\n]/).map((s) => s.trim()).filter(Boolean);
    if (!parts.length) return;
    setD((p) => ({ ...p, channels: Array.from(new Set([...p.channels, ...parts])), channelInput: "" }));
  }
  const removeChannel = (c: string) => setD((p) => ({ ...p, channels: p.channels.filter((x) => x !== c) }));

  // --- formatting toolbar (wraps the textarea selection in a Telegram HTML tag) ---
  function wrap(open: string, close: string) {
    const el = textRef.current; if (!el) return;
    const s = el.selectionStart, e = el.selectionEnd;
    const sel = d.text.slice(s, e);
    const next = d.text.slice(0, s) + open + sel + close + d.text.slice(e);
    set("text", next);
    requestAnimationFrame(() => { el.focus(); el.selectionStart = s + open.length; el.selectionEnd = e + open.length; });
  }
  const fmt: { ic: string; t: string; fn: () => void }[] = [
    { ic: "format_bold", t: "Жирный", fn: () => wrap("<b>", "</b>") },
    { ic: "format_italic", t: "Курсив", fn: () => wrap("<i>", "</i>") },
    { ic: "format_underlined", t: "Подчёркнутый", fn: () => wrap("<u>", "</u>") },
    { ic: "format_strikethrough", t: "Зачёркнутый", fn: () => wrap("<s>", "</s>") },
    { ic: "code", t: "Моноширинный", fn: () => wrap("<code>", "</code>") },
    { ic: "visibility_off", t: "Скрытый текст (спойлер)", fn: () => wrap("<tg-spoiler>", "</tg-spoiler>") },
    { ic: "format_quote", t: "Цитата", fn: () => wrap("<blockquote>", "</blockquote>") },
    { ic: "link", t: "Ссылка", fn: () => wrap('<a href="https://">', "</a>") },
  ];

  async function create() {
    const channels = d.channelInput.trim()
      ? Array.from(new Set([...d.channels, ...d.channelInput.split(/[,\n]/).map((s) => s.trim()).filter(Boolean)]))
      : d.channels;
    if (!channels.length) { setMsg("Укажите хотя бы один канал (@name или id)"); return; }
    if (!d.text.trim() && !d.photoUrl.trim()) { setMsg("Введите текст или ссылку на фото"); return; }
    if ((d.btnText.trim() ? 1 : 0) + (d.btnUrl.trim() ? 1 : 0) === 1) { setMsg("Для кнопки нужны и текст, и ссылка"); return; }
    let when: Date | null = null;
    if (d.sendMode === "schedule") {
      if (!d.schedule) { setMsg("Укажите дату и время публикации"); return; }
      when = new Date(d.schedule);
      if (when.getTime() <= Date.now()) { setMsg("Время публикации должно быть в будущем"); return; }
    }
    const action = when ? `запланировать на ${when.toLocaleString("ru")}` : "поставить в очередь (опубликуется в ближайшую минуту)";
    if (!confirm(`Публикация в ${channels.length} канал(ов): ${channels.join(", ")}\n\n${action}?`)) return;

    setCreating(true);
    const body = {
      text: d.text.trim(), photo_url: d.photoUrl.trim() || null,
      button_text: d.btnText.trim() || null, button_url: d.btnUrl.trim() || null,
      scheduled_at: when ? when.toISOString() : null,
    };
    const failed: string[] = [];
    for (const ch of channels) {
      try { await posts.create({ ...body, channel: ch }); }
      catch { failed.push(ch); }
    }
    setCreating(false);
    if (failed.length) setMsg(`⚠ Не удалось создать для: ${failed.join(", ")}`);
    else { setD(EMPTY); localStorage.removeItem(DRAFT_KEY); setMsg(`✅ Создано публикаций: ${channels.length}`); }
    await load();
  }

  async function act(id: number, fn: () => Promise<unknown>, confirmMsg?: string) {
    if (confirmMsg && !confirm(confirmMsg)) return;
    setBusy(id);
    try { await fn(); setMsg(""); await load(); }
    catch (e) { setMsg(String(e)); }
    finally { setBusy(null); }
  }

  function duplicate(p: ChannelPostRow) {
    setD({
      ...EMPTY, channels: [p.channel], text: p.text || "", photoUrl: p.photo_url || "",
      btnText: p.button_text || "", btnUrl: p.button_url || "",
    });
    setMsg("📋 Публикация скопирована в конструктор");
    openBuilder();
  }

  function saveTemplate() {
    if (!d.text.trim() && !d.photoUrl.trim()) { setMsg("Нечего сохранять — заполните контент"); return; }
    const name = prompt("Название шаблона:", d.name.trim() || "Шаблон"); if (!name) return;
    const t: Template = { id: String(Date.now()), name, d: { name: d.name, text: d.text, photoUrl: d.photoUrl, btnText: d.btnText, btnUrl: d.btnUrl } };
    const next = [t, ...templates].slice(0, 20);
    setTemplates(next); localStorage.setItem(TPL_KEY, JSON.stringify(next));
    setMsg(`✅ Шаблон «${name}» сохранён`);
  }
  const applyTemplate = (id: string) => { const t = templates.find((x) => x.id === id); if (t) setD((p) => ({ ...p, ...t.d })); };

  const kpi = useMemo(() => {
    const r = rows || [];
    const today = new Date(); today.setHours(0, 0, 0, 0);
    const sent = r.filter((p) => p.status === "sent");
    const sentDays = new Set(sent.map((p) => p.sent_at && dayKey(new Date(p.sent_at))).filter(Boolean));
    const future = r.filter((p) => p.status === "pending" && p.scheduled_at && new Date(p.scheduled_at).getTime() > Date.now());
    const nextAt = future.map((p) => new Date(p.scheduled_at as string).getTime()).sort((a, b) => a - b)[0];
    return {
      scheduled: future.length,
      published: sent.length,
      today: sent.filter((p) => p.sent_at && new Date(p.sent_at) >= today).length,
      errors: r.filter((p) => p.status === "failed").length,
      channels: new Set(r.map((p) => p.channel)).size,
      queue: r.filter((p) => p.status === "pending" && (!p.scheduled_at || new Date(p.scheduled_at).getTime() <= Date.now())).length,
      avg: sentDays.size ? Math.round((sent.length / sentDays.size) * 10) / 10 : 0,
      next: nextAt ? new Date(nextAt) : null,
    };
  }, [rows]);

  // Per-channel aggregation for the Channels section.
  const channelsAgg = useMemo(() => {
    const m = new Map<string, { total: number; sent: number; failed: number; pending: number; last: number; next: number }>();
    for (const p of rows || []) {
      const a = m.get(p.channel) || { total: 0, sent: 0, failed: 0, pending: 0, last: 0, next: 0 };
      a.total++;
      if (p.status === "sent") { a.sent++; if (p.sent_at) a.last = Math.max(a.last, new Date(p.sent_at).getTime()); }
      else if (p.status === "failed") a.failed++;
      else { a.pending++; if (p.scheduled_at) { const t = new Date(p.scheduled_at).getTime(); if (t > Date.now()) a.next = a.next ? Math.min(a.next, t) : t; } }
      m.set(p.channel, a);
    }
    return Array.from(m.entries()).sort((x, y) => y[1].total - x[1].total);
  }, [rows]);

  // Posts-by-day (last 14 days) for the mini analytics panel.
  const byDay = useMemo(() => {
    const days: { label: string; sent: number; failed: number }[] = [];
    for (let i = 13; i >= 0; i--) {
      const dd = new Date(); dd.setHours(0, 0, 0, 0); dd.setDate(dd.getDate() - i);
      const key = dayKey(dd);
      let sent = 0, failed = 0;
      for (const p of rows || []) {
        const ref = p.status === "sent" ? p.sent_at : p.status === "failed" ? (p.scheduled_at || p.created_at) : null;
        if (ref && dayKey(new Date(ref)) === key) { p.status === "sent" ? sent++ : failed++; }
      }
      days.push({ label: `${dd.getDate()}.${dd.getMonth() + 1}`, sent, failed });
    }
    return days;
  }, [rows]);

  // Calendar grid (Mon-first) for the selected month.
  const calCells = useMemo(() => {
    const first = new Date(cal.y, cal.m, 1);
    const startOffset = (first.getDay() + 6) % 7; // Mon=0
    const start = new Date(cal.y, cal.m, 1 - startOffset);
    const byKey = new Map<string, ChannelPostRow[]>();
    for (const p of rows || []) {
      const ref = dateOf(p); if (!ref) continue;
      const k = dayKey(new Date(ref));
      (byKey.get(k) || byKey.set(k, []).get(k)!).push(p);
    }
    const cells: { date: Date; inMonth: boolean; key: string; items: ChannelPostRow[] }[] = [];
    for (let i = 0; i < 42; i++) {
      const dd = new Date(start); dd.setDate(start.getDate() + i);
      const k = dayKey(dd);
      cells.push({ date: dd, inMonth: dd.getMonth() === cal.m, key: k, items: byKey.get(k) || [] });
    }
    return cells;
  }, [cal, rows]);

  const dirty = JSON.stringify(d) !== JSON.stringify(EMPTY);
  const isEmpty = !d.text.trim() && !d.photoUrl.trim();
  const todayKey = dayKey(new Date());
  const selDayPosts = selDay ? (rows || []).filter((p) => { const r = dateOf(p); return r && dayKey(new Date(r)) === selDay; }) : [];

  return (
    <div>
      <h1 className="page-title">Автопостинг в каналы</h1>
      <p className="page-sub">Центр управления публикациями Telegram-каналов: конструктор, контент-план, расписание и аналитика.</p>

      {msg && (
        <p className={msg.startsWith("✅") || msg.startsWith("📋") ? "note-ok" : "note-err"}>
          <span className="ms sm">{msg.startsWith("✅") ? "check_circle" : msg.startsWith("📋") ? "content_copy" : "error"}</span>
          {msg}
          <button className="btn ghost sm" onClick={() => setMsg("")} aria-label="Скрыть">×</button>
        </p>
      )}

      <div className="page-stack">
        {/* KPI */}
        <div className="metrics">
          <Metric icon="schedule" label="Запланировано" value={kpi.scheduled} tone={kpi.scheduled ? "purple" : undefined} />
          <Metric icon="check_circle" label="Опубликовано" value={kpi.published} />
          <Metric icon="today" label="Сегодня" value={kpi.today} />
          <Metric icon="error" label="Ошибок" value={kpi.errors} tone={kpi.errors ? "danger" : undefined} />
          <Metric icon="rss_feed" label="Каналов" value={kpi.channels} />
          <Metric icon="pending_actions" label="Очередь" value={kpi.queue} tone={kpi.queue ? "purple" : undefined} />
          <Metric icon="trending_up" label="Avg / день" value={kpi.avg} />
          <Metric icon="upcoming" label="Следующая" value={kpi.next ? relTime(kpi.next) : "—"} small />
        </div>

        {/* Constructor */}
        <div className="panel" ref={builderRef}>
          <div className="section-head">
            <div className="panel-title" style={{ margin: 0 }}>
              <span className="ms sm">edit_note</span> Новая публикация
              {dirty && <span className="pill warn">● черновик</span>}
            </div>
            <div className="form-row">
              {showBuilder ? (
                <>
                  {templates.length > 0 && (
                    <Select ariaLabel="Шаблон" width={180} value="" onChange={applyTemplate}
                      options={[{ value: "", label: "Шаблоны…" }, ...templates.map((t) => ({ value: t.id, label: t.name }))]} />
                  )}
                  <button className="btn ghost sm" onClick={saveTemplate} title="Сохранить как шаблон">
                    <span className="ms sm">bookmark_add</span> Шаблон
                  </button>
                  {dirty && (
                    <button className="btn ghost sm" onClick={() => { setD(EMPTY); localStorage.removeItem(DRAFT_KEY); }} title="Очистить">
                      <span className="ms sm">restart_alt</span> Очистить
                    </button>
                  )}
                  <button className="btn ghost sm" onClick={() => setShowBuilder(false)} title="Свернуть конструктор">
                    <span className="ms sm">expand_less</span> Свернуть
                  </button>
                </>
              ) : (
                <button className="btn sm" onClick={openBuilder}>
                  <span className="ms sm">add</span> {dirty ? "Продолжить черновик" : "Новая публикация"}
                </button>
              )}
            </div>
          </div>

          {showBuilder && <div className="bc-grid">
            <div style={{ display: "flex", flexDirection: "column", gap: "var(--sp-4)" }}>
              <Group title="Основная информация"
                hint="Название/категория/теги/комментарий — поля черновика для вашей команды. Постоянное хранение метаданных требует миграции (новые столбцы), пока сохраняются только локально.">
                <div className="form-grid">
                  <div className="cfg-field">
                    <span className="cfg-cap">Название (внутреннее)</span>
                    <input placeholder="Напр. «Анонс релиза»" value={d.name} onChange={(e) => set("name", e.target.value)} />
                  </div>
                  <div className="cfg-field">
                    <span className="cfg-cap">Категория</span>
                    <Select width="100%" ariaLabel="Категория" value={d.category} onChange={(v) => set("category", v)}
                      options={CATEGORIES.map((c) => ({ value: c, label: c || "— без категории —" }))} />
                  </div>
                </div>
                <div className="form-grid">
                  <div className="cfg-field">
                    <span className="cfg-cap">Теги</span>
                    <input placeholder="через запятую" value={d.tags} onChange={(e) => set("tags", e.target.value)} />
                  </div>
                  <div className="cfg-field">
                    <span className="cfg-cap">Внутренний комментарий</span>
                    <input placeholder="Заметка" value={d.comment} onChange={(e) => set("comment", e.target.value)} />
                  </div>
                </div>
              </Group>

              <Group title="Каналы" hint="Можно указать несколько каналов — публикация создаётся в каждый. Enter или запятая добавляют канал.">
                <div className="cfg-field">
                  <span className="cfg-cap">Каналы назначения (@name или числовой id)</span>
                  {/* FIX: AUDIT12-M13/M14 - aria-label + maxLength 255 on channel input. */}
                  <input placeholder="@mychannel, -1001234567890" value={d.channelInput}
                    onChange={(e) => set("channelInput", e.target.value)}
                    onKeyDown={(e) => { if (e.key === "Enter" || e.key === ",") { e.preventDefault(); addChannels(d.channelInput); } }}
                    onBlur={() => d.channelInput.trim() && addChannels(d.channelInput)}
                    maxLength={255} aria-label="Каналы назначения" />
                  {d.channels.length > 0 && (
                    <div className="chip-row" style={{ marginTop: "var(--sp-2)" }}>
                      {d.channels.map((c) => (
                        <span className="chip" key={c}>
                          <span className="code-key" style={{ color: "var(--text)" }}>{c}</span>
                          <button onClick={() => removeChannel(c)} aria-label={`Убрать ${c}`}><span className="ms sm">close</span></button>
                        </span>
                      ))}
                    </div>
                  )}
                </div>
              </Group>

              <Group title="Контент"
                hint="Telegram HTML: <b>, <i>, <u>, <s>, <code>, <a href>, <blockquote>, <tg-spoiler>. Бот публикует с parse_mode=HTML. Эмодзи — как обычный текст.">
                <div className="form-row" style={{ gap: 4, flexWrap: "wrap", marginBottom: "var(--sp-2)" }}>
                  {fmt.map((f) => (
                    <button key={f.ic} className="btn ghost sm" title={f.t} onClick={f.fn} type="button"
                      style={{ padding: "6px 9px" }}><span className="ms sm">{f.ic}</span></button>
                  ))}
                </div>
                <textarea ref={textRef} style={{ minHeight: 130 }} maxLength={4096} placeholder="Текст публикации…"
                  value={d.text} onChange={(e) => set("text", e.target.value)} />
              </Group>

              <Group title="Медиа"
                hint="Сейчас поддерживается одно изображение по URL. Загрузка файлов, альбомы, видео, GIF, документы, аудио, голосовые и кружки требуют файлового бэкенда — в разработке.">
                <div className="cfg-field">
                  <span className="cfg-cap">Изображение (URL)</span>
                  <input placeholder="https://…/banner.jpg" value={d.photoUrl} onChange={(e) => set("photoUrl", e.target.value)} />
                </div>
              </Group>

              <Group title="Inline-кнопка"
                hint="Поддерживается одна URL-кнопка под публикацией. Callback / WebApp / Login и многострочные клавиатуры с Drag&Drop требуют доработки воркера.">
                <div className="form-grid">
                  <div className="cfg-field"><span className="cfg-cap">Текст кнопки</span>
                    <input placeholder="Открыть" value={d.btnText} onChange={(e) => set("btnText", e.target.value)} /></div>
                  <div className="cfg-field"><span className="cfg-cap">Ссылка кнопки</span>
                    <input placeholder="https://t.me/…" value={d.btnUrl} onChange={(e) => set("btnUrl", e.target.value)} /></div>
                </div>
              </Group>

              <Group title="Планировщик"
                hint="Время — в вашем часовом поясе, сохраняется в UTC. Воркер публикует раз в минуту. Повторение (ежедн./еженед./ежемес.), Cron, интервал и автоповтор требуют доработки планировщика.">
                <div className="seg-tabs" style={{ marginBottom: "var(--sp-3)" }}>
                  <button className={d.sendMode === "now" ? "on" : ""} onClick={() => set("sendMode", "now")}>В очередь</button>
                  <button className={d.sendMode === "schedule" ? "on" : ""} onClick={() => set("sendMode", "schedule")}>Запланировать</button>
                </div>
                {d.sendMode === "schedule" && (
                  <div className="cfg-field"><span className="cfg-cap">Дата и время публикации</span>
                    <input type="datetime-local" value={d.schedule} onChange={(e) => set("schedule", e.target.value)} /></div>
                )}
              </Group>

              <div className="toolbar" style={{ marginTop: "var(--sp-2)", marginBottom: 0 }}>
                <button className="btn spacer" onClick={create} disabled={creating || isEmpty}>
                  <span className="ms sm">{d.sendMode === "schedule" ? "schedule_send" : "send"}</span>
                  {creating ? "Создание…" : d.sendMode === "schedule" ? "Запланировать" : "В очередь"}
                </button>
              </div>
            </div>

            <div className="bc-preview">
              <div className="panel-title sm" style={{ marginBottom: "var(--sp-3)" }}>
                <span className="ms sm">smartphone</span> Предпросмотр Telegram
              </div>
              <TgPreview text={d.text} photo={d.photoUrl} btnText={d.btnText} btnUrl={d.btnUrl} />
              {d.channels.length > 1 && (
                <p className="cfg-hint" style={{ marginTop: "var(--sp-3)" }}>
                  <span className="ms sm" style={{ verticalAlign: "-3px" }}>groups</span> Будет создано {d.channels.length} публикаций — по одной в каждый канал.
                </p>
              )}
            </div>
          </div>}
        </div>

        {/* Content plan: list / calendar */}
        <div className="panel">
          <div className="section-head">
            <div className="panel-title" style={{ margin: 0 }}>
              <span className="ms sm">event_note</span> Контент-план
              {hasPending && <span className="pill live"><span className="dot" /> live</span>}
            </div>
            <div className="form-row">
              <div className="seg-tabs">
                <button className={plan === "list" ? "on" : ""} onClick={() => setPlan("list")}>Список</button>
                <button className={plan === "calendar" ? "on" : ""} onClick={() => setPlan("calendar")}>Календарь</button>
              </div>
              <button className="btn ghost sm" onClick={refresh} disabled={refreshing} title="Обновить">
                <span className={"ms sm" + (refreshing ? " spin" : "")}>refresh</span>
              </button>
            </div>
          </div>

          {rows === null ? (
            <div className="loading">Загрузка…</div>
          ) : rows.length === 0 ? (
            <div className="empty-state">
              <div className="es-icon"><span className="ms">rss_feed</span></div>
              <p className="es-title">Публикаций ещё нет</p>
              <p className="es-desc">Создайте первую публикацию: соберите пост в конструкторе, выберите каналы и отправьте сразу или по расписанию.</p>
              <button className="btn" onClick={openBuilder}>
                <span className="ms sm">add</span> Создать первую публикацию
              </button>
            </div>
          ) : plan === "calendar" ? (
            <>
              <div className="section-head" style={{ marginBottom: "var(--sp-3)" }}>
                <div className="form-row">
                  <button className="btn ghost sm" onClick={() => setCal((c) => ({ y: c.m === 0 ? c.y - 1 : c.y, m: (c.m + 11) % 12 }))}><span className="ms sm">chevron_left</span></button>
                  <b style={{ minWidth: 150, textAlign: "center", fontFamily: "var(--display)" }}>{MONTHS[cal.m]} {cal.y}</b>
                  <button className="btn ghost sm" onClick={() => setCal((c) => ({ y: c.m === 11 ? c.y + 1 : c.y, m: (c.m + 1) % 12 }))}><span className="ms sm">chevron_right</span></button>
                </div>
                <span className="cfg-hint" style={{ margin: 0 }}>Дни с публикациями отмечены точками — нажмите день, чтобы увидеть список.</span>
              </div>
              <div className="cal-head">{WD.map((w) => <span key={w}>{w}</span>)}</div>
              <div className="cal">
                {calCells.map((c) => (
                  <div key={c.key} onClick={() => setSelDay(c.key === selDay ? null : c.key)}
                    className={"cal-cell" + (c.inMonth ? "" : " muted-day") + (c.key === todayKey ? " today" : "") + (c.key === selDay ? " sel" : "")}>
                    <span className="d">{c.date.getDate()}</span>
                    {c.items.length > 0 && (
                      <div className="dots">
                        {c.items.slice(0, 6).map((p) => <span key={p.id} className={"cal-dot " + statusInfo(p).cls} />)}
                        {c.items.length > 6 && <span className="cfg-hint" style={{ fontSize: 10 }}>+{c.items.length - 6}</span>}
                      </div>
                    )}
                  </div>
                ))}
              </div>
              {selDay && (
                <div style={{ marginTop: "var(--sp-4)" }}>
                  <div className="panel-title sm" style={{ marginBottom: "var(--sp-2)" }}>Публикации за {selDay.split("-").reverse().slice(0, 2).join(".")}</div>
                  {selDayPosts.length === 0 ? <p className="cfg-hint">Нет публикаций.</p> : (
                    <div style={{ display: "flex", flexDirection: "column", gap: "var(--sp-2)" }}>
                      {selDayPosts.map((p) => (
                        <div key={p.id} className="form-row" style={{ justifyContent: "space-between", padding: "8px 10px", background: "var(--surface-1)", borderRadius: "var(--r-sm)", border: "1px solid var(--border)" }}>
                          <span className="form-row" style={{ gap: 8 }}><StatusBadge p={p} /><span className="code-key">{p.channel}</span>
                            <span className="muted clamp-2" style={{ maxWidth: 280, fontSize: 12 }}>{p.text.replace(/<[^>]+>/g, "") || contentType(p)}</span></span>
                          <button className="btn ghost sm" onClick={() => setView(p)} title="Просмотр"><span className="ms sm">visibility</span></button>
                        </div>
                      ))}
                    </div>
                  )}
                </div>
              )}
            </>
          ) : (
            <div className="table-wrap" tabIndex={0} style={{ border: "none" }}>
              <table className="tbl">
                <thead>
                  <tr>
                    <th style={{ width: 48 }}>ID</th><th>Канал</th><th>Статус</th><th>Тип</th>
                    <th>Время публикации</th><th>Создана</th><th>Изменена</th><th style={{ width: 150 }}>Действия</th>
                  </tr>
                </thead>
                <tbody>
                  {rows.map((p) => (
                    <tr key={p.id}>
                      <td className="code-key">{p.id}</td>
                      <td className="code-key">{p.channel}</td>
                      <td><StatusBadge p={p} />{p.error && <div className="muted clamp-2" style={{ fontSize: 11, maxWidth: 180 }}>{p.error}</div>}</td>
                      <td className="muted">{contentType(p)}</td>
                      <td className="muted" style={{ whiteSpace: "nowrap" }}>{dt(p.sent_at || p.scheduled_at)}</td>
                      <td className="muted" style={{ whiteSpace: "nowrap" }}>{dt(p.created_at)}</td>
                      <td className="muted" style={{ whiteSpace: "nowrap" }}>{dt(p.updated_at)}</td>
                      <td>
                        <div className="form-row" style={{ gap: 4, flexWrap: "nowrap" }}>
                          <button className="btn ghost sm" onClick={() => setView(p)} title="Просмотр"><span className="ms sm">visibility</span></button>
                          <button className="btn ghost sm" onClick={() => duplicate(p)} title="Дублировать"><span className="ms sm">content_copy</span></button>
                          {p.status === "pending" && (<>
                            <button className="btn ghost sm" disabled={busy === p.id} title="Поставить в очередь сейчас"
                              onClick={() => act(p.id, () => posts.sendNow(p.id), "Поставить в очередь? Опубликуется в ближайшую минуту.")}><span className="ms sm">bolt</span></button>
                            <button className="btn ghost sm" disabled={busy === p.id} title="Отменить / удалить"
                              onClick={() => act(p.id, () => posts.remove(p.id), `Отменить публикацию #${p.id}? Её нельзя восстановить.`)}><span className="ms sm" style={{ color: "var(--danger)" }}>delete</span></button>
                          </>)}
                        </div>
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          )}
        </div>

        {/* Channels + analytics */}
        {rows && rows.length > 0 && (
          <div className="bc-grid" style={{ gridTemplateColumns: "minmax(0,1fr) minmax(0,1fr)" }}>
            <div className="panel" style={{ margin: 0 }}>
              <div className="panel-title"><span className="ms sm">rss_feed</span> Каналы</div>
              <div className="table-wrap" tabIndex={0} style={{ border: "none" }}>
                <table className="tbl">
                  <thead><tr><th>Канал</th><th style={{ textAlign: "right" }}>Всего</th><th style={{ textAlign: "right" }}>Опубл.</th><th style={{ textAlign: "right" }}>Ошибок</th><th>След.</th></tr></thead>
                  <tbody>
                    {channelsAgg.map(([ch, a]) => (
                      <tr key={ch}>
                        <td className="code-key">{ch}</td>
                        <td style={{ textAlign: "right", fontVariantNumeric: "tabular-nums" }}>{a.total}</td>
                        <td style={{ textAlign: "right", fontVariantNumeric: "tabular-nums" }}>{a.sent}</td>
                        <td style={{ textAlign: "right", fontVariantNumeric: "tabular-nums" }}><span className={a.failed ? "danger" : "muted"}>{a.failed}</span></td>
                        <td className="muted" style={{ whiteSpace: "nowrap", fontSize: 12 }}>{a.next ? new Date(a.next).toLocaleString("ru") : "—"}</td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
              <p className="cfg-hint" style={{ marginTop: "var(--sp-3)" }}>
                <span className="ms sm" style={{ verticalAlign: "-3px" }}>info</span> Реестр каналов (аватар, права бота, лимиты, таймзона) — отдельная сущность, требует бэкенда; здесь агрегировано по фактическим публикациям.
              </p>
            </div>

            <div className="panel" style={{ margin: 0 }}>
              <div className="panel-title"><span className="ms sm">bar_chart</span> Публикации за 14 дней</div>
              <BarPanel data={byDay} />
            </div>
          </div>
        )}
      </div>

      {view && <ViewModal p={view} onClose={() => setView(null)}
        onDuplicate={() => { duplicate(view); setView(null); }}
        onSendNow={view.status === "pending" ? () => { act(view.id, () => posts.sendNow(view.id), "Поставить в очередь? Опубликуется в ближайшую минуту."); setView(null); } : undefined}
        onDelete={view.status === "pending" ? () => { act(view.id, () => posts.remove(view.id), `Отменить публикацию #${view.id}?`); setView(null); } : undefined} />}
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
        {photo.trim() && <img src={photo} alt="" onError={(e) => { e.currentTarget.style.display = "none"; }} />}
        <div className="tg-text" dangerouslySetInnerHTML={{ __html: sanitizeTelegramHtml(text) }} />
        {btnText.trim() && btnUrl.trim() && (
          <div className="tg-kbd"><div className="tg-btn"><span className="ms">open_in_new</span> {btnText}</div></div>
        )}
      </div>
    </div>
  );
}

function BarPanel({ data }: { data: { label: string; sent: number; failed: number }[] }) {
  const max = Math.max(1, ...data.map((x) => x.sent + x.failed));
  return (
    <div style={{ display: "flex", alignItems: "flex-end", gap: 6, height: 150, padding: "var(--sp-2) 0" }}>
      {data.map((x) => (
        <div key={x.label} title={`${x.label}: ${x.sent} опубл., ${x.failed} ошибок`}
          style={{ flex: 1, display: "flex", flexDirection: "column", alignItems: "center", gap: 4, minWidth: 0 }}>
          <div style={{ width: "100%", maxWidth: 18, display: "flex", flexDirection: "column", justifyContent: "flex-end", height: 120 }}>
            {x.failed > 0 && <div style={{ height: (x.failed / max) * 120, background: "var(--danger)", borderRadius: "3px 3px 0 0" }} />}
            {x.sent > 0 && <div style={{ height: (x.sent / max) * 120, background: "var(--accent)", borderRadius: x.failed ? 0 : "3px 3px 0 0" }} />}
            {x.sent === 0 && x.failed === 0 && <div style={{ height: 2, background: "var(--border)" }} />}
          </div>
          <span style={{ fontSize: 9, color: "var(--hint)", whiteSpace: "nowrap" }}>{x.label}</span>
        </div>
      ))}
    </div>
  );
}

function ViewModal({ p, onClose, onDuplicate, onSendNow, onDelete }: {
  p: ChannelPostRow; onClose: () => void; onDuplicate: () => void; onSendNow?: () => void; onDelete?: () => void;
}) {
  return (
    <Modal title={`Публикация #${p.id}`} icon="rss_feed" onClose={onClose} wide
      footer={<>
        {onSendNow && <button className="btn" onClick={onSendNow}><span className="ms sm">bolt</span> В очередь</button>}
        <button className="btn ghost spacer" onClick={onDuplicate}><span className="ms sm">content_copy</span> Дублировать</button>
        {onDelete && <button className="btn danger" onClick={onDelete}><span className="ms sm">delete</span> Отменить</button>}
        <button className="btn ghost" onClick={onClose}>Закрыть</button>
      </>}>
      <div style={{ display: "flex", alignItems: "center", gap: 10, marginBottom: "var(--sp-4)" }}>
        <StatusBadge p={p} /><span className="code-key">{p.channel}</span>
        <span className="muted" style={{ fontSize: 13 }}>{contentType(p)}</span>
      </div>
      {p.error && <p className="note-err" style={{ marginBottom: "var(--sp-4)" }}><span className="ms sm">error</span>{p.error}</p>}
      <div className="panel-title sm" style={{ margin: "0 0 var(--sp-2)" }}>Контент</div>
      <TgPreview text={p.text} photo={p.photo_url || ""} btnText={p.button_text || ""} btnUrl={p.button_url || ""} />
      <div className="form-grid" style={{ marginTop: "var(--sp-4)" }}>
        <div className="cfg-field"><span className="cfg-cap">Время публикации</span><span>{dt(p.scheduled_at)}</span></div>
        <div className="cfg-field"><span className="cfg-cap">Опубликована</span><span>{dt(p.sent_at)}</span></div>
        <div className="cfg-field"><span className="cfg-cap">Создана</span><span>{dt(p.created_at)}</span></div>
        <div className="cfg-field"><span className="cfg-cap">Изменена</span><span>{dt(p.updated_at)}</span></div>
      </div>
    </Modal>
  );
}

function relTime(d: Date): string {
  const ms = d.getTime() - Date.now();
  if (ms <= 0) return "сейчас";
  const min = Math.round(ms / 60000);
  if (min < 60) return `через ${min} мин`;
  const h = Math.round(min / 60);
  if (h < 24) return `через ${h} ч`;
  return `через ${Math.round(h / 24)} дн`;
}

function Metric({ icon, label, value, suffix, tone, small }: {
  icon: string; label: string; value: number | string; suffix?: string; tone?: "purple" | "danger"; small?: boolean;
}) {
  return (
    <div className={"metric" + (tone ? " " + tone : "")}>
      <span className="glow" />
      <div className="top"><span className="lbl">{label}</span><span className="ms sm">{icon}</span></div>
      <div><div className="num" style={small ? { fontSize: 16 } : undefined}>
        {typeof value === "number" ? value.toLocaleString("ru") : value}{suffix && <small>{suffix}</small>}
      </div></div>
    </div>
  );
}
