import { useCallback, useEffect, useState } from "react";
import { api, type SecurityOverview } from "../api";
import { revokeAllSessions } from "../api";

// Security Center (ТЗ §8) — IAM / Zero-Trust class, grounded in the REAL backend.
// Everything shown is derived from real state: the current admin's account, org-wide
// AdminUser aggregates, the deploy's auth policy (config) and recent security events
// from the audit log (GET /auth/security), plus the real self-service TOTP flow.
// Sessions are stateless JWTs — the genuine lever is "revoke all" (token_version
// bump via logout). Areas that need tables we don't have (per-device sessions, login
// history, failed-login lockout, passkeys/WebAuthn, backup codes, cert status) are
// honestly gated, never faked.

type Tab = "overview" | "auth" | "access" | "events";
const TABS: { id: Tab; label: string; icon: string }[] = [
  { id: "overview", label: "Обзор", icon: "shield" },
  { id: "auth", label: "Аутентификация", icon: "password" },
  { id: "access", label: "Права доступа", icon: "admin_panel_settings" },
  { id: "events", label: "События", icon: "history" },
];
const ROLE_CLS: Record<string, string> = { superadmin: "danger", admin: "pro", moderator: "warn", support: "muted" };

function ago(s: string | null | undefined): string {
  if (!s) return "—";
  const m = Math.floor((Date.now() - new Date(s).getTime()) / 60000);
  if (m < 1) return "только что"; if (m < 60) return `${m} мин назад`;
  const h = Math.floor(m / 60); if (h < 24) return `${h} ч назад`;
  const d = Math.floor(h / 24); if (d < 30) return `${d} дн назад`;
  return new Date(s).toLocaleDateString("ru");
}
function fmtDate(s: string): string {
  return new Date(s).toLocaleString("ru", { day: "2-digit", month: "short", year: "numeric", hour: "2-digit", minute: "2-digit" });
}
const fmtInt = (n: number | undefined) => (n ?? 0).toLocaleString("ru");

export function Security() {
  const [tab, setTab] = useState<Tab>("overview");
  const [ov, setOv] = useState<SecurityOverview | null>(null);
  const [limited, setLimited] = useState(false); // 403 → lower role: 2FA self-service only
  const [msg, setMsg] = useState(""); const [err, setErr] = useState("");
  // FIX: POLISH-13 - revoking state was referenced on the "Завершить все сессии"
  // button (disabled={revoking}) but never declared → ReferenceError crashed the
  // whole page on first render. Add the state + wire it into revokeAll so the
  // button is disabled (and shows a spinner) while the request is in flight.
  const [revoking, setRevoking] = useState(false);

  const load = useCallback(() => {
    api.securityOverview().then((d) => { setOv(d); setLimited(false); })
      .catch((e) => { if (/403/.test(String(e))) setLimited(true); else setErr(String(e)); });
  }, []);
  useEffect(() => { load(); }, [load]);

  const notify = (m: string, isErr = false) => { if (isErr) { setErr(m); setMsg(""); } else { setMsg(m); setErr(""); } };

  async function revokeAll() {
    if (!confirm("Завершить ВСЕ активные сессии? Будут отозваны все токены (включая текущий) — потребуется повторный вход на всех устройствах.")) return;
    // Await the server-side token_version bump BEFORE reloading, so the reload can't
    // cancel the in-flight request and leave other sessions silently still valid.
    setRevoking(true);
    try {
      await revokeAllSessions();
      location.reload();
    } catch (e) {
      setRevoking(false);
      notify(String(e), true);
    }
  }

  return (
    <div>
      <div className="section-head">
        <div>
          <h1 className="page-title">Центр безопасности</h1>
          <p className="page-sub">Оценка защищённости, политика аутентификации, двухфакторная защита, права доступа и журнал событий безопасности. Все показатели — из реального состояния системы.</p>
        </div>
        <div className="form-row" style={{ gap: "var(--sp-2)", margin: 0 }}>
          <button className="btn ghost sm" onClick={load}><span className="ms sm">refresh</span> Обновить</button>
          <button className="btn danger sm" disabled={revoking} onClick={revokeAll}><span className="ms sm">logout</span> Завершить все сессии</button>
        </div>
      </div>

      {(msg || err) && (
        <p className={err ? "note-err" : "note-ok"}>
          <span className="ms sm">{err ? "error" : "check_circle"}</span>{err || msg}
          <button className="btn ghost sm" onClick={() => { setMsg(""); setErr(""); }} style={{ marginLeft: "auto" }}>×</button>
        </p>
      )}

      {limited && (
        <p className="note-ok"><span className="ms sm">info</span>Полный обзор безопасности доступен роли admin и выше. Вам доступно управление собственной двухфакторной аутентификацией.</p>
      )}

      <div className="panel" style={{ padding: "var(--sp-2) var(--sp-3)", position: "sticky", top: 0, zIndex: 6, marginBottom: "var(--sp-4)" }}>
        <div className="seg-tabs" style={{ marginBottom: 0, flexWrap: "wrap" }}>
          {TABS.map((t) => (
            <button key={t.id} className={tab === t.id ? "on" : ""} onClick={() => setTab(t.id)} disabled={limited && t.id !== "auth"}>
              <span className="ms sm" style={{ verticalAlign: "-3px", marginRight: 4 }}>{t.icon}</span>{t.label}
            </button>
          ))}
        </div>
      </div>

      {tab === "overview" && (limited ? <LimitedHint go={() => setTab("auth")} /> : <OverviewTab ov={ov} onRevoke={revokeAll} />)}
      {tab === "auth" && <AuthTab ov={ov} notify={notify} reload={load} />}
      {tab === "access" && (limited ? <LimitedHint go={() => setTab("auth")} /> : <AccessTab ov={ov} />)}
      {tab === "events" && (limited ? <LimitedHint go={() => setTab("auth")} /> : <EventsTab ov={ov} />)}
    </div>
  );
}

