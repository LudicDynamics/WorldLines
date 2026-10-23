"""Tests for the card i18n helpers."""

import pytest

from neonrp.core.i18n_card import (
    card_field,
    card_name_for_locale,
    field_as_i18n,
    build_i18n_block,
    locale_to_source_lang,
)


class TestCardField:
    def test_plain_string(self):
        assert card_field("hello", "en") == "hello"
        assert card_field("hello", "ja") == "hello"

    def test_i18n_dict_exact_match(self):
        field = {"en": "Hello", "zh": "你好", "ja": "こんにちは"}
        assert card_field(field, "en") == "Hello"
        assert card_field(field, "zh") == "你好"
        assert card_field(field, "ja") == "こんにちは"

    def test_i18n_dict_fallback_to_source_lang(self):
        field = {"en": "Hello", "zh": "你好"}
        # ja not present → fall back to source_lang (en)
        assert card_field(field, "ja", source_lang="en") == "Hello"
        # if source_lang is zh → fall back to zh
        assert card_field(field, "ja", source_lang="zh") == "你好"

    def test_i18n_dict_fallback_to_first_available(self):
        field = {"zh": "你好", "ja": "こんにちは"}
        # en not present, source_lang=en not in field → first available
        assert card_field(field, "en", source_lang="en") == "你好"

    def test_none_returns_empty(self):
        assert card_field(None, "en") == ""

    def test_empty_dict_returns_empty(self):
        assert card_field({}, "en") == ""


class TestCardNameForLocale:
    def test_plain_name_no_local(self):
        assert card_name_for_locale("Elena", "", "en") == "Elena"

    def test_name_with_local_same_locale(self):
        # Chinese UI, Chinese card → show both
        result = card_name_for_locale("Elena", "艾琳娜", "zh", source_lang="zh")
        assert result == "Elena (艾琳娜)"

    def test_non_source_locale_prefers_latin(self):
        # Japanese UI, Chinese-sourced card → show latin only (jarring CJK)
        result = card_name_for_locale("Elena", "艾琳娜", "ja", source_lang="zh")
        assert result == "Elena"

    def test_korean_ui_also_prefers_latin(self):
        result = card_name_for_locale("Elena", "艾琳娜", "ko", source_lang="zh")
        assert result == "Elena"

    def test_name_i18n_has_locale(self):
        # If name_i18n has a ja entry → use it
        result = card_name_for_locale(
            "Elena", "艾琳娜", "ja", source_lang="zh",
            name_i18n={"ja": "エレナ", "zh": "艾琳娜", "en": "Elena"},
        )
        assert result == "エレナ"

    def test_name_i18n_missing_locale_falls_back(self):
        # name_i18n has no ko entry → fall back to source_lang
        result = card_name_for_locale(
            "Elena", "艾琳娜", "ko", source_lang="zh",
            name_i18n={"zh": "艾琳娜", "en": "Elena"},
        )
        assert result == "艾琳娜"


class TestBuildI18nBlock:
    def test_source_only_stays_dict(self):
        # When only source_lang is provided, still returns a dict
        block = build_i18n_block(en="Hello")
        assert block == {"en": "Hello"}

    def test_multiple_locales(self):
        block = build_i18n_block(en="Hello", zh="你好", ja="こんにちは")
        assert block == {"en": "Hello", "zh": "你好", "ja": "こんにちは"}

    def test_empty_returns_empty(self):
        assert build_i18n_block() == {}


class TestLocaleToSourceLang:
    def test_zh(self):
        assert locale_to_source_lang("zh") == "zh"

    def test_ja(self):
        assert locale_to_source_lang("ja") == "ja"

    def test_ko(self):
        assert locale_to_source_lang("ko") == "ko"

    def test_en(self):
        assert locale_to_source_lang("en") == "en"

    def test_unknown(self):
        assert locale_to_source_lang("fr") == "en"
