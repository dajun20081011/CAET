"""Safe, dependency-light PowerPoint (.pptx) text importer.

The first import path intentionally keeps the course readable and editable in
CabinLingo: slide text and order are preserved, while animations, embedded
video and binary legacy .ppt files are reported as unsupported.  The output is
always generated HTML and is still passed through the normal HTML sanitizer.
"""

from __future__ import annotations

from dataclasses import dataclass
from html import escape
from io import BytesIO
import re
from zipfile import BadZipFile, ZipFile
import xml.etree.ElementTree as ET


MAX_PPTX_BYTES = 50 * 1024 * 1024
MAX_UNCOMPRESSED_BYTES = 120 * 1024 * 1024
MAX_SLIDES = 100
MAX_TOTAL_TEXT = 1_500_000
MAX_SLIDE_XML_BYTES = 8 * 1024 * 1024
SLIDE_RE = re.compile(r"^ppt/slides/slide(\d+)\.xml$")


@dataclass(frozen=True)
class PPTSlide:
    number: int
    title: str
    paragraphs: tuple[str, ...]
    html: str


@dataclass(frozen=True)
class PPTDeck:
    title: str
    source_filename: str
    slides: tuple[PPTSlide, ...]
    warnings: tuple[str, ...]


def _local_name(tag: str) -> str:
    return tag.rsplit("}", 1)[-1]


def _slide_paragraphs(xml_bytes: bytes) -> list[str]:
    if len(xml_bytes) > MAX_SLIDE_XML_BYTES:
        raise ValueError("PPTX 单页内容过大，无法导入")
    try:
        root = ET.fromstring(xml_bytes)
    except ET.ParseError as exc:
        raise ValueError("PPTX 中包含无法读取的幻灯片 XML") from exc

    paragraphs: list[str] = []
    for paragraph in (node for node in root.iter() if _local_name(node.tag) == "p"):
        text = "".join((node.text or "") for node in paragraph.iter() if _local_name(node.tag) == "t")
        text = " ".join(text.split())
        if text:
            paragraphs.append(text)
    if paragraphs:
        return paragraphs
    # Some generated decks omit paragraph nodes. Keep their visible text.
    fallback = " ".join((node.text or "") for node in root.iter() if _local_name(node.tag) == "t")
    fallback = " ".join(fallback.split())
    return [fallback] if fallback else []


def _slide_html(number: int, paragraphs: list[str]) -> str:
    heading = paragraphs[0] if paragraphs else f"第 {number} 页"
    body = paragraphs[1:]
    pieces = [
        '<article class="ppt-slide">',
        f"<p class=\"ppt-slide-number\">第 {number} 页</p>",
        f"<h2>{escape(heading)}</h2>",
    ]
    pieces.extend(f"<p>{escape(item)}</p>" for item in body)
    pieces.append("</article>")
    return "".join(pieces)


def parse_pptx(data: bytes, source_filename: str) -> PPTDeck:
    """Parse a PowerPoint OOXML package and return sanitized-ready slide HTML.

    This function performs no network or filesystem access. It rejects legacy
    .ppt files because those are an OLE binary format and need conversion to
    .pptx before safe server-side import.
    """
    filename = (source_filename or "").strip()
    if not filename.lower().endswith(".pptx"):
        raise ValueError("只支持 .pptx 格式；旧版 .ppt 请先另存为 .pptx")
    if not data:
        raise ValueError("PPTX 文件为空")
    if len(data) > MAX_PPTX_BYTES:
        raise ValueError("PPTX 文件不能超过 50 MB")
    if not data.startswith(b"PK"):
        raise ValueError("文件不是有效的 PPTX 压缩包")

    slide_files: list[tuple[int, str]] = []
    try:
        with ZipFile(BytesIO(data)) as archive:
            infos = archive.infolist()
            if sum(max(0, info.file_size) for info in infos) > MAX_UNCOMPRESSED_BYTES:
                raise ValueError("PPTX 解压后内容过大")
            for info in infos:
                match = SLIDE_RE.match(info.filename)
                if match:
                    slide_files.append((int(match.group(1)), info.filename))
            if not slide_files:
                raise ValueError("PPTX 中没有可导入的幻灯片")
            slide_files.sort(key=lambda item: item[0])
            if len(slide_files) > MAX_SLIDES:
                raise ValueError(f"PPTX 最多支持 {MAX_SLIDES} 页")

            slides: list[PPTSlide] = []
            total_text = 0
            for number, name in slide_files:
                paragraphs = _slide_paragraphs(archive.read(name))
                total_text += sum(len(item) for item in paragraphs)
                if total_text > MAX_TOTAL_TEXT:
                    raise ValueError("PPTX 文本总量过大，请拆分课程后再导入")
                slides.append(PPTSlide(number, paragraphs[0] if paragraphs else f"第 {number} 页", tuple(paragraphs), _slide_html(number, paragraphs)))
    except BadZipFile as exc:
        raise ValueError("文件不是有效的 PPTX 压缩包") from exc

    title = re.sub(r"\.pptx$", "", filename, flags=re.IGNORECASE).strip() or "导入课程"
    warnings = ("仅导入幻灯片文字与顺序；图片、动画、视频和演讲者备注未导入。",)
    return PPTDeck(title=title[:200], source_filename=filename[:255], slides=tuple(slides), warnings=warnings)