// ================= Overview =================
function OverviewTab({ ov, onRevoke }: { ov: SecurityOverview | null; onRevoke: () => void }) {
  if (!ov) return <SkeletonGrid />;
  const s = ov.self; const org = ov.org; const p = ov.policy;
  const scoreTone = ov.score >= 80 ? "var(--ok)" : ov.score >= 60 ? "var(--warn)" : "var(--danger)";

  return (
    <div className="page-stack">
      <div className="prov-grid" style={{ gridTemplateColumns: "minmax(240px, 320px) 1fr" }}>
        {/* Score */}
        <div className="panel" style={{ display: "flex", flexDirection: "column", alignItems: "center", gap: "var(--sp-3)", justifyContent: "center" }}>
          <div className="panel-title sm" style={{ alignSelf: "flex-start" }}><span className="ms sm">verified_user</span> Security Score</div>
          <ScoreRing score={ov.score} color={scoreTone} />
          <span className="muted" style={{ fontSize: 12 }}>{ov.recommendations.length === 0 ? "Все ключевые проверки пройдены" : `${ov.recommendations.length} рекомендаций ниже`}</span>
        </div>

        {/* Recommendations / checks */}
        <div className="panel">
          <div className="panel-title sm"><span className="ms sm">checklist</span> Проверки безопасности</div>
          <div className="page-stack" style={{ gap: 8, marginTop: "var(--sp-2)" }}>
            {ov.checks.map((c) => (
              <div key={c.id} className="form-row" style={{ margin: 0, gap: "var(--sp-2)", alignItems: "flex-start", padding: "8px 10px", borderRadius: "var(--r-sm)", background: "var(--panel-2)" }}>
                <span className="ms sm" style={{ color: c.ok ? "var(--ok)" : "var(--danger)", marginTop: 1 }}>{c.ok ? "check_circle" : "cancel"}</span>
                <span style={{ flex: 1, minWidth: 0 }}>
                  <div style={{ fontSize: 13, fontWeight: 600 }}>{c.label}</div>
                  {!c.ok && <div className="muted" style={{ fontSize: 12 }}>{c.rec}</div>}
                </span>
                <span className={"pill " + (c.ok ? "ok" : "muted")} style={{ fontSize: 10 }}>+{c.weight}</span>
              </div>
            ))}
          </div>
        </div>
      </div>

      {/* KPIs */}
      <div className="metrics">
        <Metric icon="shield" label="2FA (ваш аккаунт)" value={s.has_2fa ? "вкл" : "выкл"} tone={s.has_2fa ? undefined : "danger"} />
        <Metric icon="group" label="Администраторов" value={fmtInt(org.admins_total)} />
        <Metric icon="verified" label="С 2FA" value={`${fmtInt(org.with_2fa)}/${fmtInt(org.admins_total)}`} tone="purple" small />
        <Metric icon="gpp_maybe" label="Без обязательной 2FA" value={fmtInt(org.missing_required_2fa)} tone={org.missing_required_2fa ? "danger" : undefined} small />
        <Metric icon="login" label="Последний вход" value={ago(s.last_login)} small />
        <Metric icon="lock_reset" label="Версия токенов" value={fmtInt(s.token_version)} small />
        <Metric icon="vpn_lock" label="IP-allowlist" value={p.ip_allowlist_configured ? `${p.ip_allowlist_count}` : "выкл"} tone={p.ip_allowlist_configured ? undefined : "danger"} small />
        <Metric icon="event" label="Послед. событие" value={ago(ov.last_security_event_at)} small />
      </div>

      {/* Posture cards */}
      <div className="prov-grid">
        <PostureCard title="Аутентификация" icon="password" ok={s.has_2fa} dim={s.has_2fa ? "2FA включена" : "2FA выключена"}>
          <KV k="Алгоритм пароля" v={p.password_algo} />
          <KV k="2FA (TOTP)" v={s.has_2fa ? <span className="pill ok">включена</span> : <span className="pill danger">выключена</span>} />
          <KV k="2FA обязательна" v={s.mfa_required ? "да (по роли)" : "нет"} />
          <KV k="TTL access-токена" v={`${p.access_ttl_minutes} мин`} />
        </PostureCard>

        <PostureCard title="Сессии" icon="devices" ok dim="JWT, stateless">
          <KV k="Модель" v="JWT (без серверного стора)" />
          <KV k="Версия токенов" v={s.token_version} />
          <KV k="Cookie" v={`httpOnly · SameSite=${p.cookie.samesite}${p.cookie.secure ? " · Secure" : ""}`} />
          <button className="btn ghost sm" style={{ marginTop: 6 }} onClick={onRevoke}><span className="ms sm">logout</span> Завершить все сессии</button>
        </PostureCard>

        <PostureCard title="Шифрование" icon="enhanced_encryption" ok={p.enc_secret_configured && !p.jwt_secret_default} dim={p.env}>
          <KV k="Хеш паролей" v={<span className="pill ok">{p.password_algo}</span>} />
          <KV k="Секрет шифрования" v={p.enc_secret_configured ? <span className="pill ok">настроен</span> : <span className="pill danger">не задан</span>} />
          <KV k="JWT-секрет" v={p.jwt_secret_default ? <span className="pill danger">дефолтный</span> : <span className="pill ok">задан</span>} />
          <KV k="Secure cookies" v={p.secure_cookies ? <span className="pill ok">да</span> : <span className="pill warn">нет (dev)</span>} />
        </PostureCard>

        <PostureCard title="Ограничения доступа" icon="vpn_lock" ok={p.ip_allowlist_configured} dim={p.ip_allowlist_configured ? `${p.ip_allowlist_count} IP` : "открыт"}>
          <KV k="IP-allowlist" v={p.ip_allowlist_configured ? <span className="pill ok">{p.ip_allowlist_count} адр.</span> : <span className="pill warn">не настроен</span>} />
          <KV k="Обязательная 2FA для ролей" v={p.mfa_required_roles.join(", ") || "—"} />
          <KV k="Окружение" v={p.env} />
          <p className="cfg-hint" style={{ margin: "4px 0 0" }}>IP-allowlist и список ролей с 2FA задаются конфигом деплоя (ADMIN_IP_ALLOWLIST / MFA_REQUIRED_ROLES).</p>
        </PostureCard>
      </div>

      <div className="prov-grid">
        <GatedCard icon="devices_other" title="Сессии и устройства по отдельности"
          text="Список активных сессий/устройств с гео, браузером и точечным Terminate требует серверного стора сессий (Redis/таблица). Сейчас сессии — stateless JWT; реальный рычаг «отозвать всё» (bump token_version) доступен выше." />
        <GatedCard icon="history_toggle_off" title="Автоблокировка при переборе"
          text="Входы и выходы теперь журналируются (auth.login / auth.login_failed / auth.logout с IP и причиной) — успешные и неудачные попытки видны во вкладке «События» и в Аудит-центре. Автоматическая блокировка аккаунта/IP при brute-force (lockout, cooldown, CAPTCHA) ещё требует отдельной таблицы блокировок и счётчиков." />
        <GatedCard icon="key" title="Passkeys / WebAuthn / Backup codes"
          text="Passkeys, аппаратные ключи (YubiKey/Titan/Windows Hello/Touch ID), recovery-коды и одноразовые backup-коды требуют WebAuthn-регистраций и таблицы кодов. Сейчас второй фактор — TOTP (вкладка «Аутентификация»)." />
      </div>
    </div>
  );
}

