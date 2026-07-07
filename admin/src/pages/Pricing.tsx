import { useEffect, useMemo, useState } from "react";
import { api } from "../api";
import { Switch } from "../components/Switch";
import { Select } from "../components/Select";
import { DateField } from "../components/DateField";

// ---- helpers ---------------------------------------------------------------
type Cfg = Record<string, unknown>;
const asObj = (v: unknown): Record<string, unknown> =>
  v && typeof v === "object" && !Array.isArray(v) ? (v as Record<string, unknown>) : {};
const num = (v: unknown, d = 0): number => { const n = Number(v); return Number.isFinite(n) ? n : d; };
const clamp = (n: number, lo: number, hi: number) => Math.max(lo, Math.min(hi, n));

interface SectionProps {
  cfg: Cfg;
  save: (patch: Cfg, ok: string) => Promise<void>;
}

const TABS = [
  { id: "prices", label: "Цены" },
  { id: "limits", label: "Лимиты" },
  { id: "sale", label: "Скидка" },
  { id: "bonus", label: "Бонусы" },
  { id: "vip", label: "VIP" },
  { id: "notifications", label: "Уведомления" },
  { id: "ads", label: "Реклама" },
  { id: "chat", label: "Чат" },
  { id: "content", label: "Контент" },
  { id: "sections", label: "Разделы" },
  { id: "service_options", label: "Опции сервисов" },
  { id: "miniapp", label: "Mini App" },
  { id: "maintenance", label: "Обслуживание" },
];

// Friendly labels for the base-price editor.
const PRODUCT_LABEL: Record<string, string> = { premium: "Premium", premium_x2: "Premium ×2" };
const PACK_LABEL: Record<string, string> = {
  image_pack: "Фото-пакет", video_pack: "Видео-пакет", music_pack: "Музыка-пакет",
};

function humanLeft(iso: string): string {
  const ms = new Date(iso).getTime() - Date.now();
  if (ms <= 0) return "срок истёк";
  const h = Math.floor(ms / 3.6e6);
  const d = Math.floor(h / 24);
  if (d > 0) return `≈ ${d} дн ${h % 24} ч`;
  const m = Math.floor(ms / 6e4);
  return h > 0 ? `≈ ${h} ч ${m % 60} мин` : `≈ ${m} мин`;
}

// ---- page ------------------------------------------------------------------
export function Pricing() {
  const [cfg, setCfg] = useState<Cfg | null>(null);
  const [tab, setTab] = useState("prices");
  const [msg, setMsg] = useState("");

  const load = () => api.businessConfig().then((d) => setCfg(d.config)).catch((e) => setMsg(String(e)));
  useEffect(() => { load(); }, []);

  async function save(patch: Cfg, ok: string) {
    try { const r = await api.setBusinessConfig(patch); setCfg(r.config); setMsg(ok); }
    catch (e) { setMsg(String(e)); }
  }

  return (
    <div>
      <h1 className="page-title">Цены и бизнес-настройки</h1>
      <p className="page-sub">Скидки, бонусы, VIP-уровни и реферальная программа. Изменения применяются мгновенно (live).</p>

      {msg && (
        <p className={msg.startsWith("✅") ? "note-ok" : "note-err"}>
          <span className="ms sm">{msg.startsWith("✅") ? "check_circle" : "error"}</span>{msg}
          <button className="btn ghost sm" onClick={() => setMsg("")}>×</button>
        </p>
      )}

      <div className="seg-tabs wrap" style={{ marginBottom: "var(--sp-5)" }}>
        {TABS.map((t) => (
          <button key={t.id} className={tab === t.id ? "on" : ""} onClick={() => setTab(t.id)}>{t.label}</button>
        ))}
      </div>

      {cfg === null ? (
        <div className="panel"><div className="loading">Загрузка…</div></div>
      ) : (
        <div className="page-stack">
          {tab === "prices" && <PricesSection cfg={cfg} save={save} />}
          {tab === "limits" && <LimitsSection cfg={cfg} save={save} />}
          {tab === "sale" && <SaleSection cfg={cfg} save={save} />}
          {tab === "bonus" && <BonusSection cfg={cfg} save={save} />}
          {tab === "vip" && <VipSection cfg={cfg} save={save} />}
          {tab === "notifications" && <NotificationsSection cfg={cfg} save={save} />}
          {tab === "ads" && <AdsSection cfg={cfg} save={save} />}
          {tab === "chat" && <ChatSection cfg={cfg} save={save} />}
          {tab === "content" && <ContentSection cfg={cfg} save={save} />}
          {tab === "sections" && <SectionsSection cfg={cfg} save={save} />}
          {tab === "service_options" && <ServiceOptionsSection cfg={cfg} save={save} />}
          {tab === "miniapp" && <MiniAppSection cfg={cfg} save={save} />}
          {tab === "maintenance" && <MaintenanceSection cfg={cfg} save={save} />}

          <p className="page-sub" style={{ margin: 0 }}>
            <span className="ms sm" style={{ verticalAlign: "-3px" }}>info</span>{" "}
            Фиче-флаги, провайдеры, API-ключи, режим обслуживания и кастомные кнопки — на отдельных страницах
            (Функции, Провайдеры, API-ключи, Обслуживание, Кнопки).
          </p>
        </div>
      )}
    </div>
  );
}

// ---- Save header (unsaved indicator + button) ------------------------------
function SaveHead({ title, icon, dirty, saving, onSave }: {
  title: string; icon: string; dirty: boolean; saving: boolean; onSave: () => void;
}) {
  return (
    <div className="section-head">
      <div className="panel-title" style={{ margin: 0 }}><span className="ms sm">{icon}</span> {title}</div>
      <div className="form-row">
        {dirty && <span className="pill warn">● не сохранено</span>}
        <button className="btn" disabled={!dirty || saving} onClick={onSave}>
          <span className="ms sm">save</span> {saving ? "Сохранение…" : "Сохранить"}
        </button>
      </div>
    </div>
  );
}

// ---- reusable field controls ----------------------------------------------
function NumField({ label, hint, value, onChange, min = 0, max, width }: {
  label: string; hint?: string; value: number; onChange: (v: number) => void;
  min?: number; max?: number; width?: number;
}) {
  return (
    <div className="cfg-field">
      <span className="cfg-cap">{label}</span>
      <input type="number" aria-label={label} min={min} max={max} value={value} style={width ? { width } : undefined}
        onChange={(e) => onChange(clamp(num(e.target.value), min, max ?? Number.MAX_SAFE_INTEGER))} />
      {hint && <p className="cfg-hint">{hint}</p>}
    </div>
  );
}
function ToggleRow({ label, hint, checked, onChange }: {
  label: string; hint?: string; checked: boolean; onChange: (v: boolean) => void;
}) {
  return (
    <div className="form-row" style={{ justifyContent: "space-between", margin: "0 0 var(--sp-3)", alignItems: "center" }}>
      <Switch checked={checked} onChange={onChange} label={label} />
      {hint && <span className="cfg-hint" style={{ margin: 0 }}>{hint}</span>}
    </div>
  );
}
function TextField({ label, hint, value, onChange, placeholder, area }: {
  label: string; hint?: string; value: string; onChange: (v: string) => void; placeholder?: string; area?: boolean;
}) {
  return (
    <div className="cfg-field">
      <span className="cfg-cap">{label}</span>
      {area
        ? <textarea rows={3} aria-label={label} value={value} placeholder={placeholder} style={{ resize: "vertical" }} onChange={(e) => onChange(e.target.value)} />
        : <input type="text" aria-label={label} value={value} placeholder={placeholder} onChange={(e) => onChange(e.target.value)} />}
      {hint && <p className="cfg-hint">{hint}</p>}
    </div>
  );
}

