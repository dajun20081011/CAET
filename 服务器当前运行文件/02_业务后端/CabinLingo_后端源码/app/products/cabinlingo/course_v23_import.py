from __future__ import annotations

from dataclasses import dataclass
from io import BytesIO
from mimetypes import guess_type
from pathlib import PurePosixPath
from xml.etree import ElementTree as ET
from xml.sax.saxutils import escape
from zipfile import ZIP_DEFLATED, BadZipFile, ZipFile


REQUIRED_SHEETS = ("课程基础信息", "课程精讲", "易错词")
MAX_EXCEL_BYTES = 10 * 1024 * 1024
MAX_MEDIA_ZIP_BYTES = 500 * 1024 * 1024
MAX_MEDIA_FILES = 600

BASE_HEADERS = (
    "course_id", "title_zh", "title_en", "category", "summary", "language",
    "version_label", "organization_id", "cover_file", "video_file", "audio_file", "audio_zh_file", "audio_en_file",
)
LESSON_HEADERS = (
    "course_id", "language", "explanation", "annotated_text", "tone", "pace",
    "rhythm", "pronunciation_notes",
)
MISTAKE_HEADERS = (
    "course_id", "language", "term", "pronunciation", "meaning", "common_mistake", "tip",
)
MISTAKE_EXPORT_HEADERS = (
    "课程编号", "语言", "易错词", "标准读音", "含义", "常见错误", "朗读提示",
)
MISTAKE_FIELD_ALIASES = {
    "course_id": ("课程编号", "course_id"),
    "language": ("语言", "language"),
    "term": ("易错词", "term"),
    "pronunciation": ("标准读音", "pronunciation"),
    "meaning": ("含义", "meaning"),
    "common_mistake": ("常见错误", "common_mistake"),
    "tip": ("朗读提示", "tip"),
}


@dataclass(frozen=True)
class ImportMedia:
    filename: str
    content: bytes
    mime_type: str
    role: str


def _xlsx_column(index: int) -> str:
    result = ""
    while index:
        index, remainder = divmod(index - 1, 26)
        result = chr(65 + remainder) + result
    return result