// ================= Authentication (2FA self-service) =================
function AuthTab({ ov, notify, reload }: { ov: SecurityOverview | null; notify: (m: string, e?: boolean) => void; reload: () => void }) {
  const [enabled, setEnabled] = useState<boolean | null>(null);
  const [required, setRequired] = useState(false);
  const [secret, setSecret] = useState(""); const [uri, setUri] = useState(""); const [code, setCode] = useState("");
  const [busy, setBusy] = useState(false);  // FIX: AUDIT12-L2 - 2FA enable/disable in-flight guard

  const loadStatus = useCallback(() => {
    api.twofaStatus().then((s) => { setEnabled(s.enabled); setRequired(s.required); }).catch((e) => notify(String(e), true));
  }, [notify]);
  useEffect(() => { loadStatus(); }, [loadStatus]);

  async function startSetup() {
    try { const r = await api.twofaSetup(); setSecret(r.secret); setUri(r.uri); }
    catch (e) { notify(String(e), true); }
  }
  async function enable() {
    setBusy(true);
    try { await api.twofaEnable(secret, code.trim()); notify("✅ Двухфакторная аутентификация включена. Потребуется повторный вход."); setSecret(""); setUri(""); setCode(""); loadStatus(); reload(); }
    catch (e) { notify(/400/.test(String(e)) ? "Неверный код — попробуйте ещё раз" : String(e), true); }
    finally { setBusy(false); }
  }
  async function disable() {
    const c = prompt("Введите текущий код из приложения, чтобы отключить 2FA:");
    if (!c) return;
    setBusy(true);
    try { await api.twofaDisable(c.trim()); notify("2FA отключена"); loadStatus(); reload(); }
    catch (e) { notify(/400/.test(String(e)) ? "Неверный код" : String(e), true); }
    finally { setBusy(false); }
  }

  return (
    <div className="page-stack">
      <div className="prov-grid">
        {/* 2FA */}
        <div className="panel">
          <div className="panel-title sm">
            <span className="ms sm">shield</span> Двухфакторная аутентификация
            {enabled !== null && <span className={"pill spacer " + (enabled ? "ok" : required ? "danger" : "muted")}>{enabled ? "включена" : required ? "обязательна, выключена" : "выключена"}</span>}
          </div>

          {enabled === null ? <SkeletonGrid rows={2} /> : enabled === false && !secret ? (
            <>
              <p className="cfg-hint">TOTP-код из приложения-аутентификатора (Google Authenticator, 1Password, Aegis и т.п.) в дополнение к паролю. {required && "Ваша роль требует включённой 2FA."}</p>
              <button className="btn" onClick={startSetup} style={{ marginTop: "var(--sp-2)" }}><span className="ms sm">add_moderator</span> Включить 2FA</button>
            </>
          ) : enabled === false && secret ? (
            <div className="page-stack" style={{ gap: "var(--sp-3)" }}>
              <div className="cfg-field">
                <span className="cfg-cap">1. Добавьте секрет в приложение-аутентификатор (вводится вручную — мы не отправляем его сторонним QR-сервисам):</span>
                <div className="loc-source" style={{ wordBreak: "break-all", fontFamily: "ui-monospace, monospace" }}>{secret}</div>
                <p className="cfg-hint" style={{ wordBreak: "break-all", marginTop: 4 }}>otpauth: {uri}</p>
              </div>
              <div className="cfg-field">
                <span className="cfg-cap">2. Введите 6-значный код из приложения:</span>
                <div className="form-row" style={{ gap: "var(--sp-2)", margin: 0 }}>
                  {/* FIX: AUDIT12-M13/M14 - aria-label + maxLength 6 on backup code. */}
                  <input style={{ width: 160, letterSpacing: 4, fontFamily: "ui-monospace, monospace" }} placeholder="123 456" inputMode="numeric" value={code} onChange={(e) => setCode(e.target.value.replace(/[^0-9]/g, "").slice(0, 6))} maxLength={6} aria-label="Резервный код" />
                  <button className="btn" disabled={code.trim().length < 6 || busy} onClick={enable}><span className="ms sm">check</span> Подтвердить</button>
                  <button className="btn ghost" onClick={() => { setSecret(""); setUri(""); setCode(""); }}>Отмена</button>
                </div>
              </div>
            </div>
          ) : (
            <>
              <p className="cfg-hint">Второй фактор активен. Отключение потребует текущий код из приложения.</p>
              <div className="form-row" style={{ marginTop: "var(--sp-2)" }}>
                <button className="btn danger" disabled={busy} onClick={disable}><span className="ms sm">remove_moderator</span> Отключить 2FA</button>
              </div>
            </>
          )}
        </div>

        {/* Account / password */}
        <div className="panel">
          <div className="panel-title sm"><span className="ms sm">account_circle</span> Учётная запись</div>
          {ov ? (
            <div className="form-grid" style={{ marginTop: "var(--sp-2)" }}>
              <KV k="Email" v={ov.self.email} />
              <KV k="Роль" v={<span className={"pill " + (ROLE_CLS[ov.self.role] ?? "muted")}>{ov.self.role}</span>} />
              <KV k="Статус" v={ov.self.is_active ? <span className="pill ok">активен</span> : <span className="pill danger">отключён</span>} />
              <KV k="Хеш пароля" v={<span className="pill ok">{ov.policy.password_algo}</span>} />
              <KV k="Последний вход" v={ago(ov.self.last_login)} />
              <KV k="Аккаунт обновлён" v={ago(ov.self.updated_at)} />
            </div>
          ) : <SkeletonGrid rows={2} />}
          <ChangePassword notify={notify} />
          <GatedNote>Расширенная политика паролей (минимальный регистр/спецсимволы, история запрета повтора, истечение срока) и точная дата последней смены требуют расширения admin_users. Базовая смена пароля выше работает: argon2id + ревокация всех сессий.</GatedNote>
        </div>
      </div>

      <GatedCard icon="vpn_key" title="Резервные коды и аппаратные ключи"
        text="Backup-коды (генерация/скачивание/счётчик), Passkeys и WebAuthn (YubiKey, Titan, Windows Hello, Touch ID, Face ID) требуют отдельных таблиц регистраций и серверного WebAuthn. Текущий второй фактор — TOTP выше." />
    </div>
  );
}

