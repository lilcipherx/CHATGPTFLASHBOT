import WebApp from "@twa-dev/sdk";
import { useEffect, useState } from "react";
import { api, BonusStatus, ReferralInfo } from "../api/client";
import { t } from "../i18n";
import { haptic } from "../theme";

// Daily login-streak bonus + referral link, surfaced in the Mini App profile so
// users don't have to switch back to the bot to claim or invite.
export function BonusReferral({ onClaimed }: { onClaimed?: () => void }) {
  const [bonus, setBonus] = useState<BonusStatus | null>(null);
  const [ref, setRef] = useState<ReferralInfo | null>(null);
  const [busy, setBusy] = useState(false);
  const [note, setNote] = useState("");

  useEffect(() => {
    api.bonusStatus().then(setBonus).catch(() => {});
    api.referrals().then(setRef).catch(() => {});
  }, []);

  async function claim() {
    if (busy || !bonus?.can_claim) return;
    haptic("medium");
    setBusy(true);
    try {
      const r = await api.bonusClaim();
      if (r.claimed) {
        setNote(t("bonus_got", { n: r.amount, s: r.streak }));
        haptic("heavy");
        onClaimed?.();
      } else {
        setNote(t("bonus_already", { s: r.streak }));
      }
      setBonus({ can_claim: false, streak: r.streak, next_amount: 0 });
    } catch {
      // FIX: AUDIT-63 - show error instead of silent
      setNote(t("failed"));
    } finally {
      setBusy(false);
    }
  }

  function invite() {
    if (!ref?.link) return;
    haptic();
    // Telegram's native share sheet with the user's referral link prefilled.
    WebApp.openTelegramLink(`https://t.me/share/url?url=${encodeURIComponent(ref.link)}`);
  }

  return (
    <div>
      <div className="section-title">{t("bonus_title")}</div>
      <button
        className="btn accent"
        style={{ width: "100%" }}
        disabled={busy || !bonus?.can_claim}
        onClick={claim}
      >
        {bonus?.can_claim
          ? t("bonus_claim", { n: bonus.next_amount })
          : t("bonus_already", { s: bonus?.streak ?? 0 })}
      </button>
      {note && <div className="muted" style={{ marginTop: 6 }}>{note}</div>}

      <div className="section-title" style={{ marginTop: 16 }}>{t("ref_title")}</div>
      <div className="list">
        <div className="item"><span>{t("ref_invited", { n: ref?.invited ?? 0 })}</span></div>
        <div className="item"><span>{t("ref_earned", { n: ref?.earned ?? 0 })}</span></div>
      </div>
      <button className="btn secondary" style={{ width: "100%" }} onClick={invite} disabled={!ref?.link}>
        {t("ref_share")}
      </button>
    </div>
  );
}
