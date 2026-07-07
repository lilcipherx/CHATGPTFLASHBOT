import { useCallback, useEffect, useRef, useState } from "react";
import { createPortal } from "react-dom";

export interface SelectOption {
  value: string;
  label: string;
}

/** Build options from a plain string list (value === label). */
export const opts = (values: string[]): SelectOption[] =>
  values.map((v) => ({ value: v, label: v }));

interface MenuPos {
  left: number;
  width: number;
  placement: "down" | "up";
  /** distance from viewport top (down) — used as `top` */
  top?: number;
  /** distance from viewport bottom (up) — used as `bottom` */
  bottom?: number;
  maxHeight: number;
}

const GAP = 6;
const OPT_H = 40; // 38px row + 2px inter-row margin
const MENU_PAD = 8; // var(--sp-1) * 2
const ANIM_MS = 130;

/**
 * Design-system dropdown — replaces the native <select> so the OPEN menu is part
 * of the design system (the OS renders native option lists, which can't be
 * themed). Matches cards/buttons/inputs: token radius + surface, accent hover /
 * selected state, custom rotating chevron, animated open AND close.
 *
 * Robust behaviour: the menu is portalled to <body> with fixed positioning so no
 * ancestor `overflow` can clip it; it anchors strictly under the trigger, flips
 * upward when there isn't room below, and re-aligns on scroll/resize. Click
 * toggles, click-outside / Escape / option-select close it, and the document
 * mousedown listener guarantees only one dropdown is open at a time. Keyboard
 * accessible (Enter/Space/↑/↓/Esc). `width:auto` wrapper drops into a `.toolbar`;
 * pass `width` for a fixed control.
 */
export function Select({
  value,
  onChange,
  options,
  width,
  ariaLabel,
}: {
  value: string;
  onChange: (value: string) => void;
  options: SelectOption[];
  width?: number | string;
  ariaLabel?: string;
}) {
  const [open, setOpen] = useState(false);
  const [show, setShow] = useState(false); // drives the enter/exit transition
  const [active, setActive] = useState(0);
  const [pos, setPos] = useState<MenuPos | null>(null);
  const wrapRef = useRef<HTMLDivElement>(null);
  const menuRef = useRef<HTMLDivElement>(null);
  const closeTimer = useRef<number | null>(null);

  const selectedIndex = Math.max(0, options.findIndex((o) => o.value === value));
  const current = options[selectedIndex];

  const computePos = useCallback(() => {
    const btn = wrapRef.current;
    if (!btn) return;
    const r = btn.getBoundingClientRect();
    const vh = window.innerHeight;
    const spaceBelow = vh - r.bottom - GAP;
    const spaceAbove = r.top - GAP;
    const desired = options.length * OPT_H + MENU_PAD;
    const placement: "down" | "up" =
      spaceBelow < desired && spaceAbove > spaceBelow ? "up" : "down";
    const room = placement === "down" ? spaceBelow : spaceAbove;
    setPos({
      left: r.left,
      width: r.width,
      placement,
      top: placement === "down" ? r.bottom + GAP : undefined,
      bottom: placement === "up" ? vh - r.top + GAP : undefined,
      maxHeight: Math.max(120, Math.min(desired, room)),
    });
  }, [options.length]);

  const closeMenu = useCallback(() => {
    setShow(false);
    if (closeTimer.current) clearTimeout(closeTimer.current);
    closeTimer.current = window.setTimeout(() => {
      setOpen(false);
      closeTimer.current = null;
    }, ANIM_MS);
  }, []);

  const openMenu = useCallback(() => {
    if (closeTimer.current) {
      clearTimeout(closeTimer.current);
      closeTimer.current = null;
    }
    computePos();
    setActive(selectedIndex);
    setOpen(true);
  }, [computePos, selectedIndex]);

  // mount → next frame flips on the `.show` class so the CSS transition runs
  useEffect(() => {
    if (!open) return;
    const id = requestAnimationFrame(() => setShow(true));
    return () => cancelAnimationFrame(id);
  }, [open]);

  // outside-click (trigger + menu excluded), Escape, and re-align on scroll/resize
  useEffect(() => {
    if (!open) return;
    function onDown(e: MouseEvent) {
      const t = e.target as Node;
      if (wrapRef.current?.contains(t) || menuRef.current?.contains(t)) return;
      closeMenu();
    }
    let raf = 0;
    function reflow() {
      cancelAnimationFrame(raf);
      raf = requestAnimationFrame(computePos);
    }
    document.addEventListener("mousedown", onDown);
    window.addEventListener("scroll", reflow, true);
    window.addEventListener("resize", reflow);
    return () => {
      document.removeEventListener("mousedown", onDown);
      window.removeEventListener("scroll", reflow, true);
      window.removeEventListener("resize", reflow);
      cancelAnimationFrame(raf);
    };
  }, [open, closeMenu, computePos]);

  useEffect(() => () => {
    if (closeTimer.current) clearTimeout(closeTimer.current);
  }, []);

  function choose(i: number) {
    const opt = options[i];
    if (opt) onChange(opt.value);
    closeMenu();
  }

  function onKey(e: React.KeyboardEvent) {
    if (e.key === "ArrowDown") {
      e.preventDefault();
      if (open) setActive((a) => Math.min(a + 1, options.length - 1));
      else openMenu();
    } else if (e.key === "ArrowUp") {
      e.preventDefault();
      if (open) setActive((a) => Math.max(a - 1, 0));
      else openMenu();
    } else if (e.key === "Enter" || e.key === " ") {
      e.preventDefault();
      if (open) choose(active);
      else openMenu();
    } else if (e.key === "Escape") {
      if (open) {
        e.preventDefault();
        closeMenu();
      }
    } else if (e.key === "Tab" && open) {
      closeMenu();
    }
  }

  return (
    <div className="select" ref={wrapRef} style={width ? { width } : undefined}>
      <button
        type="button"
        className={"select-btn" + (open ? " open" : "")}
        aria-haspopup="listbox"
        aria-expanded={open}
        aria-label={ariaLabel}
        onClick={() => (open ? closeMenu() : openMenu())}
        onKeyDown={onKey}
      >
        <span className="select-val">{current?.label ?? ""}</span>
        <span className="ms sm select-caret">expand_more</span>
      </button>

      {open && pos &&
        createPortal(
          <div
            ref={menuRef}
            role="listbox"
            className={"select-menu" + (pos.placement === "up" ? " up" : "") + (show ? " show" : "")}
            style={{
              position: "fixed",
              left: pos.left,
              width: pos.width,
              top: pos.top,
              bottom: pos.bottom,
              maxHeight: pos.maxHeight,
            }}
          >
            {options.map((o, i) => (
              <button
                type="button"
                role="option"
                aria-selected={o.value === value}
                key={o.value}
                className={
                  "select-opt" +
                  (i === active ? " active" : "") +
                  (o.value === value ? " selected" : "")
                }
                onMouseEnter={() => setActive(i)}
                onClick={() => choose(i)}
              >
                <span className="select-opt-label">{o.label}</span>
                {o.value === value && <span className="ms sm select-check">check</span>}
              </button>
            ))}
          </div>,
          document.body,
        )}
    </div>
  );
}
