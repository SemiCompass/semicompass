"""事実確認（P08）：文章から、主張（数値・日付・URL・固有名詞の候補）を取り出す（要件定義書6.5）。

* 文章は NFKC に正規化して読む（全角の数字・記号を半角にする）。出典の番号 [S1] は、読む前に除く
* 数値：数字と単位の組と、その前の項目名（売上収益、営業利益など）。年・月・日は、日付として別に取り出す
* 日付：年月日、年月（「2025年12月期」を含む）、年度、年
* URL：本文のリンク
* 固有名詞の候補：企業名らしい語（「…製作所」「…エレクトロン」「…株式会社」など）。辞書にある語の判定は factcheck.py で行う
本文（資料）の文字列は、ここでは扱わない。扱うのは、変更後の文章（公開される文章）だけである。
"""

from __future__ import annotations

import re
import unicodedata
from dataclasses import dataclass

CITATION = re.compile(r"\[S\d+\]")
URL = re.compile(r"https?://[^\s)\]>\"'」』）]+")
TRAILING_PUNCT = ".,;:、。，．"

# 単位 → (分類, 倍率)。倍率は、分類の基本の単位（円、人、ドルなど）にそろえるための値
UNITS: dict[str, tuple[str, float]] = {
    "兆円": ("yen", 1e12), "億円": ("yen", 1e8), "百万円": ("yen", 1e6), "千円": ("yen", 1e3), "万円": ("yen", 1e4), "円": ("yen", 1.0),
    "億米ドル": ("usd", 1e8), "億ドル": ("usd", 1e8), "百万米ドル": ("usd", 1e6), "百万ドル": ("usd", 1e6), "米ドル": ("usd", 1.0), "ドル": ("usd", 1.0),
    "万人": ("person", 1e4), "人": ("person", 1.0),
    "%": ("percent", 1.0), "社": ("company", 1.0), "件": ("count", 1.0), "枚": ("wafer", 1.0), "倍": ("times", 1.0),
    "ナノメートル": ("nm", 1.0), "nm": ("nm", 1.0), "か月": ("month", 1.0), "カ月": ("month", 1.0), "ヶ月": ("month", 1.0),
}
UNIT_PATTERN = "|".join(sorted((re.escape(u) for u in UNITS), key=len, reverse=True))
NUMBER_BODY = r"\d{1,3}(?:,\d{3})+(?:\.\d+)?|\d+(?:\.\d+)?"
NUMBER = re.compile(rf"(?<![0-9A-Za-z.,/])({NUMBER_BODY})\s*({UNIT_PATTERN})")
BARE_NUMBER = re.compile(rf"(?<![0-9A-Za-z.,/])({NUMBER_BODY})(?![0-9A-Za-z])")
LABEL_STOP = "、。，．「」『』（）()[]【】\n\t 　:：;；/／"
LABEL_TAIL = "はがをのにでともへやからより"
DATE_FULL = re.compile(r"(\d{4})年(\d{1,2})月(\d{1,2})日")
DATE_MONTH = re.compile(r"(\d{4})年(\d{1,2})月(?!\d{1,2}日)")
DATE_FISCAL = re.compile(r"(\d{4})年度")
DATE_YEAR = re.compile(r"(\d{4})年(?!\d{1,2}月|度)")
COMPANY_SUFFIXES = ("株式会社", "製作所", "エレクトロニクス", "エレクトロン", "セミコンダクターズ", "セミコンダクター", "ホールディングス", "テクノロジーズ", "テクノロジー", "ソリューションズ", "化学", "電機", "電子", "工業")
WORD_CHARS = re.compile(r"[0-9A-Za-z一-龥ぁ-んァ-ヶー・&.\-]+")
COMPANY_CANDIDATE = re.compile(
    r"(?:株式会社[一-龥ァ-ヶーA-Za-z]{2,12})|(?:[一-龥ァ-ヶーA-Za-z]{2,12}(?:" + "|".join(COMPANY_SUFFIXES[1:]) + r"|株式会社))")


@dataclass
class Claim:
    id: str
    kind: str          # number | date | url | proper
    text: str          # 文章にある表記（NFKC 後）
    start: int         # 正規化後の文章での位置
    value: float | None = None
    unit: str | None = None
    decimals: int = 0
    label: str = ""
    key: tuple | None = None   # 日付の正規化したキー

    def fingerprint(self) -> str:
        return f"{self.kind}:{self.text}"


def normalize(text: str) -> str:
    return unicodedata.normalize("NFKC", CITATION.sub("", text))


def to_number(raw: str) -> tuple[float, int]:
    raw = raw.replace(",", "")
    return float(raw), (len(raw.split(".")[1]) if "." in raw else 0)


