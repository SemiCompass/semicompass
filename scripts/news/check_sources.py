"""ニュースの情報源の接続の確認（運営者が手動で動かす。config/news.yaml に足す前の試験）。

使い方:
    python3 scripts/news/check_sources.py URL [URL ...]

URLごとに、取得できるか（HTTPの状態）、フィードかページか、記事の数と最新の公表日、ページに書かれたフィードの案内（link rel="alternate"）を表示する。
本文は表示しない。出すのは、URL、状態、件数、日付、見出しの先頭の1件だけ。
"""

from __future__ import annotations

import re
import sys
import urllib.error
import urllib.request
from pathlib import Path
from urllib.parse import urljoin

sys.path.insert(0, str(Path(__file__).resolve().parent))
import collect  # noqa: E402


def feed_links(body: bytes, base: str) -> list[str]:
    text = body.decode("utf-8", errors="ignore")
    links = []
    for m in re.finditer(r"<link\b[^>]*>", text, re.I):
        tag = m.group(0)
        if re.search(r"type\s*=\s*[\"']application/(rss|atom)\+xml", tag, re.I):
            href = re.search(r"href\s*=\s*[\"']([^\"']+)", tag, re.I)
            if href:
                links.append(urljoin(base, href.group(1)))
    return links


def check(url: str, fetcher=collect.fetch) -> str:
    try:
        body = fetcher(url)
    except urllib.error.HTTPError as error:
        return f"NG  {url}  HTTP {error.code}"
    except (urllib.error.URLError, OSError, ValueError, TimeoutError) as error:
        return f"NG  {url}  {type(error).__name__}"
    kind, entries = "ページ", []
    try:
        entries, kind = collect.parse_feed(body), "フィード"
    except ValueError:
        entries = collect.parse_page(body, url)
    newest = max((e["published_on"] for e in entries), default="-")
    head = entries[0]["title"][:40] if entries else "-"
    extra = feed_links(body, url) if kind == "ページ" else []
    note = f"  フィードの案内: {', '.join(extra[:3])}" if extra else ""
    return f"OK  {url}  {kind}  {len(entries)}件  最新 {newest}  先頭「{head}」{note}"


def main(argv=None) -> int:
    urls = [u for u in (argv if argv is not None else sys.argv[1:]) if u.strip()]
    for url in urls:
        print(check(url), flush=True)
    return 0


if __name__ == "__main__":
    sys.exit(main())
