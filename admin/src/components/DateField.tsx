import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { createPortal } from "react-dom";

/**
 * Design-system date picker — drop-in replacement for `<input type="date">`. The
 * native control's popup is rendered by the OS and can only be coarsely themed
 * (`color-scheme: dark`), so it never carries the acid-lime accent. This renders
 * its own month grid (portalled to <body>, fixed-positioned, flips up when there
 * is no room below, closes on outside-click / Escape) with the selected day filled
 * in `--accent` and today ringed.
 *
 * Contract matches the native input it replaces: `value` is a "YYYY-MM-DD" string
 * (or "" for empty) and `onChange` receives the same. All date math is done on
 * local Y/M/D integers — never `new Date(isoString)` — so a day never shifts by a
 * timezone offset.
 */
const WEEKDAYS = ["Пн", "Вт", "Ср", "Чт", "Пт", "Сб", "Вс"];
const MONTHS = [
  "Январь", "Февраль", "Март", "Апрель", "Май", "Июнь",
  "Июль", "Август", "Сентябрь", "Октябрь", "Ноябрь", "Декабрь",
];
const GAP = 6;
const MENU_W = 264;
const MENU_H = 332;
const ANIM_MS = 130;

interface YMD { y: number; m: number; d: number; }

const pad = (n: number) => String(n).padStart(2, "0");
const toIso = ({ y, m, d }: YMD) => `${y}-${pad(m)}-${pad(d)}`;
const toDisplay = ({ y, m, d }: YMD) => `${pad(d)}.${pad(m)}.${y}`;

function parseIso(value: string): YMD | null {
  const match = /^(\d{4})-(\d{2})-(\d{2})$/.exec(value || "");
  if (!match) return null;
  const y = +match[1], m = +match[2], d = +match[3];
  if (m < 1 || m > 12 || d < 1 || d > 31) return null;
  return { y, m, d };
}

interface Pos { left: number; top?: number; bottom?: number; }

