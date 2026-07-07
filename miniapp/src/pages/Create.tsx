import { useEffect, useMemo, useRef, useState } from "react";
import {
  api, EffectDetail, EffectKind, EffectSummary, FreeModel, mediaUrl, ModelCard, pollJob,
} from "../api/client";
import { t } from "../i18n";
import { haptic } from "../theme";
import { ModeSwitch } from "../components/create/ModeSwitch";
import { PresetPicker } from "../components/create/PresetPicker";
import { ModelPicker } from "../components/create/ModelPicker";
import { UploadSection } from "../components/create/UploadSection";
import { PromptSection } from "../components/create/PromptSection";
import { SettingsPanel } from "../components/create/SettingsPanel";
import { GenerateBar, Phase } from "../components/create/GenerateBar";
import { ElementsPanel } from "../components/create/ElementsPanel";

type Params = Record<string, string | number | boolean>;
const MAX_BYTES = 30 * 1024 * 1024;
const ALL_KINDS: EffectKind[] = ["video", "photo"];
// §11 — persisted prompt draft: survives reloads and preset/mode switches.
const DRAFT_KEY = "cm_draft_prompt";

/**
 * Create Media (§12 ТЗ) — оркестратор Higgsfield-подобной страницы генерации.
 * Держит всё состояние потока и связывает независимые модули (ModeSwitch /
 * PresetPicker / UploadSection / PromptSection / SettingsPanel / GenerateBar).
 * Логика генерации идёт через существующий каталог пресетов бэкенда: выбранный
 * пресет = «модель», его `detail` даёт под-модели, настройки и стоимость.
 * Результат сохраняется бэкендом в историю (вкладка «История»).
 *
 * Расширяемость: каждый шаг — отдельный компонент с чистым контрактом props, так
 * что добавление Elements, @-ссылок, negative prompt, пресетов и batch-генерации
 * не требует переписывания оркестратора.
 */
