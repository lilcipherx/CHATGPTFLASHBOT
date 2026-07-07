import WebApp from "@twa-dev/sdk";
import { useEffect, useRef, useState } from "react";
import { api, Banner, CarouselBehavior, mediaUrl } from "../api/client";
import { t, onLangChange } from "../i18n";
import { haptic } from "../theme";

const DEFAULT_BEHAVIOR: CarouselBehavior = {
  animation: "slide", speed_ms: 400, autoplay: true, pause_on_interaction: true,
  loop: true, show_indicators: true, show_arrows: false, manual_swipe: true,
};

/** Admin-managed promo carousel shown at the top of the home screen. Slides, the
 *  rotation interval AND the render behaviour (animation/autoplay/loop/indicators/
 *  arrows/swipe/speed) all come from the backend (/api/banners) so the admin
 *  "Настройки карусели" panel is authoritative. Engagement (impression on show,
 *  click on tap) is reported back for the admin CTR. */
export function Carousel() {
  const [slides, setSlides] = useState<Banner[]>([]);
  const [interval, setIntervalMs] = useState(5000);
  const [behavior, setBehavior] = useState<CarouselBehavior>(DEFAULT_BEHAVIOR);
  const [idx, setIdx] = useState(0);
  const [paused, setPaused] = useState(false);
  const timer = useRef<number | null>(null);
  const drag = useRef<{ x: number; active: boolean }>({ x: 0, active: false });
  const seen = useRef<Set<number>>(new Set());  // slide ids already counted this session

  useEffect(() => {
    let cancelled = false;
    const load = () => {
      api.banners()
        .then((d) => {
          if (cancelled) return;
          // FIX: null-safety - a null/missing slides array would make slides.length
          // crash the home screen; interval_ms omitted would give a NaN timeout.
          setSlides(d.slides ?? []);
          setIntervalMs(d.interval_ms ?? 5000);
          if (d.behavior) setBehavior({ ...DEFAULT_BEHAVIOR, ...d.behavior });
        })
        .catch(() => { if (!cancelled) setSlides([]); });
    };
    load();
    // FIX: AUDIT13-M17 - re-fetch banners when the language changes (e.g. /profile
    // syncs a different bot-side language_code after mount). api.banners() uses live
    // getLang(), but the effect only ran once, so banner titles/images stayed frozen
    // in the initial language.
    const off = onLangChange(load);
    return () => { cancelled = true; off(); };
  }, []);

  // Count one impression per slide the first time it is shown (deduped per session,
  // so the autoplay timer can't inflate the number). Fire-and-forget.
  useEffect(() => {
    const s = slides[idx];
    if (!s || seen.current.has(s.id)) return;
    seen.current.add(s.id);
    api.bannerImpression(s.id).catch(() => {});
  }, [idx, slides]);

  // Auto-advance, re-armed on every idx change so a manual nav restarts the
  // countdown. Honours autoplay + pause_on_interaction.
  useEffect(() => {
    if (!behavior.autoplay || paused || slides.length <= 1) return;
    timer.current = window.setTimeout(
      () => setIdx((i) => (i + 1) % slides.length),
      Math.max(1500, interval),
    );
    return () => { if (timer.current) window.clearTimeout(timer.current); };
  }, [slides.length, interval, idx, behavior.autoplay, paused]);

  if (slides.length === 0) return null;

  const n = slides.length;
  const go = (i: number) => {
    haptic();
    setIdx(behavior.loop ? (i + n) % n : Math.max(0, Math.min(n - 1, i)));
  };

  function onStart(x: number) {
    if (!behavior.manual_swipe) return;
    drag.current = { x, active: true };
    if (behavior.pause_on_interaction) setPaused(true);
  }
  function onEnd(x: number) {
    if (!drag.current.active) return;
    const dx = x - drag.current.x;
    drag.current.active = false;
    if (behavior.pause_on_interaction) setPaused(false);
    if (Math.abs(dx) > 40) go(idx + (dx < 0 ? 1 : -1));
  }
  function onTap(s: Banner) {
    api.bannerClick(s.id).catch(() => {});
    if (s.link_url) { haptic(); WebApp.openLink(s.link_url); }
  }

  return (
    <div className="carousel">
      <div
        className={"carousel-track " + behavior.animation}
        style={{
          ["--mc-speed" as string]: `${behavior.speed_ms / 1000}s`,
          ...(behavior.animation === "slide" ? { transform: `translateX(-${idx * 100}%)` } : {}),
        }}
        onMouseEnter={() => behavior.pause_on_interaction && setPaused(true)}
        onMouseLeave={() => behavior.pause_on_interaction && setPaused(false)}
        onTouchStart={(e) => onStart(e.touches[0].clientX)}
        onTouchEnd={(e) => onEnd(e.changedTouches[0].clientX)}
        onMouseDown={(e) => onStart(e.clientX)}
        onMouseUp={(e) => onEnd(e.clientX)}
      >
        {slides.map((s, i) => (
          <div
            key={s.id}
            className={"carousel-slide" + (i === idx ? " on" : "")}
            style={behavior.animation === "fade" ? { opacity: i === idx ? 1 : 0 } : undefined}
            onClick={() => onTap(s)}
          >
            {/* Eager, not lazy: a carousel is a tiny above-the-fold set, and lazy
                loading left off-screen slides (incl. a just-uploaded last slide)
                blank until the user rotated to them — reading as "my photo isn't
                showing". Preload all so every slide is ready before it's revealed. */}
            <img src={mediaUrl(s.image_url)} alt={s.title ?? s.subtitle ?? t("promo_banner")} draggable={false} loading="eager" decoding="async" />
            {(s.title || s.subtitle) && (
              <div className="carousel-cap">
                {s.title && <b>{s.title}</b>}
                {s.subtitle && <span>{s.subtitle}</span>}
              </div>
            )}
          </div>
        ))}
      </div>

      {behavior.show_arrows && n > 1 && (
        <>
          <button className="carousel-arrow l" onClick={() => go(idx - 1)} aria-label={t("prev")}>‹</button>
          <button className="carousel-arrow r" onClick={() => go(idx + 1)} aria-label={t("next")}>›</button>
        </>
      )}

      {behavior.show_indicators && n > 1 && (
        <div className="carousel-dots">
          {slides.map((s, i) => (
            <button
              key={s.id}
              className={i === idx ? "on" : ""}
              onClick={() => go(i)}
              aria-label={`slide ${i + 1}`}
            />
          ))}
        </div>
      )}
    </div>
  );
}
