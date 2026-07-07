import { useEffect, useState } from "react";
import { api, EffectKind, EffectSummary } from "../api/client";
import { t } from "../i18n";
import { haptic } from "../theme";
import { EffectCard } from "./EffectCard";

const CATEGORIES: Record<EffectKind, string[]> = {
  video: ["all", "dance", "emotion", "effect", "transform"],
  photo: ["all", "female", "male", "children", "couple"],
};

/**
 * Catalog grid for one effect kind. When `trending` is set the category pills
 * are hidden and only trending presets are shown (the Тренды tab).
 */
export function EffectGrid({
  kind,
  trending = false,
  onPick,
}: {
  kind: EffectKind;
  trending?: boolean;
  onPick: (e: EffectSummary) => void;
}) {
  const [category, setCategory] = useState("all");
  const [items, setItems] = useState<EffectSummary[] | null>(null);
  // FIX: AUDIT12-5b - declare err/setErr (was: referenced in catch without
  // useState declaration → ReferenceError on /api/effects failure).
  const [err, setErr] = useState(false);
  // FIX: AUDIT-H7 - bump this to re-trigger the load from the Retry button.
  const [reload, setReload] = useState(0);

  useEffect(() => {
    // Guard against out-of-order responses: switching kind/category fast keeps
    // several requests in flight, and the API client has no cancellation — without
    // this a slower earlier response could overwrite the freshly-selected one,
    // showing effects that don't match the active segment/pill.
    let ignore = false;
    setItems(null);
    setErr(false);
    api.listEffects(kind, category, trending)
      .then((r) => { if (!ignore) setItems(r); })
      // FIX: AUDIT-H7 - surface real failures (500/timeout/401) as an error+retry
      // state instead of the misleading "empty category" message (setErr was dead).
      .catch(() => { if (!ignore) setErr(true); });
    return () => { ignore = true; };
  }, [kind, category, trending, reload]);
  // FIX: L14 - reset category when kind changes so a stale photo-incompatible category doesn't show an empty grid.
  useEffect(() => setCategory("all"), [kind]);

  return (
    <>
      {!trending && (
        <div className="pills">
          {CATEGORIES[kind].map((c) => (
            <button
              key={c}
              className={`pill ${category === c ? "active" : ""}`}
              onClick={() => { haptic(); setCategory(c); }}
            >
              {t(`cat_${c}`)}
            </button>
          ))}
        </div>
      )}

      {err ? (
        <div className="center">
          <div>{t("err_server")}</div>
          <button className="btn" onClick={() => { haptic(); setReload((n) => n + 1); }}>{t("retry")}</button>
        </div>
      ) : items === null ? (
        <div className="grid">
          {Array.from({ length: 6 }).map((_, i) => <div key={i} className="skeleton" />)}
        </div>
      ) : items.length === 0 ? (
        <div className="center">{t("empty_cat")}</div>
      ) : (
        <div className="grid">
          {items.map((e) => <EffectCard key={`${e.kind}-${e.id}`} effect={e} onClick={() => onPick(e)} />)}
        </div>
      )}
    </>
  );
}
