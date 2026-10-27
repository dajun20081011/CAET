from pathlib import Path

from bs4 import BeautifulSoup

from schemas.course import BroadcastContent, CAET2Content, CAET3Content


def _text(root, selector: str, default=None):
    node = root.select_one(selector)
    if not node:
        return default
    value = node.get_text(" ", strip=True)
    return value if value else default


def _audio_src(root, selector: str):
    node = root.select_one(selector)
    if not node:
        return None
    return node.get("src")


def _keywords(root):
    items = []
    for node in root.select("[data-keyword]"):
        item = {
            "word": _text(node, '[data-field="word"]', ""),
            "phonetic": _text(node, '[data-field="phonetic"]'),
            "meaning": _text(node, '[data-field="meaning"]'),
            "note": _text(node, '[data-field="note"]'),
            "audio_url": _audio_src(node, '[data-field="audio"]'),
        }
        if item["word"]:
            items.append(item)
    return items


def _images(root):
    result = []
    for node in root.select("img[data-caet-image]"):
        src = node.get("src")
        if src:
            result.append(src)
    return result


def parse_course_html(file_path: str):
    path = Path(file_path)
    if not path.exists():
        raise ValueError("HTML file not found")

    soup = BeautifulSoup(path.read_text(encoding="utf-8"), "html.parser")
    article = soup.select_one("[data-caet-template]")
    if not article:
        raise ValueError("Missing data-caet-template")

    template_type = article.get("data-caet-template")
    title = _text(article, '[data-field="title"]')
    if not title:
        raise ValueError("Missing lesson title")

    images = _images(article)

    if template_type == "broadcast":
        content = BroadcastContent(
            chinese_text=_text(article, '[data-field="chinese_text"]', ""),
            english_text=_text(article, '[data-field="english_text"]', ""),
            standard_audio_url=_audio_src(article, '[data-field="standard_audio"]'),
            slow_audio_url=_audio_src(article, '[data-field="slow_audio"]'),
            key_words=_keywords(article),
            images=images,
        )
    elif template_type == "caet2":
        content = CAET2Content(
            scenario=_text(article, '[data-field="scenario"]'),
            chinese_prompt=_text(article, '[data-field="chinese_prompt"]', ""),
            standard_english=_text(article, '[data-field="standard_english"]', ""),
            standard_audio_url=_audio_src(article, '[data-field="standard_audio"]'),
            key_words=_keywords(article),
            expression_tips=[
                node.get_text(" ", strip=True)
                for node in article.select("[data-expression-tip]")
                if node.get_text(" ", strip=True)
            ],
            images=images,
        )
    elif template_type == "caet3":
        content = CAET3Content(
            scenario=_text(article, '[data-field="scenario"]'),
            chinese_task=_text(article, '[data-field="chinese_task"]', ""),
            reference_english=_text(article, '[data-field="reference_english"]'),
            standard_audio_url=_audio_src(article, '[data-field="standard_audio"]'),
            key_points=[
                node.get_text(" ", strip=True)
                for node in article.select("[data-key-point]")
                if node.get_text(" ", strip=True)
            ],
            key_words=_keywords(article),
            expression_logic=[
                node.get_text(" ", strip=True)
                for node in article.select("[data-expression-logic]")
                if node.get_text(" ", strip=True)
            ],
            images=images,
        )
    else:
        raise ValueError(f"Unsupported template type: {template_type}")

    return {
        "title": title,
        "template_type": template_type,
        "content": content.model_dump(mode="json"),
    }
