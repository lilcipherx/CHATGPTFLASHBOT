"""A user-controlled document filename must be HTML-escaped before it goes into the
"document received" confirmation, which is sent with the bot's default HTML parse
mode. Otherwise a name like `<b>x</b>.txt` injects markup, and a stray `<` makes
Telegram reject the message with a 400."""
from __future__ import annotations

from types import SimpleNamespace

from bot.handlers import documents


class _Editable:
    def __init__(self):
        self.text = None

    async def edit_text(self, text, **kw):
        self.text = text


async def test_received_confirmation_escapes_filename(monkeypatch):
    wait = _Editable()

    async def _answer(*a, **k):
        return wait

    async def _download(_file_id):
        return SimpleNamespace(read=lambda: b"bytes")

    doc = SimpleNamespace(file_name="<b>x</b>.txt", file_size=10, file_id="f1")
    message = SimpleNamespace(
        document=doc, caption="", answer=_answer, bot=SimpleNamespace(download=_download)
    )
    user = SimpleNamespace(user_id=1, is_banned=False, is_premium=True,
                           selected_model="m", language_code="ru")

    async def _section(_s, _name):
        return {"enabled": True, "soon": ""}

    async def _cost(_s):
        return 1

    # Documents section gates on pricing.section_state now (default OFF for the
    # chat-only launch); enable it so the upload reaches the confirmation.
    monkeypatch.setattr(documents.pricing, "section_state", _section)
    monkeypatch.setattr(documents.pricing, "document_cost", _cost)
    monkeypatch.setattr(documents, "ext_of", lambda name: ".txt")
    monkeypatch.setattr(documents, "SUPPORTED_EXT", {".txt"})
    monkeypatch.setattr(documents, "extract_text", lambda name, data: "extracted")

    async def _set_doc(*a, **k):
        return None

    monkeypatch.setattr(documents, "set_document", _set_doc)

    # translator echoes the rendered name so we can inspect what was interpolated
    def _tr(key, **kw):
        return f"{key}|{kw.get('name', '')}"

    await documents.on_document(message, session=None, user=user, _=_tr)

    assert wait.text is not None
    assert "&lt;b&gt;x&lt;/b&gt;.txt" in wait.text  # escaped
    assert "<b>x</b>" not in wait.text              # raw markup never reaches HTML
