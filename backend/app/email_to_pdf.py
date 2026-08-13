"""Convert .eml / .msg email files into PDFs."""

from __future__ import annotations

import base64
import html
import re
import tempfile
from dataclasses import dataclass, field
from email import policy
from email.parser import BytesParser
from pathlib import Path

import extract_msg
from weasyprint import HTML
from weasyprint.urls import default_url_fetcher

# Outlook/Word HTML encodes list bullets and dingbats as Private-Use-Area codepoints
# that only render correctly through the Windows-specific Wingdings/Symbol/Webdings
# glyph tables (e.g. U+F0B7 means bullet, but only when shown in the Symbol font).
# Pango (WeasyPrint's text shaper) has no way to resolve those, so they'd otherwise
# render as a missing-glyph "tofu" box. Map the common ones to real Unicode characters
# and fall back to a plain bullet for anything else in the PUA range. These usually
# arrive as numeric HTML entities (e.g. "&#61623;") rather than raw characters, so we
# decode those specifically before WeasyPrint's own HTML parser ever sees them.
_MS_SYMBOL_GLYPH_MAP = {
    '\uf0b7': '•',
    '\uf06c': '◦',
    '\uf0a7': '▪',
    '\uf0d8': '➢',
    '\uf0e0': '➤',
    '\uf0fc': '✓',
    '\uf020': ' ',
}
_PUA_RANGE = re.compile('[\ue000-\uf8ff]')
_PUA_ENTITY_RANGE = re.compile(r"&#x?[0-9A-Fa-f]+;", re.IGNORECASE)


def _decode_pua_entity(match: "re.Match[str]") -> str:
    ref = match.group(0)
    try:
        codepoint = int(ref[3:-1], 16) if ref[2:3].lower() == "x" else int(ref[2:-1])
    except ValueError:
        return ref
    if 0xE000 <= codepoint <= 0xF8FF:
        return _MS_SYMBOL_GLYPH_MAP.get(chr(codepoint), '•')
    return ref


def _fix_symbol_font_glyphs(text: str) -> str:
    text = _PUA_ENTITY_RANGE.sub(_decode_pua_entity, text)
    return _PUA_RANGE.sub(lambda m: _MS_SYMBOL_GLYPH_MAP.get(m.group(0), '•'), text)

PAGE_STYLE = """
@page { margin: 2cm; }
body { font-family: -apple-system, Helvetica, Arial, sans-serif; font-size: 11pt; color: #111; }
.header { border-bottom: 2px solid #333; padding-bottom: 10px; margin-bottom: 18px; }
.header div { margin: 2px 0; }
.label { font-weight: bold; display: inline-block; width: 60px; }
.plain-body { white-space: pre-wrap; word-wrap: break-word; }
.attachments { margin-top: 20px; padding-top: 10px; border-top: 1px solid #ccc; font-size: 0.9em; color: #555; }
"""


@dataclass
class ParsedEmail:
    subject: str = "(no subject)"
    sender: str = ""
    to: str = ""
    date: str = ""
    body: str = ""
    is_html: bool = False
    attachments: list[str] = field(default_factory=list)
    # cid -> data: URI. HTML emails reference inline images (logos, signature
    # graphics) via "cid:xxx", which points at another part of the same message,
    # not a URL - our WeasyPrint url_fetcher blocks all real network fetches (to
    # stop tracking pixels phoning home), which was also silently breaking these
    # legitimate inline images. Resolving them to data: URIs up front sidesteps
    # the fetcher entirely.
    inline_images: dict[str, str] = field(default_factory=dict)


_CID_REF = re.compile(r'(src|background)=(["\'])cid:([^"\']+)\2', re.IGNORECASE)


def _inline_cid_images(html_body: str, inline_images: dict[str, str]) -> str:
    def replace(match: "re.Match[str]") -> str:
        attr, quote, cid = match.group(1), match.group(2), match.group(3)
        data_uri = inline_images.get(cid.strip("<>"))
        if data_uri is None:
            return match.group(0)
        return f"{attr}={quote}{data_uri}{quote}"

    return _CID_REF.sub(replace, html_body)


def _blocked_url_fetcher(url, timeout=10, ssl_context=None):
    # Email HTML can embed remote tracking pixels / images. Refuse all *remote*
    # fetches so converting an email never phones home - WeasyPrint just drops
    # the resource and continues rendering the rest of the page. data: URIs are
    # self-contained (used for inline cid: images we've already resolved locally
    # in _inline_cid_images) and never touch the network, so let those through -
    # WeasyPrint's default fetcher just decodes them in-process.
    if url.startswith("data:"):
        return default_url_fetcher(url)
    raise ValueError(f"remote fetch blocked: {url}")


