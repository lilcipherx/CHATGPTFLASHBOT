import { EffectSummary, mediaUrl } from "../../api/client";
import { t } from "../../i18n";
import { haptic } from "../../theme";

/**
 * Create Media — выбор стиля/модели (§6 ТЗ). В варианте «через текущий API»
 * доступные модели предоставляются бэкендом как пресеты (эффекты) выбранного
 * режима; выбор пресета определяет модель, настройки и стоимость генерации.
 * Горизонтальная лента карточек-превью; выбранная подсвечена акцентом.
 * Расширяемо: панель легко заменить на полноценную сетку с LoRA/ControlNet-табами.
 */
export function PresetPicker({
  presets, loading, selectedId, onPick,
}: {
  presets: EffectSummary[] | null;
  loading: boolean;
  selectedId: number | null;
  onPick: (p: EffectSummary) => void;
}) {
  return (
    <div>
      <div className="section-title">{t("create_style")}</div>
      {loading || presets === null ? (
        <div className="preset-row" aria-busy="true">
          {Array.from({ length: 4 }).map((_, i) => (
            <div key={i} className="preset-tile">
              <span className="preset-thumb skeleton" />
              <span className="skeleton sk-line" />
            </div>
          ))}
        </div>
      ) : presets.length === 0 ? (
        <div className="muted hint">{t("empty_cat")}</div>
      ) : (
        <div className="preset-row">
          {presets.map((p) => (
            <button
              key={p.id}
              className={`preset-tile ${selectedId === p.id ? "on" : ""}`}
              aria-pressed={selectedId === p.id}
              onClick={() => { haptic(); onPick(p); }}
            >
              <span className="preset-thumb">
                {p.preview_url
                  ? <img src={mediaUrl(p.preview_url)} alt="" loading="lazy" />
                  : <span className="preset-thumb-fallback">{p.kind === "video" ? "🎬" : "🎨"}</span>}
                {p.badge && <span className="preset-badge">{p.badge}</span>}
              </span>
              <span className="preset-name">{p.name}</span>
            </button>
          ))}
        </div>
      )}
    </div>
  );
}
