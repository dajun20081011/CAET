#!/usr/bin/env python3
"""Create a CabinLingo Learning Card Package V1 from finished HTML assets."""

from argparse import ArgumentParser
from pathlib import Path, PurePosixPath
import json
from zipfile import ZIP_DEFLATED, ZipFile


ALLOWED = {".html", ".css", ".js", ".json", ".png", ".jpg", ".jpeg", ".webp", ".svg", ".mp3", ".wav", ".m4a", ".mp4", ".webm"}


def main() -> None:
    parser = ArgumentParser(description="Build CabinLingo Learning Card Package V1")
    parser.add_argument("source", type=Path, help="Folder containing index.html and optional assets/")
    parser.add_argument("--title", required=True)
    parser.add_argument("--category", required=True)
    parser.add_argument("--duration", type=int)
    parser.add_argument("--languages", default="zh-CN,en", help="Comma-separated language tags")
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    source = args.source.resolve()
    entry = source / "index.html"
    if not entry.is_file():
        raise SystemExit("source must contain index.html")
    manifest = {
        "format": "cabinlingo-learning-card", "version": "1.0", "title": args.title.strip(),
        "category": args.category.strip(), "entry": "index.html",
        "languages": [value.strip() for value in args.languages.split(",") if value.strip()],
    }
    if args.duration is not None:
        manifest["estimatedDuration"] = args.duration
    files = [entry]
    assets = source / "assets"
    if assets.is_dir():
        files.extend(path for path in assets.rglob("*") if path.is_file())
    for path in files:
        relative = PurePosixPath(path.relative_to(source).as_posix())
        if relative.suffix.lower() not in ALLOWED:
            raise SystemExit(f"unsupported resource type: {relative}")
    args.output.parent.mkdir(parents=True, exist_ok=True)
    with ZipFile(args.output, "w", ZIP_DEFLATED) as archive:
        archive.writestr("course.json", json.dumps(manifest, ensure_ascii=False, indent=2))
        for path in files:
            archive.write(path, path.relative_to(source).as_posix())
    print(args.output.resolve())


if __name__ == "__main__":
    main()
