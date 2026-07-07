import { useEffect, useRef, useState } from "react";
import { t } from "../../i18n";

/**
 * Create Media — загрузка референс-медиа (§2 ТЗ) + UX-слой (§11): drag & drop,
 * вставка из буфера (Ctrl/Cmd+V), превью с удалением и @image-тегом под каждым
 * файлом (§3). Показывается только когда пресет требует фото (`maxPhotos > 0`).
 * Валидацию размера/типа делает контейнер (CreatePage).
 */
export function UploadSection({
  maxPhotos, files, previews, onAdd, onRemove,
}: {
  maxPhotos: number;
  files: File[];
  previews: string[];
  onAdd: (list: FileList | null) => void;
  onRemove: (i: number) => void;
}) {
  const fileRef = useRef<HTMLInputElement>(null);
  const [drag, setDrag] = useState(false);

  // Paste an image from the clipboard while the Create tab is open.
  useEffect(() => {
    if (maxPhotos <= 0) return;
    function onPaste(e: ClipboardEvent) {
      const imgs = Array.from(e.clipboardData?.files ?? []).filter((f) => f.type.startsWith("image/"));
      if (!imgs.length) return;
      const dt = new DataTransfer();
      imgs.forEach((f) => dt.items.add(f));
      onAdd(dt.files);
    }
    document.addEventListener("paste", onPaste);
    return () => document.removeEventListener("paste", onPaste);
  }, [maxPhotos, onAdd]);

  if (maxPhotos <= 0) return null;
  return (
    <div>
      <div className="section-title">{t("your_photos")} {files.length}/{maxPhotos}</div>
      <div
        className={"photo-strip drop-zone" + (drag ? " drag-active" : "")}
        onDragOver={(e) => { e.preventDefault(); setDrag(true); }}
        onDragLeave={() => setDrag(false)}
        onDrop={(e) => { e.preventDefault(); setDrag(false); onAdd(e.dataTransfer.files); }}
      >
        {previews.map((src, i) => (
          <div key={i} className="photo-ref">
            <button className="photo-thumb" onClick={() => onRemove(i)} aria-label="✕">
              <img src={src} alt="" />
              <span className="photo-x">✕</span>
            </button>
            <span className="photo-ref-tag">@image{i + 1}</span>
          </div>
        ))}
        {files.length < maxPhotos && (
          <button className="photo-add" aria-label={t("choose_photo")} onClick={() => fileRef.current?.click()}>+</button>
        )}
      </div>
      <div className="muted hint">{t("upload_size")}</div>
      <input ref={fileRef} type="file" accept="image/*" multiple hidden
        onChange={(e) => onAdd(e.target.files)} />
    </div>
  );
}