// ---- Base prices (subscriptions / packs / credits / avatar — all in ⭐) -----
// A row of tier inputs (e.g. a product's months, or a pack's quantities). Keys are
// preserved as strings and sorted numerically so the order is stable.
function PriceRow({ label, unit, map, onChange }: {
  label: string; unit: string; map: Record<string, number>; onChange: (k: string, v: number) => void;
}) {
  const keys = Object.keys(map).sort((a, b) => Number(a) - Number(b));
  return (
    <div className="price-row">
      <span className="price-row-label">{label}</span>
      <div className="price-tiers">
        {keys.map((k) => (
          <label key={k} className="price-tier">
            <span className="cfg-cap">{k} {unit}</span>
            <input type="number" min={0} value={map[k]}
              onChange={(e) => onChange(k, Math.max(0, num(e.target.value)))} />
          </label>
        ))}
      </div>
    </div>
  );
}

// Deep-copy a {key: number} map (string keys preserved).
const copyMap = (v: unknown): Record<string, number> => {
  const o = asObj(v); const r: Record<string, number> = {};
  for (const k of Object.keys(o)) r[k] = num(o[k]);
  return r;
};
// Deep-copy a {product: {tier: number}} map.
const copyNested = (v: unknown): Record<string, Record<string, number>> => {
  const o = asObj(v); const r: Record<string, Record<string, number>> = {};
  for (const k of Object.keys(o)) r[k] = copyMap(o[k]);
  return r;
};

const PHOTOTOOL_LABEL: Record<string, string> = {
  face_swap: "Замена лица (face swap)", upscale: "Апскейл (база)", avatars: "Аватар (реестр)",
  upscale_x2: "Апскейл ×2", upscale_x4: "Апскейл ×4",
};

function PricesSection({ cfg, save }: SectionProps) {
  const initSubs = useMemo(() => copyNested(cfg.subscription_prices), [cfg]);
  const initPacks = useMemo(() => copyNested(cfg.pack_prices), [cfg]);
  const initCredits = useMemo(() => copyMap(cfg.credit_packs), [cfg]);
  const initAvatar = num(cfg.avatar_price);
  const initPhoto = useMemo(() => copyMap(cfg.phototools), [cfg]);
  const initDoc = num(asObj(cfg.documents).cost, 3);

  const [subs, setSubs] = useState(initSubs);
  const [packs, setPacks] = useState(initPacks);
  const [credits, setCredits] = useState(initCredits);
  const [avatar, setAvatar] = useState(initAvatar);
  const [photo, setPhoto] = useState(initPhoto);
  const [docCost, setDocCost] = useState(initDoc);
  const [saving, setSaving] = useState(false);

  const snap = (s = subs, p = packs, c = credits, a = avatar, ph = photo, d = docCost) => JSON.stringify({ s, p, c, a, ph, d });
  const dirty = snap() !== snap(initSubs, initPacks, initCredits, initAvatar, initPhoto, initDoc);

  const updSub = (prod: string, k: string, v: number) =>
    setSubs((m) => ({ ...m, [prod]: { ...m[prod], [k]: v } }));
  const updPack = (pack: string, k: string, v: number) =>
    setPacks((m) => ({ ...m, [pack]: { ...m[pack], [k]: v } }));
  const updCredit = (k: string, v: number) => setCredits((m) => ({ ...m, [k]: v }));
  const updPhoto = (k: string, v: number) => setPhoto((m) => ({ ...m, [k]: v }));

  async function onSave() {
    setSaving(true);
    try {
      await save(
        {
          subscription_prices: subs, pack_prices: packs, credit_packs: credits,
          avatar_price: Math.max(0, avatar), phototools: photo, documents: { cost: Math.max(0, docCost) },
        },
        "✅ Цены сохранены (применяются мгновенно)",
      );
    } finally { setSaving(false); }
  }

  return (
    <div className="panel">
      <SaveHead title="Базовые цены (в Telegram Stars ⭐)" icon="sell" dirty={dirty} saving={saving} onSave={onSave} />
      <p className="cfg-hint" style={{ marginTop: 0 }}>
        Все цены в ⭐. Применяются мгновенно к боту и Mini App. Скидка со вкладки «Скидка» накладывается поверх этих цен.
      </p>

      <div className="price-block-title">Подписки · ⭐ за период</div>
      {Object.keys(subs).map((prod) => (
        <PriceRow key={prod} label={PRODUCT_LABEL[prod] ?? prod} unit="мес"
          map={subs[prod]} onChange={(k, v) => updSub(prod, k, v)} />
      ))}

      <div className="price-block-title">Пакеты генераций · ⭐ за количество</div>
      {Object.keys(packs).map((pack) => (
        <PriceRow key={pack} label={PACK_LABEL[pack] ?? pack} unit="шт"
          map={packs[pack]} onChange={(k, v) => updPack(pack, k, v)} />
      ))}

      <div className="price-block-title">Кредитные пакеты ✨ · ⭐ за количество</div>
      <PriceRow label="Кредиты ✨" unit="✨" map={credits} onChange={updCredit} />

      <div className="price-block-title">Аватар (/ava) · ⭐</div>
      <div className="price-row">
        <span className="price-row-label">Создание аватара</span>
        <div className="price-tiers">
          <label className="price-tier">
            <span className="cfg-cap">цена ⭐</span>
            <input type="number" min={0} value={avatar}
              onChange={(e) => setAvatar(Math.max(0, num(e.target.value)))} />
          </label>
        </div>
      </div>

      <div className="price-block-title">Фото-инструменты и документы · в генерациях ✨</div>
      <div className="form-grid">
        {Object.keys(photo).map((k) => (
          <NumField key={k} label={PHOTOTOOL_LABEL[k] ?? k} value={photo[k]} onChange={(v) => updPhoto(k, v)} />
        ))}
        <NumField label="Запрос к документу" hint="Списывается генераций ✨ за один вопрос к документу"
          value={docCost} onChange={setDocCost} />
      </div>
    </div>
  );
}

