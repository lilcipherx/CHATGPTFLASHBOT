import { useEffect, useRef, useState } from "react";
import { adminFetch, logout } from "../api";  // FIX: B17 - logout on 401
import { Select } from "../components/Select";
import { useLatestGuard } from "../lib/latestGuard";  // FIX: F46 - guard stale fetches

// JSON wrapper over the shared `adminFetch` — inherits credential handling plus the
// transparent token refresh on 401 (no premature "session expired" mid-session).
async function gReq<T>(path: string, init: RequestInit = {}): Promise<T> {
  const res = await adminFetch(path, {
    ...init,
    headers: { ...(init.headers ?? {}), "Content-Type": "application/json" },
  });
  if (res.status === 401) { logout(); window.dispatchEvent(new CustomEvent("admin:unauth")); throw new Error("session expired"); }  // FIX: B17 + AUDIT-H8
  if (!res.ok) throw new Error(`API ${res.status}`);
  return res.json() as Promise<T>;
}

interface GalleryItem {
  id: number;
  user_id: number;
  image_url: string;
  prompt: string | null;
  status: string;
  created_at: string | null;
}

type GStatus = "pending" | "approved" | "rejected";

const gallery = {
  list: (status: GStatus) => gReq<GalleryItem[]>(`/gallery/list?status=${status}&limit=200`),
  approve: (id: number) => gReq(`/gallery/${id}/approve`, { method: "POST" }),
  reject: (id: number) => gReq(`/gallery/${id}/reject`, { method: "POST" }),
};

const STATUS_OPTS = [
  { value: "pending", label: "На модерации" },
  { value: "approved", label: "Одобренные" },
  { value: "rejected", label: "Отклонённые" },
];
const REFRESH_MS = 30_000;
const fmtDate = (s: string | null) => (s ? s.slice(0, 19).replace("T", " ") : "—");

