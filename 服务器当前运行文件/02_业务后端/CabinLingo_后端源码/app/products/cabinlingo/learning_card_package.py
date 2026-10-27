"""Validation and extraction for CabinLingo Learning Card Package V1."""

from __future__ import annotations

from dataclasses import dataclass
from hashlib import sha256
from html.parser import HTMLParser
from io import BytesIO
import json
import mimetypes
import posixpath
from pathlib import PurePosixPath
import re
import stat
import unicodedata
import zlib
from typing import Any
from zipfile import BadZipFile, ZipFile, ZIP_STORED, ZIP_DEFLATED


class LearningCardPackageError(ValueError):
    """A user-safe package validation error."""


@dataclass(frozen=True)
class PackageLimits:
    max_package_bytes: int = 50 * 1024 * 1024
    max_resource_bytes: int = 50 * 1024 * 1024
    max_uncompressed_bytes: int = 150 * 1024 * 1024
    max_entries: int = 1000
    max_compression_ratio: int = 150
    max_manifest_bytes: int = 64 * 1024


@dataclass(frozen=True)
class LearningCardResource:
    path: str
    data: bytes
    mime_type: str
    sha256: str


@dataclass(frozen=True)
class LearningCardPackage:
    manifest: dict[str, Any]
    resources: tuple[LearningCardResource, ...]
    package_sha256: str


ALLOWED_EXTENSIONS = {
    ".html", ".css", ".js", ".json",
    ".png", ".jpg", ".jpeg", ".webp", ".svg",
    ".mp3", ".wav", ".m4a", ".mp4", ".webm",
    ".woff", ".woff2", ".ttf", ".otf", ".gif", ".ico", ".ogg",
}
PROHIBITED_EXTENSIONS = {
    ".php", ".py", ".pyc", ".sh", ".bash", ".exe", ".dll",
    ".bat", ".cmd", ".ps1", ".jar", ".wasm", ".com", ".msi",
}
EXTERNAL_URL_RE = re.compile(
    rb"(?:src|href|action|formaction)\s*=\s*['\"]\s*(?:https?:)?//",
    re.IGNORECASE,
)
CSS_EXTERNAL_URL_RE = re.compile(rb"url\(\s*['\"]?\s*(?:https?:)?//", re.IGNORECASE)
ACTIVE_SVG_RE = re.compile(
    rb"<\s*(?:script|foreignObject)\b|\bon[a-z]+\s*=|(?:href|xlink:href)\s*=\s*['\"]\s*(?:https?:)?//",
    re.IGNORECASE,
)


def _safe_path(raw: str) -> str:
    if (not raw or len(raw) > 240 or unicodedata.normalize('NFC', raw) != raw
            or re.search(r'[\\<>:"|?*%#\x00-\x1f\x7f]', raw)):
        raise LearningCardPackageError("课程包路径不安全")
    if raw.startswith(("/", "//")) or re.match(r"^[A-Za-z]:", raw):
        raise LearningCardPackageError("课程包路径不安全")
    path = PurePosixPath(raw)
    if path.is_absolute() or any(part in {"", ".", ".."} or part.endswith((' ', '.'))
                                 or re.fullmatch(r'(?i)(con|prn|aux|nul|com[1-9]|lpt[1-9])(?:\..*)?', part)
                                 for part in raw.split('/')):
        raise LearningCardPackageError("课程包路径不安全")
    return path.as_posix()


def _local_reference(value: str, source_path: str = 'index.html') -> None:
    """URL validation is defense in depth; resource-scoped CSP enforces runtime isolation."""
    value = value.strip()
    if value.startswith('#') or not value:
        return
    if value.startswith('data:image/') or value.startswith('data:font/'):
        return
    if re.search(r'[\x00-\x20\\]', value) or value.startswith('/') or re.match(r'^[\w+.-]+:', value):
        raise LearningCardPackageError('课程包包含危险外部资源或绝对引用')
    resource = value.split('?', 1)[0].split('#', 1)[0]
    resolved = _safe_path(posixpath.normpath(posixpath.join(posixpath.dirname(source_path), resource)))
    if resolved not in {'index.html', 'course.json'} and not resolved.startswith('assets/'):
        raise LearningCardPackageError('课程包资源引用超出当前课程包')


