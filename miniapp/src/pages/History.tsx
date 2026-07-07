import WebApp from "@twa-dev/sdk";
import { useEffect, useState } from "react";
import { api, EffectKind, HistoryItem, mediaUrl } from "../api/client";
import { t } from "../i18n";
import { haptic } from "../theme";
import { posterStyle } from "../poster";

const STATUS_ICON: Record<string, string> = {
  pending: "⏳", processing: "⏳", complete: "✅", failed: "⚠️",
};

// FIX: null-safety - a null/missing/malformed created_at makes new Date(...) an
// "Invalid Date" (rendered literally) or the 1970 epoch; show nothing instead.
function fmtDate(v: string | null | undefined): string {
  if (!v) return "";
  const d = new Date(v);
  return Number.isNaN(d.getTime()) ? "" : d.toLocaleDateString();
}

export function History({
  onRecreate,
}: {
  onCredits?: (credits: number) => void;
  // §10 — replay one-click: hand the job's kind + preset to the Create page.
  onRecreate?: (kind: EffectKind, presetId: number) => void;
}) {
  const [items, setItems] = useState<HistoryItem[] | null>(null);
  // FIX: AUDIT12-5 - declare err/setErr (was: referenced in catch and render
  // without a useState declaration, causing a ReferenceError on any /api/jobs
  // failure and leaving the user stuck on the spinner forever).
  const [err, setErr] = useState(false);

  useEffect(() => {
    api.history().then(setItems).catch(() => { setItems([]); setErr(true); });  // FIX: AUDIT-3
  }, []);

  function rerun(it: HistoryItem) {
    if (it.preset_id == null) return;
    haptic("medium");
    onRecreate?.(it.kind, it.preset_id);
  }

  if (items === null) return <div className="center"><span className="spinner" /> {t("loading")}</div>;
  if (err) return <div className="center"><div>{t("err_server")}</div><button className="btn" onClick={() => { setErr(false); setItems(null); api.history().then(setItems).catch(() => { setItems([]); setErr(true); }); }}>{t("retry")}</button></div>;  {/* FIX: AUDIT13-L22 - reset items to null so the spinner shows during retry instead of a false "empty" flash */}
  if (items.length === 0) return <div className="center">🗂 {t("history_empty")}</div>;  // FIX: AUDIT-3

  return (
    <div className="content">
      <div className="grid">
        {items.map((it) => (
          <div key={it.id} className="card">
            <span className={`badge ${it.status === "complete" ? "new" : it.status === "failed" ? "ad" : "top"}`}>
              {STATUS_ICON[it.status] ?? ""}
            </span>
            <div
              className="card-tap"
              onClick={() => it.result_url && WebApp.openLink(mediaUrl(it.result_url))}
            >
              {it.result_url && it.kind === "photo" ? (
                <img className="thumb" src={mediaUrl(it.result_url)} alt="result" loading="lazy" decoding="async" />
              ) : (
                <div className="thumb-fallback poster" style={posterStyle(`${it.kind}-${it.id}`)}>
                  {it.kind === "video" && <span className="poster-play" />}
                </div>
              )}
            </div>
            <div className="label-overlay">
              <span>{fmtDate(it.created_at)}</span>
              {it.preset_id != null && (
                <button className="hist-redo" title={t("recreate")} onClick={() => rerun(it)}>↻ {t("recreate")}</button>
              )}
            </div>
          </div>
        ))}
      </div>
    </div>
  );
}
