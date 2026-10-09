"""ニュース候補の収集（J02の前半。AIは使わない。運用ルール書 3.1、データ定義書 7.3）。

使い方:
    python3 scripts/news/collect.py --out candidates.json [--config config/news.yaml] [--seen FILE ...] [--days 3]

* config/news.yaml の sources を順に読む。feed_url はRSS 2.0／RDF／Atom、page_url は一覧のページ（リンクと日付を取り出す）。
* 情報源ごとに失敗しても、ほかの情報源は続ける。失敗した情報源は out の `failed` に入れる（本文は入れない）。
* 重複を除く：同じURL（#以降とutm_*を除く）、既に扱った記事のURL（content/news の source_article.url と --seen のファイル）。
* 新しい順に、candidate_limit 件まで。公表日が --days 日より前のものは入れない。
* 出力に入れるのは、見出し・URL・公表日・情報源の区分だけ。元記事の本文は集めない（LG-05）。
* 通信は標準ライブラリだけで行う（依存を増やさない）。
"""

from __future__ import annotations

import argparse
import html
import json
import re
import sys
import urllib.error
import urllib.request
import xml.etree.ElementTree as ET
from datetime import date, datetime, timedelta
from email.utils import parsedate_to_datetime
from pathlib import Path
from urllib.parse import parse_qsl, urlencode, urljoin, urlsplit, urlunsplit
from zoneinfo import ZoneInfo

import yaml

ROOT = Path(__file__).resolve().parents[2]
JST = ZoneInfo("Asia/Tokyo")
USER_AGENT = "SemiCompassBot/1.0 (+https://github.com/SemiCompass/semicompass)"
TIMEOUT = 20
MAX_BYTES = 3_000_000
# 一次情報の区分（運用ルール書 3.1）。press は報道で、観測報道かどうかは AG-10 が見る
PRIMARY_KINDS = {"company", "government", "association"}


def normalize_url(url: str) -> str:
    """比較のために、#以降と、追跡用のパラメータ（utm_*）を除く。"""
    parts = urlsplit(url.strip())
    query = [(k, v) for k, v in parse_qsl(parts.query, keep_blank_values=True) if not k.lower().startswith("utm_")]
    return urlunsplit((parts.scheme.lower(), parts.netloc.lower(), parts.path, urlencode(query), ""))


def _text(element: ET.Element | None) -> str:
    return re.sub(r"\s+", " ", "".join(element.itertext())).strip() if element is not None else ""


def _local(tag: str) -> str:
    return tag.rsplit("}", 1)[-1]


# 「2026年10月 9日」のように、月と日の間に空白がある書き方も読む
DATE_RE = r"(\d{4})\s*[-/.年]\s*(\d{1,2})\s*[-/.月]\s*(\d{1,2})"


def parse_date(value: str) -> date | None:
    value = value.strip()
    if not value:
        return None
    m = re.search(DATE_RE, value)
    if m:
        try:
            return date(int(m[1]), int(m[2]), int(m[3]))
        except ValueError:
            return None
    try:
        moment = parsedate_to_datetime(value)  # RSS 2.0 の RFC 822
        return (moment.astimezone(JST) if moment.tzinfo else moment).date()
    except (TypeError, ValueError):
        return None


def parse_feed(body: bytes) -> list[dict]:
    """RSS 2.0、RSS 1.0（RDF）、Atom から、{title, url, published_on} を取り出す。"""
    try:
        root = ET.fromstring(body)
    except ET.ParseError:
        raise ValueError("フィードを読めなかった") from None
    entries = []
    for node in root.iter():
        if _local(node.tag) not in ("item", "entry"):
            continue
        fields: dict[str, str] = {}
        link = ""
        for child in node:
            name = _local(child.tag)
            if name == "title":
                fields["title"] = _text(child)
            elif name == "link":
                href = child.attrib.get("href")  # Atom
                if href and child.attrib.get("rel", "alternate") == "alternate":
                    link = link or href
                elif not href and _text(child):
                    link = link or _text(child)
            elif name in ("pubDate", "date", "published", "updated", "issued") and "date" not in fields:
                fields["date"] = _text(child)
        published = parse_date(fields.get("date", ""))
        if fields.get("title") and link and published:
            entries.append({"title": html.unescape(fields["title"]), "url": link, "published_on": published.isoformat()})
    return entries


