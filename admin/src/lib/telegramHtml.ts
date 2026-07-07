// Sanitize admin-authored "Telegram HTML" before it is injected into a preview
// via dangerouslySetInnerHTML. The broadcast / channel-post body is free-form HTML
// stored on the server and re-rendered when ANOTHER admin opens the history — so an
// unsanitized preview was a stored-XSS vector between admins (e.g. an
// `<img src=x onerror=...>` running in a superadmin's authenticated session).
//
// We keep only the inline tags Telegram itself renders, drop every attribute except
// a safe href on <a>, and escape all text. Disallowed elements are UNWRAPPED (their
// sanitized children survive, the tag + its attributes/handlers do not), so a
// payload element like <img>/<script>/<svg onload> contributes nothing executable.
// Implemented with the browser's own parser (available in jsdom for tests too) and a
// rebuild-from-allowed-nodes walk, which is safe by construction (no attributes from
// the source are ever re-emitted unless explicitly allowlisted).

const ALLOWED_TAGS = new Set([
  "b", "strong", "i", "em", "u", "ins", "s", "strike", "del",
  "a", "code", "pre", "br", "span", "tg-spoiler", "blockquote",
]);

function escapeText(s: string): string {
  return s.replace(/&/g, "&amp;").replace(/</g, "&lt;").replace(/>/g, "&gt;");
}

function escapeAttr(s: string): string {
  return s.replace(/&/g, "&amp;").replace(/"/g, "&quot;").replace(/</g, "&lt;").replace(/>/g, "&gt;");
}

function safeHref(raw: string | null): string {
  const href = (raw || "").trim();
  // Only navigable, non-script schemes. Everything else (javascript:, data:, vbscript:)
  // is dropped, so the <a> renders without an href instead of becoming an XSS sink.
  return /^(https?:|tg:|mailto:)/i.test(href) ? href : "";
}

function clean(node: Node): string {
  let out = "";
  node.childNodes.forEach((child) => {
    if (child.nodeType === 3 /* TEXT_NODE */) {
      out += escapeText(child.textContent || "");
      return;
    }
    if (child.nodeType !== 1 /* ELEMENT_NODE */) return;
    const el = child as Element;
    const tag = el.tagName.toLowerCase();
    if (!ALLOWED_TAGS.has(tag)) {
      out += clean(el); // unwrap: drop the tag + all its attributes, keep clean children
      return;
    }
    if (tag === "br") {
      out += "<br>";
      return;
    }
    if (tag === "a") {
      const href = safeHref(el.getAttribute("href"));
      out += href ? `<a href="${escapeAttr(href)}">${clean(el)}</a>` : clean(el);
      return;
    }
    out += `<${tag}>${clean(el)}</${tag}>`;
  });
  return out;
}

export function sanitizeTelegramHtml(html: string): string {
  if (!html) return "";
  const doc = new DOMParser().parseFromString(html, "text/html");
  return clean(doc.body);
}
