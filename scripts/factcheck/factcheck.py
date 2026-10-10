"""事実確認（P08、AG-20〜AG-22。要件定義書6.5、アーキテクチャ設計書9.3）。

使い方:
    python3 scripts/factcheck/factcheck.py --draft content/news/xxx.md --source S1=原資料1.txt [--source S2=…] \\
        [--root .] [--url-check] [--ack ack.json] [--out report.md] [--json result.json]

流れ: 変更後の文章（front matter を除く本文）から主張を取り出し（claims.py）、原資料（--source）と辞書（企業マスタ、用語集）に照合する。
結果は4つ：根拠あり／矛盾／根拠なし／確認不能。矛盾、根拠なし、確認不能で、運営者の記録（--ack。主張の指紋の一覧）がないものがあれば、不合格（終了コード1）。
原資料の本文は、結果の表に出さない（資料の番号と位置だけ。公開リポジトリのコメントに貼らない。CLAUDE.md 2章10）。
通信は、--url-check のときだけ（URLの存在の確認）。既定では行わない。
終了コード: 0 合格 / 1 不合格 / 2 入力の誤り
"""

from __future__ import annotations

import argparse
import hashlib
import json
import re
import sys
import unicodedata
from dataclasses import dataclass
from pathlib import Path

import yaml

sys.path.insert(0, str(Path(__file__).resolve().parent))
import morph  # noqa: E402
from claims import BARE_NUMBER, CITATION, UNITS, Claim, edit_distance, extract_claims, normalize, to_number  # noqa: E402

ROOT = Path(__file__).resolve().parents[2]
GROUNDED, CONTRADICTION, UNSUPPORTED, UNVERIFIABLE = "根拠あり", "矛盾", "根拠なし", "確認不能"
WINDOW = 60  # 項目名を探す範囲（値の前後の文字数）


@dataclass
class Result:
    claim: Claim
    result: str
    where: str = ""     # 原資料の該当箇所（資料の番号と位置。本文は入れない）
    note: str = ""


# ---- 原資料 ----

@dataclass
class Source:
    id: str
    text: str            # NFKC 後
    numbers: list        # (start, value, decimals, unit or None)
    date_keys: set


def _source_numbers(text: str) -> list:
    out = []
    for m in BARE_NUMBER.finditer(text):
        value, decimals = to_number(m[1])
        tail = text[m.end(): m.end() + 8].lstrip()
        unit = next((u for u in sorted(UNITS, key=len, reverse=True) if tail.startswith(u)), None)
        out.append((m.start(), value, decimals, unit))
    return out


_DATE_FORMS = (
    (re.compile(r"(\d{4})年(\d{1,2})月(\d{1,2})日"), 3), (re.compile(r"(\d{4})[/.-](\d{1,2})[/.-](\d{1,2})"), 3),
    (re.compile(r"(\d{4})年(\d{1,2})月(?!\d{1,2}日)"), 2), (re.compile(r"(\d{4})年度"), 1), (re.compile(r"(\d{4})年"), 1),
)


def _source_date_keys(text: str) -> set:
    keys = set()
    for pattern, n in _DATE_FORMS:
        for m in pattern.finditer(text):
            key = tuple(int(m[i]) for i in range(1, n + 1))
            keys.add(key)
            for k in range(1, len(key)):  # 年月日があれば、年月・年も、あるものとして扱う
                keys.add(key[:k])
    return keys


def make_source(source_id: str, raw: str) -> Source:
    text = normalize(raw)
    return Source(source_id, text, _source_numbers(text), _source_date_keys(text))


# ---- 照合 ----

def _tolerance(decimals: int, mult: float) -> float:
    return 0.5 * 10 ** (-decimals) * mult + 1e-9


def _comparable(claim_unit: str, src_unit: str | None) -> list[float] | None:
    """原資料の数字（単位 src_unit または なし）を、主張の単位にそろえるときの倍率の候補。合わなければ None。"""
    cfam, cmult = UNITS[claim_unit]
    if src_unit is not None:
        sfam, smult = UNITS[src_unit]
        return [smult] if sfam == cfam else None
    if cfam in ("yen", "usd"):  # 表の見出しに単位がある書き方（百万円、千円）を許す
        return [1.0, 1e3, 1e4, 1e6, 1e8]
    return [cmult] if cmult == 1.0 else [1.0, cmult]


def _label_near(text: str, pos: int, label: str) -> bool:
    if len(label) < 2:
        return True
    window = text[max(0, pos - WINDOW): pos + WINDOW]
    return any(label[i:i + 2] in window for i in range(len(label) - 1))


