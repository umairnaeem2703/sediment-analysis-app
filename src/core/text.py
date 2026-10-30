"""Text rules shared by the models and the services: Turkish lowercasing and ASCII folding, and the key that
compares dam and sub-basin names (D70)."""

import re
import unicodedata


def turkish_lower(text: str) -> str:
    """Lowercase string using Turkish character rules (I -> ı, İ -> i)."""
    if text is None:
        return ""
    normalized = unicodedata.normalize("NFC", str(text))
    tr_map = {
        ord("I"): "ı",
        ord("İ"): "i",
    }
    return normalized.translate(tr_map).lower()


def to_ascii_turkish(text: str) -> str:
    """Convert Turkish characters to ASCII equivalents for robust matching."""
    if text is None:
        return ""
    ascii_map = {
        ord("ç"): "c",
        ord("Ç"): "C",
        ord("ğ"): "g",
        ord("Ğ"): "G",
        ord("ı"): "i",
        ord("I"): "I",
        ord("İ"): "I",
        ord("i"): "i",
        ord("ö"): "o",
        ord("Ö"): "O",
        ord("ş"): "s",
        ord("Ş"): "S",
        ord("ü"): "u",
        ord("Ü"): "U",
        ord("â"): "a",
        ord("Â"): "A",
        ord("î"): "i",
        ord("Î"): "I",
        ord("û"): "u",
        ord("Û"): "U",
    }
    return str(text).translate(ascii_map)


_PLAIN_NUMBER = re.compile(r"([+-]?)(\d+)(?:\.(\d+))?")
_ALNUM_RUN = re.compile(r"[^\W_]+")


def name_key(text) -> str:
    """The comparison key of a dam or sub-basin name (D70): Turkish letters folded to ASCII, lowercase, and only
    letters and digits kept, so 'Çubuk 1', 'ÇUBUK-1' and 'cubuk1' give 'cubuk1'. Two numbers stay apart ('1.1' and
    '11' are different names), and a name that is only a number is written the shortest way ('1.0' and '01' give '1')."""
    text = "" if text is None else str(text).strip()
    plain = _PLAIN_NUMBER.fullmatch(text)
    if plain:
        sign, whole, fraction = plain.group(1), plain.group(2).lstrip("0") or "0", (plain.group(3) or "").rstrip("0")
        return (
            ("-" if sign == "-" and (whole != "0" or fraction) else "") + whole + ("." + fraction if fraction else "")
        )
    key = ""
    for run in _ALNUM_RUN.findall(to_ascii_turkish(turkish_lower(text))):
        key += "." + run if key[-1:].isdigit() and run[0].isdigit() else run
    return key
