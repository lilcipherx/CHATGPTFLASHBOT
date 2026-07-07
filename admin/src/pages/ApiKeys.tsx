import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { api, AuditEntry, ProviderKeyRow } from "../api";
import { Select } from "../components/Select";
import { Modal } from "../components/Modal";

// Native provider API keys. A key entered here is stored ENCRYPTED in the DB and
// overrides the .env default; the server never returns the full key (only a masked
// tail + its source), so "reveal/copy" only applies to a key you are typing.
const SRC: Record<string, { label: string; cls: string }> = {
  db: { label: "из админки", cls: "ok" },
  env: { label: "из .env", cls: "warn" },
  none: { label: "не задан", cls: "muted" },
};
// Lenient, real format expectations for the draft being typed (security §12/§20).
const KEY_RULES: Record<string, { prefix?: string[]; min: number }> = {
  openai: { prefix: ["sk-"], min: 20 }, anthropic: { prefix: ["sk-ant-"], min: 20 },
  google: { prefix: ["AIza"], min: 30 }, deepseek: { prefix: ["sk-"], min: 20 },
  perplexity: { prefix: ["pplx-"], min: 20 }, openrouter: { prefix: ["sk-or-", "sk-"], min: 20 },
  xai: { prefix: ["xai-"], min: 20 },
};
function validateKey(name: string, v: string): { level: "ok" | "warn" | "err"; msg: string } | null {
  const t = v.trim(); if (!t) return null;
  if (/\s/.test(v)) return { level: "err", msg: "Ключ содержит пробелы" };
  if (/^(test|xxx+|placeholder|your[-_]?key|changeme|secret)$/i.test(t)) return { level: "err", msg: "Похоже на placeholder" };
  const rule = KEY_RULES[name] || { min: 8 };
  if (t.length < rule.min) return { level: "warn", msg: `Короткий ключ (${t.length} симв.)` };
  if (rule.prefix && !rule.prefix.some((p) => t.startsWith(p))) return { level: "warn", msg: `Ожидается префикс ${rule.prefix.join(" / ")}` };
  return { level: "ok", msg: `Формат OK · ${t.length} симв.` };
}
function useDebounced<T>(v: T, ms = 200): T {
  const [d, setD] = useState(v);
  useEffect(() => { const t = setTimeout(() => setD(v), ms); return () => clearTimeout(t); }, [v, ms]);
  return d;
}

