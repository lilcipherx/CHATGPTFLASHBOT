import { EffectKind } from "../../api/client";
import { t } from "../../i18n";
import { haptic } from "../../theme";

/**
 * Create Media — режим генерации (Image / Video). Модуль §1 ТЗ.
 * Показывает только те режимы, для которых у пользователя есть рабочий провайдер
 * (`available`); при единственном доступном режиме переключатель скрыт.
 * Презентационный: состояние и загрузка каталога живут в CreatePage.
 */
export function ModeSwitch({
  mode, available, onMode,
}: {
  mode: EffectKind;
  available: EffectKind[];
  onMode: (m: EffectKind) => void;
}) {
  if (available.length < 2) return null;
  return (
    <div className="segmented" role="tablist" aria-label={t("mode")}>
      {available.map((m) => (
        <button
          key={m}
          role="tab"
          aria-selected={mode === m}
          className={`seg ${mode === m ? "active" : ""}`}
          onClick={() => { haptic(); onMode(m); }}
        >
          {t(m === "video" ? "seg_video" : "seg_photo")}
        </button>
      ))}
    </div>
  );
}