class _LinkParser:
    """一覧のページから、リンク（aタグ）の文字と、その周りの日付を取り出す。"""

    def __init__(self, html_text: str, base: str):
        self.items: list[dict] = []
        pattern = re.compile(r"<a\b[^>]*?href\s*=\s*[\"']([^\"'#][^\"']*)[\"'][^>]*>(.*?)</a>", re.I | re.S)
        for m in pattern.finditer(html_text):
            title = re.sub(r"\s+", " ", html.unescape(re.sub(r"<[^>]+>", " ", m[2]))).strip()
            # 日付がリンクの文字の中にある書き方（「2026.10.07 見出し」「2026/09/30 区分 見出し」）。見つけたら、見出しから除く
            inner = re.search(DATE_RE, title)
            if inner and parse_date(inner.group(0)):
                found = [parse_date(inner.group(0))]
                title = re.sub(r"\s+", " ", (title[:inner.start()] + " " + title[inner.end():])).strip()
            else:
                found = []
            if len(title) < 8:
                continue
            if not found:
                before = re.sub(r"<[^>]+>", " ", html_text[max(0, m.start() - 160): m.start()])
                after = re.sub(r"<[^>]+>", " ", html_text[m.end(): m.end() + 80])
                # 日付は、リンクの前にある書き方（JEITA）が多い。前の最も近い日付を先に探し、なければ後ろを見る
                found = [d for d in (parse_date(x.group(0)) for x in re.finditer(DATE_RE, before)) if d]
                found = found[-1:] or [d for d in (parse_date(x.group(0)) for x in re.finditer(DATE_RE, after)) if d][:1]
            if not found:
                continue
            dates = found
            self.items.append({"title": title, "url": urljoin(base, m[1]), "published_on": dates[0].isoformat()})


def parse_page(body: bytes, base: str) -> list[dict]:
    text = None
    for encoding in ("utf-8", "shift_jis", "euc-jp"):
        try:
            text = body.decode(encoding)
            break
        except UnicodeDecodeError:
            continue
    if text is None:
        raise ValueError("ページの文字コードを読めなかった")
    return _LinkParser(text, base).items


def fetch(url: str) -> bytes:
    if not url.startswith("https://"):
        raise ValueError("https ではないURLは読まない")
    request = urllib.request.Request(url, headers={"User-Agent": USER_AGENT, "Accept": "*/*"})
    with urllib.request.urlopen(request, timeout=TIMEOUT) as response:  # noqa: S310（https だけ）
        body = response.read(MAX_BYTES + 1)
    if len(body) > MAX_BYTES:
        raise ValueError("大きすぎる")
    return body


def seen_urls(content_dir: Path, extra_files: list[Path]) -> set[str]:
    urls: set[str] = set()
    if content_dir.is_dir():
        for path in content_dir.glob("*.md"):
            m = re.search(r"^---\n(.*?)\n---", path.read_text(encoding="utf-8"), re.S)
            if not m:
                continue
            try:
                url = (yaml.safe_load(m[1]) or {}).get("source_article", {}).get("url")
            except yaml.YAMLError:
                continue
            if isinstance(url, str):
                urls.add(normalize_url(url))
    for path in extra_files:
        if path.is_file():
            urls.update(normalize_url(line.split()[0]) for line in path.read_text(encoding="utf-8").splitlines() if line.strip())
    return urls


def collect(config: dict, *, today: date, days: int, seen: set[str], fetcher=fetch) -> dict:
    cutoff = today - timedelta(days=days)
    found: dict[str, dict] = {}
    failed: list[dict] = []
    per_source: dict[str, int] = {}
    for source in config["sources"]:
        try:
            if source.get("feed_url"):
                entries = parse_feed(fetcher(source["feed_url"]))
            else:
                entries = parse_page(fetcher(source["page_url"]), source["page_url"])
        except (urllib.error.URLError, OSError, ValueError, TimeoutError) as error:
            reason = type(error).__name__ + (f" {error.code}" if isinstance(error, urllib.error.HTTPError) else "")
            failed.append({"source": source["id"], "reason": reason})
            continue
        count = 0
        for e in entries:
            url = e["url"]
            key = normalize_url(url)
            published = date.fromisoformat(e["published_on"])
            if not url.startswith("https://") or key in seen or key in found or published < cutoff or published > today + timedelta(days=1):
                continue
            found[key] = {**e, "source": source["id"], "publisher": source["name"], "kind": source["kind"],
                          "reliability": source["reliability"], "company": source.get("company"),
                          "reporting_hint": "primary" if source["kind"] in PRIMARY_KINDS else "press"}
            count += 1
        per_source[source["id"]] = count
    ordered = sorted(found.values(), key=lambda c: (c["published_on"], c["url"]), reverse=True)[: config["candidate_limit"]]
    for i, c in enumerate(ordered, 1):
        c["id"] = f"c{i:02d}"
    return {"collected_on": today.isoformat(), "candidates": ordered, "per_source": per_source, "failed": failed}


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    parser.add_argument("--out", required=True, type=Path)
    parser.add_argument("--config", type=Path, default=ROOT / "config" / "news.yaml")
    parser.add_argument("--content-dir", type=Path, default=ROOT / "content" / "news")
    parser.add_argument("--seen", type=Path, action="append", default=[])
    parser.add_argument("--days", type=int, default=3)
    args = parser.parse_args(argv)
    config = yaml.safe_load(args.config.read_text(encoding="utf-8"))
    result = collect(config, today=datetime.now(JST).date(), days=args.days, seen=seen_urls(args.content_dir, args.seen))
    args.out.write_text(json.dumps(result, ensure_ascii=False, indent=1) + "\n", encoding="utf-8")
    print(f"候補 {len(result['candidates'])}件（情報源ごと: {result['per_source']}）、取得に失敗した情報源: {[(f['source'], f['reason']) for f in result['failed']]}")
    # 全部の情報源が失敗したときだけ、失敗にする
    return 1 if result["failed"] and not result["per_source"] else 0


if __name__ == "__main__":
    sys.exit(main())