// ---- Sale ------------------------------------------------------------------
// On-brand date + time picker (replaces native datetime-local). The value stays an
// ISO string; date/time are derived in LOCAL time. `defTime` is used when only a date
// is picked (end of day for "until", start of day for "from").
function DateTimeField({ label, value, onChange, defTime, ariaPrefix, hint }: {
  label: string; value: string | null; onChange: (iso: string | null) => void;
  defTime: string; ariaPrefix: string; hint: string;
}) {
  const pad = (n: number) => String(n).padStart(2, "0");
  const dt = value ? new Date(value) : null;
  const dateVal = dt ? `${dt.getFullYear()}-${pad(dt.getMonth() + 1)}-${pad(dt.getDate())}` : "";
  const [timeVal, setTimeVal] = useState(dt ? `${pad(dt.getHours())}:${pad(dt.getMinutes())}` : defTime);
  const combine = (date: string, time: string): string | null =>
    date ? new Date(`${date}T${time || defTime}:00`).toISOString() : null;
  return (
    <div className="cfg-field">
      <span className="cfg-cap">{label}</span>
      <div className="form-row" style={{ gap: "var(--sp-2)", margin: 0 }}>
        <DateField value={dateVal} onChange={(d) => onChange(combine(d, timeVal))}
          title={label} ariaLabel={`${ariaPrefix} распродажи`} />
        <input type="time" aria-label={`${ariaPrefix} — время`} value={timeVal} style={{ width: 120 }}
          onChange={(e) => { setTimeVal(e.target.value); onChange(combine(dateVal, e.target.value)); }} />
        {dateVal && (
          <button className="btn ghost sm" title="Очистить"
            onClick={() => onChange(null)}><span className="ms sm">close</span></button>
        )}
      </div>
      <p className="cfg-hint">{hint}</p>
    </div>
  );
}

function SaleSection({ cfg, save }: SectionProps) {
  const sale = asObj(cfg.sale);
  const initPercent = num(sale.percent);
  const initFrom = (sale.from as string | null) ?? null;
  const initUntil = (sale.until as string | null) ?? null;
  const [percent, setPercent] = useState(initPercent);
  const [from, setFrom] = useState<string | null>(initFrom);
  const [until, setUntil] = useState<string | null>(initUntil);
  const [saving, setSaving] = useState(false);

  const initial = useMemo(() => JSON.stringify({ p: initPercent, f: initFrom, u: initUntil }), [initPercent, initFrom, initUntil]);
  const dirty = JSON.stringify({ p: percent, f: from, u: until }) !== initial;
  // Live status mirrors the backend _sale_percent gate: on when percent>0 and inside
  // the [from..until] window; "scheduled" when a future start hasn't been reached.
  const now = Date.now();
  const started = !from || new Date(from).getTime() <= now;
  const ended = !!until && new Date(until).getTime() <= now;
  const active = percent > 0 && started && !ended;
  const scheduled = percent > 0 && !started && !ended;

  async function onSave() {
    setSaving(true);
    try { await save({ sale: { percent: clamp(percent, 0, 95), from, until } }, percent > 0 ? `✅ Распродажа −${percent}% сохранена` : "✅ Распродажа выключена"); }
    finally { setSaving(false); }
  }

  return (
    <div className="panel">
      <SaveHead title="Распродажа (скидка на все цены)" icon="sell" dirty={dirty} saving={saving} onSave={onSave} />
      <div className="form-grid">
        <div className="cfg-field">
          <span className="cfg-cap">Скидка, %</span>
          <input type="number" aria-label="Скидка, %" min={0} max={95} value={percent}
            onChange={(e) => setPercent(clamp(num(e.target.value), 0, 95))} />
          <p className="cfg-hint">0% = выключена. Применяется ко всем подпискам, пакетам, ✨ и аватарам.</p>
        </div>
        <DateTimeField label="Начало (необязательно)" value={from} onChange={setFrom}
          defTime="00:00" ariaPrefix="Дата начала"
          hint="Пусто = сразу. Можно запланировать заранее — скидка включится сама в это время." />
        <DateTimeField label="Действует до (необязательно)" value={until} onChange={setUntil}
          defTime="23:59" ariaPrefix="Дата окончания"
          hint="Пусто = бессрочно, пока скидка > 0. После срока скидка перестаёт применяться." />
      </div>
      <div className="info-row" style={{ marginTop: "var(--sp-4)", alignItems: "center" }}>
        <span className={"pill " + (active ? "ok" : scheduled ? "warn" : "muted")}>
          {active ? "активна" : scheduled ? "запланирована" : "выключена"}
        </span>
        {active && until && <span className="pill warn">{humanLeft(until)}</span>}
        {scheduled && from && <span className="pill">старт {humanLeft(from)}</span>}
        {percent > 0 && (
          <span className="muted" style={{ fontSize: 13 }}>
            Предпросмотр: <b style={{ color: "var(--text)" }}>1000 ⭐</b> → <b style={{ color: "var(--accent)" }}>{Math.round(1000 * (1 - percent / 100))} ⭐</b>
          </span>
        )}
      </div>
    </div>
  );
}

// ---- Bonuses ---------------------------------------------------------------
const PROMO_FIELDS = [
  { key: "welcome_bonus", label: "Приветственный бонус", hint: "✨ новому пользователю при первом /start" },
  { key: "first_purchase_bonus", label: "Бонус за первую покупку", hint: "✨ при первой оплате (любой продукт)" },
  { key: "cashback_percent", label: "Кэшбэк, %", hint: "% от пополнения ✨ возвращается бонусными ✨" },
];

function BonusSection({ cfg, save }: SectionProps) {
  const promos = asObj(cfg.promos);
  const init = useMemo(() => PROMO_FIELDS.reduce<Record<string, number>>((a, f) => (a[f.key] = num(promos[f.key]), a), {}), [cfg]);
  const [draft, setDraft] = useState<Record<string, number>>(init);
  const [saving, setSaving] = useState(false);
  const dirty = JSON.stringify(draft) !== JSON.stringify(init);

  async function onSave() {
    setSaving(true);
    try { await save({ promos: draft }, "✅ Промо-механики сохранены"); }
    finally { setSaving(false); }
  }

  return (
    <div className="panel">
      <SaveHead title="Промо-механики (бонусы ✨)" icon="redeem" dirty={dirty} saving={saving} onSave={onSave} />
      <div className="form-grid">
        {PROMO_FIELDS.map((f) => (
          <div className="cfg-field" key={f.key}>
            <span className="cfg-cap">{f.label}{(draft[f.key] ?? 0) > 0 && <span className="pill ok" style={{ marginLeft: 8 }}>вкл</span>}</span>
            <input type="number" aria-label={f.label} min={0} value={draft[f.key] ?? 0}
              onChange={(e) => setDraft({ ...draft, [f.key]: Math.max(0, num(e.target.value)) })} />
            <p className="cfg-hint">{f.hint}{(draft[f.key] ?? 0) === 0 ? " · 0 = выключено" : ""}</p>
          </div>
        ))}
      </div>
    </div>
  );
}

// ---- VIP (dynamic tier editor, no JSON) ------------------------------------
type Tier = { name: string; min_spent: number; bonus_daily: number; bonus_weekly: number };
const tierOf = (v: unknown): Tier => {
  const o = asObj(v);
  return { name: String(o.name ?? ""), min_spent: num(o.min_spent), bonus_daily: num(o.bonus_daily), bonus_weekly: num(o.bonus_weekly) };
};

