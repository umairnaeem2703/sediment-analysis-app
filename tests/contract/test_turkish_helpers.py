"""C-X-02: the Turkish-first helpers behind header and name matching (FR-X-02)."""

import pytest

from src.core.text import to_ascii_turkish, turkish_lower
from src.services.labels import fold


@pytest.mark.parametrize(
    "header, expected",
    [
        ("Flow Q (m³/s)", "flowq(m3/s)"),
        ("Yıllar", "yillar"),
        ("YILLAR", "yillar"),
        ("TOP.", "top"),
        ("ORT.", "ort"),
        ("Ağustos", "agustos"),
        ("Eylül", "eylul"),
        (" Tarih ", "tarih"),
        ("Water_Year", "water_year"),
    ],
)
def test_c_x_02_headers_are_folded_to_lowercase_ascii_without_spaces(header, expected):
    assert fold(header) == expected


@pytest.mark.parametrize(
    "text, expected",
    [
        ("IŞIK", "ışık"),
        ("İSTANBUL", "istanbul"),
        ("ÇORUH", "çoruh"),
        ("GÖKSU", "göksu"),
        ("AŞAĞI", "aşağı"),
        ("DÜZCE", "düzce"),
    ],
)
def test_c_x_02_turkish_lower_follows_the_turkish_casing_rules(text, expected):
    assert turkish_lower(text) == expected


@pytest.mark.parametrize(
    "text, expected",
    [
        ("ışık", "isik"),
        ("istanbul", "istanbul"),
        ("çoruh", "coruh"),
        ("göksu", "goksu"),
        ("aşağı", "asagi"),
        ("düzce", "duzce"),
        ("ÖMERLİ", "OMERLI"),
    ],
)
def test_c_x_02_to_ascii_turkish_transliterates_and_keeps_the_case(text, expected):
    assert to_ascii_turkish(text) == expected
