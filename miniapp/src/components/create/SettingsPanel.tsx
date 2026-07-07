import { ModelCard } from "../../api/client";
import { t } from "../../i18n";
import { haptic } from "../../theme";

type Params = Record<string, string | number | boolean>;

// spec flag -> the param key it writes (kept in sync with the backend generate contract)
const FLAG_PARAM: Record<string, string> = {
  audio: "audio", fourk: "fourk", seed: "seed", prompt_enhance: "enhance",
};

/**
 * Create Media — выбор модели (§6) + динамические настройки (§7 ТЗ). Показывает
 * ТОЛЬКО те параметры, которые заявляет выбранная модель (`ModelCard`) — ничего
 * лишнего. Каждая настройка — независимая группа «чипов», так что добавить новый
 * параметр (Negative Prompt, CFG, Steps, Seed…) = одна строка здесь, без правок
 * контейнера. Значения пишутся в общий объект `params`, который уходит в generate.
 */
function Chips<T extends string | number>({
  title, values, current, label, onPick,
}: {
  title: string;
  values: T[];
  current: T | undefined;
  label: (v: T) => string;
  onPick: (v: T) => void;
}) {
  return (
    <div>
      <div className="section-title">{title}</div>
      <div className="btn-row">
        {values.map((v) => (
          <button
            key={String(v)}
            className={`btn-sm ${current === v ? "on" : ""}`}
            aria-pressed={current === v}
            onClick={() => { haptic(); onPick(v); }}
          >
            {label(v)}
          </button>
        ))}
      </div>
    </div>
  );
}

export function SettingsPanel({
  models, model, onModel, card, params, setParam,
}: {
  models: ModelCard[];
  model: string;
  onModel: (key: string) => void;
  card: ModelCard | undefined;
  params: Params;
  setParam: (k: string, v: string | number | boolean) => void;
}) {
  return (
    <>
      {models.length > 1 && (
        <Chips
          title={t("ai_model")}
          values={models.map((m) => m.key)}
          current={model}
          label={(k) => models.find((m) => m.key === k)?.title ?? k}
          onPick={onModel}
        />
      )}

      {card?.models && (
        <Chips title={t("variant")} values={card.models.map((m) => m[0])}
          current={params.model as string}
          label={(v) => card.models!.find((m) => m[0] === v)?.[1] ?? v}
          onPick={(v) => setParam("model", v)} />
      )}
      {card?.qualities && (
        <Chips title={t("quality")} values={card.qualities}
          current={params.quality as string} label={(v) => v.toUpperCase()}
          onPick={(v) => setParam("quality", v)} />
      )}
      {card?.ratios && (
        <Chips title={t("aspect_ratio")} values={card.ratios}
          current={params.ratio as string} label={(v) => v}
          onPick={(v) => setParam("ratio", v)} />
      )}
      {card?.durations && (
        <Chips title={t("duration")} values={card.durations}
          current={params.duration as number} label={(v) => `${v}s`}
          onPick={(v) => setParam("duration", v)} />
      )}
      {card?.resolutions && (
        <Chips title={t("resolution")} values={card.resolutions}
          current={params.res as string} label={(v) => v}
          onPick={(v) => setParam("res", v)} />
      )}
      {card?.modes && (
        <Chips title={t("mode")} values={card.modes.map((m) => m[0])}
          current={params.mode as string}
          label={(v) => card.modes!.find((m) => m[0] === v)?.[1] ?? v}
          onPick={(v) => setParam("mode", v)} />
      )}

      {card && (["audio", "fourk", "seed", "prompt_enhance"] as const).some((f) => card[f]) && (
        <div className="btn-row">
          {(["audio", "fourk", "seed", "prompt_enhance"] as const).map((flag) =>
            card[flag] ? (
              <button key={flag} className={`btn-sm ${params[FLAG_PARAM[flag]] ? "on" : ""}`}
                aria-pressed={!!params[FLAG_PARAM[flag]]}
                onClick={() => { haptic(); setParam(FLAG_PARAM[flag], !params[FLAG_PARAM[flag]]); }}>
                {t(`flag_${flag}`)}
              </button>
            ) : null,
          )}
        </div>
      )}
    </>
  );
}
