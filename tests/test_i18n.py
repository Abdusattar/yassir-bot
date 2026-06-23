from core.i18n import T


def test_returns_russian_by_default():
    assert "серия" in T("mystats_streak", n=5).lower()


def test_kyrgyz_translation():
    result = T("mystats_streak", "ky", n=5)
    assert "5" in result
    assert "күн" in result


def test_fallback_to_russian_for_unknown_lang():
    result = T("mystats_streak", "xx", n=3)
    assert "3" in result
    assert result == T("mystats_streak", "ru", n=3)


def test_unknown_key_returns_empty():
    assert T("nonexistent_key_xyz") == ""


def test_format_kwargs():
    result = T("mystats_rank", "ru", n=2)
    assert "#2" in result


def test_rating_points_languages():
    assert T("rating_points", "ru") == "очков"
    assert T("rating_points", "ky") == "упай"
    assert T("rating_points", "en") == "pts"


def test_not_registered_all_langs():
    for lang in ("ru", "ky", "uz", "kk", "ar", "en"):
        result = T("not_registered", lang)
        assert len(result) > 5, f"Пустой перевод для lang={lang}"


def test_help_redirect_all_langs():
    for lang in ("ru", "ky", "uz", "kk", "ar", "en"):
        result = T("help_redirect", lang)
        assert "/help" in result, f"Нет /help для lang={lang}"