def _parse_eml(data: bytes) -> ParsedEmail:
    msg = BytesParser(policy=policy.default).parsebytes(data)

    body_part = msg.get_body(preferencelist=("html", "plain"))
    body = ""
    is_html = False
    if body_part is not None:
        content = body_part.get_content()
        is_html = body_part.get_content_type() == "text/html"
        body = content if isinstance(content, str) else str(content)

    attachments = [
        part.get_filename()
        for part in msg.iter_attachments()
        if part.get_filename()
    ]

    inline_images = {}
    for part in msg.walk():
        content_id = part.get("Content-ID")
        if not content_id or not part.get_content_type().startswith("image/"):
            continue
        try:
            payload = part.get_content()
        except Exception:
            continue
        if not isinstance(payload, bytes):
            continue
        cid = content_id.strip().strip("<>")
        b64 = base64.b64encode(payload).decode("ascii")
        inline_images[cid] = f"data:{part.get_content_type()};base64,{b64}"

    return ParsedEmail(
        subject=msg.get("subject", "(no subject)"),
        sender=msg.get("from", ""),
        to=msg.get("to", ""),
        date=msg.get("date", ""),
        body=body,
        is_html=is_html,
        attachments=attachments,
        inline_images=inline_images,
    )


def _parse_msg(data: bytes) -> ParsedEmail:
    with tempfile.NamedTemporaryFile(suffix=".msg", delete=False) as tmp:
        tmp.write(data)
        tmp_path = Path(tmp.name)

    try:
        msg = extract_msg.Message(str(tmp_path))
        try:
            html_body = msg.htmlBody
            if isinstance(html_body, bytes):
                html_body = html_body.decode("utf-8", errors="replace")

            if html_body:
                body, is_html = html_body, True
            else:
                body, is_html = (msg.body or ""), False

            attachments = [
                att.longFilename or att.shortFilename or "attachment"
                for att in msg.attachments
            ]

            inline_images = {}
            for att in msg.attachments:
                cid = getattr(att, "cid", None)
                if not cid:
                    continue
                mimetype = getattr(att, "mimetype", None) or "application/octet-stream"
                if not mimetype.startswith("image/"):
                    continue
                b64 = base64.b64encode(att.data).decode("ascii")
                inline_images[cid.strip("<>")] = f"data:{mimetype};base64,{b64}"

            return ParsedEmail(
                subject=msg.subject or "(no subject)",
                sender=msg.sender or "",
                to=msg.to or "",
                date=str(msg.date) if msg.date else "",
                body=body,
                is_html=is_html,
                attachments=attachments,
                inline_images=inline_images,
            )
        finally:
            msg.close()
    finally:
        tmp_path.unlink(missing_ok=True)


def _render_html(parsed: ParsedEmail) -> str:
    body = _fix_symbol_font_glyphs(parsed.body)
    if parsed.is_html:
        if parsed.inline_images:
            body = _inline_cid_images(body, parsed.inline_images)
        body_html = f'<div class="html-body">{body}</div>'
    else:
        body_html = f'<div class="plain-body">{html.escape(body)}</div>'

    attachments_html = ""
    if parsed.attachments:
        items = "".join(f"<li>{html.escape(name)}</li>" for name in parsed.attachments)
        attachments_html = f'<div class="attachments"><strong>Attachments:</strong><ul>{items}</ul></div>'

    return f"""<!doctype html>
<html><head><meta charset="utf-8"><style>{PAGE_STYLE}</style></head>
<body>
<div class="header">
<div><span class="label">From:</span> {html.escape(parsed.sender)}</div>
<div><span class="label">To:</span> {html.escape(parsed.to)}</div>
<div><span class="label">Date:</span> {html.escape(parsed.date)}</div>
<div><span class="label">Subject:</span> {html.escape(parsed.subject)}</div>
</div>
{body_html}
{attachments_html}
</body></html>"""


def convert_email_to_pdf(filename: str, data: bytes) -> bytes:
    suffix = Path(filename).suffix.lower()
    if suffix == ".eml":
        parsed = _parse_eml(data)
    elif suffix == ".msg":
        parsed = _parse_msg(data)
    else:
        raise ValueError(f"unsupported email format: {suffix}")

    html_doc = _render_html(parsed)
    return HTML(string=html_doc, url_fetcher=_blocked_url_fetcher).write_pdf()