def check_number(c: Claim, src: list[Source]) -> Result:
    cfam, cmult = UNITS[c.unit]
    target = c.value * cmult
    different = None
    for s in src:
        for start, value, decimals, unit in s.numbers:
            for mult in _comparable(c.unit, unit) or []:
                tol = max(_tolerance(c.decimals, cmult), _tolerance(decimals, mult))
                if abs(value * mult - target) <= tol:
                    if _label_near(s.text, start, c.label):
                        return Result(c, GROUNDED, f"{s.id} の {start}字目付近")
                elif different is None and c.label and len(c.label) >= 2:
                    # 項目名の直後にある、同じ単位の違う値（矛盾の候補）
                    idx = s.text.rfind(c.label, max(0, start - 30), start)
                    if idx != -1 and unit is not None and UNITS[unit][0] == cfam:
                        different = f"{s.id} の {start}字目付近に、同じ項目名の近くで違う値がある"
    if different:
        return Result(c, CONTRADICTION, different)
    return Result(c, UNSUPPORTED, "原資料に、同じ値が見つからない")


def check_date(c: Claim, src: list[Source]) -> Result:
    for s in src:
        if c.key in s.date_keys:
            return Result(c, GROUNDED, f"{s.id}")
    return Result(c, UNSUPPORTED, "原資料に、同じ日付がない")


def load_dictionary(root: Path) -> set[str]:
    """企業マスタ（名称、略称、英語表記）と用語集（用語、別名）の語。"""
    words: set[str] = set()
    for path in (root / "data" / "companies").glob("*.yaml"):
        data = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
        for key in ("name", "name_en"):
            if isinstance(data.get(key), str):
                words.add(data[key])
        words.update(w for w in data.get("short_names") or [] if isinstance(w, str))
        words.update(w for w in data.get("search_aliases") or [] if isinstance(w, str))
    for path in (root / "content" / "glossary").glob("*.md"):
        m = re.match(r"^---\n(.*?)\n---", path.read_text(encoding="utf-8"), re.S)
        if m:
            data = yaml.safe_load(m[1]) or {}
            words.update(w for w in [data.get("term"), *(data.get("aliases") or [])] if isinstance(w, str))
    return {normalize(w) for w in words if w}


def _strip_company_form(word: str) -> str:
    return word.replace("株式会社", "")


def check_proper(c: Claim, src: list[Source], dictionary: set[str]) -> Result:
    word = _strip_company_form(c.text)
    plain = {_strip_company_form(w) for w in dictionary}
    if c.text in dictionary or word in plain:
        return Result(c, GROUNDED, "辞書（企業マスタ・用語集）")
    for s in src:
        if word in s.text:
            return Result(c, GROUNDED, f"{s.id}")
    near = sorted((w for w in plain if len(w) >= 3 and 1 <= edit_distance(word, w) <= 2 and abs(len(w) - len(word)) <= 2), key=lambda w: edit_distance(word, w))
    if near:
        return Result(c, CONTRADICTION, f"辞書の語（{near[0]}）と似ているが、違う")
    return Result(c, UNSUPPORTED, "辞書にも原資料にもない")


def check_url(c: Claim, listed: set[str], fetcher=None) -> Result:
    norm = c.text.rstrip("/").lower()
    if norm not in listed:
        return Result(c, UNSUPPORTED, "出典の一覧にないURLである")
    if fetcher is None:
        return Result(c, UNVERIFIABLE, "URLの存在は確認していない（--url-check なし）")
    try:
        status = fetcher(c.text)
    except Exception:  # noqa: BLE001（一時的な接続の失敗は、確認不能）
        return Result(c, UNVERIFIABLE, "取得できなかった（接続の失敗）")
    if status == 404 or status == 410:
        return Result(c, CONTRADICTION, f"HTTP {status}（存在しない）")
    if 200 <= status < 400:
        return Result(c, GROUNDED, "出典の一覧にあり、取得できた")
    return Result(c, UNVERIFIABLE, f"HTTP {status}")


def check_claims(text: str, sources: list[Source], dictionary: set[str], listed_urls: set[str], fetcher=None, is_common=None) -> list[Result]:
    results = []
    if is_common is None:
        is_common = morph.is_common_word  # SudachiPy がなければ、常に False
    for c in extract_claims(text, dictionary, is_common):
        if c.kind == "number":
            results.append(check_number(c, sources))
        elif c.kind == "date":
            results.append(check_date(c, sources))
        elif c.kind == "url":
            results.append(check_url(c, listed_urls, fetcher))
        else:
            results.append(check_proper(c, sources, dictionary))
    return results


# ---- 判定と結果の表 ----

def fingerprint(claim: Claim) -> str:
    return hashlib.sha1(claim.fingerprint().encode("utf-8")).hexdigest()[:10]


