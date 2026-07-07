import { useEffect, useMemo, useRef, useState } from "react";
import { createPortal } from "react-dom";  // FIX: AUDIT-55

export interface CommandItem {
  id: string;
  label: string;
  icon: string;
  section: string;
}

/**
 * Cmd/Ctrl+K command palette (ТЗ §8): fuzzy-jump to any admin page from the
 * keyboard. Opens on the shortcut, filters by label/section, arrows + Enter to
 * navigate, Esc to close.
 */
export function CommandPalette({
  items,
  onSelect,
}: {
  items: CommandItem[];
  onSelect: (id: string) => void;
}) {
  const [open, setOpen] = useState(false);
  const [query, setQuery] = useState("");
  const [active, setActive] = useState(0);
  const inputRef = useRef<HTMLInputElement>(null);

  useEffect(() => {
    function onKey(e: KeyboardEvent) {
      if ((e.metaKey || e.ctrlKey) && e.key.toLowerCase() === "k") {
        e.preventDefault();
        setOpen((v) => !v);
        setQuery("");
        setActive(0);
      } else if (e.key === "Escape") {
        setOpen(false);
      }
    }
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, []);

  useEffect(() => {
    if (open) setTimeout(() => inputRef.current?.focus(), 0);
  }, [open]);

  const filtered = useMemo(() => {
    const q = query.trim().toLowerCase();
    if (!q) return items;
    // FIX: AUDIT-55 - fuzzy subsequence match (not just substring)
    const fuzzy = (haystack: string, needle: string): boolean => {
      if (haystack.toLowerCase().includes(needle)) return true;
      // subsequence match: each char of needle appears in order in haystack
      let hi = 0;
      for (const nc of needle) {
        hi = haystack.toLowerCase().indexOf(nc, hi);
        if (hi < 0) return false;
        hi++;
      }
      return true;
    };
    return items.filter(
      (it) => fuzzy(it.label, q) || fuzzy(it.section, q),
    );
  }, [items, query]);

  useEffect(() => {
    if (active >= filtered.length) setActive(0);
  }, [filtered, active]);

  if (!open) return null;

  function choose(id: string) {
    onSelect(id);
    setOpen(false);
  }

  function onInputKey(e: React.KeyboardEvent) {
    if (e.key === "ArrowDown") {
      e.preventDefault();
      setActive((a) => Math.min(a + 1, filtered.length - 1));
    } else if (e.key === "ArrowUp") {
      e.preventDefault();
      setActive((a) => Math.max(a - 1, 0));
    } else if (e.key === "Enter") {
      e.preventDefault();
      const hit = filtered[active];
      if (hit) choose(hit.id);
    }
  }

  // FIX: AUDIT-55 - render via createPortal to document.body
  return createPortal(
    <div className="cmdk-backdrop" onClick={() => setOpen(false)}>
      <div className="cmdk-panel" onClick={(e) => e.stopPropagation()}>
        <div className="cmdk-search">
          <span className="ms sm">search</span>
          <input
            ref={inputRef}
            value={query}
            placeholder="Перейти к разделу…"
            onChange={(e) => setQuery(e.target.value)}
            onKeyDown={onInputKey}
          />
          <kbd>Esc</kbd>
        </div>
        <div className="cmdk-list">
          {filtered.length === 0 && <div className="cmdk-empty">Ничего не найдено</div>}
          {filtered.map((it, i) => (
            <button
              key={it.id}
              className={"cmdk-item" + (i === active ? " active" : "")}
              onMouseEnter={() => setActive(i)}
              onClick={() => choose(it.id)}
            >
              <span className="ms sm">{it.icon}</span>
              <span className="cmdk-label">{it.label}</span>
              <span className="cmdk-section">{it.section}</span>
            </button>
          ))}
        </div>
      </div>
    </div>,
    document.body
  );
}
