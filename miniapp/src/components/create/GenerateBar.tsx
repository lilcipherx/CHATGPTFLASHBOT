import WebApp from "@twa-dev/sdk";
import { EffectKind } from "../../api/client";
import { t } from "../../i18n";

export type Phase = "config" | "running" | "done" | "error";

/**
 * Create Media — панель генерации (§8, §9 ТЗ). Редизайн ключевого флоу (Вариант A):
 *  - config  → ЛИПКИЙ нижний футер: строка стоимости/баланса + крупная CTA. Когда
 *              баланса не хватает — CTA превращается в предупреждение (не молчаливый
 *              disabled), чтобы причина была очевидна;
 *  - running → тот же липкий футер с ПОШАГОВЫМ прогрессом (Загрузка → Очередь →
 *              Генерация) поверх линейной полосы, чтобы ожидание читалось как этапы;
 *  - error   → баннер ошибки над CTA (форма выше сохранена для повтора);
 *  - done    → «геройский» крупный показ результата + Скачать / Ещё / Поделиться.
 * Обычная DOM-кнопка (не нативный Telegram MainButton): страница живёт как вкладка с
 * постоянной нижней навигацией. Контракт props НЕ изменён — оркестратор не трогаем.
 */
export function GenerateBar({
  phase, kind, cost, balance, progress, status, error, resultUrl,
  canGenerate, onGenerate, onReset,
}: {
  phase: Phase;
  kind: EffectKind;
  cost: number;
  balance: number | null;
  progress: number;
  status: string;
  error: string;
  resultUrl: string | null;
  canGenerate: boolean;
  onGenerate: () => void;
  onReset: () => void;
}) {
  function download() {
    if (!resultUrl) return;
    const name = `result.${kind === "video" ? "mp4" : "jpg"}`;
    const dl = (WebApp as unknown as {
      downloadFile?: (p: { url: string; file_name: string }) => void;
    }).downloadFile;
    if (dl) dl({ url: resultUrl, file_name: name });
    else WebApp.openLink(resultUrl);
  }
  function share() { if (resultUrl) WebApp.openLink(resultUrl); }

  // done → hero reveal (not sticky; it's the payoff, viewed in place).
  if (phase === "done" && resultUrl) {
    return (
      <div className="gen-result">
        <div className="gen-hero">
          {kind === "video"
            ? <video className="preview" src={resultUrl} controls autoPlay loop muted playsInline />
            : <img className="preview" src={resultUrl} alt="result" />}
        </div>
        <button className="btn accent" onClick={download}>{t("download")}</button>
        <div className="btn-row">
          <button className="btn secondary" onClick={onReset}>{t("create_more")}</button>
          <button className="btn secondary" onClick={share}>{t("share")}</button>
        </div>
      </div>
    );
  }

  // Insufficient balance: surface the reason instead of a silent disabled button.
  const insufficient = balance !== null && cost > 0 && balance < cost;
  const running = phase === "running";

  // Stepped progress: map the container's status string to the active stage. The
  // container drives status via t("uploading") → t("queued")/t("generating").
  const steps = [t("uploading"), t("queued"), t("generating")];
  const active = status === t("queued") ? 1 : status === t("generating") ? 2 : 0;

  return (
    <div className="gen-bar">
      {phase === "error" && <div className="error-banner">{error}</div>}

      {running && (
        <div className="gen-progress">
          <div className="gen-steps" aria-hidden="true">
            {steps.map((label, i) => (
              <div
                key={i}
                className={`gen-step ${i < active ? "done" : i === active ? "active" : "pending"}`}
              >
                <span className="gen-step-dot" />
                <span className="gen-step-label">{label}</span>
              </div>
            ))}
          </div>
          <div className="progress" role="progressbar" aria-valuenow={progress} aria-valuemin={0} aria-valuemax={100}>
            <i style={{ width: `${progress}%` }} />
          </div>
        </div>
      )}

      <div className="gen-cost">
        <span>{t("cost")} <b>{cost}✨</b></span>
        {balance !== null && (
          <span className={`gen-balance ${insufficient ? "low" : ""}`}>
            {t("balance")} {balance}✨
          </span>
        )}
      </div>

      <button
        className={`btn gen-cta ${insufficient && !running ? "warn" : "accent"}`}
        disabled={running || !canGenerate || insufficient}
        onClick={onGenerate}
      >
        {running
          ? (status || t("generating")) + (progress ? ` · ${progress}%` : "")
          : insufficient
            ? t("err_limit")
            : `${t("generate")} ${cost}✨`}
      </button>
    </div>
  );
}
