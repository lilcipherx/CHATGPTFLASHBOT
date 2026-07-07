import { RefObject, useState } from "react";
import { t } from "../../i18n";
import { haptic } from "../../theme";
import { PROMPT_TEMPLATES } from "./templates";

/**
 * Create Media — главное текстовое поле (§3) + шаблоны (§11) + negative prompt (§13).
 *  - textarea: длинный текст и переносы строк; «*» когда промпт обязателен;
 *  - инструменты: «Элементы» (§4) и @image-ссылки (§3) — вставка в позицию курсора;
 *  - быстрые шаблоны (§11): стартовые заготовки в один тап;
 *  - negative prompt (§13): сворачиваемое поле «чего избегать».
 * Скрывается целиком, когда пресет не принимает промпт (`mode === "hidden"`).
 */
export function PromptSection({
  value, mode, onChange, textareaRef, refs, negative, onNegative, onInsert, onOpenElements,
}: {
  value: string;
  mode: "hidden" | "optional" | "required";
  onChange: (v: string) => void;
  textareaRef: RefObject<HTMLTextAreaElement>;
  refs: string[];
  negative: string;
  onNegative: (v: string) => void;
  onInsert: (text: string) => void;
  onOpenElements: () => void;
}) {
  const [showNeg, setShowNeg] = useState(false);
  if (mode === "hidden") return null;
  return (
    <div>
      <div className="section-title">{t("prompt")}{mode === "required" ? " *" : ""}</div>
      <textarea
        ref={textareaRef}
        className="prompt-input"
        rows={3}
        value={value}
        placeholder={t("prompt_ph")}
        onChange={(e) => onChange(e.target.value)}
      />

      <div className="prompt-tools">
        <button className="btn-sm" title={t("elements")} onClick={onOpenElements}>✨ {t("elements")}</button>
        {refs.map((r) => (
          <button key={r} className="btn-sm ref-chip" title={r} onClick={() => onInsert(r)}>{r}</button>
        ))}
      </div>

      <div className="tpl-row">
        <span className="tpl-label">{t("templates")}</span>
        {PROMPT_TEMPLATES.map((tpl) => (
          <button key={tpl.label} className="btn-sm tpl-chip" title={tpl.text}
            onClick={() => { haptic(); onInsert(tpl.text); }}>
            {tpl.label}
          </button>
        ))}
      </div>

      <button className="neg-toggle" aria-expanded={showNeg}
        onClick={() => { haptic(); setShowNeg((v) => !v); }}>
        {showNeg ? "−" : "+"} {t("negative")}
      </button>
      {showNeg && (
        <textarea
          className="prompt-input neg-input"
          rows={2}
          value={negative}
          placeholder={t("negative_ph")}
          onChange={(e) => onNegative(e.target.value)}
        />
      )}
    </div>
  );
}