// ---- self-service password change (argon2id + revoke-all on the backend) ----
function ChangePassword({ notify }: { notify: (m: string, e?: boolean) => void }) {
  const [open, setOpen] = useState(false);
  const [cur, setCur] = useState("");
  const [nw, setNw] = useState("");
  const [conf, setConf] = useState("");
  const [busy, setBusy] = useState(false);
  const [show, setShow] = useState(false);
  const tooShort = nw.length > 0 && nw.length < 8;
  const mismatch = conf.length > 0 && nw !== conf;
  const sameAsOld = nw.length > 0 && nw === cur;
  const valid = cur.length >= 1 && nw.length >= 8 && nw === conf && nw !== cur;

  async function submit() {
    if (!valid) return;
    setBusy(true);
    try {
      await api.changePassword(cur, nw);
      notify("✅ Пароль изменён. Все сессии завершены — сейчас потребуется повторный вход.");
      setTimeout(() => location.reload(), 1600);
    } catch (e) {
      notify(/400/.test(String(e))
        ? "Неверный текущий пароль (или новый не отличается / короче 8 символов)"
        : String(e), true);
      setBusy(false);
    }
  }

  if (!open) {
    return (
      <div style={{ marginTop: "var(--sp-3)" }}>
        <button className="btn ghost sm" onClick={() => setOpen(true)}><span className="ms sm">key</span> Сменить пароль</button>
      </div>
    );
  }
  return (
    <div className="cfg-field" style={{ marginTop: "var(--sp-3)" }}>
      <span className="cfg-cap"><span className="ms sm" style={{ verticalAlign: "-3px" }}>key</span> Смена пароля</span>
      <div className="page-stack" style={{ gap: "var(--sp-2)", marginTop: 4 }}>
        {/* FIX: AUDIT12-M13/M14 - aria-label + maxLength 128 on current password. */}
        <input type={show ? "text" : "password"} placeholder="Текущий пароль" autoComplete="current-password" value={cur} onChange={(e) => setCur(e.target.value)} maxLength={128} aria-label="Текущий пароль" />
        {/* FIX: AUDIT12-M13/M14 - aria-label + maxLength 128 on new password. */}
        <input type={show ? "text" : "password"} placeholder="Новый пароль (мин. 8 символов)" autoComplete="new-password" value={nw} onChange={(e) => setNw(e.target.value)} maxLength={128} aria-label="Новый пароль" />
        {/* FIX: AUDIT12-M13/M14 - aria-label + maxLength 128 on confirm password. */}
        <input type={show ? "text" : "password"} placeholder="Повторите новый пароль" autoComplete="new-password" value={conf} onChange={(e) => setConf(e.target.value)} maxLength={128} aria-label="Повторите новый пароль" />
        {tooShort && <span className="cfg-hint" style={{ color: "var(--danger)" }}>Минимум 8 символов</span>}
        {mismatch && <span className="cfg-hint" style={{ color: "var(--danger)" }}>Пароли не совпадают</span>}
        {sameAsOld && <span className="cfg-hint" style={{ color: "var(--danger)" }}>Новый пароль должен отличаться от текущего</span>}
        <div className="form-row" style={{ gap: "var(--sp-2)", margin: 0, alignItems: "center" }}>
          <button className="btn" disabled={!valid || busy} onClick={submit}><span className="ms sm">{busy ? "hourglass_top" : "check"}</span> {busy ? "Меняем…" : "Изменить пароль"}</button>
          <button className="btn ghost" onClick={() => { setOpen(false); setCur(""); setNw(""); setConf(""); }}>Отмена</button>
          <button className="btn ghost sm" onClick={() => setShow((s) => !s)} title="Показать/скрыть"><span className="ms sm">{show ? "visibility_off" : "visibility"}</span></button>
        </div>
      </div>
    </div>
  );
}

