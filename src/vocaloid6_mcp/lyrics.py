"""Split lyric text into one token per note, and map languages to VOCALOID language IDs.

Japanese: one mora per note ("ー" becomes a "-" note, which VOCALOID sings as the held vowel). Chinese: one
character (or one pinyin syllable) per note. Korean: one syllable block per note. English / Spanish: one syllable
per note; hyphenated words become VOCALOID's syllable form ("hel-lo" -> "hel-", "lo").
"""

import re
import unicodedata

from .errors import VocaloidError

# VOCALOID language IDs (VSQX "bs", VPR "langID").
LANG_IDS = {"ja": 0, "en": 1, "ko": 2, "es": 3, "zh": 4}
LANG_NAMES = {v: k for k, v in LANG_IDS.items()}
CONTINUE = "-"  # VOCALOID's "continue the previous syllable" lyric

_KANA = re.compile(r"[぀-ヿㇰ-ㇿｦ-ﾟ]")
_KANJI = re.compile(r"[㐀-䶿一-鿿豈-﫿々〆]")
_HANGUL = re.compile(r"[가-힣]")
_SMALL = set("ゃゅょぁぃぅぇぉゎャュョァィゥェォヮ")
_OWN = set("っッ")
_LONG = set("ーｰ〜～")  # long vowel: holds the previous mora, so it becomes a continuation note
_EXTENDERS = {"+", "-", "+~", "+*"}


def lang_id(language: str) -> int:
    key = (language or "").lower()
    aliases = {"japanese": "ja", "jp": "ja", "english": "en", "korean": "ko", "kr": "ko", "spanish": "es",
               "chinese": "zh", "cn": "zh", "zh-cn": "zh"}
    key = aliases.get(key, key)
    if key not in LANG_IDS:
        raise VocaloidError(f"Unknown language {language!r}: use ja, en, ko, es or zh",
                            f"不明な言語 {language!r}: ja・en・ko・es・zh のいずれかを指定してください")
    return LANG_IDS[key]


def detect_language(text: str) -> str:
    if _KANA.search(text):
        return "ja"
    if _HANGUL.search(text):
        return "ko"
    if _KANJI.search(text):
        return "zh"  # kanji without any kana: treat as Chinese
    return "en"


def _kanji_to_hiragana(text: str, warnings: list[str]) -> str:
    if not _KANJI.search(text):
        return text
    try:
        import pykakasi
    except ImportError:
        warnings.append(
            "Kanji kept as-is: install pykakasi (pip install pykakasi) to convert kanji to hiragana / "
            "漢字はそのまま残しました: pykakasi をインストールするとひらがなに変換できます"
        )
        return text
    out = []
    for item in pykakasi.kakasi().convert(text):
        orig = item["orig"]
        out.append(item["hira"] if _KANJI.search(orig) else orig)
    return "".join(out)


def _split_japanese(text: str, warnings: list[str]) -> list[str]:
    text = unicodedata.normalize("NFKC", text)  # half-width kana → full-width, full-width ASCII → ASCII
    text = _kanji_to_hiragana(text, warnings)
    tokens: list[str] = []
    prev_kana = False
    word = ""
    for ch in text + " ":
        if ch.isascii() and (ch.isalnum() or ch in "'"):
            word += ch  # romaji: one space-separated word per note
            prev_kana = False
            continue
        if word:
            tokens.append(word.lower())
            word = ""
        if ch in _LONG or (ch in "+-" and tokens):
            if tokens:
                tokens.append(CONTINUE)
            prev_kana = False
        elif ch in _SMALL and prev_kana and ch not in _OWN:
            tokens[-1] += ch
        elif ch in _OWN or _KANA.match(ch):
            tokens.append(ch)
            prev_kana = ch not in _OWN
        elif _KANJI.match(ch):
            tokens.append(ch)  # only reached without pykakasi
            prev_kana = False
        else:
            prev_kana = False  # spaces, punctuation (、。！？…「」 etc.) are dropped
    return tokens


def _vowel_groups(word: str) -> int:
    groups = len(re.findall(r"[aeiouyáéíóúü]+", word))
    if groups > 1 and word.endswith("e") and not word.endswith(("le", "ee")):
        groups -= 1  # silent final e: "love", "time"
    return groups


def _split_words(text: str, warnings: list[str]) -> list[str]:
    """English / Spanish: one syllable per note. VOCALOID looks a word up from its syllables written with a
    trailing hyphen ("hel-" + "lo"); a multi-syllable word on one note, or a "-" hold note, sings as "u:"."""
    tokens: list[str] = []
    unsplit, holds = [], 0
    for raw in text.split():
        if raw in _EXTENDERS:
            tokens.append(CONTINUE)
            holds += 1
            continue
        word = re.sub(r"^[^\w'-]+|[^\w'-]+$", "", raw).lower().strip("-")
        if not word.strip("'"):
            continue
        syllables = [s for s in word.split("-") if s]
        if len(syllables) == 1 and _vowel_groups(syllables[0]) > 1:
            unsplit.append(syllables[0])
        tokens.extend([s + "-" for s in syllables[:-1]] + syllables[-1:])
    if unsplit:
        warnings.append(
            f"These words look like more than one syllable: {unsplit}. VOCALOID sings a multi-syllable word on one "
            f"note as 'u:'; hyphenate them (hel-lo) so each syllable gets its own note / 複数音節に見える単語: {unsplit}。"
            f"1つの音符に複数音節の単語を置くと 'u:' になります。hel-lo のようにハイフンで区切ってください")
    if holds:
        warnings.append(
            "VOCALOID sings a '-' hold note as 'u:' outside Japanese: give the hold note the vowel as its phoneme "
            "(edit_notes phoneme, e.g. '@U') / 日本語以外では '-' の伸ばし音符は 'u:' になります。"
            "edit_notes で母音の発音記号（例 '@U'）を指定してください")
    return tokens


def _split_chinese(text: str) -> list[str]:
    """One hanzi per note; ASCII runs are pinyin, one space-separated syllable per note."""
    tokens: list[str] = []
    for chunk in re.findall(r"[㐀-䶿一-鿿豈-﫿]|[A-Za-züÜ:]+\d?|[+\-]", unicodedata.normalize("NFKC", text)):
        tokens.append(CONTINUE if chunk in "+-" else chunk.lower())
    return tokens


def _split_korean(text: str) -> list[str]:
    tokens: list[str] = []
    for chunk in re.findall(r"[가-힣]|[+\-]", unicodedata.normalize("NFC", text)):
        tokens.append(CONTINUE if chunk in "+-" else chunk)
    return tokens


def split_lyrics(text: str, language: str = "auto") -> tuple[list[str], list[str], str]:
    """Returns (tokens, warnings, language used)."""
    lang = (language or "auto").lower()
    if lang == "auto":
        lang = detect_language(text)
    lang = LANG_NAMES[lang_id(lang)]
    warnings: list[str] = []
    if lang == "ja":
        tokens = _split_japanese(text, warnings)
    elif lang == "zh":
        tokens = _split_chinese(text)
    elif lang == "ko":
        tokens = _split_korean(text)
    else:
        tokens = _split_words(text, warnings)
    return tokens, warnings, lang
