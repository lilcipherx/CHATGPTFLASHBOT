"""Safe Markdown -> Telegram-HTML rendering for AI replies (§3.2).

Telegram rejects malformed HTML, and AI output is free-form, so we HTML-escape all
non-tag text FIRST (so a stray ``<`` / ``&`` can never form an invalid tag), then
emit only the small set of tags Telegram supports: <b> <i> <code> <pre> <a>.
Conservative by design — when in doubt, escape and leave as plain text.
"""
from __future__ import annotations

import re

_ESCAPES = (("&", "&amp;"), ("<", "&lt;"), (">", "&gt;"))


def _esc(text: str) -> str:
    """HTML-escape & < > (ampersand first so we don't double-escape the entities)."""
    for a, b in _ESCAPES:
        text = text.replace(a, b)
    return text


# Order matters: fenced code blocks first (they swallow inner markup), then inline
# code, then links, then bold, then italic. Each pattern's text payload is escaped.
_FENCE_RE = re.compile(r"```[ \t]*\w*\n?(.*?)```", re.DOTALL)
_INLINE_CODE_RE = re.compile(r"`([^`\n]+)`")
_LINK_RE = re.compile(r"\[([^\]]+)\]\((https?://[^\s)]+)\)")
_BOLD_RE = re.compile(r"\*\*(.+?)\*\*|__(.+?)__", re.DOTALL)
_ITALIC_RE = re.compile(r"(?<!\*)\*(?!\*)([^*\n]+?)\*(?!\*)|(?<!\w)(?<!_)_(?!_)([^_\n]+?)_(?!_)(?!\w)")  # FIX: B3/L3 - word-boundary guards prevent intraword _ italic


def to_telegram_html(md: str) -> str:
    """Convert common Markdown to Telegram-supported HTML, escaping all literal text.

    Never raises: any input string yields valid (escaped) HTML."""
    if not md:
        return ""

    # Carve out code first so markup inside it stays literal. We replace each code
    # span with an unescapable placeholder, build the safe HTML for it, and splice
    # back at the end — keeps inner ``*`` / ``<`` from being reinterpreted.
    placeholders: list[str] = []

    def _stash(html: str) -> str:
        placeholders.append(html)
        return f"\x00{len(placeholders) - 1}\x00"

    def _fence(m: re.Match) -> str:
        return _stash(f"<pre>{_esc(m.group(1))}</pre>")

    def _inline(m: re.Match) -> str:
        return _stash(f"<code>{_esc(m.group(1))}</code>")

    text = _FENCE_RE.sub(_fence, md)
    text = _INLINE_CODE_RE.sub(_inline, text)

    # Escape everything that's left (plain prose + any stray ``< & >``) before we
    # inject our own trusted tags.
    text = _esc(text)

    def _link(m: re.Match) -> str:
        # URL is already escaped by the blanket _esc above; safe to inline.
        return f'<a href="{m.group(2).replace(chr(34), "&quot;")}">{m.group(1)}</a>'

    text = _LINK_RE.sub(_link, text)

    def _bold(m: re.Match) -> str:
        return f"<b>{m.group(1) or m.group(2)}</b>"

    def _italic(m: re.Match) -> str:
        return f"<i>{m.group(1) or m.group(2)}</i>"

    text = _BOLD_RE.sub(_bold, text)
    text = _ITALIC_RE.sub(_italic, text)

    # Splice the code placeholders back in.
    for i, html in enumerate(placeholders):
        text = text.replace(f"\x00{i}\x00", html)
    return text


def render_reply(md: str, *, markdown: bool) -> tuple[str, str | None]:
    """Return (text, parse_mode) for sending. markdown=True -> safe HTML + "HTML";
    markdown=False -> the original text + None (plain)."""
    if markdown:
        return to_telegram_html(md), "HTML"
    return md, None


# Telegram rejects a message whose text exceeds 4096 chars. AI/search replies
# routinely exceed that, so callers split long text on natural boundaries and send
# several messages. CHUNK_LIMIT keeps a little headroom under the hard cap.
TG_LIMIT = 4096
CHUNK_LIMIT = 3900


def split_text(text: str, limit: int = CHUNK_LIMIT) -> list[str]:
    """Split `text` into ≤`limit`-char chunks, preferring paragraph → line → space
    boundaries and never cutting a word. Always returns at least one chunk."""
    text = text or ""
    if len(text) <= limit:
        return [text]
    out: list[str] = []
    rest = text
    while len(rest) > limit:
        window = rest[:limit]
        cut = window.rfind("\n\n")
        if cut < limit // 2:
            cut = window.rfind("\n")
        if cut < limit // 2:
            cut = window.rfind(" ")
        if cut <= 0:
            cut = limit  # no boundary in range → hard cut
        out.append(rest[:cut].rstrip())
        rest = rest[cut:].lstrip()
    if rest:
        out.append(rest)
    return out
