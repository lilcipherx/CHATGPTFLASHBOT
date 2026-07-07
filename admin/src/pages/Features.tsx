import { useCallback, useEffect, useMemo, useState } from "react";
import { api, AuditEntry, ModerationRule } from "../api";
import { Select } from "../components/Select";
import { Switch } from "../components/Switch";
import { Modal } from "../components/Modal";

interface Flag { key: string; enabled: boolean; label: string; default: boolean }
interface Gate { channel: string; is_active: boolean }

// Category + "requires provider" are derived from the catalogue label (the backend
// flags are simple booleans; richer attributes aren't modelled server-side).
function flagCat(f: Flag): { key: string; label: string; cls: string } {
  if (f.label.startsWith("Гейт")) return { key: "gate", label: "Гейт", cls: "warn" };
  if (f.label.startsWith("Сервис")) return { key: "service", label: "Сервис", cls: "pro" };
  return { key: "core", label: "Core", cls: "ok" };
}
const needsProvider = (f: Flag) => /провайдер/i.test(f.label);
const flagTitle = (f: Flag) => f.label.replace(/^(Гейт|Сервис):\s*/, "");

function useDebounced<T>(v: T, ms = 200): T {
  const [d, setD] = useState(v);
  useEffect(() => { const t = setTimeout(() => setD(v), ms); return () => clearTimeout(t); }, [v, ms]);
  return d;
}

type Tab = "flags" | "gates" | "moderation";

