import type { CSSProperties } from "react";

/** Stable string hash → uint32. */
function hash(s: string): number {
  let h = 2166136261;
  for (let i = 0; i < s.length; i++) {
    h ^= s.charCodeAt(i);
    h = Math.imul(h, 16777619);
  }
  return h >>> 0;
}

/**
 * Deterministic "cinematic poster" gradient for an effect card that has no real
 * preview image. Each effect gets its own rich, dark, Higgsfield-style mesh so
 * the catalog looks intentionally art-directed rather than empty.
 */
export function posterStyle(seed: string | number): CSSProperties {
  const h = hash(String(seed));
  const hue = h % 360;
  const hue2 = (hue + 30 + ((h >> 5) % 70)) % 360;
  const angle = 120 + (h % 80);
  return {
    background: `
      radial-gradient(115% 115% at 20% 16%, hsl(${hue} 66% 32%), transparent 58%),
      radial-gradient(125% 125% at 84% 88%, hsl(${hue2} 60% 26%), transparent 55%),
      linear-gradient(${angle}deg, hsl(${hue} 28% 14%), #0a0a0c 74%)
    `,
  };
}
