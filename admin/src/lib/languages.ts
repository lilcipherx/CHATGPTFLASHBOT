// Telegram language_code → human label for the language filter / geo panel.
// Telegram sends BCP-47-ish codes ("ru", "en", "pt-br", "zh-hans"); we key off the
// base subtag. Each language maps to a representative flag + native name; unknown
// codes fall back to the raw code.

const LANGS: Record<string, { flag: string; name: string }> = {
  ru: { flag: "🇷🇺", name: "Русский" },
  en: { flag: "🇬🇧", name: "English" },
  es: { flag: "🇪🇸", name: "Español" },
  fr: { flag: "🇫🇷", name: "Français" },
  pt: { flag: "🇵🇹", name: "Português" },
  uz: { flag: "🇺🇿", name: "Oʻzbek" },
  ar: { flag: "🇸🇦", name: "العربية" },
  zh: { flag: "🇨🇳", name: "中文" },
  de: { flag: "🇩🇪", name: "Deutsch" },
  it: { flag: "🇮🇹", name: "Italiano" },
  tr: { flag: "🇹🇷", name: "Türkçe" },
  fa: { flag: "🇮🇷", name: "فارسی" },
  hi: { flag: "🇮🇳", name: "हिन्दी" },
  id: { flag: "🇮🇩", name: "Indonesia" },
  kk: { flag: "🇰🇿", name: "Қазақ" },
  uk: { flag: "🇺🇦", name: "Українська" },
  pl: { flag: "🇵🇱", name: "Polski" },
  ky: { flag: "🇰🇬", name: "Кыргызча" },
  tg: { flag: "🇹🇯", name: "Тоҷикӣ" },
  az: { flag: "🇦🇿", name: "Azərbaycan" },
  hy: { flag: "🇦🇲", name: "Հայերեն" },
  ka: { flag: "🇬🇪", name: "ქართული" },
  be: { flag: "🇧🇾", name: "Беларуская" },
  ja: { flag: "🇯🇵", name: "日本語" },
  ko: { flag: "🇰🇷", name: "한국어" },
};

function base(code: string): string {
  return (code || "").trim().toLowerCase().split(/[-_]/)[0];
}

export function languageName(code: string): string {
  const b = base(code);
  return LANGS[b]?.name || b.toUpperCase() || "—";
}

/** "🇷🇺 Русский" — flag + native name, for option labels. */
export function languageLabel(code: string): string {
  const b = base(code);
  const meta = LANGS[b];
  return meta ? `${meta.flag} ${meta.name}` : (b.toUpperCase() || "—");
}
