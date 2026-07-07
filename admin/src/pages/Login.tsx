import { useRef, useState } from "react";
import { api, login } from "../api";

type Stage = "creds" | "enroll";

export function Login({ onAuthed }: { onAuthed: () => void }) {
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [otp, setOtp] = useState("");
  const [needOtp, setNeedOtp] = useState(false);
  const [error, setError] = useState("");
  const [busy, setBusy] = useState(false);
  const [failCount, setFailCount] = useState(0);  // FIX: AUDIT-84
  const [lockUntil, setLockUntil] = useState(0);
  // Synchronous re-entry guard (a ref, not state) so a rapid double submit can't
  // slip a second request through before React re-renders the disabled button.
  const inFlight = useRef(false);

  // Mandatory-2FA enrollment (§8): a privileged role logged in with the right
  // password but no enrolled secret. The session is restricted to setup until done.
  const [stage, setStage] = useState<Stage>("creds");
  const [secret, setSecret] = useState("");
  const [uri, setUri] = useState("");
  const [enrollCode, setEnrollCode] = useState("");
  const [info, setInfo] = useState("");

  async function startEnrollment() {
    try {
      const r = await api.twofaSetup();
      setSecret(r.secret);
      setUri(r.uri);
      setStage("enroll");
      setError("");
      setInfo("Для вашей роли 2FA обязательна. Добавьте секрет в приложение-аутентификатор и подтвердите кодом.");
    } catch {
      setError("Не удалось начать настройку 2FA. Попробуйте войти снова.");
    }
  }

  async function submit(e: React.FormEvent) {
    e.preventDefault();
    if (inFlight.current) return;
    if (Date.now() < lockUntil) { setError("Слишком много попыток. Подождите 30 секунд."); return; }  // ignore a double submit while a login is in flight
    inFlight.current = true;
    setBusy(true);
    setError("");
    try {
      const { mfaSetup } = await login(email, password, needOtp ? otp : undefined);
      if (mfaSetup) {
        await startEnrollment();
        return;
      }
      onAuthed();
    } catch (err) {
      // FIX: AUDIT-84 - increment fail count for client-side rate limiting
      const newCount = failCount + 1;
      setFailCount(newCount);
      if (newCount >= 5) { setLockUntil(Date.now() + 30000); setFailCount(0); }
      const msg = err instanceof Error ? err.message : String(err);
      // FIX: AUDIT-6 - anti-enumeration: treat otp_required and otp_invalid identically
      if (msg === "otp_required" || msg === "otp_invalid") {
        setNeedOtp(true);
        setError("Введите код двухфакторной аутентификации");
      } else {
        setError("Неверный email или пароль");
      }
    } finally {
      inFlight.current = false;
      setBusy(false);
    }
  }

  async function confirmEnrollment(e: React.FormEvent) {
    e.preventDefault();
    if (inFlight.current) return;
    inFlight.current = true;
    setBusy(true);
    setError("");
    try {
      await api.twofaEnable(secret, enrollCode.trim());
      // Session was invalidated server-side; return to login for a full sign-in.
      setStage("creds");
      setNeedOtp(true);
      setSecret("");
      setUri("");
      setEnrollCode("");
      setOtp("");
      setPassword("");
      setInfo("");
      setError("2FA включена. Войдите снова, указав код из приложения.");
    } catch (err) {
      const msg = err instanceof Error ? err.message : String(err);
      setError(msg === "code_invalid" ? "Неверный код, попробуйте ещё раз" : "Ошибка подтверждения 2FA");
    } finally {
      inFlight.current = false;
      setBusy(false);
    }
  }

  if (stage === "enroll") {
    return (
      <div className="login-wrap">
        <form onSubmit={confirmEnrollment} className="login-card">
          <h1><span className="dot" /> Настройка 2FA</h1>
          <p className="sub">Обязательная двухфакторная аутентификация</p>
          {info && <p className="muted" style={{ fontSize: 13 }}>{info}</p>}
          <label>Секрет (введите вручную в Google Authenticator / 1Password)</label>
          {/* FIX: AUDIT12-M13/M14 - aria-label + maxLength 128 on 2FA secret field. */}
          <input value={secret} readOnly aria-label="Секрет 2FA" onFocus={(ev) => ev.target.select()} maxLength={128} />
          {uri && (
            <p className="muted" style={{ fontSize: 11, wordBreak: "break-all" }}>{uri}</p>
          )}
          <label>Код из приложения</label>
          {/* FIX: AUDIT12-M14 - maxLength 6 (OTP codes are 6 digits). */}
          <input placeholder="123456" value={enrollCode} onChange={(e) => setEnrollCode(e.target.value)} inputMode="numeric" maxLength={6} aria-label="Код из приложения-аутентификатора" autoFocus />
          <button type="submit" className="btn" disabled={busy}>{busy ? "Подтверждение…" : "Включить и продолжить"}</button>
          {error && <p className="err">{error}</p>}
        </form>
      </div>
    );
  }

  return (
    <div className="login-wrap">
      <form onSubmit={submit} className="login-card">
        <h1><span className="dot" /> ИИ Бот №1</h1>
        <p className="sub">Панель администратора</p>
        <label>Email</label>
        {/* FIX: AUDIT12-M13/M14 - aria-label + maxLength 254 (RFC 5321 max email length). */}
        <input placeholder="admin@example.com" value={email} onChange={(e) => setEmail(e.target.value)}
          type="email" autoComplete="username" autoCapitalize="none" autoCorrect="off" spellCheck={false}
          maxLength={254} aria-label="Email" />
        <label>Пароль</label>
        {/* FIX: AUDIT12-M14 - maxLength 128 (server cap on credential length). */}
        <input placeholder="••••••••" type="password" value={password} onChange={(e) => setPassword(e.target.value)} autoComplete="current-password" maxLength={128} aria-label="Пароль" />
        {needOtp && (
          <>
            <label>Код 2FA</label>
            {/* FIX: AUDIT12-M14 - maxLength 6 (OTP codes are 6 digits). */}
            <input placeholder="123456" value={otp} onChange={(e) => setOtp(e.target.value)}
              inputMode="numeric" maxLength={6} aria-label="Код двухфакторной аутентификации" autoFocus />
          </>
        )}
        <button type="submit" className="btn" disabled={busy}>{busy ? "Вход…" : "Войти"}</button>
        {info && <p className="muted">{info}</p>}
        {error && <p className="err">{error}</p>}
      </form>
    </div>
  );
}
