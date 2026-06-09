"""ローマ字 → ひらがな（LNAIME はローマ字ベタ打ち入力が前提）。
貪欲な最長一致 + 促音(子音重ね→っ) + 撥音(n)。Hepburn/訓令の主要表記に対応。
"""
from __future__ import annotations

_T = {
    "a": "あ", "i": "い", "u": "う", "e": "え", "o": "お",
    "ka": "か", "ki": "き", "ku": "く", "ke": "け", "ko": "こ",
    "ga": "が", "gi": "ぎ", "gu": "ぐ", "ge": "げ", "go": "ご",
    "sa": "さ", "si": "し", "shi": "し", "su": "す", "se": "せ", "so": "そ",
    "za": "ざ", "zi": "じ", "ji": "じ", "zu": "ず", "ze": "ぜ", "zo": "ぞ",
    "ta": "た", "ti": "ち", "chi": "ち", "tu": "つ", "tsu": "つ", "te": "て", "to": "と",
    "da": "だ", "di": "ぢ", "du": "づ", "de": "で", "do": "ど",
    "na": "な", "ni": "に", "nu": "ぬ", "ne": "ね", "no": "の",
    "ha": "は", "hi": "ひ", "hu": "ふ", "fu": "ふ", "he": "へ", "ho": "ほ",
    "ba": "ば", "bi": "び", "bu": "ぶ", "be": "べ", "bo": "ぼ",
    "pa": "ぱ", "pi": "ぴ", "pu": "ぷ", "pe": "ぺ", "po": "ぽ",
    "ma": "ま", "mi": "み", "mu": "む", "me": "め", "mo": "も",
    "ya": "や", "yu": "ゆ", "yo": "よ",
    "ra": "ら", "ri": "り", "ru": "る", "re": "れ", "ro": "ろ",
    "wa": "わ", "wo": "を", "wi": "うぃ", "we": "うぇ",
    "kya": "きゃ", "kyu": "きゅ", "kyo": "きょ",
    "gya": "ぎゃ", "gyu": "ぎゅ", "gyo": "ぎょ",
    "sha": "しゃ", "shu": "しゅ", "sho": "しょ", "sya": "しゃ", "syu": "しゅ", "syo": "しょ",
    "ja": "じゃ", "ju": "じゅ", "jo": "じょ", "jya": "じゃ", "jyu": "じゅ", "jyo": "じょ",
    "zya": "じゃ", "zyu": "じゅ", "zyo": "じょ",
    "cha": "ちゃ", "chu": "ちゅ", "cho": "ちょ", "tya": "ちゃ", "tyu": "ちゅ", "tyo": "ちょ",
    "nya": "にゃ", "nyu": "にゅ", "nyo": "にょ",
    "hya": "ひゃ", "hyu": "ひゅ", "hyo": "ひょ",
    "bya": "びゃ", "byu": "びゅ", "byo": "びょ",
    "pya": "ぴゃ", "pyu": "ぴゅ", "pyo": "ぴょ",
    "mya": "みゃ", "myu": "みゅ", "myo": "みょ",
    "rya": "りゃ", "ryu": "りゅ", "ryo": "りょ",
    "fa": "ふぁ", "fi": "ふぃ", "fe": "ふぇ", "fo": "ふぉ",
    "che": "ちぇ", "she": "しぇ", "je": "じぇ",
    "la": "ぁ", "li": "ぃ", "lu": "ぅ", "le": "ぇ", "lo": "ぉ",
    "xa": "ぁ", "xi": "ぃ", "xu": "ぅ", "xe": "ぇ", "xo": "ぉ",
    "ltu": "っ", "xtu": "っ", "ltsu": "っ",
    "-": "ー",
}


def romaji_to_hiragana(s: str) -> str:
    s = s.lower()
    out: list[str] = []
    i, n = 0, len(s)
    while i < n:
        c = s[i]
        # 促音: 同じ子音の重ね（n を除く）→ っ
        if c in "bcdfghjkmpqrstvwz" and i + 1 < n and s[i + 1] == c:
            out.append("っ")
            i += 1
            continue
        # 撥音 ん
        if c == "n":
            nxt = s[i + 1] if i + 1 < n else ""
            if nxt == "'":
                out.append("ん")
                i += 2
                continue
            if nxt == "n":
                if i + 2 < n and s[i + 2] in "aiueoy":   # nni → ん + に
                    out.append("ん")
                    i += 1
                    continue
                out.append("ん")                          # nn → ん
                i += 2
                continue
            if nxt not in "aiueoy":                        # n + 子音/末尾 → ん
                out.append("ん")
                i += 1
                continue
            # nxt が母音/y → な行（最長一致へ）
        # 最長一致（4→1）
        for ln in (4, 3, 2, 1):
            chunk = s[i:i + ln]
            if chunk in _T:
                out.append(_T[chunk])
                i += ln
                break
        else:
            out.append(c)  # 数字・記号・未知はそのまま
            i += 1
    return "".join(out)
