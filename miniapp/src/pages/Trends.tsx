import { useState } from "react";
import { EffectKind, EffectSummary } from "../api/client";
import { CreateSheet } from "../components/CreateSheet";
import { EffectGrid } from "../components/EffectGrid";
import { t } from "../i18n";
import { haptic } from "../theme";

type Sections = { photo: boolean; video: boolean };
const ALL: EffectKind[] = ["video", "photo"];

export function Trends({ onCredits, sections }: {
  onCredits?: (credits: number) => void;
  sections?: Sections;
}) {
  const avail = ALL.filter((s) => (sections ? sections[s] : true));
  const [kind, setKind] = useState<EffectKind>("video");
  const activeKind = avail.includes(kind) ? kind : (avail[0] ?? "video");
  const [picked, setPicked] = useState<EffectSummary | null>(null);

  if (avail.length === 0) {
    return <div className="content"><div className="center">{t("section_off")}</div></div>;
  }

  return (
    <div className="content">
      {avail.length > 1 && (
        <div className="segmented">
          {avail.map((s) => (
            <button
              key={s}
              className={`seg ${activeKind === s ? "active" : ""}`}
              onClick={() => { haptic(); setKind(s); }}
            >
              {t(s === "video" ? "seg_video" : "seg_photo")}
            </button>
          ))}
        </div>
      )}

      <EffectGrid kind={activeKind} trending onPick={setPicked} />

      {picked && <CreateSheet effect={picked} onClose={() => setPicked(null)} onCredits={onCredits} />}
    </div>
  );
}