def build_course_template() -> bytes:
    """Create a small, standards-compliant XLSX without a runtime spreadsheet dependency."""
    sheets = (
        ("课程基础信息", BASE_HEADERS, (
            ("BC001", "等待停机位", "Waiting for a Parking Bay", "常用广播", "落地后等待停机位的解释与安全提醒", "bilingual", "V1.0", "", "BC001_cover.webp", "", "BC001_audio.mp3", "", ""),
        )),
        ("课程精讲", LESSON_HEADERS, (
            ("BC001", "zh", "说明等待原因并安抚旅客。", "女士们、先生们 // 我们已经安全抵达目的地 ↓", "平稳|解释性|安抚", "中速", "清晰|从容", "停机位作为完整词组连贯读出。"),
            ("BC001", "en", "Explain the delay and keep the cabin calm.", "Ladies and gentlemen // we have arrived safely / at our destination ↓", "calm|reassuring", "medium", "clear|measured", "Keep parking bay in one phrase group."),
        )),
        ("易错词", MISTAKE_HEADERS, (
            ("BC001", "zh", "停机位", "tíng jī wèi", "航空器停放的指定位置", "在“停机”和“位”之间断开", "作为完整词组连贯读出"),
            ("BC001", "en", "assigned parking bay", "/əˈsaɪnd ˈpɑːrkɪŋ beɪ/", "指定停机位", "吞掉 assigned 的词尾", "assigned 与 parking 自然连读"),
        )),
    )
    content_types = '<?xml version="1.0" encoding="UTF-8" standalone="yes"?><Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types"><Default Extension="rels" ContentType="application/vnd.openxmlformats-package.relationships+xml"/><Default Extension="xml" ContentType="application/xml"/><Override PartName="/xl/workbook.xml" ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet.main+xml"/><Override PartName="/xl/styles.xml" ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.styles+xml"/>' + ''.join(f'<Override PartName="/xl/worksheets/sheet{i}.xml" ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.worksheet+xml"/>' for i in range(1, len(sheets) + 1)) + '</Types>'
    root_rels = '<?xml version="1.0" encoding="UTF-8" standalone="yes"?><Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships"><Relationship Id="rId1" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/officeDocument" Target="xl/workbook.xml"/></Relationships>'
    workbook = '<?xml version="1.0" encoding="UTF-8" standalone="yes"?><workbook xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main" xmlns:r="http://schemas.openxmlformats.org/officeDocument/2006/relationships"><sheets>' + ''.join(f'<sheet name="{escape(name)}" sheetId="{i}" r:id="rId{i}"/>' for i, (name, _, _) in enumerate(sheets, 1)) + '</sheets></workbook>'
    workbook_rels = '<?xml version="1.0" encoding="UTF-8" standalone="yes"?><Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">' + ''.join(f'<Relationship Id="rId{i}" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/worksheet" Target="worksheets/sheet{i}.xml"/>' for i in range(1, len(sheets) + 1)) + f'<Relationship Id="rId{len(sheets)+1}" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/styles" Target="styles.xml"/></Relationships>'
    styles = '<?xml version="1.0" encoding="UTF-8" standalone="yes"?><styleSheet xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main"><fonts count="2"><font><sz val="11"/><name val="Aptos"/></font><font><b/><color rgb="FFFFFFFF"/><sz val="11"/><name val="Aptos"/></font></fonts><fills count="3"><fill><patternFill patternType="none"/></fill><fill><patternFill patternType="gray125"/></fill><fill><patternFill patternType="solid"><fgColor rgb="FF1E5ED8"/><bgColor indexed="64"/></patternFill></fill></fills><borders count="1"><border><left/><right/><top/><bottom/><diagonal/></border></borders><cellStyleXfs count="1"><xf numFmtId="0" fontId="0" fillId="0" borderId="0"/></cellStyleXfs><cellXfs count="2"><xf xfId="0" numFmtId="0" fontId="0" fillId="0" borderId="0"/><xf xfId="0" numFmtId="0" fontId="1" fillId="2" borderId="0" applyFont="1" applyFill="1"/></cellXfs><cellStyles count="1"><cellStyle name="Normal" xfId="0" builtinId="0"/></cellStyles><dxfs count="0"/></styleSheet>'
    output = BytesIO()
    with ZipFile(output, "w", ZIP_DEFLATED) as archive:
        archive.writestr("[Content_Types].xml", content_types)
        archive.writestr("_rels/.rels", root_rels)
        archive.writestr("xl/workbook.xml", workbook)
        archive.writestr("xl/_rels/workbook.xml.rels", workbook_rels)
        archive.writestr("xl/styles.xml", styles)
        for sheet_index, (_, headers, data_rows) in enumerate(sheets, 1):
            rows = [headers, *data_rows]
            xml_rows = []
            for row_index, row in enumerate(rows, 1):
                cells = []
                for col_index, value in enumerate(row, 1):
                    ref = f"{_xlsx_column(col_index)}{row_index}"
                    style = ' s="1"' if row_index == 1 else ""
                    cells.append(f'<c r="{ref}" t="inlineStr"{style}><is><t>{escape(str(value))}</t></is></c>')
                xml_rows.append(f'<row r="{row_index}">{"".join(cells)}</row>')
            widths = ''.join(f'<col min="{i}" max="{i}" width="{28 if i > 1 else 16}" customWidth="1"/>' for i in range(1, len(headers) + 1))
            dimension = f"A1:{_xlsx_column(len(headers))}{len(rows)}"
            worksheet = f'<?xml version="1.0" encoding="UTF-8" standalone="yes"?><worksheet xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main"><dimension ref="{dimension}"/><sheetViews><sheetView workbookViewId="0"><pane ySplit="1" topLeftCell="A2" activePane="bottomLeft" state="frozen"/></sheetView></sheetViews><cols>' + widths + '</cols><sheetData>' + ''.join(xml_rows) + f'</sheetData><autoFilter ref="{dimension}"/></worksheet>'
            archive.writestr(f"xl/worksheets/sheet{sheet_index}.xml", worksheet)
    return output.getvalue()


