/**
 * Create Media — каталог «Элементов» (§4 ТЗ). Каждый элемент при выборе
 * дописывает в промпт короткую англоязычную фразу (модели лучше понимают
 * английские дескрипторы) — как reference-подсказка стиля/камеры/света и т.д.
 *
 * Данные вынесены отдельно от UI, чтобы расширять каталог (или позже заменить
 * на серверный список / реальные @image-reference) без правок компонентов.
 * Категории и элементы намеренно на английском — это доменные термины генерации,
 * идентичные интерфейсу Higgsfield/Runway; локализуется только UI-обвязка.
 */
export interface ElementItem {
  /** Ярлык на чипе. */
  label: string;
  /** Фраза, дописываемая в промпт. */
  insert: string;
}
export interface ElementCategory {
  id: string;
  /** Короткий значок для таба категории. */
  icon: string;
  label: string;
  items: ElementItem[];
}

export const ELEMENT_CATEGORIES: ElementCategory[] = [
  {
    id: "style", icon: "🎨", label: "Style",
    items: [
      { label: "Cinematic", insert: "cinematic style" },
      { label: "Ultra Realistic", insert: "ultra realistic" },
      { label: "Anime", insert: "anime style" },
      { label: "Cyberpunk", insert: "cyberpunk aesthetic" },
      { label: "3D Render", insert: "3d render" },
      { label: "Vintage Film", insert: "vintage film look" },
    ],
  },
  {
    id: "camera", icon: "🎥", label: "Camera",
    items: [
      { label: "Close-up", insert: "close-up shot" },
      { label: "Wide", insert: "wide angle shot" },
      { label: "Drone", insert: "aerial drone shot" },
      { label: "Tracking", insert: "tracking shot" },
      { label: "Low Angle", insert: "low angle" },
    ],
  },
  {
    id: "lighting", icon: "💡", label: "Lighting",
    items: [
      { label: "Golden Hour", insert: "golden hour lighting" },
      { label: "Neon", insert: "neon lighting" },
      { label: "Studio", insert: "studio lighting" },
      { label: "Backlight", insert: "dramatic backlight" },
      { label: "Soft", insert: "soft diffused light" },
    ],
  },
  {
    id: "background", icon: "🌆", label: "Background",
    items: [
      { label: "City", insert: "city background" },
      { label: "Nature", insert: "nature background" },
      { label: "Studio", insert: "studio backdrop" },
      { label: "Abstract", insert: "abstract background" },
    ],
  },
  {
    id: "pose", icon: "🕺", label: "Pose",
    items: [
      { label: "Dynamic", insert: "dynamic pose" },
      { label: "Walking", insert: "walking" },
      { label: "Portrait", insert: "portrait pose" },
      { label: "Action", insert: "action pose" },
    ],
  },
];