class _CardHTMLValidator(HTMLParser):
    def __init__(self, source_path):
        super().__init__(convert_charrefs=True)
        self.source_path = source_path
        self.in_style = False

    def handle_starttag(self, tag, attrs):
        if tag == 'style':
            self.in_style = True
        values = dict(attrs)
        if tag in {'base', 'iframe', 'frame', 'object', 'embed', 'form'}:
            raise LearningCardPackageError('课程包包含不允许的嵌入或跳转')
        if tag == 'meta' and values.get('http-equiv'):
            raise LearningCardPackageError('课程包不允许 http-equiv 元信息')
        for key, value in attrs:
            if not value:
                continue
            if key in {'src', 'href', 'poster', 'action', 'formaction', 'data', 'background'}:
                _local_reference(value, self.source_path)
            if key == 'srcset':
                for candidate in value.split(','):
                    _local_reference(candidate.strip().split(' ')[0], self.source_path)
            if key == 'style':
                _validate_css(value, self.source_path)

    def handle_endtag(self, tag):
        if tag == 'style':
            self.in_style = False

    def handle_data(self, data):
        if self.in_style:
            _validate_css(data, self.source_path)

    handle_startendtag = handle_starttag


def _validate_css(source: str, source_path: str = 'index.html') -> None:
    # Escaped URLs can disguise protocols; don't accept them in resource references.
    for match in re.finditer(r'url\(\s*([^)]*)\)|@import\s+([\"\'][^\"\']+[\"\'])', source, re.I):
        _local_reference((match.group(1) or match.group(2)).strip().strip('\"\''), source_path)


def _mime_type(path: str) -> str:
    overrides = {
        ".js": "text/javascript; charset=utf-8",
        ".json": "application/json; charset=utf-8",
        ".html": "text/html; charset=utf-8",
        ".css": "text/css; charset=utf-8",
        ".svg": "image/svg+xml",
        ".m4a": "audio/mp4",
    }
    return overrides.get(PurePosixPath(path).suffix.lower()) or mimetypes.guess_type(path)[0] or "application/octet-stream"


def _validate_manifest(raw: bytes, available_paths: set[str]) -> dict[str, Any]:
    def unique_object(pairs):
        result = {}
        for key, value in pairs:
            if key in result:
                raise LearningCardPackageError('course.json 包含重复字段')
            result[key] = value
        return result
    try:
        value = json.loads(raw.decode("utf-8-sig"), object_pairs_hook=unique_object)
    except (UnicodeDecodeError, json.JSONDecodeError, RecursionError) as exc:
        raise LearningCardPackageError("course.json 格式错误") from exc
    if not isinstance(value, dict):
        raise LearningCardPackageError("course.json 格式错误")
    if value.get("format") != "cabinlingo-learning-card":
        raise LearningCardPackageError("course.json format 必须为 cabinlingo-learning-card")
    if value.get("version") != "1.0":
        raise LearningCardPackageError("暂不支持该课程包版本")
    if value.get("entry") != "index.html":
        raise LearningCardPackageError("V1 课程包 entry 必须为 index.html")
    if value["entry"] not in available_paths:
        raise LearningCardPackageError("课程包 entry 文件不存在")
    title = value.get("title")
    category = value.get("category")
    if not isinstance(title, str) or not title.strip() or len(title.strip()) > 200:
        raise LearningCardPackageError("course.json title 无效")
    if not isinstance(category, str) or not category.strip() or len(category.strip()) > 100:
        raise LearningCardPackageError("course.json category 无效")
    duration = value.get("estimatedDuration")
    if duration is not None and (isinstance(duration, bool) or not isinstance(duration, int) or not 0 <= duration <= 86400):
        raise LearningCardPackageError("course.json estimatedDuration 无效")
    languages = value.get("languages")
    if languages is not None and (
        not isinstance(languages, list) or len(languages) > 10
        or any(not isinstance(item, str) or not item.strip() or len(item) > 20 for item in languages)
    ):
        raise LearningCardPackageError("course.json languages 无效")
    value["title"] = title.strip()
    value["category"] = category.strip()
    return value


def _validate_static_content(path: str, data: bytes) -> None:
    suffix = PurePosixPath(path).suffix.lower()
    if suffix == ".html":
        lowered = data.lower()
        if b"<base" in lowered or b"http-equiv" in lowered and b"refresh" in lowered:
            raise LearningCardPackageError("课程包包含危险外部跳转")
        if EXTERNAL_URL_RE.search(data):
            raise LearningCardPackageError("课程包包含危险外部资源")
        try:
            _CardHTMLValidator(path).feed(data.decode('utf-8-sig'))
        except UnicodeDecodeError as exc:
            raise LearningCardPackageError('HTML 必须为 UTF-8') from exc
    elif suffix == ".css":
        try:
            _validate_css(data.decode('utf-8-sig'), path)
        except UnicodeDecodeError as exc:
            raise LearningCardPackageError('CSS 必须为 UTF-8') from exc
    elif suffix == ".svg" and ACTIVE_SVG_RE.search(data):
        raise LearningCardPackageError("SVG 包含不允许的活动内容")