def label_before(text: str, pos: int, limit: int = 15) -> str:
    start = pos
    while start > 0 and pos - start < limit and text[start - 1] not in LABEL_STOP:
        start -= 1
    label = text[start:pos]
    while label and label[-1] in LABEL_TAIL:
        label = label[:-1]
    return label


def edit_distance(a: str, b: str) -> int:
    prev = list(range(len(b) + 1))
    for i, ca in enumerate(a, 1):
        cur = [i]
        for j, cb in enumerate(b, 1):
            cur.append(min(prev[j] + 1, cur[j - 1] + 1, prev[j - 1] + (ca != cb)))
        prev = cur
    return prev[-1]


def near_dictionary_words(text: str, dictionary: set[str], is_common=None) -> list[tuple[int, str]]:
    """辞書の語と1文字だけ違う語（書き間違い）を、文章の中から探す。(位置, 文章にある表記)。
    1文字の違いなら、語の前半か後半（2文字）は一致しているため、その位置だけを調べる。辞書の語は4文字以上だけを対象にする。"""
    found: list[tuple[int, str]] = []
    exact_spans = []
    for w in dictionary:
        i = text.find(w)
        while i != -1:
            exact_spans.append((i, i + len(w)))
            i = text.find(w, i + 1)
    for w in dictionary:
        n = len(w)
        if n < 4:
            continue
        head, tail = w[:2], w[-2:]
        for length in (n - 1, n, n + 1):
            for p in range(0, len(text) - length + 1):
                if text[p:p + 2] != head and text[p + length - 2:p + length] != tail:
                    continue
                cand = text[p:p + length]
                if cand == w or edit_distance(cand, w) != 1:
                    continue
                if any(s <= p and p + length <= e for s, e in exact_spans):
                    continue  # 別の辞書の語の一部
                if w in cand:
                    continue  # 辞書の語を、そのまま含む（前後の1文字を足しただけ）
                if not WORD_CHARS.fullmatch(cand):
                    continue  # 空白や句読点をまたぐ
                found.append((p, cand))
    if is_common:
        # 一般の語（形態素解析で、辞書にある1語の普通名詞）は、指摘にしない。その語と重なる候補（一部だけの切り出し）も除く
        common = [(p, p + len(c)) for p, c in found if is_common(c)]
        found = [(p, c) for p, c in found if not any(p < e and s < p + len(c) for s, e in common)]
    out: list[tuple[int, str]] = []
    for p, cand in sorted(set(found), key=lambda x: (-len(x[1]), x[0])):  # 長いものを先に、重ならないように選ぶ
        if not any(p < q + len(c) and q < p + len(cand) for q, c in out):
            out.append((p, cand))
    return sorted(out)


def extract_claims(text: str, dictionary: set[str] | None = None, is_common=None) -> list[Claim]:
    """変更後の文章（本文）から主張を取り出す。位置の順に並べる。dictionary があれば、辞書の語の書き間違いも、固有名詞の候補にする。"""
    t = normalize(text)
    claims: list[Claim] = []
    masked = list(t)

    def mask(m: re.Match) -> None:
        for i in range(m.start(), m.end()):
            masked[i] = " "

    for m in URL.finditer(t):
        url = m.group(0).rstrip(TRAILING_PUNCT)
        claims.append(Claim("", "url", url, m.start()))
        mask(m)
    for m in DATE_FULL.finditer(t):
        claims.append(Claim("", "date", m.group(0), m.start(), key=(int(m[1]), int(m[2]), int(m[3])))); mask(m)
    for m in DATE_MONTH.finditer("".join(masked)):
        claims.append(Claim("", "date", m.group(0), m.start(), key=(int(m[1]), int(m[2])))); mask(m)
    for m in DATE_FISCAL.finditer("".join(masked)):
        claims.append(Claim("", "date", m.group(0), m.start(), key=(int(m[1]),))); mask(m)
    for m in DATE_YEAR.finditer("".join(masked)):
        claims.append(Claim("", "date", m.group(0), m.start(), key=(int(m[1]),))); mask(m)
    rest = "".join(masked)
    for m in NUMBER.finditer(rest):
        value, decimals = to_number(m[1])
        claims.append(Claim("", "number", m.group(0), m.start(), value, m[2], decimals, label_before(rest, m.start())))
    for m in COMPANY_CANDIDATE.finditer(rest):
        claims.append(Claim("", "proper", m.group(0), m.start()))
    if dictionary:
        have = {(c.start, c.text) for c in claims if c.kind == "proper"}
        for p, cand in near_dictionary_words(rest, dictionary, is_common):
            if not any(c.kind == "proper" and c.start <= p < c.start + len(c.text) for c in claims):
                claims.append(Claim("", "proper", cand, p))
    claims.sort(key=lambda c: c.start)
    for i, c in enumerate(claims, 1):
        c.id = f"C{i:03d}"
    return claims
