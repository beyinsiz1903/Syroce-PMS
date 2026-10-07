from domains.ai.endpoints import _primary_language


def test_primary_language_accepts_browser_locale_tags():
    assert _primary_language("tr-TR") == "tr"
    assert _primary_language("tr_TR") == "tr"
    assert _primary_language("en-US") == "en"
    assert _primary_language(None) == "tr"