export function DateField({
  value,
  onChange,
  placeholder = "дд.мм.гггг",
  title,
  ariaLabel,
  style,
}: {
  value: string;
  onChange: (value: string) => void;
  placeholder?: string;
  title?: string;
  ariaLabel?: string;
  style?: React.CSSProperties;
}) {
  const [open, setOpen] = useState(false);
  const [show, setShow] = useState(false);
  const [mode, setMode] = useState<"days" | "years">("days");
  const [pos, setPos] = useState<Pos | null>(null);
  const wrapRef = useRef<HTMLDivElement>(null);
  const menuRef = useRef<HTMLDivElement>(null);
  const closeTimer = useRef<number | null>(null);

  const selected = useMemo(() => parseIso(value), [value]);
  const today = useMemo<YMD>(() => {
    const n = new Date();
    return { y: n.getFullYear(), m: n.getMonth() + 1, d: n.getDate() };
  }, []);
  // Year dropdown range so the user can jump straight to any year (e.g. 10 years back)
  // in one click instead of paging month-by-month through the chevrons.
  const years = useMemo(() => {
    const list: number[] = [];
    for (let y = today.y - 30; y <= today.y + 2; y++) list.push(y);
    return list;
  }, [today]);

  // The month currently shown in the grid (independent of the selected value so
  // the user can browse other months without changing the selection).
  const [view, setView] = useState<{ y: number; m: number }>(() => {
    const base = selected ?? today;
    return { y: base.y, m: base.m };
  });

  const computePos = useCallback(() => {
    const el = wrapRef.current;
    if (!el) return;
    const r = el.getBoundingClientRect();
    const vw = window.innerWidth, vh = window.innerHeight;
    const flipUp = vh - r.bottom - GAP < MENU_H && r.top - GAP > vh - r.bottom;
    const left = Math.max(8, Math.min(r.left, vw - MENU_W - 8));
    setPos({
      left,
      top: flipUp ? undefined : r.bottom + GAP,
      bottom: flipUp ? vh - r.top + GAP : undefined,
    });
  }, []);

  const closeMenu = useCallback(() => {
    setShow(false);
    if (closeTimer.current) clearTimeout(closeTimer.current);
    closeTimer.current = window.setTimeout(() => { setOpen(false); closeTimer.current = null; }, ANIM_MS);
  }, []);

  const openMenu = useCallback(() => {
    if (closeTimer.current) { clearTimeout(closeTimer.current); closeTimer.current = null; }
    const base = parseIso(value) ?? today;
    setView({ y: base.y, m: base.m });
    setMode("days");
    computePos();
    setOpen(true);
  }, [computePos, value, today]);

  useEffect(() => {
    if (!open) return;
    const id = requestAnimationFrame(() => setShow(true));
    return () => cancelAnimationFrame(id);
  }, [open]);

  useEffect(() => {
    if (!open) return;
    function onDown(e: MouseEvent) {
      const t = e.target as Node;
      if (wrapRef.current?.contains(t) || menuRef.current?.contains(t)) return;
      closeMenu();
    }
    function onKey(e: KeyboardEvent) { if (e.key === "Escape") closeMenu(); }
    let raf = 0;
    function reflow() { cancelAnimationFrame(raf); raf = requestAnimationFrame(computePos); }
    document.addEventListener("mousedown", onDown);
    document.addEventListener("keydown", onKey);
    window.addEventListener("scroll", reflow, true);
    window.addEventListener("resize", reflow);
    return () => {
      document.removeEventListener("mousedown", onDown);
      document.removeEventListener("keydown", onKey);
      window.removeEventListener("scroll", reflow, true);
      window.removeEventListener("resize", reflow);
      cancelAnimationFrame(raf);
    };
  }, [open, closeMenu, computePos]);

  useEffect(() => () => { if (closeTimer.current) clearTimeout(closeTimer.current); }, []);

  function shiftMonth(delta: number) {
    setView((v) => {
      const idx = (v.y * 12 + (v.m - 1)) + delta;
      return { y: Math.floor(idx / 12), m: (idx % 12) + 1 };
    });
  }

  function pick(d: number) {
    onChange(toIso({ y: view.y, m: view.m, d }));
    closeMenu();
  }

  function pickToday() {
    onChange(toIso(today));
    closeMenu();
  }

  // Monday-first grid: leading blanks for the weekday of the 1st, then each day.
  const firstWeekday = (new Date(view.y, view.m - 1, 1).getDay() + 6) % 7;
  const daysInMonth = new Date(view.y, view.m, 0).getDate();
  const cells: (number | null)[] = [
    ...Array.from({ length: firstWeekday }, () => null),
    ...Array.from({ length: daysInMonth }, (_, i) => i + 1),
  ];

  const isSelected = (d: number) =>
    !!selected && selected.y === view.y && selected.m === view.m && selected.d === d;
  const isToday = (d: number) =>
    today.y === view.y && today.m === view.m && today.d === d;

  return (
    <div className="select datefield" ref={wrapRef} style={style}>
      <button
        type="button"
        className={"select-btn datefield-btn" + (open ? " open" : "")}
        aria-haspopup="dialog"
        aria-expanded={open}
        aria-label={ariaLabel ?? title}
        title={title}
        onClick={() => (open ? closeMenu() : openMenu())}
      >
        <span className={"select-val" + (selected ? "" : " datefield-ph")}>
          {selected ? toDisplay(selected) : placeholder}
        </span>
        {selected && (
          <span
            className="ms sm datefield-clear"
            role="button"
            aria-label="Очистить"
            onClick={(e) => { e.stopPropagation(); onChange(""); }}
          >
            close
          </span>
        )}
        <span className="ms sm select-caret">calendar_month</span>
      </button>

      {open && pos &&
        createPortal(
          <div
            ref={menuRef}
            role="dialog"
            className={"select-menu dfc-pop" + (show ? " show" : "")}
            style={{ position: "fixed", left: pos.left, top: pos.top, bottom: pos.bottom, width: MENU_W }}
          >
            <div className="dfc-head">
              {/* chevrons page months only in day view; the year view shows every year
                  at once, so they'd have nothing to do there. */}
              {mode === "days" ? (
                <button type="button" className="dfc-nav" aria-label="Предыдущий месяц" onClick={() => shiftMonth(-1)}>
                  <span className="ms sm">chevron_left</span>
                </button>
              ) : <span className="dfc-nav-spacer" />}
              {/* the year is a button: tap it to switch to the year grid and back */}
              <span className="dfc-title">
                {mode === "days" && <span>{MONTHS[view.m - 1]} </span>}
                <button
                  type="button"
                  className={"dfc-year-btn" + (mode === "years" ? " on" : "")}
                  aria-label="Выбрать год"
                  onClick={() => setMode((m) => (m === "years" ? "days" : "years"))}
                >
                  {view.y}
                </button>
              </span>
              {mode === "days" ? (
                <button type="button" className="dfc-nav" aria-label="Следующий месяц" onClick={() => shiftMonth(1)}>
                  <span className="ms sm">chevron_right</span>
                </button>
              ) : <span className="dfc-nav-spacer" />}
            </div>
            {mode === "years" ? (
              <div className="dfc-grid dfc-years">
                {years.map((y) => (
                  <button
                    type="button"
                    key={y}
                    className={"dfc-cell dfc-year-cell" + (y === view.y ? " selected" : "") + (y === today.y ? " today" : "")}
                    onClick={() => { setView((v) => ({ ...v, y })); setMode("days"); }}
                  >
                    {y}
                  </button>
                ))}
              </div>
            ) : (
              <>
                <div className="dfc-grid dfc-wd">
                  {WEEKDAYS.map((w) => <span key={w} className="dfc-wd-cell">{w}</span>)}
                </div>
                {/* FIX: UI-11 - removed a broken arrow-key handler (AUDIT-54): it did
                    `const cells = cells.length` (self-reference → "Cannot access 'cells'
                    before initialization" TDZ crash) and read `view.d` which doesn't
                    exist on the {y,m} view. Pressing an arrow key in the open calendar
                    crashed the page. The calendar has no focused-day state, so real
                    keyboard day-navigation needs that added first; dates are pickable by
                    click meanwhile. */}
                <div className="dfc-grid">
                  {cells.map((d, i) => d === null
                    ? <span key={`b${i}`} className="dfc-cell empty" />
                    : (
                      <button
                        type="button"
                        key={d}
                        className={"dfc-cell" + (isSelected(d) ? " selected" : "") + (isToday(d) ? " today" : "")}
                        onClick={() => pick(d)}
                      >
                        {d}
                      </button>
                    ))}
                </div>
              </>
            )}
            <div className="dfc-foot">
              <button type="button" className="dfc-today-btn" onClick={pickToday}>
                <span className="ms sm">today</span> Сегодня
              </button>
            </div>
          </div>,
          document.body,
        )}
    </div>
  );
}
