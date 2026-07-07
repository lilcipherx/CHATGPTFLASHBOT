import { describe, expect, it, vi } from "vitest";

// The Telegram SDK isn't available in jsdom — mock it so i18n's language pick
// (which reads WebApp.initDataUnsafe at import) resolves deterministically.
vi.mock("@twa-dev/sdk", () => ({
  default: {
    initDataUnsafe: { user: { language_code: "ru" } },
    ready: () => {},
    expand: () => {},
  },
}));

import { LANG, MESSAGES, t } from "../i18n";

describe("i18n", () => {
  it("defaults to ru and translates a known key", () => {
    expect(LANG).toBe("ru");
    expect(t("tab_home")).toBe("Главная");
  });

  it("falls back to the raw key when missing in all dicts", () => {
    expect(t("____missing_key____")).toBe("____missing_key____");
  });

  it("substitutes {param} placeholders", () => {
    expect(t("cost {n}", { n: 5 })).toBe("cost 5");
  });

  it("interpolates by_author", () => {
    expect(t("by_author", { name: "ann" })).toBe("от ann"); // ru
  });

  it("every locale defines the same keys as ru (no silent RU fallback)", () => {
    const ruKeys = Object.keys(MESSAGES.ru).sort();
    for (const code of Object.keys(MESSAGES)) {
      const keys = Object.keys(MESSAGES[code]).sort();
      const missing = ruKeys.filter((k) => !keys.includes(k));
      expect(missing, `${code} is missing keys`).toEqual([]);
    }
  });
});