def build_mistake_words_workbook(course_id: str = "", mistake_words: list[dict] | None = None) -> bytes:
    """Build the focused, Chinese-header workbook used by the course editor."""
    rows = mistake_words if mistake_words is not None else [
        {
            "language": "en", "term": "medical assistance", "pronunciation": "/ˈmedɪkəl əˈsɪstəns/",
            "meaning": "医疗帮助", "common_mistake": "重音位置错误", "tip": "突出主重音",
        },
        {
            "language": "zh", "term": "医护人员", "pronunciation": "yī hù rén yuán",
            "meaning": "医疗工作人员", "common_mistake": "逐字断开", "tip": "作为完整词组朗读",
        },
    ]
    data_rows = [
        (
            course_id,
            str(item.get("language") or ""),
            str(item.get("term") or ""),
            str(item.get("pronunciation") or ""),
            str(item.get("meaning") or ""),
            str(item.get("common_mistake") or ""),
            str(item.get("tip") or ""),
        )
        for item in rows
    ]
    sheets = (("易错词", MISTAKE_EXPORT_HEADERS, data_rows),)
    content_types = '<?xml version="1.0" encoding="UTF-8" standalone="yes"?><Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types"><Default Extension="rels" ContentType="application/vnd.openxmlformats-package.relationships+xml"/><Default Extension="xml" ContentType="application/xml"/><Override PartName="/xl/workbook.xml" ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet.main+xml"/><Override PartName="/xl/styles.xml" ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.styles+xml"/><Override PartName="/xl/worksheets/sheet1.xml" ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.worksheet+xml"/></Types>'
    root_rels = '<?xml version="1.0" encoding="UTF-8" standalone="yes"?><Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships"><Relationship Id="rId1" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/officeDocument" Target="xl/workbook.xml"/></Relationships>'
    workbook = '<?xml version="1.0" encoding="UTF-8" standalone="yes"?><workbook xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main" xmlns:r="http://schemas.openxmlformats.org/officeDocument/2006/relationships"><sheets><sheet name="易错词" sheetId="1" r:id="rId1"/></sheets></workbook>'
    workbook_rels = '<?xml version="1.0" encoding="UTF-8" standalone="yes"?><Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships"><Relationship Id="rId1" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/worksheet" Target="worksheets/sheet1.xml"/><Relationship Id="rId2" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/styles" Target="styles.xml"/></Relationships>'
    styles = '<?xml version="1.0" encoding="UTF-8" standalone="yes"?><styleSheet xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main"><fonts count="2"><font><sz val="11"/><name val="Aptos"/></font><font><b/><color rgb="FFFFFFFF"/><sz val="11"/><name val="Aptos"/></font></fonts><fills count="3"><fill><patternFill patternType="none"/></fill><fill><patternFill patternType="gray125"/></fill><fill><patternFill patternType="solid"><fgColor rgb="FF1E5ED8"/><bgColor indexed="64"/></patternFill></fill></fills><borders count="1"><border><left/><right/><top/><bottom/><diagonal/></border></borders><cellStyleXfs count="1"><xf numFmtId="0" fontId="0" fillId="0" borderId="0"/></cellStyleXfs><cellXfs count="2"><xf xfId="0" numFmtId="0" fontId="0" fillId="0" borderId="0"/><xf xfId="0" numFmtId="0" fontId="1" fillId="2" borderId="0" applyFont="1" applyFill="1"/></cellXfs><cellStyles count="1"><cellStyle name="Normal" xfId="0" builtinId="0"/></cellStyles><dxfs count="0"/></styleSheet>'
    rows = [MISTAKE_EXPORT_HEADERS, *data_rows]
    xml_rows = []
    for row_index, row in enumerate(rows, 1):
        cells = []
        for col_index, value in enumerate(row, 1):
            ref = f"{_xlsx_column(col_index)}{row_index}"
            style = ' s="1"' if row_index == 1 else ""
            cells.append(f'<c r="{ref}" t="inlineStr"{style}><is><t>{escape(str(value))}</t></is></c>')
        xml_rows.append(f'<row r="{row_index}">{"".join(cells)}</row>')
    widths = ''.join(f'<col min="{i}" max="{i}" width="{18 if i < 4 else 28}" customWidth="1"/>' for i in range(1, len(MISTAKE_EXPORT_HEADERS) + 1))
    dimension = f"A1:{_xlsx_column(len(MISTAKE_EXPORT_HEADERS))}{len(rows)}"
    worksheet = f'<?xml version="1.0" encoding="UTF-8" standalone="yes"?><worksheet xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main"><dimension ref="{dimension}"/><sheetViews><sheetView workbookViewId="0"><pane ySplit="1" topLeftCell="A2" activePane="bottomLeft" state="frozen"/></sheetView></sheetViews><cols>{widths}</cols><sheetData>{"".join(xml_rows)}</sheetData><autoFilter ref="{dimension}"/></worksheet>'
    output = BytesIO()
    with ZipFile(output, "w", ZIP_DEFLATED) as archive:
        archive.writestr("[Content_Types].xml", content_types)
        archive.writestr("_rels/.rels", root_rels)
        archive.writestr("xl/workbook.xml", workbook)
        archive.writestr("xl/_rels/workbook.xml.rels", workbook_rels)
        archive.writestr("xl/styles.xml", styles)
        archive.writestr("xl/worksheets/sheet1.xml", worksheet)
    return output.getvalue()