// ================= Access / permissions =================
interface Area { id: string; label: string; icon: string; read: number; manage: number; note?: string }
const AREAS: Area[] = [
  { id: "users", label: "Пользователи", icon: "group", read: 2, manage: 3, note: "модерация — moderator+" },
  { id: "payments", label: "Платежи / возвраты", icon: "payments", read: 3, manage: 3 },
  { id: "providers", label: "AI-провайдеры", icon: "hub", read: 3, manage: 3, note: "ключи провайдеров — superadmin" },
  { id: "ai", label: "AI-маршрутизация", icon: "smart_toy", read: 3, manage: 3, note: "base_url — superadmin" },
  { id: "localization", label: "Локализация", icon: "translate", read: 3, manage: 3 },
  { id: "settings", label: "Настройки / цены / флаги", icon: "tune", read: 3, manage: 4 },
  { id: "audit", label: "Аудит-лог", icon: "receipt_long", read: 3, manage: 3, note: "только чтение" },
  { id: "maintenance", label: "Обслуживание", icon: "build", read: 3, manage: 4, note: "VACUUM/бэкап/flush — superadmin" },
  { id: "security", label: "IAM / администраторы", icon: "admin_panel_settings", read: 4, manage: 4 },
];
const ROLE_NAMES = ["support", "moderator", "admin", "superadmin"];

