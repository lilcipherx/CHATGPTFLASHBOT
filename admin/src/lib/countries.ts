// ISO-3166 alpha-2 helpers for the user-country filter. Flags are derived
// algorithmically (no image assets); names cover the codes we actually see, with a
// graceful fallback to the raw code for anything not in the map.

/** Two-letter country code → flag emoji via Unicode regional-indicator letters. */
export function flagEmoji(code: string): string {
  const cc = (code || "").trim().toUpperCase();
  if (!/^[A-Z]{2}$/.test(cc)) return "🏳️";
  return String.fromCodePoint(...[...cc].map((c) => 0x1f1e6 + c.charCodeAt(0) - 65));
}

// Russian display names for the common codes. Not exhaustive — countryName() falls
// back to the code itself so an unmapped country still renders sanely.
const NAMES: Record<string, string> = {
  RU: "Россия", UZ: "Узбекистан", KZ: "Казахстан", UA: "Украина", BY: "Беларусь",
  KG: "Киргизия", TJ: "Таджикистан", TM: "Туркмения", AZ: "Азербайджан",
  AM: "Армения", GE: "Грузия", MD: "Молдова", US: "США", GB: "Великобритания",
  DE: "Германия", FR: "Франция", IT: "Италия", ES: "Испания", PT: "Португалия",
  NL: "Нидерланды", PL: "Польша", TR: "Турция", IN: "Индия", CN: "Китай",
  JP: "Япония", KR: "Южная Корея", BR: "Бразилия", CA: "Канада", AU: "Австралия",
  AE: "ОАЭ", SA: "Саудовская Аравия", IL: "Израиль", EG: "Египет", ID: "Индонезия",
  PK: "Пакистан", BD: "Бангладеш", VN: "Вьетнам", TH: "Таиланд", PH: "Филиппины",
  MX: "Мексика", AR: "Аргентина", CO: "Колумбия", CL: "Чили", NG: "Нигерия",
  ZA: "ЮАР", KE: "Кения", MA: "Марокко", RO: "Румыния", CZ: "Чехия",
  SE: "Швеция", FI: "Финляндия", NO: "Норвегия", DK: "Дания", CH: "Швейцария",
  AT: "Австрия", BE: "Бельгия", GR: "Греция", HU: "Венгрия", IE: "Ирландия",
  LT: "Литва", LV: "Латвия", EE: "Эстония", RS: "Сербия", BG: "Болгария",
};

export function countryName(code: string): string {
  const cc = (code || "").trim().toUpperCase();
  return NAMES[cc] || cc || "—";
}

/** "🇷🇺 Россия" — flag + name, for option labels. */
export function countryLabel(code: string): string {
  return `${flagEmoji(code)} ${countryName(code)}`;
}
