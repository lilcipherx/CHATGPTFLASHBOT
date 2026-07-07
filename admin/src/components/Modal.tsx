import { ReactNode, useEffect, useRef } from "react";
import { createPortal } from "react-dom";

/** Design-system modal dialog. Closes on backdrop click or Esc. */
export function Modal({ title, icon, onClose, children, footer, wide }: {
  title: string;
  icon?: string;
  onClose: () => void;
  children: ReactNode;
  footer?: ReactNode;
  wide?: boolean;
}) {
  const cardRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    // FIX: AUDIT-LOW - focus trap + focus restore. Remember what was focused before
    // the dialog opened, move focus into the dialog, keep Tab inside it, and restore
    // focus on close (aria-modal="true" previously advertised trapping that wasn't
    // implemented, so keyboard/screen-reader users could Tab out behind the backdrop).
    const prevFocused = document.activeElement as HTMLElement | null;
    const focusables = () =>
      Array.from(
        cardRef.current?.querySelectorAll<HTMLElement>(
          'a[href], button:not([disabled]), textarea:not([disabled]), input:not([disabled]), select:not([disabled]), [tabindex]:not([tabindex="-1"])'
        ) ?? []
      );
    // Focus the first field, else the dialog card itself.
    (focusables()[0] ?? cardRef.current)?.focus();

    const onKey = (e: KeyboardEvent) => {
      if (e.key === "Escape") { onClose(); return; }
      if (e.key !== "Tab") return;
      const items = focusables();
      if (items.length === 0) { e.preventDefault(); cardRef.current?.focus(); return; }
      const first = items[0];
      const last = items[items.length - 1];
      const active = document.activeElement;
      if (e.shiftKey && (active === first || !cardRef.current?.contains(active))) {
        e.preventDefault(); last.focus();
      } else if (!e.shiftKey && active === last) {
        e.preventDefault(); first.focus();
      }
    };
    window.addEventListener("keydown", onKey);
    // FIX: AUDIT-37 - lock body scroll while modal is open
    const prev = document.body.style.overflow;
    document.body.style.overflow = "hidden";
    return () => {
      window.removeEventListener("keydown", onKey);
      document.body.style.overflow = prev;
      prevFocused?.focus?.();
    };
  }, [onClose]);

  // FIX: AUDIT-37 - render via createPortal to document.body + aria-labelledby
  return createPortal(
    <div className="modal-backdrop" onClick={onClose}>
      <div ref={cardRef} tabIndex={-1} className={"modal-card" + (wide ? " wide" : "")} role="dialog" aria-modal="true" aria-labelledby="modal-title"
        onClick={(e) => e.stopPropagation()}>
        <div className="modal-head">
          <div id="modal-title" className="panel-title" style={{ margin: 0 }}>
            {icon && <span className="ms sm">{icon}</span>} {title}
          </div>
          <button className="btn ghost sm" onClick={onClose} aria-label="Закрыть"><span className="ms sm">close</span></button>
        </div>
        {children}
        {footer && <div className="toolbar" style={{ marginTop: "var(--sp-5)", marginBottom: 0 }}>{footer}</div>}
      </div>
    </div>,
    document.body
  );
}