def _cell_text(cell: ET.Element, shared: list[str], ns: dict[str, str]) -> str:
    cell_type = cell.attrib.get("t")
    if cell_type == "inlineStr":
        return "".join(node.text or "" for node in cell.findall(".//m:t", ns)).strip()
    value = cell.findtext("m:v", default="", namespaces=ns)
    if cell_type == "s" and value:
        try:
            return shared[int(value)].strip()
        except (ValueError, IndexError):
            return ""
    return value.strip()


def read_xlsx_tables(body: bytes) -> dict[str, list[dict[str, str]]]:
    if not body or len(body) > MAX_EXCEL_BYTES:
        raise ValueError("Excel 文件为空或超过 10 MB")
    ns = {"m": "http://schemas.openxmlformats.org/spreadsheetml/2006/main", "r": "http://schemas.openxmlformats.org/officeDocument/2006/relationships", "p": "http://schemas.openxmlformats.org/package/2006/relationships"}
    try:
        with ZipFile(BytesIO(body)) as archive:
            shared: list[str] = []
            if "xl/sharedStrings.xml" in archive.namelist():
                root = ET.fromstring(archive.read("xl/sharedStrings.xml"))
                shared = ["".join(node.text or "" for node in item.findall(".//m:t", ns)) for item in root.findall("m:si", ns)]
            workbook = ET.fromstring(archive.read("xl/workbook.xml"))
            rels = ET.fromstring(archive.read("xl/_rels/workbook.xml.rels"))
            targets = {item.attrib["Id"]: item.attrib["Target"] for item in rels.findall("p:Relationship", ns)}
            tables: dict[str, list[dict[str, str]]] = {}
            for sheet in workbook.findall("m:sheets/m:sheet", ns):
                name = sheet.attrib["name"]
                target = targets[sheet.attrib[f"{{{ns['r']}}}id"]].lstrip("/")
                path = target if target.startswith("xl/") else f"xl/{target}"
                root = ET.fromstring(archive.read(path))
                matrix: list[list[str]] = []
                for row in root.findall(".//m:sheetData/m:row", ns):
                    values: dict[int, str] = {}
                    for cell in row.findall("m:c", ns):
                        reference = cell.attrib.get("r", "A1")
                        letters = "".join(ch for ch in reference if ch.isalpha())
                        index = 0
                        for char in letters:
                            index = index * 26 + ord(char.upper()) - 64
                        values[index - 1] = _cell_text(cell, shared, ns)
                    if values:
                        matrix.append([values.get(i, "") for i in range(max(values) + 1)])
                headers = [value.strip() for value in (matrix[0] if matrix else [])]
                tables[name] = [dict(zip(headers, row + [""] * (len(headers) - len(row)))) for row in matrix[1:] if any(value.strip() for value in row)]
            return tables
    except (BadZipFile, KeyError, ET.ParseError) as exc:
        raise ValueError("Excel 文件不是有效的 .xlsx 工作簿") from exc


def _aliased_value(row: dict[str, str], field: str) -> str:
    return next((row.get(name, "") for name in MISTAKE_FIELD_ALIASES[field] if name in row), "").strip()