export function ApiKeys() {
  const [rows, setRows] = useState<ProviderKeyRow[] | null>(null);
  const [drafts, setDrafts] = useState<Record<string, string>>({});
  const [busy, setBusy] = useState("");
  const [msg, setMsg] = useState("");
  const [baseUrl, setBaseUrl] = useState("");
  const [baseSrc, setBaseSrc] = useState<"db" | "env">("env");
  // FIX: AUDIT13-M2 - Suno base URL + model, editable here.
  const [sunoBase, setSunoBase] = useState("");
  const [sunoModel, setSunoModel] = useState("");
  const [sunoSrc, setSunoSrc] = useState<"db" | "env">("env");
  const [view, setView] = useState<"grid" | "table">("grid");
  const [q, setQ] = useState(""); const dq = useDebounced(q);
  const [fSrc, setFSrc] = useState("all");
  const [fStatus, setFStatus] = useState("all");
  const [sel, setSel] = useState<Set<string>>(new Set());
  const [detail, setDetail] = useState<ProviderKeyRow | null>(null);
  const [history, setHistory] = useState<AuditEntry[] | null>(null);

  const load = useCallback(() => {
    api.providerKeys().then(setRows).catch((e) => { setMsg(String(e)); setRows([]); });
    api.openaiBaseUrl().then((r) => { setBaseUrl(r.value); setBaseSrc(r.source); }).catch(() => {});
    api.sunoConfig().then((r) => { setSunoBase(r.base_url.value); setSunoModel(r.model.value); setSunoSrc(r.base_url.source === "db" || r.model.source === "db" ? "db" : "env"); }).catch(() => {});
    // Real change history from the audit log (provider.key.* / base_url actions).
    api.audit({ limit: 200 }).then((es) => setHistory(es.filter((e) => e.action.startsWith("provider.")))).catch(() => setHistory([]));
  }, []);
  useEffect(() => { load(); }, [load]);
  const toast = (m: string) => setMsg(m);
  const setDraft = (name: string, v: string) => setDrafts((d) => ({ ...d, [name]: v }));

  async function saveKey(name: string) {
    const value = (drafts[name] ?? "").trim(); if (!value) return;
    setBusy(name);
    try { await api.setProviderKeys({ [name]: value }); setDraft(name, ""); toast(`✅ Ключ сохранён: ${name}`); load(); }
    catch (e) { toast(String(e)); } finally { setBusy(""); }
  }
  async function clearKey(name: string) {
    if (!confirm(`Удалить ключ «${name}» из админки? Будет использовано значение из .env (если есть). Это действие необратимо.`)) return;
    setBusy(name);
    try { await api.clearProviderKey(name); toast(`✅ Ключ удалён: ${name}`); load(); }
    catch (e) { toast(String(e)); } finally { setBusy(""); }
  }
  async function saveBaseUrl() {
    if (baseUrl.trim() && !/^https?:\/\//.test(baseUrl.trim())) { toast("Base URL должен начинаться с http(s)://"); return; }
    setBusy("__base");
    try { const r = await api.setOpenaiBaseUrl(baseUrl); setMsg(`✅ OpenAI base URL: ${r.value}`); load(); }
    catch (e) { toast(String(e)); } finally { setBusy(""); }
  }
  async function saveSunoConfig() {
    if (sunoBase.trim() && !/^https?:\/\//.test(sunoBase.trim())) { toast("Suno Base URL должен начинаться с http(s)://"); return; }
    setBusy("__suno");
    try { const r = await api.setSunoConfig(sunoBase, sunoModel); setMsg(`✅ Suno: ${r.model || "(модель из .env)"} @ ${r.base_url || "(URL из .env)"}`); load(); }
    catch (e) { toast(String(e)); } finally { setBusy(""); }
  }
  async function bulkClear() {
    const targets = (rows || []).filter((r) => sel.has(r.name) && r.source === "db");
    if (!targets.length) { toast("Среди выбранных нет ключей из админки"); return; }
    if (!confirm(`Удалить ${targets.length} ключ(ей) из админки? Необратимо.`)) return;
    setBusy("__bulk");
    try { for (const r of targets) await api.clearProviderKey(r.name); setSel(new Set()); toast(`✅ Удалено: ${targets.length}`); load(); }
    catch (e) { toast(String(e)); } finally { setBusy(""); }
  }
  function exportStatus(only?: Set<string>) {
    const list = (rows || []).filter((r) => !only || only.has(r.name)).map((r) => ({ name: r.name, label: r.label, configured: r.configured, source: r.source, masked: r.masked }));
    const blob = new Blob([JSON.stringify(list, null, 2)], { type: "application/json" });
    const url = URL.createObjectURL(blob);
    const a = document.createElement("a"); a.href = url; a.download = "provider-keys-status.json"; a.click();
    // FIX: FRONTEND - release the blob URL now that the download has started.
    URL.revokeObjectURL(url);  // FIX: AUDIT-92 - immediate revoke;
  }

  // duplicate detection across drafts (same secret typed for two providers)
  const dupNames = useMemo(() => {
    const seen = new Map<string, string>(); const dups = new Set<string>();
    for (const [n, v] of Object.entries(drafts)) { const t = v.trim(); if (t.length < 8) continue; if (seen.has(t)) { dups.add(n); dups.add(seen.get(t)!); } else seen.set(t, n); }
    return dups;
  }, [drafts]);

  const lastChange = history && history.length ? history[0].created_at : null;
  const kpi = useMemo(() => {
    const r = rows || [];
    return {
      total: r.length, configured: r.filter((x) => x.configured).length, missing: r.filter((x) => !x.configured).length,
      db: r.filter((x) => x.source === "db").length, env: r.filter((x) => x.source === "env").length,
    };
  }, [rows]);

  const filtered = useMemo(() => (rows || []).filter((r) => {
    if (fSrc !== "all" && r.source !== fSrc) return false;
    if (fStatus === "configured" && !r.configured) return false;
    if (fStatus === "missing" && r.configured) return false;
    if (dq.trim()) { const s = dq.toLowerCase(); if (![r.name, r.label].some((f) => f.toLowerCase().includes(s))) return false; }
    return true;
  }), [rows, dq, fSrc, fStatus]);

  const allSel = filtered.length > 0 && filtered.every((r) => sel.has(r.name));

  return (
    <div>
      <div className="section-head">
        <div>
          <h1 className="page-title">Ключи API</h1>
          <p className="page-sub">Центр управления ключами провайдеров: шифрованное хранение, переопределение .env, валидация и журнал изменений.</p>
        </div>
        <div className="form-row">
          <div className="seg-tabs">
            <button className={view === "grid" ? "on" : ""} onClick={() => setView("grid")} title="Карточки"><span className="ms sm">grid_view</span></button>
            <button className={view === "table" ? "on" : ""} onClick={() => setView("table")} title="Таблица"><span className="ms sm">table_rows</span></button>
          </div>
          <button className="btn ghost sm" onClick={() => exportStatus()}><span className="ms sm">download</span> Экспорт статуса</button>
        </div>
      </div>

      {msg && (
        <p className={msg.startsWith("✅") ? "note-ok" : "note-err"}>
          <span className="ms sm">{msg.startsWith("✅") ? "check_circle" : "error"}</span>
          {msg}<button className="btn ghost sm" onClick={() => setMsg("")} aria-label="Скрыть">×</button>
        </p>
      )}

      <div className="page-stack">
        <div className="metrics">
          <Metric icon="key" label="Всего провайдеров" value={kpi.total} />
          <Metric icon="check_circle" label="Настроено" value={kpi.configured} />
          <Metric icon="key_off" label="Не задано" value={kpi.missing} tone={kpi.missing ? "purple" : undefined} />
          <Metric icon="admin_panel_settings" label="Из админки" value={kpi.db} />
          <Metric icon="dns" label="Из .env" value={kpi.env} />
          <Metric icon="sync" label="Посл. изменение" value={lastChange ? new Date(lastChange).toLocaleDateString("ru") : "—"} small />
        </div>

        {/* OpenAI base URL */}
        <div className="panel">
          <div className="panel-title"><span className="ms sm">link</span> OpenAI Base URL
            <span className={"pill " + (baseSrc === "db" ? "ok" : "warn")}>{baseSrc === "db" ? "из админки" : "из .env"}</span>
          </div>
          <p className="cfg-hint" style={{ marginTop: 0 }}>OpenAI-совместимый шлюз (по умолчанию <code className="code-key">https://api.openai.com/v1</code>). Применяется движком в течение ~30 сек.</p>
          <div className="form-row" style={{ marginBottom: 0, gap: "var(--sp-2)" }}>
            <input className="mono" style={{ flex: 1 }} placeholder="https://api.openai.com/v1" value={baseUrl} onChange={(e) => setBaseUrl(e.target.value)} />
            <button className="btn" disabled={busy === "__base"} onClick={saveBaseUrl}><span className="ms sm">save</span> {busy === "__base" ? "…" : "Сохранить"}</button>
            {/* FIX: F39 - call saveBaseUrl AFTER setBaseUrl("") has re-rendered, not via a
                stale closure captured at click time. setTimeout(fn, 0) fired the OLD closure
                (with the previous baseUrl), so "Сброс" saved the OLD typed value as a DB
                override instead of clearing it. Use a fresh arrow that reads the just-set "". */}
            <button className="btn ghost" disabled={busy === "__base"} title="Сбросить к значению из .env" onClick={() => { setBaseUrl(""); setBusy("__base"); (async () => { try { await api.setOpenaiBaseUrl(""); await load(); } catch (e) { setMsg(String(e)); } finally { setBusy(""); } })(); }}><span className="ms sm">restart_alt</span> Сброс</button>
          </div>
        </div>

        {/* FIX: AUDIT13-M2 - Suno base URL + model (music). Lets the operator set the
            EXACT model your Suno aggregator expects for the advertised "V5.5" instead of
            the hard-coded suno-v4 downgrade — without a redeploy. */}
        <div className="panel">
          <div className="panel-title"><span className="ms sm">music_note</span> Suno (музыка)
            <span className={"pill " + (sunoSrc === "db" ? "ok" : "warn")}>{sunoSrc === "db" ? "из админки" : "из .env"}</span>
          </div>
          <p className="cfg-hint" style={{ marginTop: 0 }}>Base URL (по умолчанию <code className="code-key">https://api.suno.ai/v1</code>) и точный id модели, который ждёт твой Suno-агрегатор для рекламируемой версии (напр. <code className="code-key">chirp-v4-5</code>). Ключ Suno задаётся выше в списке провайдеров.</p>
          <div className="form-row" style={{ marginBottom: "var(--sp-2)", gap: "var(--sp-2)" }}>
            <input className="mono" style={{ flex: 1 }} placeholder="https://api.suno.ai/v1" value={sunoBase} onChange={(e) => setSunoBase(e.target.value)} />
            <input className="mono" style={{ flex: 1 }} placeholder="модель, напр. chirp-v4-5" value={sunoModel} onChange={(e) => setSunoModel(e.target.value)} />
          </div>
          <div className="form-row" style={{ marginBottom: 0, gap: "var(--sp-2)" }}>
            <button className="btn" disabled={busy === "__suno"} onClick={saveSunoConfig}><span className="ms sm">save</span> {busy === "__suno" ? "…" : "Сохранить"}</button>
            <button className="btn ghost" disabled={busy === "__suno"} title="Сбросить к значениям из .env" onClick={() => { setSunoBase(""); setSunoModel(""); setBusy("__suno"); (async () => { try { await api.setSunoConfig("", ""); await load(); } catch (e) { setMsg(String(e)); } finally { setBusy(""); } })(); }}><span className="ms sm">restart_alt</span> Сброс</button>
          </div>
        </div>

        {/* Toolbar */}
        <div className="panel" style={{ padding: "var(--sp-3) var(--sp-4)" }}>
          <div className="section-head" style={{ margin: 0 }}>
            <div className="form-row" style={{ gap: "var(--sp-2)", flexWrap: "wrap" }}>
              <input style={{ width: 220 }} placeholder="Поиск: провайдер, описание" value={q} onChange={(e) => setQ(e.target.value)} />
              <Select width={160} ariaLabel="Источник" value={fSrc} onChange={setFSrc} options={[{ value: "all", label: "Любой источник" }, { value: "db", label: "Из админки" }, { value: "env", label: "Из .env" }, { value: "none", label: "Не задан" }]} />
              <Select width={160} ariaLabel="Статус" value={fStatus} onChange={setFStatus} options={[{ value: "all", label: "Все" }, { value: "configured", label: "Настроенные" }, { value: "missing", label: "Без ключа" }]} />
            </div>
            <span className="cfg-hint" style={{ margin: 0 }}>{filtered.length} из {rows?.length ?? 0}</span>
          </div>
          {sel.size > 0 && (
            <div className="form-row" style={{ gap: "var(--sp-2)", flexWrap: "wrap", marginTop: "var(--sp-3)", paddingTop: "var(--sp-3)", borderTop: "1px solid var(--border)" }}>
              <span className="pill pro">{sel.size} выбрано</span>
              <button className="btn ghost sm" disabled={busy === "__bulk"} onClick={bulkClear}><span className="ms sm" style={{ color: "var(--danger)" }}>delete</span> Удалить (db)</button>
              <button className="btn ghost sm" onClick={() => exportStatus(sel)}><span className="ms sm">download</span> Экспорт</button>
              <button className="btn ghost sm" onClick={() => setSel(new Set())}>Снять</button>
            </div>
          )}
        </div>

        {/* Providers */}
        {rows === null ? (
          view === "grid" ? <div className="prov-grid">{Array.from({ length: 6 }).map((_, i) => <div key={i} className="prov-card"><div className="skeleton" style={{ height: 16, width: "60%" }} /><div className="skeleton" style={{ height: 38 }} /></div>)}</div> : <div className="panel"><div className="loading">Загрузка…</div></div>
        ) : filtered.length === 0 ? (
          <div className="panel"><EmptyState icon="key" title={rows.length === 0 ? "Провайдеры не настроены" : "Ничего не найдено"} desc={rows.length === 0 ? "Список провайдеров задаётся в коде; как только он появится, ключи можно будет вводить здесь." : "Измените поиск или фильтры."} /></div>
        ) : view === "grid" ? (
          <div className="prov-grid">
            {filtered.map((r) => (
              <div key={r.name} className={"prov-card" + (r.configured ? "" : " off")}>
                <input type="checkbox" className="fx-check pc-sel" aria-label="Выбрать" checked={sel.has(r.name)} onChange={() => setSel((p) => { const n = new Set(p); n.has(r.name) ? n.delete(r.name) : n.add(r.name); return n; })} />
                <div className="pc-head">
                  <div className="prov-logo"><span className="ms" style={{ fontSize: 20, color: r.configured ? "var(--accent)" : "var(--hint)" }}>{r.configured ? "key" : "key_off"}</span></div>
                  <div style={{ minWidth: 0 }}>
                    <div className="pc-name">{r.name}</div>
                    <div className="pc-vendor clamp-2">{r.label}</div>
                  </div>
                </div>
                <div className="form-row" style={{ gap: 6 }}>
                  <span className={"pill " + (r.configured ? "ok" : "muted")}>{r.configured ? "настроен" : "нет ключа"}</span>
                  <span className={"pill " + (SRC[r.source]?.cls ?? "muted")}>{SRC[r.source]?.label ?? r.source}</span>
                  {r.configured && <span className="code-key" style={{ marginLeft: "auto" }}>{r.masked}</span>}
                </div>
                <KeyEditor name={r.name} row={r} draft={drafts[r.name] ?? ""} setDraft={(v) => setDraft(r.name, v)}
                  onSave={() => saveKey(r.name)} onClear={() => clearKey(r.name)} busy={busy === r.name} dup={dupNames.has(r.name)} />
                <div className="pc-foot">
                  <button className="btn ghost sm" onClick={() => setDetail(r)}><span className="ms sm">visibility</span> Карточка</button>
                </div>
              </div>
            ))}
          </div>
        ) : (
          <div className="panel">
            <div className="table-wrap sticky" tabIndex={0} style={{ border: "none" }}>
              <table className="tbl">
                <thead><tr>
                  <th style={{ width: 32 }}><input type="checkbox" className="fx-check" aria-label="Выбрать" checked={allSel} onChange={(e) => setSel(e.target.checked ? new Set(filtered.map((r) => r.name)) : new Set())} /></th>
                  <th>Провайдер</th><th>Тип сервиса</th><th>Источник</th><th>Текущий ключ</th><th>Статус</th><th style={{ width: 130 }}>Действия</th>
                </tr></thead>
                <tbody>
                  {filtered.map((r) => (
                    <tr key={r.name}>
                      <td><input type="checkbox" className="fx-check" aria-label="Выбрать" checked={sel.has(r.name)} onChange={() => setSel((p) => { const n = new Set(p); n.has(r.name) ? n.delete(r.name) : n.add(r.name); return n; })} /></td>
                      <td><b style={{ cursor: "pointer" }} onClick={() => setDetail(r)}>{r.name}</b></td>
                      <td className="muted clamp-2" style={{ maxWidth: 280, fontSize: 12 }}>{r.label}</td>
                      <td><span className={"pill " + (SRC[r.source]?.cls ?? "muted")}>{SRC[r.source]?.label ?? r.source}</span></td>
                      <td>{r.configured ? <span className="code-key">{r.masked}</span> : <span className="muted">—</span>}</td>
                      <td><span className={"pill " + (r.configured ? "ok" : "muted")}>{r.configured ? "настроен" : "нет ключа"}</span></td>
                      <td>
                        <div className="form-row" style={{ gap: 2, flexWrap: "nowrap" }}>
                          <button className="btn ghost sm" title="Карточка / изменить" onClick={() => setDetail(r)}><span className="ms sm">edit</span></button>
                          {r.source === "db" && <button className="btn ghost sm" title="Удалить" onClick={() => clearKey(r.name)}><span className="ms sm" style={{ color: "var(--danger)" }}>delete</span></button>}
                        </div>
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          </div>
        )}

        {/* Change history (real, from audit log) */}
        <div className="panel">
          <div className="panel-title"><span className="ms sm">history</span> История изменений ключей</div>
          {history === null ? <div className="loading">Загрузка…</div>
            : history.length === 0 ? <p className="cfg-hint" style={{ margin: 0 }}>Изменений пока нет (или журнал аудита недоступен для вашей роли).</p>
              : (
                <div className="table-wrap" tabIndex={0} style={{ border: "none" }}>
                  <table className="tbl">
                    <thead><tr><th>Дата</th><th>Действие</th><th>Провайдер</th><th>Админ</th><th>IP</th></tr></thead>
                    <tbody>
                      {history.slice(0, 30).map((e) => (
                        <tr key={e.id}>
                          <td className="muted" style={{ whiteSpace: "nowrap" }}>{new Date(e.created_at).toLocaleString("ru")}</td>
                          <td><span className={"pill " + (e.action.includes("clear") ? "danger" : e.action.includes("base_url") ? "muted" : "ok")}>{e.action.replace("provider.", "")}</span></td>
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

      {detail && (
        <KeyCard r={detail} history={(history || []).filter((e) => e.target_id === detail.name)} onClose={() => setDetail(null)}
          draft={drafts[detail.name] ?? ""} setDraft={(v) => setDraft(detail.name, v)}
          onSave={() => saveKey(detail.name)} onClear={() => clearKey(detail.name)} busy={busy === detail.name} dup={dupNames.has(detail.name)} />
      )}
    </div>
  );
}

// Inline key editor: masked password field, reveal-with-auto-hide, format hint, save/clear.
function KeyEditor({ name, row, draft, setDraft, onSave, onClear, busy, dup }: {
  name: string; row: ProviderKeyRow; draft: string; setDraft: (v: string) => void;
  onSave: () => void; onClear: () => void; busy: boolean; dup: boolean;
}) {
  const [reveal, setReveal] = useState(false);
  const [test, setTest] = useState<{ ok: boolean; supported: boolean; status_code: number; latency_ms: number; detail: string } | null>(null);
  const [testing, setTesting] = useState(false);
  const hideTimer = useRef<ReturnType<typeof setTimeout> | null>(null);
  useEffect(() => () => { if (hideTimer.current) clearTimeout(hideTimer.current); }, []);
  async function runTest() {
    setTesting(true); setTest(null);
    try { setTest(await api.testProviderKey(name)); }
    catch (e) { setTest({ ok: false, supported: true, status_code: 0, latency_ms: 0, detail: String(e) }); }
    finally { setTesting(false); }
  }
  function toggleReveal() {
    setReveal((v) => {
      const nv = !v;
      if (nv) { if (hideTimer.current) clearTimeout(hideTimer.current); hideTimer.current = setTimeout(() => setReveal(false), 10_000); }
      return nv;
    });
  }
  const valid = validateKey(name, draft);
  return (
    <div style={{ display: "flex", flexDirection: "column", gap: 6 }}>
      <div className="form-row" style={{ gap: 6 }}>
        <div style={{ position: "relative", flex: 1 }}>
          <input type={reveal ? "text" : "password"} className="mono" autoComplete="off" placeholder={row.configured ? "заменить ключ…" : "вставьте ключ…"}
            value={draft} onChange={(e) => setDraft(e.target.value)} style={{ width: "100%", paddingRight: 34 }}
            onKeyDown={(e) => { if (e.key === "Enter" && draft.trim()) onSave(); }} />
          {draft && <button className="btn ghost sm" title={reveal ? "Скрыть" : "Показать (на 10 сек)"} onClick={toggleReveal}
            style={{ position: "absolute", right: 2, top: "50%", transform: "translateY(-50%)", padding: "4px 6px" }}><span className="ms sm">{reveal ? "visibility_off" : "visibility"}</span></button>}
        </div>
        <button className="btn sm" title="Сохранить ключ" aria-label="Сохранить ключ" disabled={busy || !draft.trim() || valid?.level === "err"} onClick={onSave}><span className="ms sm">save</span></button>
        {row.configured && <button className="btn ghost sm" disabled={testing} title="Проверить ключ онлайн" onClick={runTest}><span className="ms sm">{testing ? "hourglass_top" : "network_check"}</span></button>}
        {row.source === "db" && <button className="btn ghost sm" disabled={busy} title="Удалить ключ" onClick={onClear}><span className="ms sm" style={{ color: "var(--danger)" }}>delete</span></button>}
      </div>
      {test && (
        <span className="cfg-hint" style={{ color: test.ok ? "var(--accent)" : !test.supported ? "var(--hint)" : "var(--danger)" }}>
          <span className="ms sm" style={{ verticalAlign: "-3px" }}>{test.ok ? "check_circle" : !test.supported ? "info" : "error"}</span>{" "}
          {test.ok ? `Ключ рабочий · ${test.latency_ms} мс (HTTP ${test.status_code})`
            : !test.supported ? test.detail
            : `${test.status_code || "нет ответа"} · ${test.latency_ms} мс${test.detail ? ` · ${test.detail}` : ""}`}
        </span>
      )}
      {valid && <span className="cfg-hint" style={{ color: valid.level === "err" ? "var(--danger)" : valid.level === "warn" ? "var(--warn)" : "var(--accent)" }}>
        <span className="ms sm" style={{ verticalAlign: "-3px" }}>{valid.level === "ok" ? "check_circle" : valid.level === "warn" ? "warning" : "error"}</span> {valid.msg}
      </span>}
      {dup && <span className="cfg-hint" style={{ color: "var(--warn)" }}><span className="ms sm" style={{ verticalAlign: "-3px" }}>content_copy</span> Тот же ключ введён для другого провайдера</span>}
    </div>
  );
}

function KeyCard({ r, history, onClose, draft, setDraft, onSave, onClear, busy, dup }: {
  r: ProviderKeyRow; history: AuditEntry[]; onClose: () => void;
  draft: string; setDraft: (v: string) => void; onSave: () => void; onClear: () => void; busy: boolean; dup: boolean;
}) {
  return (
    <Modal title={r.name} icon="key" onClose={onClose} wide>
      <div className="form-row" style={{ gap: 8, marginBottom: "var(--sp-4)" }}>
        <span className={"pill " + (r.configured ? "ok" : "muted")}>{r.configured ? "настроен" : "нет ключа"}</span>
        <span className={"pill " + (SRC[r.source]?.cls ?? "muted")}>{SRC[r.source]?.label ?? r.source}</span>
        {r.configured && <span className="code-key" style={{ marginLeft: "auto" }}>{r.masked}</span>}
      </div>
      <p className="cfg-hint" style={{ margin: "0 0 var(--sp-4)" }}>{r.label}</p>

      <div className="cfg-field"><span className="cfg-cap">{r.configured ? "Заменить ключ" : "Задать ключ"}</span>
        <KeyEditor name={r.name} row={r} draft={draft} setDraft={setDraft} onSave={onSave} onClear={onClear} busy={busy} dup={dup} />
      </div>

      <div style={{ marginTop: "var(--sp-4)", padding: "var(--sp-3)", background: "var(--surface-1)", border: "1px solid var(--border)", borderRadius: "var(--r-sm)" }}>
        <span className="panel-title sm" style={{ margin: 0, display: "block", marginBottom: "var(--sp-2)" }}><span className="ms sm">shield</span> Безопасность</span>
        <p className="cfg-hint" style={{ margin: 0 }}>
          Сервер никогда не возвращает полный ключ — только маскированный хвост <code className="code-key">{r.masked || "…"}</code>.
          Раскрыть/скопировать можно только новый ключ, который вы вводите (с авто-скрытием через 10 сек). Ключ хранится в БД в зашифрованном виде и переопределяет .env.
        </p>
      </div>

      <div style={{ marginTop: "var(--sp-4)" }}>
        <span className="panel-title sm" style={{ margin: "0 0 var(--sp-2)" }}><span className="ms sm">history</span> История изменений</span>
        {history.length === 0 ? <p className="cfg-hint" style={{ margin: 0 }}>Изменений для этого провайдера нет.</p> : (
          <div style={{ display: "flex", flexDirection: "column", gap: 4 }}>
            {history.slice(0, 8).map((e) => (
              <div key={e.id} className="form-row" style={{ justifyContent: "space-between", fontSize: 12 }}>
                <span><span className={"pill " + (e.action.includes("clear") ? "danger" : "ok")}>{e.action.replace("provider.", "")}</span> <span className="muted">#{e.admin_id} · {e.ip || "—"}</span></span>
                <span className="muted">{new Date(e.created_at).toLocaleString("ru")}</span>
              </div>
            ))}
          </div>
        )}
      </div>

      <p className="cfg-hint" style={{ marginTop: "var(--sp-4)" }}>
        <span className="ms sm" style={{ verticalAlign: "-3px" }}>info</span>{" "}
        Organization, project, headers, endpoint, health-URL, а также телеметрия (запросы/ошибки/latency/баланс/rate-limits) и онлайн-тест ключа не предусмотрены текущей моделью секретов — потребуют доп. полей и провайдер-специфичного валидатора. Формат и дубликаты проверяются локально при вводе.
      </p>
    </Modal>
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
function Metric({ icon, label, value, tone, small }: { icon: string; label: string; value: number | string; tone?: "purple" | "danger"; small?: boolean }) {
  return (
    <div className={"metric" + (tone ? " " + tone : "")}>
      <span className="glow" />
      <div className="top"><span className="lbl">{label}</span><span className="ms sm">{icon}</span></div>
      <div><div className="num" style={small ? { fontSize: 16 } : undefined}>{typeof value === "number" ? value.toLocaleString("ru") : value}</div></div>
    </div>
  );
}