export function Create({
  onCredits, sections, prefill, onPrefillConsumed,
}: {
  onCredits?: (credits: number) => void;
  sections?: { photo: boolean; video: boolean };
  /** §10 — replay from History: preselect this kind + preset. */
  prefill?: { kind: EffectKind; presetId: number } | null;
  onPrefillConsumed?: () => void;
}) {
  const available = useMemo<EffectKind[]>(
    () => ALL_KINDS.filter((k) => (sections ? sections[k] : true)),
    [sections],
  );
  const [mode, setMode] = useState<EffectKind>(available[0] ?? "video");
  // §variant3 — generation SOURCE: curated preset-styles vs a directly-chosen model.
  const [source, setSource] = useState<"preset" | "model">("preset");

  const [presets, setPresets] = useState<EffectSummary[] | null>(null);
  const [preset, setPreset] = useState<EffectSummary | null>(null);
  const [detail, setDetail] = useState<EffectDetail | null>(null);
  const [detailLoading, setDetailLoading] = useState(false);
  // Free model choice
  const [freeList, setFreeList] = useState<FreeModel[] | null>(null);
  const [freeModel, setFreeModel] = useState<FreeModel | null>(null);

  const [model, setModel] = useState("");
  const [params, setParams] = useState<Params>({});
  const [files, setFiles] = useState<File[]>([]);
  const [previews, setPreviews] = useState<string[]>([]);
  const [prompt, setPrompt] = useState("");
  const [negative, setNegative] = useState("");

  const [cost, setCost] = useState(0);
  const [balance, setBalance] = useState<number | null>(null);
  const [phase, setPhase] = useState<Phase>("config");
  const [status, setStatus] = useState("");
  const [progress, setProgress] = useState(0);
  const [resultUrl, setResultUrl] = useState<string | null>(null);
  const [error, setError] = useState("");
  const [elementsOpen, setElementsOpen] = useState(false);

  const textareaRef = useRef<HTMLTextAreaElement>(null);
  const abortRef = useRef<AbortController | null>(null);
  const runRef = useRef<() => void>(() => {});
  const previewsRef = useRef<string[]>([]);
  previewsRef.current = previews;
  // Abort any in-flight poll and free preview blobs when the tab unmounts.
  useEffect(() => () => {
    abortRef.current?.abort();
    previewsRef.current.forEach((u) => URL.revokeObjectURL(u));
  }, []);

  // Keep the mode valid if the available set changes (provider toggled server-side).
  useEffect(() => {
    if (available.length && !available.includes(mode)) setMode(available[0]);
  }, [available, mode]);

  const card: ModelCard | undefined = useMemo(
    () => detail?.models?.find((m) => m.key === model),
    [detail, model],
  );
  const maxPhotos = detail?.max_photos ?? 0;
  const promptMode = detail?.prompt_mode ?? "optional";

  // Unified "active target" so the form/generate logic works identically for a
  // curated preset (via `detail`) OR a directly-chosen model (`freeModel.card`).
  const isModel = source === "model";
  const hasSel = isModel ? !!freeModel : !!preset;
  const activeModels: ModelCard[] = isModel ? (freeModel ? [freeModel.card] : []) : (detail?.models ?? []);
  const activeCard = isModel ? freeModel?.card : card;
  const activeMaxPhotos = isModel ? (freeModel?.max_photos ?? 0) : maxPhotos;
  const activePromptMode: "hidden" | "optional" | "required" = isModel ? "optional" : promptMode;
  const activeReady = isModel ? !!freeModel : (!!preset && !!detail && !detailLoading);

  // Current balance for the cost bar (also refreshed after a spend).
  useEffect(() => {
    let ignore = false;
    api.profile().then((p) => { if (!ignore) setBalance(p.credits); }).catch(() => {});
    return () => { ignore = true; };
  }, []);

  // §11 — restore the prompt draft once on mount, then persist it (debounced).
  useEffect(() => {
    const saved = localStorage.getItem(DRAFT_KEY);
    if (saved) setPrompt(saved);
  }, []);
  useEffect(() => {
    const id = setTimeout(() => {
      if (prompt.trim()) localStorage.setItem(DRAFT_KEY, prompt);
      else localStorage.removeItem(DRAFT_KEY);
    }, 400);
    return () => clearTimeout(id);
  }, [prompt]);

  // @image-references for uploaded photos (§3): "@image1", "@image2", …
  const refs = useMemo(() => files.map((_, i) => `@image${i + 1}`), [files]);

  // Insert a phrase/reference into the prompt at the caret (or append), keeping a
  // readable separator. Elements add ", phrase"; @-refs add " @imageN".
  function insertToPrompt(text: string) {
    const el = textareaRef.current;
    setPrompt((prev) => {
      const glue = (before: string) =>
        !before || /\s$/.test(before) ? "" : text.startsWith("@") ? " " : ", ";
      if (el && document.activeElement === el) {
        const s = el.selectionStart ?? prev.length;
        const e = el.selectionEnd ?? prev.length;
        const before = prev.slice(0, s);
        const ins = glue(before) + text;
        const next = before + ins + prev.slice(e);
        const pos = before.length + ins.length;
        requestAnimationFrame(() => { el.focus(); el.setSelectionRange(pos, pos); });
        return next;
      }
      return prev + glue(prev) + text;
    });
  }

  // Load the preset catalog whenever the mode changes; reset the downstream form.
  useEffect(() => {
    let ignore = false;
    setPresets(null);
    resetForm();
    api.listEffects(mode).then((list) => { if (!ignore) setPresets(list); })
      .catch(() => { if (!ignore) setPresets([]); });
    return () => { ignore = true; };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [mode]);

  // Load the selected preset's detail (models / settings / price).
  useEffect(() => {
    if (!preset) { setDetail(null); return; }
    let ignore = false;
    setDetailLoading(true);
    setDetail(null);
    api.effectDetail(preset.kind, preset.id).then((d) => {
      if (ignore) return;
      setDetail(d);
      setModel(d.recommended_model ?? d.models?.[0]?.key ?? "");
      setParams({ ...d.default_params });
      setCost(d.price);
      setDetailLoading(false);
    }).catch((e) => {
      if (ignore) return;
      setDetailLoading(false);
      setError(t(e instanceof Error ? e.message : "err_generic")); setPhase("error");  // FIX: AUDIT13-M16 - translate the i18n key
    });
    return () => { ignore = true; };
  }, [preset]);

  // Re-price on model/params change (debounced) via the live cost endpoint.
  useEffect(() => {
    if (!preset || !detail || !model) return;
    const id = setTimeout(() => {
      api.effectCost(preset.kind, preset.id, model, params)
        .then((r) => setCost(r.cost)).catch(() => {});
    }, 300);
    return () => clearTimeout(id);
  }, [preset, detail, model, params]);

  // Free model: load the catalog for the current mode (on source/mode change).
  useEffect(() => {
    if (source !== "model") return;
    let ignore = false;
    setFreeList(null);
    resetForm();
    api.freeModels(mode).then((l) => { if (!ignore) setFreeList(l); })
      .catch(() => { if (!ignore) setFreeList([]); });
    return () => { ignore = true; };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [source, mode]);

  // Free model: re-price on params change (debounced) via the free-model cost endpoint.
  useEffect(() => {
    if (source !== "model" || !freeModel) return;
    const id = setTimeout(() => {
      api.freeModelCost(mode, freeModel.key, params)
        .then((r) => setCost(r.cost)).catch(() => {});
    }, 300);
    return () => clearTimeout(id);
  }, [source, freeModel, params, mode]);

  // §10 — replay from History: switch to the requested kind, wait for its catalog,
  // then load the preset directly (works even if it isn't in the visible strip) and
  // clear the prefill so this runs once.
  useEffect(() => {
    if (!prefill) return;
    if (source !== "preset") { setSource("preset"); return; }
    if (mode !== prefill.kind) { setMode(prefill.kind); return; }
    if (presets === null) return;
    let ignore = false;
    api.effectDetail(prefill.kind, prefill.presetId).then((d) => {
      if (ignore) return;
      pickPreset({
        id: d.id, kind: d.kind, name: d.name, author: d.author, category: d.category,
        badge: null, is_ad: false, preview_url: d.preview_url,
        recommended_model: d.recommended_model, price: d.price,
      });
      onPrefillConsumed?.();
    }).catch(() => onPrefillConsumed?.());
    return () => { ignore = true; };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [prefill, mode, presets]);

  // §11 — Ctrl/Cmd+Enter triggers generation from anywhere on the page.
  useEffect(() => {
    function onKey(e: KeyboardEvent) {
      if ((e.metaKey || e.ctrlKey) && e.key === "Enter") { e.preventDefault(); runRef.current(); }
    }
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, []);

  function resetForm() {
    setPreset(null); setDetail(null); setFreeModel(null); setModel(""); setParams({});
    setFiles([]); setPreviews((prev) => { prev.forEach((u) => URL.revokeObjectURL(u)); return []; });
    // NOTE: the prompt is intentionally NOT cleared — it is a persisted draft (§11)
    // that carries across preset/mode switches until the user edits it.
    setCost(0); setPhase("config"); setProgress(0);
    setResultUrl(null); setError(""); setStatus("");
  }

  function pickPreset(p: EffectSummary) {
    setPhase("config"); setError(""); setProgress(0); setResultUrl(null);
    setFiles([]); setPreviews((prev) => { prev.forEach((u) => URL.revokeObjectURL(u)); return []; });
    setPreset(p);
  }

  function pickFreeModel(m: FreeModel) {
    setPhase("config"); setError(""); setProgress(0); setResultUrl(null);
    setFiles([]); setPreviews((prev) => { prev.forEach((u) => URL.revokeObjectURL(u)); return []; });
    setFreeModel(m);
    setModel(m.card.key);
    setParams({ ...m.default_params });
    setCost(m.price);
  }

  // Switch the generation source (preset styles ↔ direct model), resetting the form.
  function switchSource(next: "preset" | "model") {
    if (next === source) return;
    haptic();
    resetForm();
    setSource(next);
  }

  function selectModel(key: string) {
    const next = detail?.models.find((m) => m.key === key);
    setModel(key);
    setParams(next ? { ...next.default } : {});
  }
  function setParam(key: string, value: string | number | boolean) {
    setParams((p) => ({ ...p, [key]: value }));
  }

  function addFiles(list: FileList | null) {
    if (!list) return;
    const room = maxPhotos - files.length;
    const next = Array.from(list).slice(0, Math.max(0, room));
    if (next.some((f) => f.size > MAX_BYTES)) { setError(t("err_too_big")); return; }
    setError("");
    setFiles((prev) => [...prev, ...next]);
    setPreviews((prev) => [...prev, ...next.map((f) => URL.createObjectURL(f))]);
  }
  function removeFile(i: number) {
    haptic();
    URL.revokeObjectURL(previews[i]);
    setFiles((prev) => prev.filter((_, j) => j !== i));
    setPreviews((prev) => prev.filter((_, j) => j !== i));
  }

  async function run() {
    if (phase === "running" || !hasSel) return;
    // A photo effect/model needs a source image (img2img); a video model's image is
    // optional (text2video), so only require an upload for the photo kind in free mode.
    const needPhoto = activeMaxPhotos > 0 && files.length === 0 && (!isModel || mode === "photo");
    if (needPhoto) { setError(t("err_need_photo")); setPhase("error"); return; }
    if (activePromptMode === "required" && !prompt.trim()) { setError(t("err_need_prompt")); setPhase("error"); return; }
    haptic("medium");
    const ctrl = new AbortController();
    abortRef.current = ctrl;
    setError(""); setPhase("running"); setStatus(t("uploading")); setProgress(8);
    try {
      // §13 — negative prompt rides along in params; the backend uses it if the
      // model supports one and ignores it otherwise (unknown keys are safe).
      const genParams = negative.trim() ? { ...params, negative: negative.trim() } : params;
      const { job_id } = isModel && freeModel
        ? await api.freeModelGenerate(mode, freeModel.key, genParams, prompt, files)
        : await api.effectGenerate(preset!.kind, preset!.id, model, genParams, prompt, files);
      if (ctrl.signal.aborted) return;
      setStatus(t("generating")); setProgress((p) => Math.max(p, 20));
      const res = await pollJob(job_id, (s) => {
        if (ctrl.signal.aborted) return;
        setStatus(s.status === "processing" ? t("generating") : t("queued"));
        setProgress((p) => Math.min(90, p + 9));
      }, ctrl.signal);
      if (ctrl.signal.aborted) return;
      if (res.status === "complete" && res.result_url) {
        setProgress(100); setResultUrl(mediaUrl(res.result_url)); setPhase("done"); haptic("heavy");
        api.profile().then((p) => { setBalance(p.credits); onCredits?.(p.credits); }).catch(() => {});
      } else {
        setError(res.error ? `${t("failed")}: ${res.error}` : t("failed")); setPhase("error");
      }
    } catch (e) {
      if (abortRef.current?.signal.aborted) return;
      const msg = e instanceof Error ? e.message : "err_generic";
      // FIX: AUDIT13-M16 - msg is an i18n KEY; translate it instead of showing it raw.
      setError(msg === "LIMIT" ? t("err_limit") : t(msg)); setPhase("error");
    }
  }

  function reset() { setPhase("config"); setResultUrl(null); setProgress(0); setStatus(""); }

  // keep the Ctrl+Enter handler pointing at the latest run(), gated on readiness
  runRef.current = () => { if (activeReady && phase !== "running") run(); };

  return (
    <div className="content">
      <ModeSwitch mode={mode} available={available} onMode={setMode} />

      {/* §variant3 — source: curated styles ↔ direct model choice */}
      <div className="segmented" role="tablist" aria-label={t("create_style")}>
        <button role="tab" aria-selected={source === "preset"}
          className={`seg ${source === "preset" ? "active" : ""}`}
          onClick={() => switchSource("preset")}>{t("create_style")}</button>
        <button role="tab" aria-selected={source === "model"}
          className={`seg ${source === "model" ? "active" : ""}`}
          onClick={() => switchSource("model")}>{t("models_label")}</button>
      </div>

      {source === "preset" ? (
        <PresetPicker
          presets={presets}
          loading={presets === null}
          selectedId={preset?.id ?? null}
          onPick={pickPreset}
        />
      ) : (
        <ModelPicker
          models={freeList}
          loading={freeList === null}
          selectedKey={freeModel?.key ?? null}
          onPick={pickFreeModel}
        />
      )}

      {!hasSel ? (
        <div className="muted hint">{t("create_pick_first")}</div>
      ) : !isModel && (detailLoading || !detail) ? (
        phase === "error"
          ? <div className="error-banner">{error}</div>
          : <div className="center"><span className="spinner" /> {t("loading")}</div>
      ) : (
        <>
          <UploadSection
            maxPhotos={activeMaxPhotos} files={files} previews={previews}
            onAdd={addFiles} onRemove={removeFile}
          />
          <PromptSection
            value={prompt} mode={activePromptMode} onChange={setPrompt}
            textareaRef={textareaRef} refs={refs}
            negative={negative} onNegative={setNegative}
            onInsert={insertToPrompt}
            onOpenElements={() => { haptic(); setElementsOpen(true); }}
          />
          <SettingsPanel
            models={activeModels} model={model} onModel={selectModel}
            card={activeCard} params={params} setParam={setParam}
          />
          <GenerateBar
            phase={phase} kind={mode} cost={cost} balance={balance}
            progress={progress} status={status} error={error} resultUrl={resultUrl}
            canGenerate={activeReady} onGenerate={run} onReset={reset}
          />
        </>
      )}

      <ElementsPanel
        open={elementsOpen}
        onClose={() => setElementsOpen(false)}
        onInsert={insertToPrompt}
      />
    </div>
  );
}