def parse_mistake_words_workbook(body: bytes, expected_course_id: str) -> tuple[list[dict], list[dict]]:
    tables = read_xlsx_tables(body)
    if "易错词" not in tables:
        raise ValueError("缺少 Sheet：易错词")
    rows = tables["易错词"]
    present = set(rows[0].keys()) if rows else set()
    missing = [aliases[0] for aliases in MISTAKE_FIELD_ALIASES.values() if not any(name in present for name in aliases)]
    if missing:
        raise ValueError(f"易错词缺少字段：{'、'.join(missing)}")
    valid: list[dict] = []
    errors: list[dict] = []
    seen: set[tuple[str, str]] = set()
    for row_number, row in enumerate(rows, 2):
        course_id = _aliased_value(row, "course_id")
        language = _aliased_value(row, "language").lower()
        term = _aliased_value(row, "term")
        row_errors: list[str] = []
        if course_id and course_id.casefold() != expected_course_id.casefold():
            row_errors.append(f"课程编号应为 {expected_course_id}，也可留空")
        if language not in {"zh", "en"}:
            row_errors.append("语言必须是 zh 或 en")
        if not term:
            row_errors.append("易错词不能为空")
        elif len(term) > 200:
            row_errors.append("易错词不能超过 200 个字符")
        key = (language, " ".join(term.casefold().split()))
        if term and language in {"zh", "en"} and key in seen:
            row_errors.append("同一文件内语言和易错词重复")
        seen.add(key)
        item = {
            "language": language,
            "term": term,
            "pronunciation": _aliased_value(row, "pronunciation"),
            "meaning": _aliased_value(row, "meaning"),
            "common_mistake": _aliased_value(row, "common_mistake"),
            "tip": _aliased_value(row, "tip"),
        }
        for field, limit, label in (
            ("pronunciation", 500, "标准读音"), ("meaning", 2000, "含义"),
            ("common_mistake", 2000, "常见错误"), ("tip", 2000, "朗读提示"),
        ):
            if len(item[field]) > limit:
                row_errors.append(f"{label}不能超过 {limit} 个字符")
        if row_errors:
            errors.append({"row": row_number, "course_id": course_id or expected_course_id, "language": language, "term": term, "message": "；".join(row_errors)})
        else:
            valid.append(item)
    if not rows:
        errors.append({"row": None, "course_id": expected_course_id, "language": "", "term": "", "message": "Excel 中没有可导入的易错词"})
    return valid, errors


def merge_mistake_words(existing: list[dict], incoming: list[dict]) -> dict:
    merged = [dict(item) for item in existing]
    positions = {
        (str(item.get("language") or "").lower(), " ".join(str(item.get("term") or "").casefold().split())): index
        for index, item in enumerate(merged)
    }
    created = updated = skipped = 0
    for item in incoming:
        key = (item["language"], " ".join(item["term"].casefold().split()))
        if key not in positions:
            positions[key] = len(merged)
            merged.append(dict(item))
            created += 1
        elif merged[positions[key]] == item:
            skipped += 1
        else:
            merged[positions[key]] = dict(item)
            updated += 1
    if len(merged) > 100:
        raise ValueError(f"合并后共有 {len(merged)} 条易错词，单门课程最多支持 100 条")
    return {"mistake_words": merged, "created": created, "updated": updated, "skipped": skipped}


def _split_list(value: str) -> list[str]:
    return [item.strip() for item in value.replace("，", "|").replace(",", "|").split("|") if item.strip()]