export function Features() {
  const [tab, setTab] = useState<Tab>("flags");
  const [flags, setFlags] = useState<Flag[] | null>(null);
  const [gates, setGates] = useState<Gate[] | null>(null);
  const [words, setWords] = useState<ModerationRule[] | null>(null);
  const [history, setHistory] = useState<AuditEntry[]>([]);
  const [msg, setMsg] = useState("");

  const load = useCallback(() => {
    api.flags().then(setFlags).catch((e) => { setMsg(String(e)); setFlags([]); });
    api.gates().then(setGates).catch(() => setGates([]));
    api.moderationWords().then((w) => setWords(w.words)).catch(() => setWords([]));
    api.audit({ limit: 200 }).then((es) => setHistory(es.filter((e) => /^(flag|gate|moderation)\./.test(e.action)))).catch(() => setHistory([]));
  }, []);
  useEffect(() => { load(); }, [load]);
  const toast = (m: string) => setMsg(m);
  const guard = (p: Promise<unknown>) => p.then(load).catch((e) => setMsg(String(e)));

  const lastChange = history.length ? history[0].created_at : null;

  return (
    <div>
      <div className="section-head">
        <div>
          <h1 className="page-title">Функции и гейты</h1>
          <p className="page-sub">Центр управления Feature Flags, гейтами обязательной подписки и модерацией.</p>
        </div>
      </div>

      {msg && (
        <p className={msg.startsWith("✅") ? "note-ok" : "note-err"}>
          <span className="ms sm">{msg.startsWith("✅") ? "check_circle" : "error"}</span>
          {msg}<button className="btn ghost sm" onClick={() => setMsg("")} aria-label="Скрыть">×</button>
        </p>
      )}

      <div className="page-stack">
        <FlagsDashboard flags={flags} gates={gates} words={words} lastChange={lastChange} />

        <div className="seg-tabs" style={{ marginBottom: 0 }}>
          <button className={tab === "flags" ? "on" : ""} onClick={() => setTab("flags")}><span className="ms sm" style={{ verticalAlign: "-3px", marginRight: 4 }}>toggle_on</span>Feature Flags</button>
          <button className={tab === "gates" ? "on" : ""} onClick={() => setTab("gates")}><span className="ms sm" style={{ verticalAlign: "-3px", marginRight: 4 }}>verified_user</span>Каналы гейта</button>
          <button className={tab === "moderation" ? "on" : ""} onClick={() => setTab("moderation")}><span className="ms sm" style={{ verticalAlign: "-3px", marginRight: 4 }}>shield</span>Модерация</button>
        </div>

        {tab === "flags" ? <FlagsTab flags={flags} guard={guard} toast={toast} history={history} />
          : tab === "gates" ? <GatesTab gates={gates} guard={guard} toast={toast} />
            : <ModerationTab words={words} guard={guard} toast={toast} />}

        {/* Global change history (real, from audit log) */}
        <div className="panel">
          <div className="panel-title"><span className="ms sm">history</span> История изменений</div>
          {history.length === 0 ? <p className="cfg-hint" style={{ margin: 0 }}>Изменений пока нет (или журнал аудита недоступен для вашей роли).</p> : (
            <div className="table-wrap" tabIndex={0} style={{ border: "none" }}>
              <table className="tbl">
                <thead><tr><th>Дата</th><th>Действие</th><th>Объект</th><th>Админ</th><th>IP</th></tr></thead>
                <tbody>
                  {history.slice(0, 30).map((e) => (
                    <tr key={e.id}>
                      <td className="muted" style={{ whiteSpace: "nowrap" }}>{new Date(e.created_at).toLocaleString("ru")}</td>
                      <td><span className={"pill " + (e.action.includes("delete") ? "danger" : e.action.includes("moderation") ? "pro" : "ok")}>{e.action}</span></td>
                      <td className="code-key">{e.target_id || "—"}</td>
                      <td className="muted">#{e.admin_id}</td>
                      <td className="muted">{e.ip || "—"}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          )}
        </div>
      </div>
    </div>
  );
}

function FlagsDashboard({ flags, gates, words, lastChange }: { flags: Flag[] | null; gates: Gate[] | null; words: ModerationRule[] | null; lastChange: string | null }) {
  const k = useMemo(() => {
    const f = flags || [];
    return {
      total: f.length, on: f.filter((x) => x.enabled).length, off: f.filter((x) => !x.enabled).length,
      drift: f.filter((x) => x.enabled !== x.default).length, gated: f.filter((x) => needsProvider(x)).length,
      gates: (gates || []).length, gatesOn: (gates || []).filter((g) => g.is_active).length, words: (words || []).length,
    };
  }, [flags, gates, words]);
  return (
    <div className="metrics">
      <Metric icon="toggle_on" label="Всего функций" value={k.total} />
      <Metric icon="check_circle" label="Включено" value={k.on} />
      <Metric icon="block" label="Выключено" value={k.off} tone={k.off ? "purple" : undefined} />
      <Metric icon="edit" label="Изменено от дефолта" value={k.drift} tone={k.drift ? "purple" : undefined} />
      <Metric icon="extension_off" label="Требуют провайдера" value={k.gated} tone={k.gated ? "danger" : undefined} />
      <Metric icon="verified_user" label="Каналы гейта" value={`${k.gatesOn}/${k.gates}`} small />
      <Metric icon="shield" label="Стоп-слов" value={k.words} />
      <Metric icon="sync" label="Посл. изменение" value={lastChange ? new Date(lastChange).toLocaleDateString("ru") : "—"} small />
    </div>
  );
}

// ---------------- Flags ----------------
function FlagsTab({ flags, guard, toast, history }: { flags: Flag[] | null; guard: (p: Promise<unknown>) => void; toast: (m: string) => void; history: AuditEntry[] }) {
  const [q, setQ] = useState(""); const dq = useDebounced(q);
  const [fCat, setFCat] = useState("all"); const [fStatus, setFStatus] = useState("all"); const [fExtra, setFExtra] = useState("all");
  const [sel, setSel] = useState<Set<string>>(new Set());
  const [detail, setDetail] = useState<Flag | null>(null);

  const filtered = useMemo(() => (flags || []).filter((f) => {
    if (fCat !== "all" && flagCat(f).key !== fCat) return false;
    if (fStatus === "on" && !f.enabled) return false;
    if (fStatus === "off" && f.enabled) return false;
    if (fExtra === "provider" && !needsProvider(f)) return false;
    if (fExtra === "drift" && f.enabled === f.default) return false;
    if (dq.trim()) { const s = dq.toLowerCase(); if (![f.key, f.label].some((x) => x.toLowerCase().includes(s))) return false; }
    return true;
  }), [flags, dq, fCat, fStatus, fExtra]);

  const setFlag = (f: Flag, v: boolean) => guard(api.setFlag(f.key, v));
  const bulk = async (v: boolean | "reset") => {
    const targets = (flags || []).filter((f) => sel.has(f.key));
    for (const f of targets) { const nv = v === "reset" ? f.default : v; if (f.enabled !== nv) await api.setFlag(f.key, nv); }
    setSel(new Set()); guard(Promise.resolve()); toast("✅ Готово");
  };
  function exportFlags(fmt: "json" | "env" | "yaml" | "csv") {
    const list = flags || [];
    let data = "";
    if (fmt === "json") data = JSON.stringify(Object.fromEntries(list.map((f) => [f.key, f.enabled])), null, 2);
    else if (fmt === "env") data = list.map((f) => `FLAG_${f.key.toUpperCase()}=${f.enabled ? "1" : "0"}`).join("\n");
    else if (fmt === "yaml") data = list.map((f) => `${f.key}: ${f.enabled}`).join("\n");
    else data = "key,enabled,default,label\n" + list.map((f) => `${f.key},${f.enabled},${f.default},"${f.label}"`).join("\n");
    const blob = new Blob([data], { type: "text/plain" }); const a = document.createElement("a");
    a.href = URL.createObjectURL(blob); a.download = `feature-flags.${fmt === "env" ? "env" : fmt}`; a.click();
    setTimeout(() => URL.revokeObjectURL(a.href), 1000);  // FIX: F65 - release the blob URL after the download starts
  }
  async function importFlags(file: File) {
    try {
      const obj = JSON.parse(await file.text());
      if (typeof obj !== "object" || Array.isArray(obj)) throw new Error("Ожидался объект {key: bool}");
      const known = new Set((flags || []).map((f) => f.key));
      const unknown = Object.keys(obj).filter((k) => !known.has(k));
      const apply = Object.entries(obj).filter(([k]) => known.has(k));
      for (const [k, v] of apply) await api.setFlag(k, Boolean(v));
      guard(Promise.resolve());
      toast(`✅ Импортировано: ${apply.length}${unknown.length ? ` · пропущено неизвестных: ${unknown.length}` : ""}`);
    } catch (e) { toast("Ошибка импорта: " + String(e)); }
  }

  const allSel = filtered.length > 0 && filtered.every((f) => sel.has(f.key));

  return (
    <div className="page-stack">
      <div className="panel" style={{ padding: "var(--sp-3) var(--sp-4)" }}>
        <div className="section-head" style={{ margin: 0 }}>
          <div className="form-row" style={{ gap: "var(--sp-2)", flexWrap: "wrap" }}>
            {/* FIX: AUDIT12-M13/M14 - aria-label + maxLength 255 on feature search. */}
            <input style={{ width: 200 }} placeholder="Поиск: название, key" value={q} onChange={(e) => setQ(e.target.value)} maxLength={255} aria-label="Поиск флага" />
            <Select width={140} ariaLabel="Категория" value={fCat} onChange={setFCat} options={[{ value: "all", label: "Все категории" }, { value: "core", label: "Core" }, { value: "service", label: "Сервис" }, { value: "gate", label: "Гейт" }]} />
            <Select width={130} ariaLabel="Статус" value={fStatus} onChange={setFStatus} options={[{ value: "all", label: "Все" }, { value: "on", label: "Вкл" }, { value: "off", label: "Выкл" }]} />
            <Select width={170} ariaLabel="Доп" value={fExtra} onChange={setFExtra} options={[{ value: "all", label: "Без доп. фильтра" }, { value: "provider", label: "Требуют провайдера" }, { value: "drift", label: "Изменены от дефолта" }]} />
          </div>
          <div className="form-row" style={{ gap: "var(--sp-2)" }}>
            <Select width={130} ariaLabel="Экспорт" value="" onChange={(v) => v && exportFlags(v as "json")} options={[{ value: "", label: "Экспорт…" }, { value: "json", label: "JSON" }, { value: "yaml", label: "YAML" }, { value: "csv", label: "CSV" }, { value: "env", label: "ENV" }]} />
            <label className="btn ghost sm" style={{ cursor: "pointer" }}><span className="ms sm">upload</span> Импорт
              <input type="file" accept="application/json" hidden onChange={(e) => { const f = e.target.files?.[0]; if (f) importFlags(f); e.target.value = ""; }} /></label>
          </div>
        </div>
        {sel.size > 0 && (
          <div className="form-row" style={{ gap: "var(--sp-2)", flexWrap: "wrap", marginTop: "var(--sp-3)", paddingTop: "var(--sp-3)", borderTop: "1px solid var(--border)" }}>
            <span className="pill pro">{sel.size} выбрано</span>
            <button className="btn ghost sm" onClick={() => bulk(true)}><span className="ms sm">check_circle</span> Включить</button>
            <button className="btn ghost sm" onClick={() => { if (confirm(`Выключить ${sel.size} функций?`)) bulk(false); }}><span className="ms sm">block</span> Выключить</button>
            <button className="btn ghost sm" onClick={() => { if (confirm("Сбросить выбранные к значениям по умолчанию?")) bulk("reset"); }}><span className="ms sm">restart_alt</span> Сброс к дефолту</button>
            <button className="btn ghost sm" onClick={() => setSel(new Set())}>Снять</button>
          </div>
        )}
      </div>

      <div className="panel">
        {flags === null ? <div className="loading">Загрузка…</div>
          : filtered.length === 0 ? <EmptyState icon="toggle_off" title={(flags.length === 0) ? "Функций нет" : "Ничего не найдено"} desc={(flags.length === 0) ? "Каталог функций задаётся в коде; при появлении флаги будут здесь." : "Измените поиск или фильтры."} />
            : (
              <div className="table-wrap sticky" tabIndex={0} style={{ border: "none" }}>
                <table className="tbl">
                  <thead><tr>
                    <th style={{ width: 32 }}><input type="checkbox" className="fx-check" aria-label="Выбрать" checked={allSel} onChange={(e) => setSel(e.target.checked ? new Set(filtered.map((f) => f.key)) : new Set())} /></th>
                    <th>Функция</th><th>Key</th><th>Категория</th><th>Условие</th><th>Дефолт</th><th>Статус</th><th style={{ width: 90 }}>Действия</th>
                  </tr></thead>
                  <tbody>
                    {filtered.map((f) => {
                      const cat = flagCat(f); const drift = f.enabled !== f.default;
                      return (
                        <tr key={f.key}>
                          <td><input type="checkbox" className="fx-check" aria-label="Выбрать" checked={sel.has(f.key)} onChange={() => setSel((s) => { const n = new Set(s); n.has(f.key) ? n.delete(f.key) : n.add(f.key); return n; })} /></td>
                          <td><b style={{ cursor: "pointer" }} onClick={() => setDetail(f)}>{flagTitle(f)}</b>{drift && <span className="pill warn" style={{ marginLeft: 6 }}>изменён</span>}</td>
                          <td className="code-key">{f.key}</td>
                          <td><span className={"pill " + cat.cls}>{cat.label}</span></td>
                          <td>{needsProvider(f) ? <span className="pill danger" title="Требует подключённого провайдера">нужен провайдер</span> : <span className="muted">—</span>}</td>
                          <td className="muted">{f.default ? "вкл" : "выкл"}</td>
                          <td><Switch checked={f.enabled} onChange={(v) => { if (!v && cat.key === "gate") { if (!confirm("Выключить гейт обязательной подписки?")) return; } setFlag(f, v); }} label={f.enabled ? "Вкл" : "Выкл"} /></td>
                          <td>
                            <div className="form-row" style={{ gap: 2, flexWrap: "nowrap" }}>
                              <button className="btn ghost sm" title="Карточка" onClick={() => setDetail(f)}><span className="ms sm">visibility</span></button>
                              {drift && <button className="btn ghost sm" title="Сбросить к дефолту" onClick={() => setFlag(f, f.default)}><span className="ms sm">restart_alt</span></button>}
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

      {detail && <FlagCard f={detail} history={history.filter((e) => e.target_id === detail.key && e.action.startsWith("flag."))} onClose={() => setDetail(null)} onToggle={(v) => { setFlag(detail, v); setDetail(null); }} />}
    </div>
  );
}

function FlagCard({ f, history, onClose, onToggle }: { f: Flag; history: AuditEntry[]; onClose: () => void; onToggle: (v: boolean) => void }) {
  const cat = flagCat(f); const drift = f.enabled !== f.default;
  return (
    <Modal title={flagTitle(f)} icon="toggle_on" onClose={onClose} wide
      footer={<>
        {drift && <button className="btn ghost spacer" onClick={() => onToggle(f.default)}><span className="ms sm">restart_alt</span> Сбросить к дефолту</button>}
        <button className={"btn " + (f.enabled ? "ghost" : "")} onClick={() => onToggle(!f.enabled)}><span className="ms sm">{f.enabled ? "block" : "check_circle"}</span> {f.enabled ? "Выключить" : "Включить"}</button>
      </>}>
      <div className="form-row" style={{ gap: 8, marginBottom: "var(--sp-4)" }}>
        <span className={"pill " + cat.cls}>{cat.label}</span>
        <span className={"pill " + (f.enabled ? "ok" : "muted")}>{f.enabled ? "включён" : "выключен"}</span>
        {drift && <span className="pill warn">изменён от дефолта</span>}
        {needsProvider(f) && <span className="pill danger">нужен провайдер</span>}
      </div>
      <div className="form-grid">
        <KV label="Key"><span className="code-key">{f.key}</span></KV>
        <KV label="Описание">{f.label}</KV>
        <KV label="Default state">{f.default ? "включён" : "выключен"}</KV>
        <KV label="Current state">{f.enabled ? "включён" : "выключен"}</KV>
      </div>
      <div style={{ marginTop: "var(--sp-4)" }}>
        <span className="panel-title sm" style={{ margin: "0 0 var(--sp-2)" }}><span className="ms sm">history</span> История изменений</span>
        {history.length === 0 ? <p className="cfg-hint" style={{ margin: 0 }}>Изменений нет.</p> : (
          <div style={{ display: "flex", flexDirection: "column", gap: 4 }}>
            {history.slice(0, 8).map((e) => (
              <div key={e.id} className="form-row" style={{ justifyContent: "space-between", fontSize: 12 }}>
                <span className="muted">#{e.admin_id} · {e.ip || "—"}</span><span className="muted">{new Date(e.created_at).toLocaleString("ru")}</span>
              </div>
            ))}
          </div>
        )}
      </div>
      <p className="cfg-hint" style={{ marginTop: "var(--sp-4)" }}>
        <span className="ms sm" style={{ verticalAlign: "-3px" }}>info</span>{" "}
        Эта функция — булев флаг. Процентный rollout, scope (платформа/окружение/регион), зависимости и ограничения по тарифу/роли потребуют расширения модели флага из bool в объект и поддержки в боте — сейчас не моделируются.
      </p>
    </Modal>
  );
}

// ---------------- Gates ----------------
type GateCheck = { ok: boolean; bot_is_admin: boolean; members: number | null; title: string; detail: string };
function GatesTab({ gates, guard, toast }: { gates: Gate[] | null; guard: (p: Promise<unknown>) => void; toast: (m: string) => void }) {
  const [channel, setChannel] = useState("");
  const [checks, setChecks] = useState<Record<string, GateCheck>>({});
  const [checking, setChecking] = useState("");
  function add() {
    const c = channel.trim(); if (!c) return;
    if ((gates || []).some((g) => g.channel === c)) { toast("Такой канал уже есть"); return; }
    guard(api.upsertGate(c.startsWith("@") || /^-?\d+$/.test(c) ? c : "@" + c, true)); setChannel("");
  }
  async function check(ch: string) {
    setChecking(ch);
    try { const r = await api.checkGate(ch); setChecks((p) => ({ ...p, [ch]: r })); }
    catch (e) { setChecks((p) => ({ ...p, [ch]: { ok: false, bot_is_admin: false, members: null, title: "", detail: String(e) } })); }
    finally { setChecking(""); }
  }
  return (
    <div className="page-stack">
      <div className="panel">
        <div className="panel-title"><span className="ms sm">verified_user</span> Каналы обязательной подписки</div>
        <p className="cfg-hint" style={{ marginTop: 0 }}>Включите флаг <code className="code-key">channel_gate</code> на вкладке «Feature Flags», чтобы форсить подписку. Бот должен быть админом канала.</p>
        {gates === null ? <div className="loading">Загрузка…</div>
          : gates.length === 0 ? (
            <EmptyState icon="group_add" title="Каналы не добавлены" desc="Добавьте канал обязательной подписки ниже — пользователи должны будут подписаться, чтобы пользоваться ботом." />
          ) : (
            <div className="table-wrap" tabIndex={0} style={{ border: "none" }}>
              <table className="tbl">
                <thead><tr><th>Канал</th><th>Тип</th><th>Статус</th><th style={{ width: 220 }}>Действия</th></tr></thead>
                <tbody>
                  {gates.map((g) => (
                    <tr key={g.channel}>
                      <td className="code-key">{g.channel}</td>
                      <td><span className="pill muted">{/^-?\d+$/.test(g.channel) ? "Chat ID" : "Username"}</span></td>
                      <td>
                        <span className={"status-dot " + (g.is_active ? "on" : "off")} /><span className={"pill " + (g.is_active ? "ok" : "muted")}>{g.is_active ? "активен" : "выключен"}</span>
                        {checks[g.channel] && (
                          <div className="cfg-hint" style={{ marginTop: 4, color: checks[g.channel].ok && checks[g.channel].bot_is_admin ? "var(--accent)" : "var(--danger)" }}>
                            <span className="ms sm" style={{ verticalAlign: "-3px" }}>{checks[g.channel].ok && checks[g.channel].bot_is_admin ? "check_circle" : "error"}</span>{" "}
                            {checks[g.channel].ok
                              ? (checks[g.channel].bot_is_admin
                                ? `Бот админ${checks[g.channel].members != null ? ` · ${checks[g.channel].members} подписчиков` : ""}`
                                : checks[g.channel].detail)
                              : checks[g.channel].detail}
                          </div>
                        )}
                      </td>
                      <td>
                        <div className="form-row" style={{ gap: 4, flexWrap: "nowrap", alignItems: "center" }}>
                          <Switch checked={g.is_active} onChange={(v) => guard(api.upsertGate(g.channel, v))} label={g.is_active ? "Вкл" : "Выкл"} />
                          <button className="btn ghost sm" title="Проверить: бот-админ + подписчики" disabled={checking === g.channel} onClick={() => check(g.channel)}><span className="ms sm">{checking === g.channel ? "hourglass_top" : "network_check"}</span></button>
                          <button className="btn ghost sm" title="Открыть в Telegram" disabled={/^-?\d+$/.test(g.channel)} onClick={() => window.open(`https://t.me/${g.channel.replace(/^@/, "")}`, "_blank", "noopener,noreferrer")}><span className="ms sm">open_in_new</span></button>
                          <button className="btn ghost sm" title="Копировать" onClick={() => { navigator.clipboard?.writeText(g.channel); toast("✅ Скопировано"); }}><span className="ms sm">content_copy</span></button>
                          <button className="btn ghost sm" title="Удалить" onClick={() => confirm(`Удалить канал ${g.channel}?`) && guard(api.deleteGate(g.channel))}><span className="ms sm" style={{ color: "var(--danger)" }}>delete</span></button>
                        </div>
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          )}
        <div className="form-row" style={{ marginTop: "var(--sp-4)", marginBottom: 0, gap: "var(--sp-2)" }}>
          {/* FIX: AUDIT12-M13/M14 - aria-label + maxLength 255 on channel input. */}
          <input style={{ flex: 1 }} placeholder="@channel или -100123… (Chat ID)" value={channel} onChange={(e) => setChannel(e.target.value)} onKeyDown={(e) => e.key === "Enter" && add()} maxLength={255} aria-label="Канал" />
          <button className="btn" onClick={add}><span className="ms sm">add</span> Добавить канал</button>
        </div>
        <p className="cfg-hint" style={{ marginTop: "var(--sp-3)" }}>
          <span className="ms sm" style={{ verticalAlign: "-3px" }}>info</span>{" "}
          Проверка прав бота (admin/can-post), число подписчиков, пригласительная ссылка и health-пинг канала требуют вызовов Telegram API на бэкенде — здесь хранятся канал и его активность.
        </p>
      </div>
    </div>
  );
}

// ---------------- Moderation ----------------
const MATCH_META: Record<string, { label: string; cls: string; next: ModerationRule["type"] }> = {
  substring: { label: "подстрока", cls: "muted", next: "exact" },
  exact: { label: "точное", cls: "ok", next: "regex" },
  regex: { label: "regex", cls: "pro", next: "substring" },
};
function ModerationTab({ words, guard, toast }: { words: ModerationRule[] | null; guard: (p: Promise<unknown>) => void; toast: (m: string) => void }) {
  const [draft, setDraft] = useState("");
  const [dtype, setDtype] = useState<ModerationRule["type"]>("substring");
  const [q, setQ] = useState("");
  const list = words || [];
  const filtered = useMemo(() => q.trim() ? list.filter((w) => w.value.toLowerCase().includes(q.trim().toLowerCase())) : list, [list, q]);
  const keyOf = (r: ModerationRule) => `${r.type}:${r.value}`;

  async function save(next: ModerationRule[]) { try { const r = await api.setModerationWords(next); guard(Promise.resolve()); toast(`✅ Сохранено: ${r.words.length} правил`); } catch (e) { toast(String(e)); } }
  function addWords() {
    // regex rules are added whole (commas may be part of the pattern); others split on , / newline.
    const parts = dtype === "regex" ? [draft.trim()] : draft.split(/[,\n]/).map((w) => w.trim()).filter(Boolean);
    const add: ModerationRule[] = parts.filter(Boolean).map((v) => ({ value: v, type: dtype }));
    if (!add.length) return;
    const have = new Set(list.map(keyOf));
    const next = [...list, ...add.filter((r) => !have.has(keyOf(r)))];
    setDraft(""); save(next);
  }
  const removeRule = (r: ModerationRule) => save(list.filter((x) => keyOf(x) !== keyOf(r)));
  const cycleType = (r: ModerationRule) => save(list.map((x) => (keyOf(x) === keyOf(r) ? { ...x, type: MATCH_META[x.type].next } : x)));
  function exportWords(fmt: "json" | "csv" | "txt") {
    const data = fmt === "json" ? JSON.stringify(list, null, 2)
      : fmt === "csv" ? "value,type\n" + list.map((r) => `"${r.value}",${r.type}`).join("\n")
        : list.map((r) => `${r.value}\t${r.type}`).join("\n");
    const blob = new Blob([data], { type: "text/plain" }); const a = document.createElement("a");
    a.href = URL.createObjectURL(blob); a.download = `stopwords.${fmt}`; a.click();
    setTimeout(() => URL.revokeObjectURL(a.href), 1000);  // FIX: F65 - release the blob URL after the download starts
  }
  async function importWords(file: File) {
    try {
      const text = await file.text();
      let rules: ModerationRule[] = [];
      try {
        const j = JSON.parse(text);
        if (Array.isArray(j)) rules = j.map((x) => typeof x === "string" ? { value: x, type: "substring" as const } : { value: String(x.value || ""), type: (x.type || "substring") });
      } catch { rules = text.split(/[\n,]/).map((w) => ({ value: w.trim(), type: "substring" as const })); }
      rules = rules.filter((r) => r.value.trim());
      const have = new Set(list.map(keyOf));
      save([...list, ...rules.filter((r) => !have.has(keyOf(r)))]);
    } catch (e) { toast("Ошибка импорта: " + String(e)); }
  }

  return (
    <div className="page-stack">
      <div className="panel">
        <div className="section-head">
          <div className="panel-title" style={{ margin: 0 }}><span className="ms sm">shield</span> Стоп-слова модерации · {list.length}</div>
          <div className="form-row" style={{ gap: "var(--sp-2)" }}>
            <Select width={120} ariaLabel="Экспорт" value="" onChange={(v) => v && exportWords(v as "json")} options={[{ value: "", label: "Экспорт…" }, { value: "json", label: "JSON" }, { value: "csv", label: "CSV" }, { value: "txt", label: "TXT" }]} />
            <label className="btn ghost sm" style={{ cursor: "pointer" }}><span className="ms sm">upload</span> Импорт
              <input type="file" accept=".json,.csv,.txt,text/plain" hidden onChange={(e) => { const f = e.target.files?.[0]; if (f) importWords(f); e.target.value = ""; }} /></label>
          </div>
        </div>
        <p className="cfg-hint" style={{ marginTop: 0 }}>Запрещённые правила поверх встроенных и OpenAI-модерации. Тип задаёт сопоставление: <b>подстрока</b> (где угодно), <b>точное</b> (отдельное слово), <b>regex</b> (шаблон). Регистр не важен.</p>

        <div className="form-row" style={{ gap: "var(--sp-2)", marginBottom: "var(--sp-3)" }}>
          <Select width={140} ariaLabel="Тип" value={dtype} onChange={(v) => setDtype(v as ModerationRule["type"])}
            options={[{ value: "substring", label: "подстрока" }, { value: "exact", label: "точное слово" }, { value: "regex", label: "regex" }]} />
          {/* FIX: AUDIT12-M13/M14 - aria-label + maxLength 8192 on stop-words draft. */}
          <input style={{ flex: 1 }} placeholder={dtype === "regex" ? "regex-шаблон + Enter" : "новые слова через запятую + Enter"} value={draft} onChange={(e) => setDraft(e.target.value)} onKeyDown={(e) => { if (e.key === "Enter") { e.preventDefault(); addWords(); } }} maxLength={8192} aria-label="Новые слова" />
          <button className="btn" onClick={addWords} disabled={!draft.trim()}><span className="ms sm">add</span> Добавить</button>
        </div>
        {/* FIX: AUDIT12-M13/M14 - aria-label + maxLength 255 on stop-words search. */}
        {list.length > 8 && <input style={{ marginBottom: "var(--sp-3)" }} placeholder="Поиск по словам…" value={q} onChange={(e) => setQ(e.target.value)} maxLength={255} aria-label="Поиск по словам" />}

        {words === null ? <div className="loading">Загрузка…</div>
          : list.length === 0 ? <EmptyState icon="shield" title="Стоп-слов нет" desc="Добавьте слова, фразы или regex-шаблоны, которые бот будет блокировать дополнительно к встроенным правилам." />
            : (
              <div className="chip-row">
                {filtered.map((r) => (
                  <span className="chip" key={keyOf(r)}>
                    <span className={r.type === "regex" ? "code-key" : ""} style={{ color: "var(--text)" }}>{r.value}</span>
                    <button className={"pill " + MATCH_META[r.type].cls} title="Сменить тип сопоставления" style={{ cursor: "pointer", padding: "0 6px", fontSize: 10 }} onClick={() => cycleType(r)}>{MATCH_META[r.type].label}</button>
                    <button onClick={() => removeRule(r)} aria-label={`Удалить ${r.value}`}><span className="ms sm">close</span></button>
                  </span>
                ))}
                {filtered.length === 0 && <span className="cfg-hint">Ничего не найдено по «{q}».</span>}
              </div>
            )}
        <p className="cfg-hint" style={{ marginTop: "var(--sp-4)" }}>
          <span className="ms sm" style={{ verticalAlign: "-3px" }}>info</span>{" "}
          Клик по типу у правила меняет его (подстрока → точное → regex). Severity и действия (warn/delete/mute/ban) — отдельный движок правил, пока не моделируются.
        </p>
      </div>
    </div>
  );
}

// ---------------- shared ----------------
function EmptyState({ icon, title, desc }: { icon: string; title: string; desc: string }) {
  return (
    <div className="empty-state">
      <div className="es-icon"><span className="ms">{icon}</span></div>
      <p className="es-title">{title}</p>
      <p className="es-desc">{desc}</p>
    </div>
  );
}
function KV({ label, children }: { label: string; children: React.ReactNode }) {
  return <div className="cfg-field"><span className="cfg-cap">{label}</span><div>{children}</div></div>;
}
function Metric({ icon, label, value, tone, small }: { icon: string; label: string; value: number | string; tone?: "purple" | "danger"; small?: boolean }) {
  return (
    <div className={"metric" + (tone ? " " + tone : "")}>
      <span className="glow" />
      <div className="top"><span className="lbl">{label}</span><span className="ms sm">{icon}</span></div>
      <div><div className="num" style={small ? { fontSize: 16 } : undefined}>{typeof value === "number" ? value.toLocaleString("ru") : value}</div></div>
    </div>
  );
}