def parse_learning_card_package(data: bytes, limits: PackageLimits | None = None) -> LearningCardPackage:
    limits = limits or PackageLimits()
    if not data:
        raise LearningCardPackageError("课程包文件为空")
    if len(data) > limits.max_package_bytes:
        raise LearningCardPackageError("课程包文件过大")
    try:
        archive = ZipFile(BytesIO(data))
    except BadZipFile as exc:
        raise LearningCardPackageError("文件不是有效 ZIP 课程包") from exc
    with archive:
        infos = archive.infolist()
        if len(infos) > limits.max_entries:
            raise LearningCardPackageError("课程包文件数量过多")
        normalized: dict[str, Any] = {}
        seen: dict[str, bool] = {}
        uncompressed_total = 0
        for info in infos:
            raw_name = info.orig_filename
            path = _safe_path(raw_name[:-1] if info.is_dir() else raw_name)
            folded = path.casefold()
            if folded in seen or any(not is_dir and folded.startswith(name + '/') for name, is_dir in seen.items()):
                raise LearningCardPackageError('课程包包含重复资源路径或文件目录冲突')
            if not info.is_dir() and any(name.startswith(folded + '/') for name in seen):
                raise LearningCardPackageError('课程包包含文件目录冲突')
            seen[folded] = info.is_dir()
            mode = stat.S_IFMT(info.external_attr >> 16)
            if mode not in {0, stat.S_IFREG, stat.S_IFDIR} or (mode == stat.S_IFDIR and not info.is_dir()):
                raise LearningCardPackageError('课程包不允许符号链接或特殊文件')
            if info.flag_bits & 0x1:
                raise LearningCardPackageError('课程包不允许加密文件')
            if info.compress_type not in {ZIP_STORED, ZIP_DEFLATED}:
                raise LearningCardPackageError('课程包压缩算法不支持')
            if info.is_dir():
                if path != "assets" and not path.startswith("assets/"):
                    raise LearningCardPackageError("课程包只允许 assets 资源目录")
                continue
            if folded in normalized:
                raise LearningCardPackageError("课程包包含重复资源路径")
            normalized[folded] = (path, info)
            mode = (info.external_attr >> 16) & 0o170000
            if mode == 0o120000:
                raise LearningCardPackageError("课程包不允许符号链接")
            if info.flag_bits & 0x1:
                raise LearningCardPackageError("课程包不允许加密文件")
            suffix = PurePosixPath(path).suffix.lower()
            if suffix in PROHIBITED_EXTENSIONS or suffix not in ALLOWED_EXTENSIONS:
                raise LearningCardPackageError("课程包包含不允许的文件类型")
            if path not in {"course.json", "index.html"} and not path.startswith("assets/"):
                raise LearningCardPackageError("课程包只允许 course.json、index.html 和 assets 目录")
            if info.file_size > limits.max_resource_bytes:
                raise LearningCardPackageError("课程包内单个文件过大")
            if path == 'course.json' and info.file_size > limits.max_manifest_bytes:
                raise LearningCardPackageError('course.json 文件过大')
            if info.file_size and info.compress_size == 0:
                raise LearningCardPackageError("课程包压缩比例异常")
            if info.compress_size and info.file_size / info.compress_size > limits.max_compression_ratio:
                raise LearningCardPackageError("课程包疑似解压炸弹")
            uncompressed_total += info.file_size
            if uncompressed_total > limits.max_uncompressed_bytes:
                raise LearningCardPackageError("课程包解压后文件过大")
        available = {item[0] for item in normalized.values()}
        if "course.json" not in available:
            raise LearningCardPackageError("课程包缺少 course.json")
        if "index.html" not in available:
            raise LearningCardPackageError("课程包缺少 index.html")
        resources: list[LearningCardResource] = []
        actual_total = 0
        for path, info in sorted(normalized.values(), key=lambda item: item[0]):
            chunks = bytearray()
            try:
                with archive.open(info) as stream:
                    while chunk := stream.read(64 * 1024):
                        actual_total += len(chunk)
                        chunks.extend(chunk)
                        if len(chunks) > limits.max_resource_bytes or actual_total > limits.max_uncompressed_bytes:
                            raise LearningCardPackageError('课程包实际解压内容过大')
            except (BadZipFile, RuntimeError, NotImplementedError, EOFError, zlib.error) as exc:
                raise LearningCardPackageError('课程包资源损坏或无法解压') from exc
            raw = bytes(chunks)
            if len(raw) != info.file_size:
                raise LearningCardPackageError("课程包资源读取失败")
            _validate_static_content(path, raw)
            resources.append(LearningCardResource(path, raw, _mime_type(path), sha256(raw).hexdigest()))
        by_path = {resource.path: resource.data for resource in resources}
        manifest = _validate_manifest(by_path["course.json"], available)
        if not by_path["index.html"].strip():
            raise LearningCardPackageError("课程包 index.html 为空")
        return LearningCardPackage(manifest, tuple(resources), sha256(data).hexdigest())
