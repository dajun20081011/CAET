import shutil
import tempfile
import uuid
import zipfile
from pathlib import Path, PurePosixPath

from services.html_parser import parse_course_html


MAX_ZIP_SIZE = 100 * 1024 * 1024
MAX_UNCOMPRESSED_SIZE = 300 * 1024 * 1024
MAX_FILES = 500
ALLOWED_RESOURCE_EXTENSIONS = {
    ".mp3", ".wav", ".m4a", ".ogg", ".aac",
    ".png", ".jpg", ".jpeg", ".webp",
}


def _safe_member(name: str) -> PurePosixPath:
    path = PurePosixPath(name)
    if path.is_absolute() or ".." in path.parts:
        raise ValueError(f"Unsafe ZIP path: {name}")
    return path


def _referenced_paths(content: dict):
    refs = []
    for key in ("standard_audio_url", "slow_audio_url"):
        value = content.get(key)
        if value:
            refs.append(value)
    for kw in content.get("key_words", []):
        if kw.get("audio_url"):
            refs.append(kw["audio_url"])
    refs.extend(content.get("images", []))
    return refs


def _rewrite(content: dict, mapping: dict):
    result = dict(content)
    for key in ("standard_audio_url", "slow_audio_url"):
        value = result.get(key)
        if value in mapping:
            result[key] = mapping[value]
    words = []
    for item in result.get("key_words", []):
        item = dict(item)
        if item.get("audio_url") in mapping:
            item["audio_url"] = mapping[item["audio_url"]]
        words.append(item)
    result["key_words"] = words
    result["images"] = [mapping.get(value, value) for value in result.get("images", [])]
    return result


def process_course_zip(zip_path: str, uploads_root: str = "/uploads"):
    zip_file = Path(zip_path)
    if zip_file.stat().st_size > MAX_ZIP_SIZE:
        raise ValueError("ZIP file is too large")

    with tempfile.TemporaryDirectory(prefix="caet_zip_") as temp_dir:
        temp_root = Path(temp_dir)
        with zipfile.ZipFile(zip_file) as zf:
            infos = [info for info in zf.infolist() if not info.is_dir()]
            if len(infos) > MAX_FILES:
                raise ValueError("ZIP contains too many files")
            if sum(info.file_size for info in infos) > MAX_UNCOMPRESSED_SIZE:
                raise ValueError("ZIP uncompressed size is too large")

            html_members = []
            for info in infos:
                member = _safe_member(info.filename)
                suffix = member.suffix.lower()
                if suffix in {".html", ".htm"}:
                    html_members.append(info)
                elif suffix not in ALLOWED_RESOURCE_EXTENSIONS:
                    raise ValueError(f"Unsupported file in ZIP: {info.filename}")

            if not html_members:
                raise ValueError("ZIP must contain an HTML file")

            selected = next((x for x in html_members if PurePosixPath(x.filename).name.lower() == "index.html"), None)
            if selected is None:
                if len(html_members) != 1:
                    raise ValueError("ZIP must contain index.html or exactly one HTML file")
                selected = html_members[0]

            for info in infos:
                member = _safe_member(info.filename)
                target = temp_root.joinpath(*member.parts)
                target.parent.mkdir(parents=True, exist_ok=True)
                with zf.open(info) as src, target.open("wb") as dst:
                    shutil.copyfileobj(src, dst)

        html_rel = PurePosixPath(selected.filename)
        parsed = parse_course_html(str(temp_root.joinpath(*html_rel.parts)))
        base_dir = html_rel.parent
        refs = _referenced_paths(parsed["content"])

        bundle_id = uuid.uuid4().hex
        dest_root = Path(uploads_root) / "lessons" / bundle_id
        mapping = {}

        for ref in refs:
            ref_path = _safe_member(ref)
            source_rel = base_dir / ref_path
            source = temp_root.joinpath(*source_rel.parts)
            if not source.exists() or not source.is_file():
                raise ValueError(f"Referenced resource not found: {ref}")
            if source.suffix.lower() not in ALLOWED_RESOURCE_EXTENSIONS:
                raise ValueError(f"Unsupported resource type: {ref}")
            target = dest_root.joinpath(*ref_path.parts)
            target.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(source, target)
            mapping[ref] = f"/media/lessons/{bundle_id}/{ref_path.as_posix()}"

        parsed["content"] = _rewrite(parsed["content"], mapping)
        parsed["bundle_id"] = bundle_id
        return parsed
