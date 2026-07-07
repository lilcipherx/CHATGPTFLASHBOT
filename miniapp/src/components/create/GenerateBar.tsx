import WebApp from "@twa-dev/sdk";
import { EffectKind } from "../../api/client";
import { t } from "../../i18n";

export type Phase = "config" | "running" | "done" | "error";

/**
 * Create Media — панель генерации (§8, §9 ТЗ). Держит все визуальные состояния
 * основного действия:
 *  - config  → строка стоимости + большая кнопка «Создать N✨» (стоимость
 *              пересчитывается контейнером при смене модели/настроек);
 *  - running → лейбл статуса + прогресс-бар;
 *  - error   → баннер ошибки (форма выше сохранена для повтора);
 *  - done    → превью результата + Скачать / Поделиться / Создать ещё.
 * Использует обычную DOM-кнопку (не нативный Telegram MainButton), т.к. страница
 * живёт как вкладка с постоянной нижней навигацией.
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

  if (phase === "done" && resultUrl) {
    return (
      <div className="gen-result">
        {kind === "video"
          ? <video className="preview" src={resultUrl} controls autoPlay loop muted />
          : <img className="preview" src={resultUrl} alt="result" />}
        <button className="btn" onClick={download}>{t("download")}</button>
        <button className="btn secondary" onClick={share}>{t("share")}</button>
        <button className="btn secondary" onClick={onReset}>{t("create_more")}</button>
      </div>
    );
  }

  return (
    <div className="gen-bar">
      {phase === "error" && <div className="error-banner">{error}</div>}
      {phase === "running" && (
        <div className="gen-progress">
          <div className="gen-progress-label"><span className="spinner" /> {status} · {progress}%</div>
          <div className="progress"><i style={{ width: `${progress}%` }} /></div>
        </div>
      )}
      <div className="cost-bar">
        {t("cost")} <b>{cost}✨</b>
        {balance !== null && <span className="muted"> · {t("balance")} {balance}✨</span>}
      </div>
      <button
        className="btn gen-cta"
        disabled={phase === "running" || !canGenerate}
        onClick={onGenerate}
      >
        {phase === "running" ? (status || t("generating")) : `${t("generate")} ${cost}✨`}
      </button>
    </div>
  );
}
