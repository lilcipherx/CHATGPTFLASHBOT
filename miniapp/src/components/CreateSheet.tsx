import WebApp from "@twa-dev/sdk";
import { useEffect, useMemo, useRef, useState } from "react";
import { api, EffectDetail, EffectSummary, mediaUrl, ModelCard, pollJob } from "../api/client";
import { t } from "../i18n";
import { haptic } from "../theme";

type Phase = "config" | "running" | "done" | "error";
type Params = Record<string, string | number | boolean>;

const MAX_BYTES = 30 * 1024 * 1024;
// spec flag -> the param key it writes
const FLAG_PARAM: Record<string, string> = {
  audio: "audio", fourk: "fourk", seed: "seed", prompt_enhance: "enhance",
};

export function CreateSheet({
  effect, onClose, onCredits,
}: {
  effect: EffectSummary;
  onClose: () => void;
  onCredits?: (credits: number) => void;
}) {
  const [detail, setDetail] = useState<EffectDetail | null>(null);
  const [model, setModel] = useState("");
  const [params, setParams] = useState<Params>({});
  const [files, setFiles] = useState<File[]>([]);
  const [previews, setPreviews] = useState<string[]>([]);
  const [prompt, setPrompt] = useState("");
  const [cost, setCost] = useState(effect.price);
  const [balance, setBalance] = useState<number | null>(null);
  const [phase, setPhase] = useState<Phase>("config");
  const [status, setStatus] = useState("");
  // Simulated progress (backend gives no real %): advances on each poll tick
  // toward 90%, then jumps to 100% on success.
  const [progress, setProgress] = useState(0);
  const [resultUrl, setResultUrl] = useState<string | null>(null);
  const [error, setError] = useState("");
  const fileRef = useRef<HTMLInputElement>(null);
  const action = useRef<() => void>(() => {});
  // Abort an in-flight poll and revoke preview blob URLs when the sheet unmounts.
  const abortRef = useRef<AbortController | null>(null);
  const previewsRef = useRef<string[]>([]);
  previewsRef.current = previews;
  useEffect(() => () => {
    abortRef.current?.abort();
    previewsRef.current.forEach((u) => URL.revokeObjectURL(u));
  }, []);

  // FIX: UI-3 - lock background scroll while the full-screen sheet is open so the page
  // behind it can't scroll-chain (the sheet is position:fixed; inset:0 over the app).
  useEffect(() => {
    const prev = document.body.style.overflow;
    document.body.style.overflow = "hidden";
    return () => { document.body.style.overflow = prev; };
  }, []);

  // FIX: null-safety - optional-chain models too; `detail?.models.find` still
  // crashes if the API returns a detail row with a null/missing models array.
  const card: ModelCard | undefined = useMemo(
    () => detail?.models?.find((m) => m.key === model),
    [detail, model],
  );
  const maxPhotos = detail?.max_photos ?? 0;

  // Load preset detail + current balance.
  // FIX: AUDIT-LOW - guard against the sheet unmounting mid-request so these async
  // resolutions don't setState on an unmounted component.
  useEffect(() => {
    let ignore = false;
    api.effectDetail(effect.kind, effect.id).then((d) => {
      if (ignore) return;
      setDetail(d);
      setModel(d.recommended_model ?? d.models?.[0]?.key ?? "");  // FIX: null-safety - models may be missing
      setParams({ ...d.default_params });
      setCost(d.price);
    }).catch((e) => { if (!ignore) { setError(t(e instanceof Error ? e.message : "err_generic")); setPhase("error"); } });  // FIX: AUDIT13-M16 - translate the i18n key, don't show it raw
    api.profile().then((p) => { if (!ignore) setBalance(p.credits); }).catch(() => {});
    return () => { ignore = true; };
  }, [effect.id, effect.kind]);

  // Re-price when the model or params change (debounced).
  useEffect(() => {
    if (!detail || !model) return;
    const id = setTimeout(() => {
      api.effectCost(effect.kind, effect.id, model, params)
        .then((r) => setCost(r.cost)).catch(() => {});
    }, 300);
    return () => clearTimeout(id);
  }, [detail, model, params, effect.id, effect.kind]);

  function selectModel(key: string) {
    haptic();
    const next = detail?.models.find((m) => m.key === key);
    setModel(key);
    setParams(next ? { ...next.default } : {});
  }

  function setParam(key: string, value: string | number | boolean) {
    haptic();
    setParams((p) => ({ ...p, [key]: value }));
  }

  function addFiles(list: FileList | null) {
    if (!list) return;
    const room = maxPhotos - files.length;
    const next = Array.from(list).slice(0, Math.max(0, room));
    const tooBig = next.find((f) => f.size > MAX_BYTES);
    if (tooBig) { setError(t("err_too_big")); return; }
    setError("");
    setFiles((prev) => [...prev, ...next]);
    setPreviews((prev) => [...prev, ...next.map((f) => URL.createObjectURL(f))]);
  }

  function removeFile(i: number) {
    haptic();
    URL.revokeObjectURL(previews[i]);  // free the blob held by this preview
    setFiles((prev) => prev.filter((_, j) => j !== i));
    setPreviews((prev) => prev.filter((_, j) => j !== i));
  }

  async function run() {
    if (phase === "running") return;
    if (maxPhotos > 0 && files.length === 0) { setError(t("err_need_photo")); return; }
    if (detail?.prompt_mode === "required" && !prompt.trim()) { setError(t("err_need_prompt")); return; }
    haptic("medium");
    const ctrl = new AbortController();
    abortRef.current = ctrl;
    setPhase("running");
    setStatus(t("uploading"));
    setProgress(8);
    try {
      const { job_id } = await api.effectGenerate(
        effect.kind, effect.id, model, params, prompt, files,
      );
      if (ctrl.signal.aborted) return;
      setStatus(t("generating"));
      setProgress((p) => Math.max(p, 20));
      const res = await pollJob(job_id, (s) => {
        if (ctrl.signal.aborted) return;
        setStatus(s.status === "processing" ? t("generating") : t("queued"));
        // Ease toward 90% but never reach it until the job actually completes.
        setProgress((p) => Math.min(90, p + 9));
      }, ctrl.signal);
      if (ctrl.signal.aborted) return;  // sheet closed mid-generation — drop the result
      if (res.status === "complete" && res.result_url) {
        setProgress(100);
        setResultUrl(mediaUrl(res.result_url));
        setPhase("done");
        haptic("heavy");
        // Credits were just spent — refresh the in-sheet balance AND the header chip.
        api.profile().then((p) => { setBalance(p.credits); onCredits?.(p.credits); }).catch(() => {});
      } else {
        setError(res.error ? `${t("failed")}: ${res.error}` : t("failed"));
        setPhase("error");
      }
    } catch (e) {
      if (abortRef.current?.signal.aborted) return;  // unmounted — don't touch state
      const msg = e instanceof Error ? e.message : "err_generic";
      // FIX: AUDIT13-M16 - msg is an i18n KEY (err_server/err_rate/...); translate it.
      setError(msg === "LIMIT" ? t("err_limit") : t(msg));
      setPhase("error");
    }
  }

  // Native Telegram BackButton closes the sheet.
  // FIX: F69 - use [] deps + onCloseRef so the BackButton isn't re-registered on every
  // parent re-render (was [onClose] where onClose is an inline arrow → flicker + waste).
  // Mirrors the MainButton effect below.
  const onCloseRef = useRef(onClose);
  onCloseRef.current = onClose;
  useEffect(() => {
    WebApp.BackButton.show();
    const close = () => onCloseRef.current();
    WebApp.BackButton.onClick(close);
    return () => { WebApp.BackButton.offClick(close); WebApp.BackButton.hide(); };
  }, []);

  // Native Telegram MainButton drives the primary action.
  useEffect(() => {
    const mb = WebApp.MainButton;
    const handler = () => action.current();
    mb.onClick(handler);
    return () => { mb.offClick(handler); mb.hide(); };
  }, []);

  useEffect(() => {
    const mb = WebApp.MainButton;
    if (phase === "done") {
      action.current = () => { setPhase("config"); setResultUrl(null); setProgress(0); };
      mb.setText(t("create_more"));
      mb.hideProgress(); mb.enable(); mb.show();
    } else if (phase === "running") {
      action.current = () => {};
      mb.setText(status || t("generating"));
      mb.show(); mb.showProgress(false);
    } else {
      action.current = run;
      mb.setText(`${t("generate")} ${cost}✨`);
      mb.hideProgress(); mb.enable(); mb.show();
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [phase, status, cost, files, model, params, prompt]);

  function share() { if (resultUrl) WebApp.openLink(resultUrl); }

  // Download the full-quality result (ТЗ §4 «кнопка Скачать»). Use Telegram's native
  // downloadFile when the client supports it (Bot API 8.0+), else fall back to
  // opening the file URL so the user can still save it.
  function download() {
    if (!resultUrl) return;
    const name = `result.${effect.kind === "video" ? "mp4" : "jpg"}`;
    const dl = (WebApp as unknown as {
      downloadFile?: (p: { url: string; file_name: string }) => void;
    }).downloadFile;
    if (dl) dl({ url: resultUrl, file_name: name });
    else WebApp.openLink(resultUrl);
  }

  return (
    <div className="sheet">
      <div className="sheet-head">
        <button className="back" onClick={onClose}>{t("back")}</button>
        <b>{effect.name}</b>
      </div>

      <div className="sheet-body">
        {phase === "done" && resultUrl ? (
          <>
            {effect.kind === "video" ? (
              <video className="preview" src={resultUrl} controls autoPlay loop muted />
            ) : (
              <img className="preview" src={resultUrl} alt="result" />
            )}
            <button className="btn" onClick={download}>{t("download")}</button>
            <button className="btn secondary" onClick={share}>{t("share")}</button>
          </>
        ) : !detail ? (
          // FIX: state-machine - effectDetail() failure sets phase="error" while
          // detail is still null. The error banner lives in the loaded branch below,
          // so without this the sheet showed an infinite spinner and never surfaced
          // the error. Show it here (Back button in the header / native BackButton
          // closes the sheet).
          phase === "error" ? (
            <div className="center"><div className="error-banner">{error}</div></div>
          ) : (
            <div className="center"><span className="spinner" /> {t("loading")}</div>
          )
        ) : (
          <>
            {(effect.preview_url || effect.author) && (
              <div className="cover">
                {effect.preview_url
                  ? <img className="cover-img" src={mediaUrl(effect.preview_url)} alt={effect.name} />
                  : <div className="cover-fallback">{effect.kind === "video" ? "🎬" : "🎨"}</div>}
                {effect.author && <span className="cover-author">{t("by_author", { name: effect.author })}</span>}
              </div>
            )}

            {maxPhotos > 0 && (
              <div>
                <div className="section-title">{t("your_photos")} {files.length}/{maxPhotos}</div>
                <div className="photo-strip">
                  {previews.map((src, i) => (
                    <button key={i} className="photo-thumb" onClick={() => removeFile(i)}>
                      <img src={src} alt="" />
                      <span className="photo-x">✕</span>
                    </button>
                  ))}
                  {files.length < maxPhotos && (
                    <button className="photo-add" aria-label={t("choose_photo")} onClick={() => fileRef.current?.click()}>+</button>
                  )}
                </div>
                <div className="muted hint">{t("upload_size")}</div>
                <input ref={fileRef} type="file" accept="image/*" multiple hidden
                  onChange={(e) => addFiles(e.target.files)} />
              </div>
            )}

            {detail.prompt_mode !== "hidden" && (
              <div>
                <div className="section-title">
                  {t("prompt")}{detail.prompt_mode === "required" ? " *" : ""}
                </div>
                <textarea className="prompt-input" rows={2} value={prompt}
                  placeholder={t("prompt_ph")} onChange={(e) => setPrompt(e.target.value)} />
              </div>
            )}

            {(detail.models?.length ?? 0) > 1 && (
              <div>
                <div className="section-title">{t("ai_model")}</div>
                <div className="btn-row">
                  {detail.models?.map((m) => (
                    <button key={m.key} className={`btn-sm ${model === m.key ? "on" : ""}`}
                      onClick={() => selectModel(m.key)}>{m.title}</button>
                  ))}
                </div>
              </div>
            )}

            {card && <ParamControls card={card} params={params} setParam={setParam} />}

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
          </>
        )}
      </div>
    </div>
  );
}

function chips<T extends string | number>(
  title: string,
  values: T[],
  current: T | undefined,
  label: (v: T) => string,
  onPick: (v: T) => void,
) {
  return (
    <div>
      <div className="section-title">{title}</div>
      <div className="btn-row">
        {values.map((v) => (
          <button key={String(v)} className={`btn-sm ${current === v ? "on" : ""}`}
            onClick={() => onPick(v)}>{label(v)}</button>
        ))}
      </div>
    </div>
  );
}

function ParamControls({
  card, params, setParam,
}: {
  card: ModelCard;
  params: Record<string, string | number | boolean>;
  setParam: (k: string, v: string | number | boolean) => void;
}) {
  return (
    <>
      {card.models && chips(t("variant"), card.models.map((m) => m[0]),
        params.model as string,
        (v) => card.models!.find((m) => m[0] === v)?.[1] ?? v,
        (v) => setParam("model", v))}
      {card.qualities && chips(t("quality"), card.qualities,
        params.quality as string, (v) => v.toUpperCase(), (v) => setParam("quality", v))}
      {card.ratios && chips(t("aspect_ratio"), card.ratios,
        params.ratio as string, (v) => v, (v) => setParam("ratio", v))}
      {card.durations && chips(t("duration"), card.durations,
        params.duration as number, (v) => `${v}s`, (v) => setParam("duration", v))}
      {card.resolutions && chips(t("resolution"), card.resolutions,
        params.res as string, (v) => v, (v) => setParam("res", v))}
      {card.modes && chips(t("mode"), card.modes.map((m) => m[0]),
        params.mode as string,
        (v) => card.modes!.find((m) => m[0] === v)?.[1] ?? v,
        (v) => setParam("mode", v))}

      <div className="btn-row">
        {(["audio", "fourk", "seed", "prompt_enhance"] as const).map((flag) =>
          card[flag] ? (
            <button key={flag} className={`btn-sm ${params[FLAG_PARAM[flag]] ? "on" : ""}`}
              onClick={() => setParam(FLAG_PARAM[flag], !params[FLAG_PARAM[flag]])}>
              {t(`flag_${flag}`)}
            </button>
          ) : null,
        )}
      </div>
    </>
  );
}