function AccessTab({ ov }: { ov: SecurityOverview | null }) {
  if (!ov) return <SkeletonGrid />;
  const rank = ov.self.role_rank;
  const level = (a: Area) => rank >= a.manage ? { label: "Полный", cls: "ok" } : rank >= a.read ? { label: "Чтение", cls: "warn" } : { label: "Нет", cls: "muted" };
  const fullCount = AREAS.filter((a) => rank >= a.manage).length;

  return (
    <div className="page-stack">
      <div className="prov-grid" style={{ gridTemplateColumns: "minmax(220px, 280px) 1fr" }}>
        <div className="panel">
          <div className="panel-title sm"><span className="ms sm">badge</span> Роль</div>
          <div className="form-grid" style={{ marginTop: "var(--sp-2)" }}>
            <KV k="Роль" v={<span className={"pill " + (ROLE_CLS[ov.self.role] ?? "muted")}>{ov.self.role}</span>} />
            <KV k="Ранг" v={`${rank} / 4`} />
            <KV k="Полный доступ к" v={`${fullCount}/${AREAS.length} разделов`} />
            <KV k="Создана" v={ov.self.created_at ? fmtDate(ov.self.created_at) : "—"} />
          </div>
          <p className="cfg-hint" style={{ marginTop: "var(--sp-2)" }}>Иерархия рангов: support(1) → moderator(2) → admin(3) → superadmin(4). Роль удовлетворяет требованию равного или меньшего ранга (наследование прав), плюс точное совпадение.</p>
        </div>

        <div className="panel">
          <div className="panel-title sm"><span className="ms sm">grid_view</span> Матрица прав (по рангу роли)</div>
          <div className="table-wrap sticky" tabIndex={0} style={{ border: "none" }}>
            <table className="tbl">
              <thead><tr><th>Раздел</th><th>Чтение с</th><th>Управление с</th><th>Ваш доступ</th></tr></thead>
              <tbody>
                {AREAS.map((a) => {
                  const lv = level(a);
                  return (
                    <tr key={a.id}>
                      <td><span className="ms sm" style={{ verticalAlign: "-3px", marginRight: 6, color: "var(--hint)" }}>{a.icon}</span><b>{a.label}</b>{a.note && <div className="muted" style={{ fontSize: 11, marginLeft: 26 }}>{a.note}</div>}</td>
                      <td><span className={"pill " + (ROLE_CLS[ROLE_NAMES[a.read - 1]] ?? "muted")} style={{ fontSize: 10 }}>{ROLE_NAMES[a.read - 1]}</span></td>
                      <td><span className={"pill " + (ROLE_CLS[ROLE_NAMES[a.manage - 1]] ?? "muted")} style={{ fontSize: 10 }}>{ROLE_NAMES[a.manage - 1]}</span></td>
                      <td><span className={"pill " + lv.cls}>{lv.label}</span></td>
                    </tr>
                  );
                })}
              </tbody>
            </table>
          </div>
        </div>
      </div>

      {/* Org by-role */}
      <div className="panel">
        <div className="panel-title sm"><span className="ms sm">groups</span> Администраторы по ролям</div>
        <div className="chip-row" style={{ marginTop: "var(--sp-2)" }}>
          {ROLE_NAMES.slice().reverse().map((r) => (
            <span key={r} className="chip"><span className={"pill " + (ROLE_CLS[r] ?? "muted")} style={{ fontSize: 10 }}>{r}</span><b>{fmtInt(ov.org.by_role[r] ?? 0)}</b></span>
          ))}
          <span className="chip"><span className="muted">всего</span><b>{fmtInt(ov.org.admins_total)}</b></span>
          <span className="chip"><span className="muted">с 2FA</span><b>{fmtInt(ov.org.with_2fa)}</b></span>
        </div>
        <p className="cfg-hint" style={{ marginTop: "var(--sp-2)" }}>Управление администраторами, ролями и сбросом 2FA — в разделе «Администраторы» (IAM). Матрица выше отражает реальные require_role-ограничения бэкенда.</p>
      </div>
    </div>
  );
}

