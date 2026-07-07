import { useState } from "react";
import { EffectKind, EffectSummary } from "../api/client";
import { Carousel } from "../components/Carousel";
import { CreateSheet } from "../components/CreateSheet";
import { EffectGrid } from "../components/EffectGrid";
import { t } from "../i18n";
import { haptic } from "../theme";

type Sections = { photo: boolean; video: boolean };
const ALL: EffectKind[] = ["video", "photo"];

export function Home({ onCredits, sections }: {
  onCredits?: (credits: number) => void;
  sections?: Sections;
}) {
  // Show only kinds with a working provider (sections undefined = still loading →
  // show all to avoid a flash of an empty screen).
  const avail = ALL.filter((s) => (sections ? sections[s] : true));
  const [kind, setKind] = useState<EffectKind>("video");
  const activeKind = avail.includes(kind) ? kind : (avail[0] ?? "video");
  const [picked, setPicked] = useState<EffectSummary | null>(null);

  return (
    <div className="content">
      <Carousel />

      <div className="banner">
        <span className="kicker">AI Studio</span>
        <b>{t("banner_title")}</b>
        <p>{t("banner_sub")}</p>
        <button className="cta" onClick={() => { haptic(); window.scrollBy({ top: 360, behavior: "smooth" }); }}>
          {t("banner_cta")}
        </button>
      </div>

      {avail.length === 0 ? (
        <div className="center">{t("section_off")}</div>
      ) : (
        <>
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

          <EffectGrid kind={activeKind} onPick={setPicked} />
        </>
      )}

      {picked && <CreateSheet effect={picked} onClose={() => setPicked(null)} onCredits={onCredits} />}
    </div>
  );
}
