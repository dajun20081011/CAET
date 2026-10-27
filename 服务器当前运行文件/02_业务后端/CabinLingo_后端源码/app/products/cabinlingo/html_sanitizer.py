from __future__ import annotations

from dataclasses import dataclass
from hashlib import sha256
from html import escape
from html.parser import HTMLParser
from urllib.parse import urlparse


MAX_HTML_BYTES = 2 * 1024 * 1024
ALLOWED_TAGS = {
    "article", "section", "header", "footer", "main", "nav", "div", "span", "p",
    "h1", "h2", "h3", "h4", "h5", "h6", "ul", "ol", "li", "dl", "dt", "dd",
    "strong", "b", "em", "i", "u", "small", "mark", "blockquote", "pre", "code",
    "table", "thead", "tbody", "tfoot", "tr", "th", "td", "caption", "br", "hr",
    "a", "img", "audio", "source",
}
VOID_TAGS = {"br", "hr", "img", "source"}
DROP_WITH_CONTENT = {"script", "style", "iframe", "object", "embed", "form", "button", "input", "textarea", "select", "option", "meta", "link", "base"}
GLOBAL_ATTRIBUTES = {"class", "title", "lang", "dir", "role", "aria-label", "aria-describedby"}
TAG_ATTRIBUTES = {
    "a": {"href", "target", "rel"},
    "img": {"src", "alt", "width", "height"},
    "audio": {"src", "controls", "preload"},
    "source": {"src", "type"},
    "th": {"scope", "colspan", "rowspan"},
    "td": {"colspan", "rowspan"},
}


def _safe_url(value: str) -> bool:
    parsed = urlparse(value.strip())
    return parsed.scheme.lower() in {"", "https", "http"} and not value.strip().lower().startswith("javascript:")


class _Sanitizer(HTMLParser):
    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.output: list[str] = []
        self.dropped_tags: set[str] = set()
        self.dropped_attributes = 0
        self._drop_depth = 0

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        tag = tag.lower()
        if tag in DROP_WITH_CONTENT:
            self.dropped_tags.add(tag)
            self._drop_depth += 1
            return
        if self._drop_depth:
            return
        if tag not in ALLOWED_TAGS:
            self.dropped_tags.add(tag)
            return
        allowed = GLOBAL_ATTRIBUTES | TAG_ATTRIBUTES.get(tag, set())
        clean: list[str] = []
        for name, value in attrs:
            name = name.lower()
            value = "" if value is None else value
            if name.startswith("on") or name not in allowed:
                self.dropped_attributes += 1
                continue
            if name in {"href", "src"} and not _safe_url(value):
                self.dropped_attributes += 1
                continue
            if name == "target" and value not in {"_blank", "_self"}:
                self.dropped_attributes += 1
                continue
            clean.append(f' {name}="{escape(value, quote=True)}"')
        if tag == "a" and any(name == "target" and value == "_blank" for name, value in attrs):
            clean.append(' rel="noopener noreferrer"')
        self.output.append(f"<{tag}{''.join(clean)}>")

    def handle_endtag(self, tag: str) -> None:
        tag = tag.lower()
        if tag in DROP_WITH_CONTENT:
            if self._drop_depth:
                self._drop_depth -= 1
            return
        if not self._drop_depth and tag in ALLOWED_TAGS and tag not in VOID_TAGS:
            self.output.append(f"</{tag}>")

    def handle_data(self, data: str) -> None:
        if not self._drop_depth:
            self.output.append(escape(data))

    def handle_entityref(self, name: str) -> None:
        if not self._drop_depth:
            self.output.append(f"&{name};")

    def handle_charref(self, name: str) -> None:
        if not self._drop_depth:
            self.output.append(f"&#{name};")


@dataclass(frozen=True)
class SanitizedHTML:
    html: str
    original_sha256: str
    sanitized_sha256: str
    report: dict[str, object]


def sanitize_html(source: str) -> SanitizedHTML:
    raw = source.encode("utf-8")
    if not source.strip():
        raise ValueError("HTML content is empty")
    if len(raw) > MAX_HTML_BYTES:
        raise ValueError("HTML file exceeds the 2 MB limit")
    parser = _Sanitizer()
    parser.feed(source)
    parser.close()
    cleaned = "".join(parser.output).strip()
    if not cleaned:
        raise ValueError("HTML contains no safe displayable content")
    return SanitizedHTML(
        html=cleaned,
        original_sha256=sha256(raw).hexdigest(),
        sanitized_sha256=sha256(cleaned.encode("utf-8")).hexdigest(),
        report={
            "safe": True,
            "original_bytes": len(raw),
            "sanitized_bytes": len(cleaned.encode("utf-8")),
            "dropped_tags": sorted(parser.dropped_tags),
            "dropped_attributes": parser.dropped_attributes,
        },
    )


class _TextExtractor(HTMLParser):
    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.parts: list[str] = []

    def handle_data(self, data: str) -> None:
        value = " ".join(data.split())
        if value:
            self.parts.append(value)


def extract_text(source: str) -> str:
    parser = _TextExtractor()
    parser.feed(source)
    parser.close()
    return " ".join(parser.parts).strip()
