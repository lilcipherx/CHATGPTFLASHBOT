"""Safe Markdown -> Telegram-HTML rendering (§3.2): escaping, conversions, fuzz."""
from __future__ import annotations

from bot.format_md import CHUNK_LIMIT, TG_LIMIT, render_reply, split_text, to_telegram_html


def test_escapes_html_specials():
    out = to_telegram_html("a < b & c > d")
    assert "&lt;" in out and "&gt;" in out and "&amp;" in out
    assert "<b>" not in out  # no stray real tags


def test_bold_italic_code():
    assert to_telegram_html("**bold**") == "<b>bold</b>"
    assert to_telegram_html("__bold__") == "<b>bold</b>"
    assert to_telegram_html("*italic*") == "<i>italic</i>"
    assert to_telegram_html("_italic_") == "<i>italic</i>"
    assert to_telegram_html("`x`") == "<code>x</code>"


def test_code_block():
    out = to_telegram_html("```python\nprint(1)\n```")
    assert out.startswith("<pre>") and out.endswith("</pre>")
    assert "print(1)" in out


def test_code_block_inner_markup_left_literal():
    # Markup-like chars inside code must stay escaped, not become tags.
    out = to_telegram_html("`a < *b* > c`")
    assert "<i>" not in out
    assert "&lt;" in out and "&gt;" in out


def test_link():
    assert to_telegram_html("[t](https://x.io)") == '<a href="https://x.io">t</a>'


def test_plain_text_intact():
    assert to_telegram_html("just words here") == "just words here"


def test_empty():
    assert to_telegram_html("") == ""


def test_never_raises_on_weird_input():
    for s in ["**", "`unclosed", "[t](", "<<<", "&&&", "*_*_*", "```\n", "a**b*c"]:
        # Should not raise; output is always a string.
        assert isinstance(to_telegram_html(s), str)


def test_render_reply_plain():
    assert render_reply("hi", markdown=False) == ("hi", None)


def test_render_reply_markdown():
    body, mode = render_reply("**hi**", markdown=True)
    assert mode == "HTML" and body == "<b>hi</b>"


# ---- split_text (Telegram's 4096-char message cap) -------------------------
def test_split_short_text_is_single_chunk():
    assert split_text("hello") == ["hello"]
    assert split_text("") == [""]


def test_split_long_text_under_limit_no_word_cut():
    text = " ".join(f"w{i}" for i in range(5000))  # well over the limit
    parts = split_text(text)
    assert len(parts) > 1
    assert all(len(p) <= CHUNK_LIMIT <= TG_LIMIT for p in parts)
    assert " ".join(parts).split() == text.split()  # no token was split


def test_split_prefers_paragraph_then_line_boundaries():
    para = "x" * 1500
    text = "\n\n".join([para] * 4)  # 4 paragraphs, > the chunk limit
    parts = split_text(text)
    assert len(parts) > 1
    assert all(len(p) <= CHUNK_LIMIT for p in parts)
    # only the original content (x runs + paragraph newlines) — no other chars
    assert all(set(p) <= set("x\n") for p in parts)
    # every 'x' is preserved across chunks (nothing dropped)
    assert sum(p.count("x") for p in parts) == text.count("x")
