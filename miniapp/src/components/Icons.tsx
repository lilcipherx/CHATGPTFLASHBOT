/** Crisp inline line-icons (stroke = currentColor) — replace emoji in the nav
 *  so the chrome looks consistent across iOS/Android/desktop Telegram. */
type Props = { name: "home" | "trends" | "create" | "history" | "profile"; size?: number };

const PATHS: Record<Props["name"], JSX.Element> = {
  create: (
    <>
      <path d="M12 3.2l1.9 5.4 5.4 1.9-5.4 1.9L12 17.8l-1.9-5.4L4.7 10.5l5.4-1.9z" />
      <path d="M18.5 15.5l.7 2 2 .7-2 .7-.7 2-.7-2-2-.7 2-.7z" />
    </>
  ),
  home: (
    <>
      <path d="M3 9.5 12 3l9 6.5" />
      <path d="M5 8.8V20a1 1 0 0 0 1 1h12a1 1 0 0 0 1-1V8.8" />
      <path d="M9.5 21v-6h5v6" />
    </>
  ),
  trends: (
    <>
      <polyline points="3 16.5 9 10.5 13 14.5 21 6.5" />
      <polyline points="15 6.5 21 6.5 21 12.5" />
    </>
  ),
  history: (
    <>
      <circle cx="12" cy="12" r="9" />
      <polyline points="12 7 12 12 15.5 14" />
    </>
  ),
  profile: (
    <>
      <circle cx="12" cy="8" r="4" />
      <path d="M5 21v-1.5A4.5 4.5 0 0 1 9.5 15h5a4.5 4.5 0 0 1 4.5 4.5V21" />
    </>
  ),
};

export function Icon({ name, size = 23 }: Props) {
  return (
    <svg
      width={size}
      height={size}
      viewBox="0 0 24 24"
      fill="none"
      stroke="currentColor"
      strokeWidth="1.7"
      strokeLinecap="round"
      strokeLinejoin="round"
    >
      {PATHS[name]}
    </svg>
  );
}