export function Gallery() {
  const [status, setStatus] = useState<GStatus>("pending");
  const [rows, setRows] = useState<GalleryItem[] | null>(null);
  const [sel, setSel] = useState<Set<number>>(new Set());
  const [msg, setMsg] = useState("");
  const [busy, setBusy] = useState(false);
  const [updatedAt, setUpdatedAt] = useState<Date | null>(null);
  const [preview, setPreview] = useState<GalleryItem | null>(null);
  const aliveRef = useRef(true);
  // FIX: F46 - useLatestGuard so a slow in-flight fetch from the PREVIOUS status filter
  // can't overwrite the new bucket's rows when it resolves (was: only unmount-guarded).
  const guard = useLatestGuard();

  const load = () => {
    const isLatest = guard();  // FIX: F46 - capture before fetch so a stale in-flight request can't overwrite
    gallery.list(status)
      .then((v) => { if (aliveRef.current && isLatest()) { setRows(v); setUpdatedAt(new Date()); setSel(new Set()); } })
      .catch((e) => { if (aliveRef.current && isLatest()) { setRows([]); setMsg(String(e)); } });
  };

  // Live moderation queue: reload on status change and poll every 30s.
  useEffect(() => {
    aliveRef.current = true;
    load();
    const id = window.setInterval(load, REFRESH_MS);
    return () => { aliveRef.current = false; window.clearInterval(id); };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [status]);

  // Apply a decision to one item; remove it from view when it no longer matches the
  // active status filter (it moved to another bucket).
  async function decide(id: number, action: "approve" | "reject") {
    setBusy(true);
    try {
      await (action === "approve" ? gallery.approve(id) : gallery.reject(id));
      const newStatus = action === "approve" ? "approved" : "rejected";
      if (newStatus !== status) {
        setRows((rs) => (rs ?? []).filter((r) => r.id !== id));
        setSel((s) => { const n = new Set(s); n.delete(id); return n; });
        setPreview((p) => (p?.id === id ? null : p));
      } else {
        load();
      }
      setMsg("");
    } catch (e) { setMsg(String(e)); }
    finally { setBusy(false); }
  }

  // Bulk-apply to the current selection, sequentially (each decision is audited
  // server-side). Reloads once at the end.
  async function bulk(action: "approve" | "reject") {
    if (sel.size === 0) return;
    if (!confirm(`${action === "approve" ? "Одобрить" : "Отклонить"} выбранные (${sel.size})?`)) return;
    setBusy(true);
    // FIX: AUDIT-81 - per-item try/catch + count
    try {
      let ok = 0, failed = 0;
      for (const id of sel) {
        try { await (action === "approve" ? gallery.approve(id) : gallery.reject(id)); ok++; }
        catch (e) { failed++; }
      }
      setMsg(`✅ Готово: ${ok}${failed ? `, ошибок: ${failed}` : ""}`);
      await load();
    } finally { setBusy(false); }
  }

  function toggle(id: number) {
    setSel((s) => { const n = new Set(s); n.has(id) ? n.delete(id) : n.add(id); return n; });
  }
  function toggleAll() {
    setSel((s) => (rows && s.size === rows.length ? new Set() : new Set((rows ?? []).map((r) => r.id))));
  }

  return (
    <div>
      <div className="page-head">
        <div>
          <h1 className="page-title">Публичная галерея</h1>
          <p className="page-sub">Модерация работ, отправленных пользователями в публичную галерею.</p>
        </div>
        <div className="health-refresh">
          {updatedAt && (
            <span className="health-updated">
              <span className="live-dot" /> обновлено {updatedAt.toLocaleTimeString("ru")}
            </span>
          )}
          <Select ariaLabel="Статус" value={status} onChange={(v) => setStatus(v as GStatus)}
            options={STATUS_OPTS} />
          <button className="btn sm ghost" onClick={load}>
            <span className="ms sm">refresh</span> Обновить
          </button>
        </div>
      </div>

      {msg && (
        <p className={msg.startsWith("✅") ? "note-ok" : "note-err"}>
          <span className="ms sm">{msg.startsWith("✅") ? "check_circle" : "error"}</span>{msg}
          <button className="btn ghost sm" onClick={() => setMsg("")}>×</button>
        </p>
      )}

      {rows && rows.length > 0 && (
        <div className="gal-bulkbar">
          <label className="gal-check">
            <input type="checkbox" checked={sel.size === rows.length} onChange={toggleAll} />
            Выбрать все ({rows.length})
          </label>
          {sel.size > 0 && (
            <>
              <span className="muted">Выбрано: {sel.size}</span>
              {status !== "approved" && (
                <button className="btn sm" disabled={busy} onClick={() => bulk("approve")}>
                  <span className="ms sm">check</span> Одобрить
                </button>
              )}
              {status !== "rejected" && (
                <button className="btn sm danger" disabled={busy} onClick={() => bulk("reject")}>
                  <span className="ms sm">close</span> Отклонить
                </button>
              )}
              <button className="btn sm ghost" onClick={() => setSel(new Set())}>Снять</button>
            </>
          )}
        </div>
      )}

      {rows === null ? (
        <div className="gal-grid">
          {Array.from({ length: 8 }).map((_, i) => <div key={i} className="gal-card skeleton-row" style={{ height: 260 }} />)}
        </div>
      ) : rows.length === 0 ? (
        <div className="panel">
          <div className="empty-state">
            <div className="es-icon"><span className="ms">photo_library</span></div>
            <p className="es-title">
              {status === "pending" ? "Очередь модерации пуста"
                : status === "approved" ? "Нет одобренных работ"
                : "Нет отклонённых работ"}
            </p>
            <p className="es-desc">Здесь появятся работы с этим статусом.</p>
          </div>
        </div>
      ) : (
        <div className="gal-grid">
          {rows.map((r) => (
            <GalleryCard key={r.id} item={r} status={status} busy={busy}
              selected={sel.has(r.id)} onToggle={() => toggle(r.id)}
              onPreview={() => setPreview(r)} onDecide={decide} />
          ))}
        </div>
      )}

      {preview && (
        <WorkModal row={preview} busy={busy} status={status}
          onClose={() => setPreview(null)} onDecide={decide} />
      )}
    </div>
  );
}

function GalleryCard({ item, status, busy, selected, onToggle, onPreview, onDecide }: {
  item: GalleryItem; status: GStatus; busy: boolean; selected: boolean;
  onToggle: () => void; onPreview: () => void;
  onDecide: (id: number, action: "approve" | "reject") => void;
}) {
  const [failed, setFailed] = useState(false);
  return (
    <div className={"gal-card" + (selected ? " sel" : "")}>
      <label className="gal-card-check" onClick={(e) => e.stopPropagation()}>
        <input type="checkbox" aria-label="Выбрать работу" checked={selected} onChange={onToggle} />
      </label>
      <button type="button" className="gal-card-img" onClick={onPreview} title="Открыть работу">
        {item.image_url && !failed
          ? <img src={item.image_url} alt="" loading="lazy" decoding="async" onError={() => setFailed(true)} />
          : <span className="ms">image_not_supported</span>}
      </button>
      <div className="gal-card-body">
        <div className="gal-card-meta">
          <a className="user-link" href={`#/users?focus=${item.user_id}`}>#{item.user_id}</a>
          <span className="muted">{fmtDate(item.created_at)}</span>
        </div>
        {item.prompt && <div className="clamp-2 gal-card-prompt" title={item.prompt}>{item.prompt}</div>}
        <div className="cell-actions">
          {status !== "approved" && (
            <button className="btn sm" disabled={busy} onClick={() => onDecide(item.id, "approve")}>
              <span className="ms sm">check</span> Одобрить
            </button>
          )}
          {status !== "rejected" && (
            <button className="btn sm danger" disabled={busy} onClick={() => onDecide(item.id, "reject")}>
              <span className="ms sm">close</span> Отклонить
            </button>
          )}
        </div>
      </div>
    </div>
  );
}

/** Lightbox / work card — full image, prompt and meta. Closes on backdrop click or Esc. */
function WorkModal({ row, busy, status, onClose, onDecide }: {
  row: GalleryItem; busy: boolean; status: GStatus;
  onClose: () => void; onDecide: (id: number, action: "approve" | "reject") => void;
}) {
  const [failed, setFailed] = useState(false);
  useEffect(() => {
    const onKey = (e: KeyboardEvent) => { if (e.key === "Escape") onClose(); };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [onClose]);

  return (
    <div className="modal-backdrop" onClick={onClose}>
      <div className="modal-card" onClick={(e) => e.stopPropagation()}>
        <div className="modal-head">
          <div className="panel-title" style={{ margin: 0 }}>
            <span className="ms sm">image</span> Работа на модерации
          </div>
          <button className="btn ghost sm" onClick={onClose}>×</button>
        </div>

        {row.image_url && !failed
          ? <img className="modal-img" src={row.image_url} alt="" decoding="async" onError={() => setFailed(true)} />
          : <div className="modal-img" style={{ height: 200, display: "grid", placeItems: "center" }}>
              <span className="ms" style={{ fontSize: 30, color: "var(--hint)" }}>image_not_supported</span>
            </div>}

        <div className="info-row muted" style={{ marginTop: "var(--sp-4)", fontSize: 13 }}>
          <span><span className="ms sm">person</span> <a className="user-link" href={`#/users?focus=${row.user_id}`}>#{row.user_id}</a></span>
          <span><span className="ms sm">schedule</span> {fmtDate(row.created_at)}</span>
          <span><span className="pill muted">{row.status}</span></span>
        </div>

        <div style={{ marginTop: "var(--sp-3)" }}>
          <div className="panel-title sm" style={{ margin: "0 0 var(--sp-2)" }}>Промпт</div>
          <div className="code-block" style={{ margin: 0, maxHeight: 160, overflowY: "auto", whiteSpace: "pre-wrap" }}>
            {row.prompt || "—"}
          </div>
        </div>

        <div className="toolbar" style={{ marginTop: "var(--sp-5)", marginBottom: 0 }}>
          {status !== "approved" && (
            <button className="btn" disabled={busy} onClick={() => onDecide(row.id, "approve")}>
              <span className="ms sm">check</span> Одобрить
            </button>
          )}
          {status !== "rejected" && (
            <button className="btn danger" disabled={busy} onClick={() => onDecide(row.id, "reject")}>
              <span className="ms sm">close</span> Отклонить
            </button>
          )}
        </div>
      </div>
    </div>
  );
}
