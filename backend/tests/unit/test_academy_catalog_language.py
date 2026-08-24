import json
import re
from pathlib import Path


ACADEMY_CONTENT = Path(__file__).resolve().parents[2] / "academy_content"
CATALOG_PATH = ACADEMY_CONTENT / "_catalog.json"
VISIBLE_KEYS = {"note", "title", "department_label", "summary", "prompt", "options"}
FORBIDDEN_ASCII_TURKISH = {
    "karsilama", "icerik", "kullanici", "egitim", "yonetim", "guvenlik",
    "gorev", "musait", "odeme", "satis", "secin", "dogrulayin", "akisi",
    "aciklama", "durumlari", "bakim", "ariza", "tedarikci",
    "ozel", "giris", "iletisim", "turkce", "ucreti",
}
ASCII_WORD = re.compile(r"[A-Za-z]+")


def _visible_strings(value, key=None):
    if isinstance(value, dict):
        for child_key, child_value in value.items():
            if child_key in VISIBLE_KEYS:
                yield from _visible_strings(child_value, child_key)
            elif isinstance(child_value, (dict, list)):
                yield from _visible_strings(child_value)
    elif isinstance(value, list):
        for item in value:
            yield from _visible_strings(item, key)
    elif isinstance(value, str) and key in VISIBLE_KEYS:
        yield value


def _forbidden_tokens(text):
    return {
        token.lower()
        for token in ASCII_WORD.findall(text)
        if token.lower() in FORBIDDEN_ASCII_TURKISH
    }


def test_academy_catalog_visible_copy_uses_turkish_characters():
    catalog = json.loads(CATALOG_PATH.read_text(encoding="utf-8"))
    offenders = [
        text
        for text in _visible_strings(catalog)
        if _forbidden_tokens(text)
    ]

    assert offenders == []
    assert catalog["courses"][0]["summary"].startswith("Misafir karşılama")
    assert any(course["title"] == "Satın Alma & Stok Yönetimi" for course in catalog["courses"])


def test_academy_lesson_copy_uses_turkish_characters():
    offenders = []
    for lesson_path in ACADEMY_CONTENT.glob("*.md"):
        lesson = lesson_path.read_text(encoding="utf-8")
        if _forbidden_tokens(lesson):
            offenders.append(lesson_path.name)

    assert offenders == []