// ================= Events =================
const DESTRUCTIVE = ["delete", "clear", "revoke", "disable", "flush"];
function evSeverity(action: string): { cls: string; icon: string } {
  const a = action.toLowerCase(); const v = a.split(".").pop() || "";
  if (a.startsWith("admin.") || /2fa|password|login/.test(a)) return { cls: "danger", icon: "shield" };
  if (DESTRUCTIVE.some((d) => v.startsWith(d))) return { cls: "warn", icon: "warning" };
  return { cls: "pro", icon: "bolt" };
}

function EventsTab({ ov }: { ov: SecurityOverview | null }) {
  if (!ov) return <SkeletonGrid />;
  return (
    <div className="page-stack">
      <div className="panel">
        <div className="section-head" style={{ margin: 0, marginBottom: "var(--sp-3)" }}>
          <div className="panel-title sm" style={{ margin: 0 }}><span className="ms sm">timeline</span> Журнал событий безопасности</div>
          <span className="muted" style={{ fontSize: 11 }}>admin.* · 2FA · ключи · флаги · доступ</span>
        </div>
        {ov.events.length === 0 ? (
          <EmptyState icon="shield_moon" title="Событий безопасности нет" desc="За последнее время чувствительных действий не зафиксировано." />
        ) : (
          <div className="page-stack" style={{ gap: 0 }}>
            {ov.events.map((e) => {
              const sv = evSeverity(e.action);
              return (
                <div key={e.id} className="audit-tl" style={{ cursor: "default" }}>
                  <span className={"audit-tl-dot " + sv.cls}><span className="ms sm">{sv.icon}</span></span>
                  <span style={{ minWidth: 0, flex: 1 }}>
                    <span className="form-row" style={{ margin: 0, gap: 8, alignItems: "center" }}>
                      <span className="code-key" style={{ fontSize: 12 }}>{e.action}</span>
                      {e.target_type && <span className="pill muted" style={{ fontSize: 9 }}>{e.target_type}:{e.target_id ?? ""}</span>}
                    </span>
                    <span className="muted" style={{ fontSize: 11.5 }}>{e.admin_email ?? `#${e.admin_id}`}{e.ip ? ` · ${e.ip}` : ""}</span>
                  </span>
                  <span className="muted" style={{ fontSize: 11, whiteSpace: "nowrap" }}>{ago(e.created_at)}</span>
                </div>
              );
            })}
          </div>
        )}
        <p className="cfg-hint" style={{ marginTop: "var(--sp-3)" }}><span className="ms sm" style={{ verticalAlign: "-3px" }}>info</span> Полный журнал, фильтры, diff изменений и экспорт — в разделе «Аудит-центр». Здесь показаны последние события, относящиеся к безопасности.</p>
      </div>

      <GatedCard icon="notifications_active" title="Алерты безопасности в реальном времени"
        text="Push-уведомления о событиях (новый вход, отключена 2FA, изменён пароль, создан/удалён администратор, новые права, новое устройство) требуют event-шины и каналов доставки. События уже фиксируются в аудите и показаны выше." />
    </div>
  );
}