def failures(results: list[Result], acks: set[str]) -> list[Result]:
    return [r for r in results if r.result != GROUNDED and fingerprint(r.claim) not in acks]


def report(results: list[Result], acks: set[str]) -> str:
    counts = {k: sum(r.result == k for r in results) for k in (GROUNDED, CONTRADICTION, UNSUPPORTED, UNVERIFIABLE)}
    bad = failures(results, acks)
    lines = [f"## 事実確認の結果：{'不合格' if bad else '合格'}", "",
             f"主張 {len(results)}件：根拠あり {counts[GROUNDED]}、矛盾 {counts[CONTRADICTION]}、根拠なし {counts[UNSUPPORTED]}、確認不能 {counts[UNVERIFIABLE]}"
             f"（運営者の記録あり {sum(r.result != GROUNDED and fingerprint(r.claim) in acks for r in results)}件）", ""]
    shown = [r for r in results if r.result != GROUNDED]
    if shown:
        lines += ["| 番号 | 種類 | 文章の該当箇所 | 結果 | 原資料の該当箇所・理由 | 記録用の指紋 |", "| :--- | :--- | :--- | :--- | :--- | :--- |"]
        kind = {"number": "数値", "date": "日付", "url": "URL", "proper": "固有名詞"}
        for r in shown:
            ack = "（記録あり）" if fingerprint(r.claim) in acks else ""
            where = (r.where + (f"：{r.note}" if r.note and r.note != r.where else "")).strip("：")
            lines.append(f"| {r.claim.id} | {kind[r.claim.kind]} | {r.claim.text.replace('|', '｜')} | {r.result}{ack} | {where} | `{fingerprint(r.claim)}` |")
        lines += ["", "記録するときは、指紋を、運営者の記録（`/factcheck-ack`）に書く。"]
    lines += ["", "事実確認は、正確性を保証するものではない。運営者の確認の代わりではない。"]
    return "\n".join(lines) + "\n"


# ---- 入口 ----

def split_front_matter(text: str) -> tuple[dict, str]:
    m = re.match(r"^---\n(.*?)\n---\n?(.*)$", text, re.S)
    if not m:
        return {}, text
    return (yaml.safe_load(m[1]) or {}), m[2]


def listed_urls_of(front: dict) -> set[str]:
    urls = [s.get("url") for s in front.get("sources") or [] if isinstance(s, dict)]
    article = front.get("source_article")
    if isinstance(article, dict):
        urls.append(article.get("url"))
    return {u.rstrip("/").lower() for u in urls if isinstance(u, str)}


def url_status(url: str) -> int:
    import urllib.error
    import urllib.request
    request = urllib.request.Request(url, method="HEAD", headers={"User-Agent": "SemiCompassBot/1.0 (+https://github.com/SemiCompass/semicompass)"})
    try:
        with urllib.request.urlopen(request, timeout=15) as response:  # noqa: S310（https のみを想定）
            return response.status
    except urllib.error.HTTPError as error:
        return error.code


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    parser.add_argument("--draft", required=True, type=Path)
    parser.add_argument("--source", action="append", default=[], help="S1=ファイル（原資料の本文）")
    parser.add_argument("--root", type=Path, default=ROOT)
    parser.add_argument("--url-check", action="store_true")
    parser.add_argument("--ack", type=Path)
    parser.add_argument("--out", type=Path)
    parser.add_argument("--json", type=Path)
    args = parser.parse_args(argv)
    try:
        front, body = split_front_matter(args.draft.read_text(encoding="utf-8"))
        sources = []
        for spec in args.source:
            sid, _, path = spec.partition("=")
            sources.append(make_source(sid, Path(path).read_text(encoding="utf-8")))
        acks = set(json.loads(args.ack.read_text(encoding="utf-8"))) if args.ack and args.ack.is_file() else set()
    except (OSError, ValueError, yaml.YAMLError) as error:
        print(f"入力の誤り：{type(error).__name__}")
        return 2
    results = check_claims(body, sources, load_dictionary(args.root), listed_urls_of(front), url_status if args.url_check else None)
    text = report(results, acks)
    print(text)
    if args.out:
        args.out.write_text(text, encoding="utf-8")
    if args.json:
        args.json.write_text(json.dumps([{"id": r.claim.id, "kind": r.claim.kind, "text": r.claim.text, "result": r.result, "where": r.where, "fingerprint": fingerprint(r.claim)} for r in results], ensure_ascii=False, indent=1) + "\n", encoding="utf-8")
    return 1 if failures(results, acks) else 0


if __name__ == "__main__":
    sys.exit(main())