def validate_course_tables(tables: dict[str, list[dict[str, str]]]) -> tuple[list[dict], list[dict]]:
    missing = [name for name in REQUIRED_SHEETS if name not in tables]
    if missing:
        raise ValueError(f"缺少 Sheet：{'、'.join(missing)}")
    expected = {"课程基础信息": BASE_HEADERS, "课程精讲": LESSON_HEADERS, "易错词": MISTAKE_HEADERS}
    for name, headers in expected.items():
        present = set(tables[name][0].keys()) if tables[name] else set()
        absent = [header for header in headers if header not in present]
        if absent:
            raise ValueError(f"{name} 缺少字段：{'、'.join(absent)}")
    errors: list[dict] = []
    lessons: dict[str, list[dict[str, str]]] = {}
    mistakes: dict[str, list[dict[str, str]]] = {}
    for row in tables["课程精讲"]:
        lessons.setdefault(row.get("course_id", "").strip(), []).append(row)
    for row in tables["易错词"]:
        mistakes.setdefault(row.get("course_id", "").strip(), []).append(row)
    drafts: list[dict] = []
    seen: set[str] = set()
    for row_number, row in enumerate(tables["课程基础信息"], 2):
        code = row.get("course_id", "").strip()
        row_errors = []
        if not code:
            row_errors.append("course_id 不能为空")
        if code.casefold() in seen:
            row_errors.append("course_id 在模板内重复")
        seen.add(code.casefold())
        for field in ("title_zh", "category", "summary", "language", "version_label"):
            if not row.get(field, "").strip():
                row_errors.append(f"{field} 不能为空")
        language = row.get("language", "").strip().lower()
        if language not in {"zh", "en", "bilingual"}:
            row_errors.append("language 必须是 zh、en 或 bilingual")
        course_lessons = lessons.get(code, [])
        required_languages = {"zh", "en"} if language == "bilingual" else {language}
        present_languages = {item.get("language", "").strip().lower() for item in course_lessons if item.get("annotated_text", "").strip()}
        absent_languages = required_languages - present_languages
        if absent_languages:
            row_errors.append(f"课程精讲缺少带 annotated_text 的语言：{','.join(sorted(absent_languages))}")
        if not any(item.get("pace", "").strip() for item in course_lessons):
            row_errors.append("课程精讲的 pace 不能为空")
        course_mistakes = [item for item in mistakes.get(code, []) if item.get("term", "").strip()]
        if not course_mistakes:
            row_errors.append("至少需要 1 条易错词")
        if row_errors:
            errors.append({"row": row_number, "course_id": code, "message": "；".join(row_errors)})
            continue
        annotated_scripts = {item["language"].strip().lower(): item["annotated_text"].strip() for item in course_lessons if item.get("annotated_text", "").strip()}
        explanation = "\n\n".join(item.get("explanation", "").strip() for item in course_lessons if item.get("explanation", "").strip())
        first_lesson = course_lessons[0]
        drafts.append({
            "course_id": code,
            "title_zh": row["title_zh"].strip(),
            "title_en": row.get("title_en", "").strip(),
            "category": row["category"].strip(),
            "summary": row["summary"].strip(),
            "language": language,
            "version_label": row["version_label"].strip(),
            "organization_id": row.get("organization_id", "").strip() or None,
            "cover_file": row.get("cover_file", "").strip(),
            "video_file": row.get("video_file", "").strip(),
            "audio_file": row.get("audio_file", "").strip(),
            "audio_zh_file": row.get("audio_zh_file", "").strip(),
            "audio_en_file": row.get("audio_en_file", "").strip(),
            "explanation": explanation,
            "annotated_scripts": annotated_scripts,
            "delivery_tone": _split_list(first_lesson.get("tone", "")),
            "delivery_pace": first_lesson.get("pace", "").strip(),
            "delivery_rhythm": _split_list(first_lesson.get("rhythm", "")),
            "pronunciation_notes": "\n".join(item.get("pronunciation_notes", "").strip() for item in course_lessons if item.get("pronunciation_notes", "").strip()),
            "mistake_words": [{
                "language": item.get("language", "").strip().lower(),
                "term": item.get("term", "").strip(),
                "pronunciation": item.get("pronunciation", "").strip(),
                "meaning": item.get("meaning", "").strip(),
                "common_mistake": item.get("common_mistake", "").strip(),
                "tip": item.get("tip", "").strip(),
            } for item in course_mistakes],
        })
    return drafts, errors