// ================= shared =================
function ScoreRing({ score, color }: { score: number; color: string }) {
  const deg = Math.round(score / 100 * 360);
  return (
    <div style={{ position: "relative", width: 170, height: 170, borderRadius: "50%", background: `conic-gradient(${color} ${deg}deg, var(--panel-2) ${deg}deg)`, display: "grid", placeItems: "center" }}>
      <div style={{ position: "absolute", inset: 14, borderRadius: "50%", background: "var(--panel)", display: "grid", placeItems: "center" }}>
        <div style={{ textAlign: "center" }}>
          <div style={{ fontSize: 40, fontWeight: 800, lineHeight: 1, color }}>{score}</div>
          <div className="muted" style={{ fontSize: 12 }}>из 100</div>
        </div>
      </div>
    </div>
  );
}
function LimitedHint({ go }: { go: () => void }) {
  return (
    <div className="panel">
      <EmptyState icon="lock" title="Раздел доступен роли admin и выше" desc="Полный обзор безопасности, права и события требуют роли admin. Управление своей 2FA доступно во вкладке «Аутентификация»." />
      <div style={{ display: "flex", justifyContent: "center" }}><button className="btn" onClick={go}><span className="ms sm">password</span> К моей 2FA</button></div>
    </div>
  );
}
function PostureCard({ title, icon, ok, dim, children }: { title: string; icon: string; ok: boolean; dim?: string; children: React.ReactNode }) {
  return (
    <div className="prov-card">
      <div className="pc-head">
        <span className="prov-logo"><span className="ms">{icon}</span></span>
        <div style={{ minWidth: 0 }}>
          <div className="pc-name">{title}</div>
          <div className="pc-vendor" style={{ display: "flex", alignItems: "center", gap: 5 }}>
            <span className="status-dot" style={{ background: ok ? "var(--ok)" : "var(--danger)" }} />{dim}
          </div>
        </div>
      </div>
      <div className="page-stack" style={{ gap: 6 }}>{children}</div>
    </div>
  );
}
function KV({ k, v }: { k: string; v: React.ReactNode }) {
  return <div className="form-row" style={{ justifyContent: "space-between", margin: 0, fontSize: 13 }}><span className="muted">{k}</span><span style={{ fontWeight: 600, textAlign: "right" }}>{v}</span></div>;
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
function GatedNote({ children }: { children: React.ReactNode }) {
  return <p className="cfg-hint" style={{ marginTop: "var(--sp-3)", display: "flex", gap: 6 }}><span className="ms sm" style={{ flex: "0 0 auto" }}>info</span><span>{children}</span></p>;
}
function GatedCard({ icon, title, text }: { icon: string; title: string; text: string }) {
  return (
    <div className="prov-card off">
      <div className="pc-head"><span className="prov-logo"><span className="ms">{icon}</span></span><div className="pc-name">{title} <span className="pill muted" style={{ marginLeft: 4, fontSize: 10 }}>требует расширения схемы</span></div></div>
      <p className="pc-desc">{text}</p>
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
function SkeletonGrid({ rows = 4 }: { rows?: number }) {
  return <div className="page-stack">{Array.from({ length: rows }).map((_, i) => <div key={i} className="skeleton" style={{ height: 64 }} />)}</div>;
}
