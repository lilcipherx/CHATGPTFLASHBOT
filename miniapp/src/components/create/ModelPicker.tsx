import { FreeModel } from "../../api/client";
import { t } from "../../i18n";
import { haptic } from "../../theme";

/**
 * Create Media — прямой выбор AI-модели (§6 ТЗ, variant 3). В отличие от
 * PresetPicker (кураторские стили-эффекты) здесь пользователь выбирает саму
 * модель (Seedance/Veo/Kling/Flux…) из каталога бэкенда `/api/models`. Каждая
 * модель несёт свою карточку настроек и базовую цену. Презентационный.
 */
export function ModelPicker({
  models, loading, selectedKey, onPick,
}: {
  models: FreeModel[] | null;
  loading: boolean;
  selectedKey: string | null;
  onPick: (m: FreeModel) => void;
}) {
  return (
    <div>
      <div className="section-title">{t("models_label")}</div>
      {loading || models === null ? (
        <div className="preset-row" aria-busy="true">
          {Array.from({ length: 4 }).map((_, i) => (
            <div key={i} className="preset-tile">
              <span className="preset-thumb skeleton" />
              <span className="skeleton sk-line" />
            </div>
          ))}
        </div>
      ) : models.length === 0 ? (
        <div className="muted hint">{t("empty_cat")}</div>
      ) : (
        <div className="preset-row">
          {models.map((m) => (
            <button
              key={m.key}
              className={`preset-tile ${selectedKey === m.key ? "on" : ""}`}
              aria-pressed={selectedKey === m.key}
              title={m.description}
              onClick={() => { haptic(); onPick(m); }}
            >
              <span className="preset-thumb">
                <span className="preset-thumb-fallback">{m.kind === "video" ? "🎬" : "🎨"}</span>
                <span className="preset-badge">{m.price}✨</span>
              </span>
              <span className="preset-name">{m.title}</span>
            </button>
          ))}
        </div>
      )}
    </div>
  );
}