def read_media_zip(body: bytes) -> dict[str, ImportMedia]:
    if not body:
        return {}
    if len(body) > MAX_MEDIA_ZIP_BYTES:
        raise ValueError("媒体 ZIP 不能超过 500 MB")
    try:
        with ZipFile(BytesIO(body)) as archive:
            files = [item for item in archive.infolist() if not item.is_dir()]
            if len(files) > MAX_MEDIA_FILES:
                raise ValueError("媒体 ZIP 最多包含 600 个文件")
            if sum(item.file_size for item in files) > MAX_MEDIA_ZIP_BYTES:
                raise ValueError("媒体 ZIP 解压后不能超过 500 MB")
            result: dict[str, ImportMedia] = {}
            for item in files:
                path = PurePosixPath(item.filename.replace("\\", "/"))
                if ".." in path.parts:
                    raise ValueError("媒体 ZIP 包含不安全路径")
                filename = path.name
                if not filename or filename.startswith("."):
                    continue
                lower = filename.lower()
                role = "cover" if "_cover." in lower else "video" if "_video." in lower else "audio_zh" if "_audio_zh." in lower else "audio_en" if "_audio_en." in lower else "audio" if "_audio." in lower else ""
                if not role:
                    raise ValueError(f"媒体文件名不符合规则：{filename}")
                explicit_types = {
                    ".jpg": "image/jpeg", ".jpeg": "image/jpeg", ".png": "image/png", ".webp": "image/webp",
                    ".mp4": "video/mp4", ".webm": "video/webm", ".mov": "video/quicktime",
                    ".mp3": "audio/mpeg", ".wav": "audio/wav", ".m4a": "audio/mp4", ".ogg": "audio/ogg",
                }
                mime_type = explicit_types.get(path.suffix.lower()) or guess_type(filename)[0] or "application/octet-stream"
                if role.startswith("audio") and path.suffix.lower() == ".webm":
                    mime_type = "audio/webm"
                allowed = {
                    "cover": {"image/jpeg", "image/png", "image/webp"},
                    "video": {"video/mp4", "video/webm", "video/quicktime"},
                    "audio": {"audio/mpeg", "audio/wav", "audio/x-wav", "audio/mp4", "audio/ogg", "audio/webm"},
                    "audio_zh": {"audio/mpeg", "audio/wav", "audio/x-wav", "audio/mp4", "audio/ogg", "audio/webm"},
                    "audio_en": {"audio/mpeg", "audio/wav", "audio/x-wav", "audio/mp4", "audio/ogg", "audio/webm"},
                }
                if mime_type not in allowed[role]:
                    raise ValueError(f"媒体格式不支持：{filename}")
                key = filename.casefold()
                if key in result:
                    raise ValueError(f"媒体 ZIP 内文件名重复：{filename}")
                result[key] = ImportMedia(filename, archive.read(item), mime_type, role)
            return result
    except BadZipFile as exc:
        raise ValueError("媒体文件不是有效 ZIP") from exc


def collect_course_media(draft: dict, media: dict[str, ImportMedia]) -> tuple[list[ImportMedia], list[str]]:
    selected: list[ImportMedia] = []
    errors: list[str] = []
    for field, role in (("cover_file", "cover"), ("video_file", "video"), ("audio_file", "audio"), ("audio_zh_file", "audio_zh"), ("audio_en_file", "audio_en")):
        filename = str(draft.get(field) or "").strip()
        if not filename:
            continue
        expected_prefix = f"{draft.get('course_id', '')}_{role}.".casefold()
        if not filename.casefold().startswith(expected_prefix):
            errors.append(f"{filename} 应按 {draft.get('course_id', '')}_{role}.扩展名 命名")
            continue
        item = media.get(filename.casefold())
        if not item:
            errors.append(f"ZIP 中未找到 {filename}")
        elif item.role != role:
            errors.append(f"{filename} 的媒体角色不匹配")
        else:
            selected.append(item)
    complete = bool(str(draft.get("audio_file") or "").strip())
    zh = bool(str(draft.get("audio_zh_file") or "").strip())
    en = bool(str(draft.get("audio_en_file") or "").strip())
    language = draft.get("language")
    if language == "bilingual" and not complete and not (zh and en):
        errors.append("双语课程需提供 audio_file，或同时提供 audio_zh_file 和 audio_en_file")
    elif language == "zh" and not (complete or zh):
        errors.append("中文课程需提供 audio_file 或 audio_zh_file")
    elif language == "en" and not (complete or en):
        errors.append("英文课程需提供 audio_file 或 audio_en_file")
    return selected, errors
