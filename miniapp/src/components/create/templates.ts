/**
 * Create Media — быстрые шаблоны промпта (§11 ТЗ). Стартовые заготовки в один
 * тап: вставляются в поле промпта как отправная точка, которую можно доредактировать.
 * Данные отделены от UI — каталог легко расширять или заменить на серверный/
 * персональный список (§13 «Prompt Templates»). Текст англоязычный: модели лучше
 * понимают английские описания.
 */
export interface PromptTemplate {
  label: string;
  text: string;
}

export const PROMPT_TEMPLATES: PromptTemplate[] = [
  { label: "Astronaut", text: "A cinematic astronaut walking through Tokyo at night, ultra realistic" },
  { label: "Portrait", text: "Close-up portrait in golden hour light, shallow depth of field" },
  { label: "Dragon", text: "Epic fantasy dragon flying over mountains, dramatic clouds" },
  { label: "Cyberpunk", text: "Cyberpunk city street, neon reflections, rain, cinematic" },
  { label: "Product", text: "Product shot on a clean studio background, soft lighting" },
  { label: "Anime", text: "Anime style character, vibrant colors, dynamic pose" },
];