function VipSection({ cfg, save }: SectionProps) {
  const vip = asObj(cfg.vip);
  const initEnabled = Boolean(vip.enabled);
  const initTiers = useMemo(() => (Array.isArray(vip.tiers) ? (vip.tiers as unknown[]).map(tierOf) : []), [cfg]);
  const [enabled, setEnabled] = useState(initEnabled);
  const [tiers, setTiers] = useState<Tier[]>(initTiers);
  const [saving, setSaving] = useState(false);
  const dirty = enabled !== initEnabled || JSON.stringify(tiers) !== JSON.stringify(initTiers);

  function upd(i: number, field: keyof Tier, value: string) {
    setTiers((ts) => ts.map((t, j) => j === i ? { ...t, [field]: field === "name" ? value : Math.max(0, num(value)) } : t));
  }
  const addTier = () => setTiers((ts) => [...ts, { name: "", min_spent: 0, bonus_daily: 0, bonus_weekly: 0 }]);
  const removeTier = (i: number) => setTiers((ts) => ts.filter((_, j) => j !== i));

  async function onSave() {
    const cleaned = tiers.filter((t) => t.name.trim()).sort((a, b) => a.min_spent - b.min_spent);
    setSaving(true);
    try { await save({ vip: { enabled, tiers: cleaned } }, enabled ? "✅ VIP-уровни включены и сохранены" : "✅ VIP-уровни выключены"); setTiers(cleaned); }
    finally { setSaving(false); }
  }

  return (
    <div className="panel">
      <SaveHead title="VIP-уровни (лояльность)" icon="workspace_premium" dirty={dirty} saving={saving} onSave={onSave} />
      <div className="form-row" style={{ marginBottom: "var(--sp-4)", justifyContent: "space-between" }}>
        <Switch checked={enabled} onChange={setEnabled} label="Включить VIP-программу" />
        <span className="muted" style={{ fontSize: 12 }}>Уровень присваивается автоматически по сумме покупок (в эквиваленте ⭐).</span>
      </div>

      <div className="table-wrap" tabIndex={0} style={{ border: "none", opacity: enabled ? 1 : .7 }}>
        <table className="tbl">
          <thead>
            <tr><th>Уровень</th><th>Мин. сумма ⭐</th><th>Бонус/день</th><th>Бонус/неделя</th><th></th></tr>
          </thead>
          <tbody>
            {tiers.length === 0 ? (
              <tr><td colSpan={5}><div className="empty">Уровней нет. Добавьте первый — например Bronze (0 ⭐).</div></td></tr>
            ) : tiers.map((t, i) => (
              <tr key={i}>
                <td><input aria-label="Название уровня" value={t.name} placeholder="Bronze" onChange={(e) => upd(i, "name", e.target.value)} /></td>
                <td><input type="number" aria-label="Мин. траты ⭐" min={0} style={{ width: 120 }} value={t.min_spent} onChange={(e) => upd(i, "min_spent", e.target.value)} /></td>
                <td><input type="number" aria-label="Бонус в день" min={0} style={{ width: 100 }} value={t.bonus_daily} onChange={(e) => upd(i, "bonus_daily", e.target.value)} /></td>
                <td><input type="number" aria-label="Бонус в неделю" min={0} style={{ width: 100 }} value={t.bonus_weekly} onChange={(e) => upd(i, "bonus_weekly", e.target.value)} /></td>
                <td style={{ width: 1 }}>
                  <button className="btn ghost sm" title="Удалить уровень" onClick={() => removeTier(i)}>
                    <span className="ms sm">delete</span>
                  </button>
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
      <div className="toolbar" style={{ marginTop: "var(--sp-3)", marginBottom: 0 }}>
        <button className="btn ghost" onClick={addTier}><span className="ms sm">add</span> Добавить уровень</button>
        <span className="cfg-hint">Бонус/день и бонус/неделя — дополнительные генерации для пользователей этого уровня.</span>
      </div>
    </div>
  );
}

// ---- Limits / retention / generation ---------------------------------------
function LimitsSection({ cfg, save }: SectionProps) {
  const initL = useMemo(() => copyMap(cfg.limits), [cfg]);
  const initR = useMemo(() => copyMap(cfg.retention), [cfg]);
  const initVar = num(asObj(cfg.generation).image_variants, 1);
  const [lim, setLim] = useState(initL);
  const [ret, setRet] = useState(initR);
  const [variants, setVariants] = useState(initVar);
  const [saving, setSaving] = useState(false);
  const dirty = JSON.stringify([lim, ret, variants]) !== JSON.stringify([initL, initR, initVar]);
  const updL = (k: string, v: number) => setLim((m) => ({ ...m, [k]: v }));
  const updR = (k: string, v: number) => setRet((m) => ({ ...m, [k]: v }));

  async function onSave() {
    setSaving(true);
    try {
      await save({ limits: lim, retention: ret, generation: { image_variants: clamp(variants, 1, 4) } }, "✅ Лимиты сохранены");
    } finally { setSaving(false); }
  }
  return (
    <div className="panel">
      <SaveHead title="Лимиты, хранение, генерация" icon="speed" dirty={dirty} saving={saving} onSave={onSave} />
      <div className="price-block-title">Лимиты генераций</div>
      <div className="form-grid">
        <NumField label="Бесплатно текст / неделя" value={lim.free_text_weekly ?? 0} onChange={(v) => updL("free_text_weekly", v)} hint="Текстовых генераций бесплатному юзеру в неделю" />
        <NumField label="Бесплатно Mini App / неделя" value={lim.free_miniapp_weekly ?? 0} onChange={(v) => updL("free_miniapp_weekly", v)} hint="Бесплатные эффекты Mini App в неделю" />
        <NumField label="Premium / день" value={lim.premium_daily ?? 0} onChange={(v) => updL("premium_daily", v)} />
        <NumField label="Premium ×2 / день" value={lim.premium_x2_daily ?? 0} onChange={(v) => updL("premium_x2_daily", v)} />
      </div>
      <div className="price-block-title">Хранение результатов · дней (0 = вечно)</div>
      <div className="form-grid">
        <NumField label="Генерации (job)" value={ret.job_days ?? 0} onChange={(v) => updR("job_days", v)} />
        <NumField label="Галерея" value={ret.gallery_days ?? 0} onChange={(v) => updR("gallery_days", v)} />
      </div>
      <div className="price-block-title">Генерация</div>
      <div className="form-grid">
        <NumField label="Вариантов изображения" min={1} max={4} value={variants} onChange={setVariants} hint="Сколько вариантов картинки предлагать (1–4)" />
      </div>
    </div>
  );
}

// ---- Notifications ---------------------------------------------------------
function NotificationsSection({ cfg, save }: SectionProps) {
  const n = asObj(cfg.notifications);
  const init = useMemo(() => ({
    premium_expiry_enabled: Boolean(n.premium_expiry_enabled),
    premium_expiry_days_before: num(n.premium_expiry_days_before, 3),
    low_balance_enabled: Boolean(n.low_balance_enabled),
    low_balance_threshold: num(n.low_balance_threshold, 5),
    winback_enabled: Boolean(n.winback_enabled),
    winback_inactive_days: num(n.winback_inactive_days, 14),
    bonus_available_enabled: Boolean(n.bonus_available_enabled),
    abandoned_cart_enabled: Boolean(n.abandoned_cart_enabled),
    abandoned_cart_after_hours: num(n.abandoned_cart_after_hours, 1),
  }), [cfg]);
  const [d, setD] = useState(init);
  const [saving, setSaving] = useState(false);
  const dirty = JSON.stringify(d) !== JSON.stringify(init);
  const set = (k: keyof typeof init, v: number | boolean) => setD((s) => ({ ...s, [k]: v }));

  async function onSave() {
    setSaving(true);
    try { await save({ notifications: d }, "✅ Уведомления сохранены"); }
    finally { setSaving(false); }
  }
  return (
    <div className="panel">
      <SaveHead title="Авто-уведомления и вовлечение" icon="notifications" dirty={dirty} saving={saving} onSave={onSave} />
      <ToggleRow label="Premium истекает" checked={d.premium_expiry_enabled} onChange={(v) => set("premium_expiry_enabled", v)} hint="Предупреждать перед концом подписки" />
      <div className="form-grid"><NumField label="За сколько дней предупреждать" value={d.premium_expiry_days_before} onChange={(v) => set("premium_expiry_days_before", v)} /></div>
      <ToggleRow label="Низкий баланс ✨" checked={d.low_balance_enabled} onChange={(v) => set("low_balance_enabled", v)} hint="Напоминать, когда кредиты кончаются" />
      <div className="form-grid"><NumField label="Порог баланса ✨" value={d.low_balance_threshold} onChange={(v) => set("low_balance_threshold", v)} /></div>
      <ToggleRow label="Win-back неактивных" checked={d.winback_enabled} onChange={(v) => set("winback_enabled", v)} hint="Возвращать давно не заходивших" />
      <div className="form-grid"><NumField label="Неактивен дней" value={d.winback_inactive_days} onChange={(v) => set("winback_inactive_days", v)} /></div>
      <ToggleRow label="Напоминание о ежедневном бонусе" checked={d.bonus_available_enabled} onChange={(v) => set("bonus_available_enabled", v)} hint="Чтобы не прерывали streak" />
      <ToggleRow label="Брошенная корзина" checked={d.abandoned_cart_enabled} onChange={(v) => set("abandoned_cart_enabled", v)} hint="Напомнить, кто начал оплату, но не завершил" />
      <div className="form-grid"><NumField label="Через сколько часов напомнить" min={1} value={d.abandoned_cart_after_hours} onChange={(v) => set("abandoned_cart_after_hours", v)} /></div>
    </div>
  );
}

// ---- Ads -------------------------------------------------------------------
function AdsSection({ cfg, save }: SectionProps) {
  const a = asObj(cfg.ads);
  const initEnabled = Boolean(a.enabled);
  const initEvery = num(a.every_n, 5);
  const initText = String(a.text ?? "");
  const [enabled, setEnabled] = useState(initEnabled);
  const [every, setEvery] = useState(initEvery);
  const [text, setText] = useState(initText);
  const [saving, setSaving] = useState(false);
  const dirty = enabled !== initEnabled || every !== initEvery || text !== initText;

  async function onSave() {
    setSaving(true);
    try { await save({ ads: { enabled, every_n: Math.max(1, every), text } }, enabled ? "✅ Реклама включена" : "✅ Реклама выключена"); }
    finally { setSaving(false); }
  }
  return (
    <div className="panel">
      <SaveHead title="Реклама для бесплатных пользователей" icon="campaign" dirty={dirty} saving={saving} onSave={onSave} />
      <ToggleRow label="Включить рекламу" checked={enabled} onChange={setEnabled} hint="Premium-пользователи рекламу не видят" />
      <div className="form-grid">
        <NumField label="После каждого N-го ответа" min={1} value={every} onChange={setEvery} hint="Реклама добавляется после каждого N-го ответа free-юзеру" />
      </div>
      <TextField label="Текст рекламы" area value={text} onChange={setText} placeholder="✨ Оформите Premium…" />
    </div>
  );
}

// ---- Chat / queue / search -------------------------------------------------
function ChatSection({ cfg, save }: SectionProps) {
  const c = asObj(cfg.chat); const q = asObj(cfg.queue); const se = asObj(cfg.search);
  const init = useMemo(() => ({
    memory_pairs: num(c.memory_pairs, 5),
    markdown_enabled: Boolean(c.markdown_enabled),
    groups_enabled: Boolean(c.groups_enabled),
    streaming_enabled: Boolean(c.streaming_enabled),
    premium_priority_enabled: Boolean(q.premium_priority_enabled),
    system_prompt: String(se.system_prompt ?? ""),
  }), [cfg]);
  const [d, setD] = useState(init);
  const [saving, setSaving] = useState(false);
  const dirty = JSON.stringify(d) !== JSON.stringify(init);
  const set = (k: keyof typeof init, v: number | boolean | string) => setD((s) => ({ ...s, [k]: v }));

  async function onSave() {
    setSaving(true);
    try {
      await save({
        chat: { memory_pairs: clamp(d.memory_pairs, 1, 20), markdown_enabled: d.markdown_enabled, groups_enabled: d.groups_enabled, streaming_enabled: d.streaming_enabled },
        queue: { premium_priority_enabled: d.premium_priority_enabled },
        search: { system_prompt: d.system_prompt },
      }, "✅ Настройки чата сохранены");
    } finally { setSaving(false); }
  }
  return (
    <div className="panel">
      <SaveHead title="Чат, очередь, поиск" icon="forum" dirty={dirty} saving={saving} onSave={onSave} />
      <div className="form-grid"><NumField label="Память (пар вопрос-ответ)" min={1} max={20} value={d.memory_pairs} onChange={(v) => set("memory_pairs", v)} hint="Сколько прошлых пар держать в контексте (5–10)" /></div>
      <ToggleRow label="Markdown в ответах" checked={d.markdown_enabled} onChange={(v) => set("markdown_enabled", v)} />
      <ToggleRow label="Отвечать в группах" checked={d.groups_enabled} onChange={(v) => set("groups_enabled", v)} hint="При упоминании или ответе на сообщение бота" />
      <ToggleRow label="Стриминг ответов" checked={d.streaming_enabled} onChange={(v) => set("streaming_enabled", v)} hint="Ответ появляется постепенно" />
      <ToggleRow label="Приоритет Premium в очереди" checked={d.premium_priority_enabled} onChange={(v) => set("premium_priority_enabled", v)} hint="Задачи Premium-юзеров идут вперёд" />
      <TextField label="Системный промпт интернет-поиска" area value={d.system_prompt} onChange={(v) => set("system_prompt", v)} hint="Инструкция модели для /s /search. Пусто = дефолт" />
    </div>
  );
}

// ---- Content: preset roles + start branding --------------------------------
type Role = { key: string; title: string; desc: string; prompt: string };
const roleOf = (v: unknown): Role => {
  const o = asObj(v);
  return {
    key: String(o.key ?? ""), title: String(o.title ?? ""),
    desc: String(o.desc ?? ""), prompt: String(o.prompt ?? ""),
  };
};
// "Инструкция"-link slots shown under photo/video service configs (empty = no button).
const DOC_SLOTS: { key: string; label: string }[] = [
  { key: "banana", label: "Nano Banana" },
  { key: "gpt_images", label: "GPT Image 2" },
  { key: "midjourney", label: "Midjourney" },
  { key: "veo", label: "Veo" },
];
function ContentSection({ cfg, save }: SectionProps) {
  const initRoles = useMemo(() => (Array.isArray(cfg.preset_roles) ? (cfg.preset_roles as unknown[]).map(roleOf) : []), [cfg]);
  const b = asObj(cfg.branding);
  const initUrl = String(b.start_media_url ?? "");
  const initType = String(b.start_media_type ?? "photo");
  const initDocs = useMemo(() => {
    const o = asObj(cfg.doc_links);
    return Object.fromEntries(DOC_SLOTS.map((s) => [s.key, String(o[s.key] ?? "")]));
  }, [cfg]);
  const [roles, setRoles] = useState<Role[]>(initRoles);
  const [url, setUrl] = useState(initUrl);
  const [mtype, setMtype] = useState(initType);
  const [docs, setDocs] = useState<Record<string, string>>(initDocs);
  const [saving, setSaving] = useState(false);
  const dirty = JSON.stringify(roles) !== JSON.stringify(initRoles) || url !== initUrl || mtype !== initType
    || JSON.stringify(docs) !== JSON.stringify(initDocs);

  const upd = (i: number, f: keyof Role, val: string) => setRoles((rs) => rs.map((r, j) => j === i ? { ...r, [f]: val } : r));
  const add = () => setRoles((rs) => [...rs, { key: "", title: "", desc: "", prompt: "" }]);
  const rm = (i: number) => setRoles((rs) => rs.filter((_, j) => j !== i));

  async function onSave() {
    const cleaned = roles.filter((r) => r.key.trim() && r.title.trim());
    const cleanedDocs = Object.fromEntries(
      Object.entries(docs).map(([k, v]) => [k, v.trim()]).filter(([, v]) => v)
    );
    setSaving(true);
    try { await save({ preset_roles: cleaned, branding: { start_media_url: url.trim(), start_media_type: mtype }, doc_links: cleanedDocs }, "✅ Контент сохранён"); setRoles(cleaned); }
    finally { setSaving(false); }
  }
  return (
    <div className="panel">
      <SaveHead title="Персоны и брендинг /start" icon="diversity_3" dirty={dirty} saving={saving} onSave={onSave} />
      <div className="price-block-title">Медиа в /start</div>
      <div className="form-grid">
        <TextField label="URL фото/видео (пусто = только текст)" value={url} onChange={setUrl} placeholder="https://…" />
        <div className="cfg-field">
          <span className="cfg-cap">Тип медиа</span>
          <Select ariaLabel="Тип медиа" value={mtype} onChange={setMtype}
            options={[{ value: "photo", label: "Фото" }, { value: "video", label: "Видео" }]} />
        </div>
      </div>
      <div className="price-block-title">Пресет-роли (/roles)</div>
      {roles.length === 0 ? <div className="empty">Ролей нет. Добавьте первую.</div> : roles.map((r, i) => (
        <div key={i} className="panel" style={{ margin: "0 0 var(--sp-3)", background: "var(--panel-2)" }}>
          <div className="form-row" style={{ margin: "0 0 var(--sp-2)", gap: "var(--sp-2)" }}>
            <input style={{ width: 140 }} placeholder="ключ (tutor)" value={r.key} onChange={(e) => upd(i, "key", e.target.value)} />
            <input className="grow" placeholder="Название (👩‍🏫 Репетитор)" value={r.title} onChange={(e) => upd(i, "title", e.target.value)} />
            <button className="btn ghost sm" title="Удалить роль" onClick={() => rm(i)}><span className="ms sm">delete</span></button>
          </div>
          <input style={{ width: "100%", marginBottom: "var(--sp-2)" }} placeholder="Краткое описание (1 строка, показывается в /roles)"
            value={r.desc} onChange={(e) => upd(i, "desc", e.target.value)} />
          <textarea rows={2} style={{ width: "100%", resize: "vertical" }} placeholder="Системный промпт роли"
            value={r.prompt} onChange={(e) => upd(i, "prompt", e.target.value)} />
        </div>
      ))}
      <button className="btn ghost" onClick={add}><span className="ms sm">add</span> Добавить роль</button>
      <div className="price-block-title">Инструкции (кнопка «Инструкция» в конфиге сервиса)</div>
      <p className="page-sub" style={{ marginTop: 0 }}>Пусто = кнопка не показывается. Только https/http-ссылки.</p>
      <div className="form-grid">
        {DOC_SLOTS.map((s) => (
          <TextField key={s.key} label={s.label} value={docs[s.key] ?? ""}
            onChange={(v) => setDocs((d) => ({ ...d, [s.key]: v }))} placeholder="https://…" />
        ))}
      </div>
    </div>
  );
}

// ---- Maintenance mode: live on/off + message (read by the bot middleware) ----
// Bot menu sections the admin can turn on/off, each with its own editable "coming
// soon" text. Keys match core.services.pricing defaults()["sections"].
const SECTION_DEFS: { key: string; label: string; placeholder: string }[] = [
  { key: "images", label: "Изображения", placeholder: "🎨 Раздел изображений скоро…" },
  { key: "video", label: "Видео", placeholder: "🎬 Генерация видео скоро…" },
  { key: "music", label: "Музыка", placeholder: "🎵 Генерация музыки скоро…" },
  { key: "documents", label: "Документы", placeholder: "📄 Работа с документами скоро…" },
  { key: "search", label: "Поиск", placeholder: "🔍 Поиск в интернете скоро…" },
];

type SecState = { enabled: boolean; soon: string };

function SectionsSection({ cfg, save }: SectionProps) {
  const src = asObj(cfg.sections);
  const init = useMemo(() => {
    const o: Record<string, SecState> = {};
    for (const s of SECTION_DEFS) {
      const v = asObj(src[s.key]);
      o[s.key] = { enabled: Boolean(v.enabled), soon: String(v.soon ?? "") };
    }
    return o;
  }, [cfg]);
  const [d, setD] = useState(init);
  const [saving, setSaving] = useState(false);
  const dirty = JSON.stringify(d) !== JSON.stringify(init);
  const set = (k: string, patch: Partial<SecState>) =>
    setD((s) => ({ ...s, [k]: { ...s[k], ...patch } }));

  async function onSave() {
    setSaving(true);
    try {
      const sections: Record<string, SecState> = {};
      for (const s of SECTION_DEFS) sections[s.key] = { enabled: d[s.key].enabled, soon: d[s.key].soon.trim() };
      await save({ sections }, "✅ Разделы сохранены");
    } finally { setSaving(false); }
  }

  return (
    <div className="panel">
      <SaveHead title="Разделы бота" icon="apps" dirty={dirty} saving={saving} onSave={onSave} />
      <p className="page-sub" style={{ marginTop: 0 }}>
        Включи раздел — он работает. Выключи — пользователь видит твой текст «Скоро» вместо раздела.
        Чат и выбор модели работают всегда. Применяется мгновенно.
      </p>
      {SECTION_DEFS.map((s) => (
        <div key={s.key} style={{ borderTop: "1px solid var(--border)", paddingTop: "var(--sp-3)", marginTop: "var(--sp-3)" }}>
          <ToggleRow
            label={s.label}
            checked={d[s.key].enabled}
            onChange={(v) => set(s.key, { enabled: v })}
            hint={d[s.key].enabled ? "Раздел работает" : "Выключено — показывается текст «Скоро»"}
          />
          {!d[s.key].enabled && (
            <TextField
              label={`Текст «Скоро» для «${s.label}»`}
              area
              value={d[s.key].soon}
              onChange={(v) => set(s.key, { soon: v })}
              hint="Пусто = текст по умолчанию"
              placeholder={s.placeholder}
            />
          )}
        </div>
      ))}
    </div>
  );
}

// ---- Per-service generation option buttons (admin-editable; ТЗ §5/§8) --------
// Mirrors the code spec defaults (image_specs.py / video_specs.py) as placeholders.
// Empty input = use the code default. Only the BUTTONS change; costs/flow stay in code.
type OptKind = "str" | "int" | "models";
const OPT_FIELD: Record<string, { label: string; kind: OptKind }> = {
  models: { label: "Модели (ключ:Название, через запятую)", kind: "models" },
  qualities: { label: "Качество", kind: "str" },
  ratios: { label: "Соотношения", kind: "str" },
  counts: { label: "Кол-во картинок", kind: "int" },
  durations: { label: "Длительность, сек", kind: "int" },
  resolutions: { label: "Разрешения", kind: "str" },
};
// Structural toggle buttons per service the admin can show/hide (hiding only removes
// an option → always cost-safe). Keys match core.services.pricing _HIDEABLE_TOGGLES.
const TOGGLE_LABEL: Record<string, string> = {
  audio: "🔊 Аудио", fourk: "4K", seed: "Seed", enhance: "Улучшение промпта",
  modes: "Режимы (Создать/Редактор)",
};
const SVC_DEFS: { key: string; label: string; fields: Record<string, string>; toggles?: string[] }[] = [
  { key: "gpt_image2", label: "📷 GPT Image 2", fields: { ratios: "1:1, 9:16, 16:9, 3:4, 4:3", counts: "1, 2, 3, 4" } },
  { key: "nano_banana", label: "📷 Nano Banana", fields: { models: "nb2:Nano Banana 2, nbpro:Nano Banana Pro", qualities: "1k, 2k, 4k", counts: "1, 2, 3, 4, 5, 6, 7, 8, 9, 10" } },
  { key: "seedream", label: "📷 Seedream 5", fields: { models: "seedream_4_5:Seedream 4.5, seedream_5:Seedream 5", qualities: "2k, 3k, 4k", ratios: "1:1, 9:16, 16:9, 3:4, 4:3" } },
  { key: "midjourney", label: "📷 Midjourney", fields: { models: "v7:V7, v8_1:V8.1" } },
  { key: "flux2", label: "📷 FLUX 2", fields: { models: "flux2:FLUX 2, flux2_flex:FLUX 2 Flex, flux2_pro:FLUX 2 Pro, flux2_max:FLUX 2 Max", ratios: "1:1, 9:16, 16:9, 3:4, 4:3" }, toggles: ["seed"] },
  { key: "recraft", label: "📷 Recraft", fields: { ratios: "1:1, 9:16, 16:9, 3:4, 4:3" } },
  { key: "seedance", label: "🎬 Seedance 2.0", fields: { models: "fast:Fast, standard:Standard", durations: "4, 8, 12, 15", resolutions: "480p, 720p", ratios: "16:9, 9:16, 1:1, 4:3, 3:4, 21:9" }, toggles: ["audio"] },
  { key: "veo", label: "🎬 Veo 3.1", fields: { models: "veo_3_1:VEO 3.1, veo_3_1_fast:VEO 3.1 FAST", ratios: "16:9, 9:16" }, toggles: ["fourk", "seed"] },
  { key: "grok", label: "🎬 Grok Imagine", fields: { ratios: "auto, 1:1, 9:16, 16:9, 4:3, 3:4", durations: "6, 9, 12, 15" }, toggles: ["modes"] },
  { key: "kling_ai", label: "🎬 Kling AI", fields: { models: "3.0:3.0, o1:O1, 2.6:2.6, 2.5t:2.5 Turbo", durations: "5, 10, 15", ratios: "1:1, 16:9, 9:16" }, toggles: ["audio", "fourk"] },
  { key: "hailuo", label: "🎬 Minimax Hailuo", fields: { models: "fast:Hailuo 2.3 Fast, 2.3:Hailuo 2.3, 02:Hailuo 02", durations: "5, 10", resolutions: "768P, 1080P" }, toggles: ["enhance"] },
  { key: "pika", label: "🎬 Pika 2.5", fields: { durations: "5, 10", resolutions: "720p, 1080p", ratios: "1:1, 16:9, 9:16" } },
];

function parseOpt(kind: OptKind, raw: string): unknown[] {
  const parts = raw.split(",").map((s) => s.trim()).filter(Boolean);
  if (kind === "int") return parts.map((s) => Number(s)).filter((n) => Number.isFinite(n));
  if (kind === "models") return parts.map((s) => { const i = s.indexOf(":"); return i < 0 ? [s, s] : [s.slice(0, i).trim(), s.slice(i + 1).trim() || s.slice(0, i).trim()]; });
  return parts;
}
function joinOpt(kind: OptKind, val: unknown): string {
  if (!Array.isArray(val)) return "";
  if (kind === "models") return (val as unknown[]).map((p) => Array.isArray(p) ? `${p[0]}:${p[1]}` : String(p)).join(", ");
  return (val as unknown[]).map(String).join(", ");
}

function ServiceEditor({ def, saved, all, save }: { def: typeof SVC_DEFS[number]; saved: Record<string, unknown>; all: Record<string, unknown>; save: SectionProps["save"] }) {
  const init = Object.fromEntries(Object.keys(def.fields).map((f) => [f, joinOpt(OPT_FIELD[f].kind, saved[f])]));
  const hidden = new Set(Array.isArray(saved.hide) ? (saved.hide as unknown[]).map(String) : []);
  // shown[toggle] = whether the toggle button is visible to users (inverse of "hide").
  const initShown = Object.fromEntries((def.toggles ?? []).map((t) => [t, !hidden.has(t)]));
  const [text, setText] = useState<Record<string, string>>(init);
  const [shown, setShown] = useState<Record<string, boolean>>(initShown);
  const [saving, setSaving] = useState(false);
  const dirty = JSON.stringify(text) !== JSON.stringify(init) || JSON.stringify(shown) !== JSON.stringify(initShown);
  async function onSave() {
    const ov: Record<string, unknown> = {};
    for (const f of Object.keys(def.fields)) {
      const parsed = parseOpt(OPT_FIELD[f].kind, text[f] ?? "");
      if (parsed.length) ov[f] = parsed;
    }
    const hide = (def.toggles ?? []).filter((t) => !shown[t]);
    if (hide.length) ov.hide = hide;
    const merged: Record<string, unknown> = { ...all };
    if (Object.keys(ov).length) merged[def.key] = ov; else delete merged[def.key];
    setSaving(true);
    try { await save({ service_options: merged }, "✅ Опции сервиса сохранены"); } finally { setSaving(false); }
  }
  return (
    <div style={{ marginTop: "var(--sp-3)" }}>
      <SaveHead title={`Опции: ${def.label}`} icon="tune" dirty={dirty} saving={saving} onSave={onSave} />
      <div className="form-grid">
        {Object.entries(def.fields).map(([f, placeholder]) => (
          <TextField key={f} label={OPT_FIELD[f].label} value={text[f] ?? ""}
            onChange={(v) => setText((t) => ({ ...t, [f]: v }))} placeholder={placeholder} />
        ))}
      </div>
      {(def.toggles ?? []).length > 0 && (
        <>
          <div className="price-block-title">Тумблеры (показывать кнопку)</div>
          {(def.toggles ?? []).map((t) => (
            <ToggleRow key={t} label={TOGGLE_LABEL[t] ?? t} checked={shown[t] ?? true}
              onChange={(v) => setShown((s) => ({ ...s, [t]: v }))}
              hint="Выкл = кнопка скрыта у пользователя" />
          ))}
        </>
      )}
    </div>
  );
}

function ServiceOptionsSection({ cfg, save }: SectionProps) {
  const all = asObj(cfg.service_options);
  const [svc, setSvc] = useState(SVC_DEFS[0].key);
  const def = SVC_DEFS.find((d) => d.key === svc) ?? SVC_DEFS[0];
  return (
    <div className="panel">
      <SaveHead title="Опции сервисов (кнопки генерации)" icon="apps" dirty={false} saving={false} onSave={() => {}} />
      <p className="page-sub" style={{ marginTop: 0 }}>
        Какие кнопки (разрешения / качество / длительность / соотношения / модели) видит юзер при настройке.
        Пусто = набор по умолчанию (показан как подсказка). Меняет только кнопки — цены и логика остаются.
        <br />⚠️ Качество / длительность / разрешение / модели — можно только <b>убирать, менять порядок или переименовать</b>
        из набора по умолчанию (новые значения, которых нет в коде, игнорируются — для них не задана цена).
        Соотношения и кол-во — любые.
      </p>
      <div className="cfg-field" style={{ maxWidth: 320 }}>
        <span className="cfg-cap">Сервис</span>
        <Select ariaLabel="Сервис" value={svc} onChange={setSvc}
          options={SVC_DEFS.map((d) => ({ value: d.key, label: d.label }))} />
      </div>
      <ServiceEditor key={svc} def={def} saved={asObj(all[svc])} all={all} save={save} />
    </div>
  );
}

function MiniAppSection({ cfg, save }: SectionProps) {
  const ms = asObj(cfg.miniapp_sections);
  const init = useMemo(() => ({
    photo: String(ms.photo ?? "auto"),
    video: String(ms.video ?? "auto"),
    sponsored: Number((cfg as Record<string, unknown>).sponsored_free_daily ?? 3),
  }), [cfg]);   // eslint-disable-line react-hooks/exhaustive-deps
  const [d, setD] = useState(init);
  const [saving, setSaving] = useState(false);
  const dirty = JSON.stringify(d) !== JSON.stringify(init);
  const set = (k: keyof typeof init, v: string | number) => setD((s) => ({ ...s, [k]: v }));
  const MODE = [
    { value: "auto", label: "Авто (если есть провайдер)" },
    { value: "on", label: "Всегда показывать" },
    { value: "off", label: "Скрыть" },
  ];

  async function onSave() {
    setSaving(true);
    try {
      await save({
        miniapp_sections: { photo: d.photo, video: d.video },
        sponsored_free_daily: Math.max(0, Math.round(d.sponsored)),
      }, "✅ Настройки Mini App сохранены");
    } finally { setSaving(false); }
  }
  return (
    <div className="panel">
      <SaveHead title="Mini App" icon="smartphone" dirty={dirty} saving={saving} onSave={onSave} />
      <p className="page-sub" style={{ marginTop: 0 }}>
        Видимость сегментов эффектов (фото/видео) и бесплатные спонсорские генерации.
        «Авто» показывает сегмент только при наличии рабочего провайдера для модальности.
      </p>
      <div className="form-grid">
        <div className="cfg-field">
          <span className="cfg-cap">Сегмент «Фото»</span>
          <Select width="100%" ariaLabel="Сегмент фото" value={d.photo}
            onChange={(v) => set("photo", v)} options={MODE} />
        </div>
        <div className="cfg-field">
          <span className="cfg-cap">Сегмент «Видео»</span>
          <Select width="100%" ariaLabel="Сегмент видео" value={d.video}
            onChange={(v) => set("video", v)} options={MODE} />
        </div>
      </div>
      <NumField
        label="Бесплатных спонсорских генераций в день на пользователя"
        hint="0 = спонсорские эффекты не бесплатны (только бейдж + поднятие в списке)"
        value={d.sponsored} onChange={(v) => set("sponsored", v)} />
    </div>
  );
}


function MaintenanceSection({ cfg, save }: SectionProps) {
  const m = asObj(cfg.maintenance);
  const init = useMemo(() => ({
    enabled: Boolean(m.enabled),
    message: String(m.message ?? ""),
  }), [cfg]);
  const [d, setD] = useState(init);
  const [saving, setSaving] = useState(false);
  const dirty = JSON.stringify(d) !== JSON.stringify(init);
  const set = (k: keyof typeof init, v: boolean | string) => setD((s) => ({ ...s, [k]: v }));

  async function onSave() {
    setSaving(true);
    try {
      await save({ maintenance: { enabled: d.enabled, message: d.message.trim() } }, "✅ Режим обслуживания сохранён");
    } finally { setSaving(false); }
  }
  return (
    <div className="panel">
      <SaveHead title="Режим обслуживания" icon="build" dirty={dirty} saving={saving} onSave={onSave} />
      <p className="page-sub" style={{ marginTop: 0 }}>
        Когда включено — бот отвечает не-админам сообщением ниже и не обрабатывает их запросы. Админы (settings.admin_ids) работают как обычно. Применяется мгновенно.
      </p>
      <ToggleRow label="Включить режим обслуживания" checked={d.enabled} onChange={(v) => set("enabled", v)} hint="Все обычные пользователи увидят сообщение и не смогут пользоваться ботом" />
      <TextField label="Сообщение пользователям" area value={d.message} onChange={(v) => set("message", v)} hint="Пусто = дефолтный текст" placeholder="🛠 Ведутся технические работы, скоро вернёмся." />
    </div>
  );
}
