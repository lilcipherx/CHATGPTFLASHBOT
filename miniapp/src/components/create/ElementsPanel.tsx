import { useEffect, useState } from "react";
import { t } from "../../i18n";
import { haptic } from "../../theme";
import { ELEMENT_CATEGORIES } from "./elements";

/**
 * Create Media — панель Элементов (§4 ТЗ). Bottom-sheet поверх страницы: слева
 * табы категорий (Style/Camera/Lighting/Background/Pose), справа — чипы; тап по
 * чипу дописывает фразу в промпт через `onInsert` и мягко закрывает панель.
 * Закрывается по фону, Esc и кнопке. Презентационная — каталог приходит из
 * `elements.ts`, вставка в промпт живёт в контейнере.
 */
export function ElementsPanel({
  open, onClose, onInsert,
}: {
  open: boolean;
  onClose: () => void;
  onInsert: (phrase: string) => void;
}) {
  const [cat, setCat] = useState(ELEMENT_CATEGORIES[0].id);

  useEffect(() => {
    if (!open) return;
    const onKey = (e: KeyboardEvent) => { if (e.key === "Escape") onClose(); };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [open, onClose]);

  if (!open) return null;
  const active = ELEMENT_CATEGORIES.find((c) => c.id === cat) ?? ELEMENT_CATEGORIES[0];

  return (
    <div className="el-backdrop" onClick={onClose}>
      <div className="el-panel" role="dialog" aria-label={t("elements")} onClick={(e) => e.stopPropagation()}>
        <div className="el-head">
          <b>{t("elements")}</b>
          <button className="el-close" aria-label={t("back")} onClick={onClose}>✕</button>
        </div>
        <div className="el-tabs" role="tablist">
          {ELEMENT_CATEGORIES.map((c) => (
            <button
              key={c.id}
              role="tab"
              aria-selected={c.id === cat}
              className={`el-tab ${c.id === cat ? "on" : ""}`}
              onClick={() => { haptic(); setCat(c.id); }}
            >
              <span aria-hidden="true">{c.icon}</span> {c.label}
            </button>
          ))}
        </div>
        <div className="el-items">
          {active.items.map((it) => (
            <button
              key={it.label}
              className="btn-sm"
              onClick={() => { haptic(); onInsert(it.insert); onClose(); }}
            >
              {it.label}
            </button>
          ))}
        </div>
      </div>
    </div>
  );
}
