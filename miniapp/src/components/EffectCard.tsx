import { EffectSummary, mediaUrl } from "../api/client";
import { t } from "../i18n";
import { posterStyle } from "../poster";
import { haptic } from "../theme";

const VIDEO_RE = /\.(mp4|webm|mov)(\?.*)?$/i;

export function EffectCard({ effect, onClick }: { effect: EffectSummary; onClick: () => void }) {
  const badge = effect.is_ad ? "ad" : effect.badge;
  const isVideo = !!effect.preview_url && VIDEO_RE.test(effect.preview_url);
  const src = mediaUrl(effect.preview_url);
  return (
    <button className="card" onClick={() => { haptic(); onClick(); }}>
      {badge && <span className={`badge ${badge}`}>{badge.toUpperCase()}</span>}
      {effect.preview_url ? (
        isVideo ? (
          <video className="thumb" src={src} muted loop autoPlay playsInline preload="metadata" />
        ) : (
          <img className="thumb" src={src} alt={effect.name} loading="lazy" decoding="async" />
        )
      ) : (
        <div className="thumb-fallback poster" style={posterStyle(`${effect.kind}-${effect.id}`)}>
          {effect.kind === "video" && <span className="poster-play" />}
        </div>
      )}
      <div className="label-overlay">
        <div className="card-name">{effect.name}</div>
        {effect.author && <div className="card-author">{t("by_author", { name: effect.author })}</div>}
      </div>
      <span className="card-go">{effect.price}✨</span>
    </button>
  );
}
