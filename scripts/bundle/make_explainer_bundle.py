"""工程・用語の解説（AG-14）の原資料束を作る。config/explainer-sources.yaml で承認したURLだけを取得し、R2 の非公開バケットに保存する。

使い方:
    R2_ACCOUNT_ID=... R2_ACCESS_KEY_ID=... R2_SECRET_ACCESS_KEY=... R2_BUCKET=... \\
        python3 scripts/bundle/make_explainer_bundle.py --kind process|term --slug SLUG [--dry-run] [--summary FILE]

* 取得するのは、その対象の sources のうち status が approved のURLだけ（candidate と rejected は取得しない）。yaml にないURLは取得しない。
  リダイレクト先のドメインが yaml のURLと違うとき（www. の有無は同じとみなす）、https でなくなるときは、取得せずに失敗として記録する
* 取得の作法：User-Agent に SemiCompass と連絡先、robots.txt に従う、同じドメインへの間隔は1秒以上、1回のタイムアウト20秒、
  1資料の大きさの上限10MB。失敗した資料があっても、ほかの資料は続け、失敗の一覧を最後に出す
* 本文の抽出：HTML は、ナビゲーション・広告などを除いた本文を段落に分ける。PDF は、ページごとに段落に分け、ページ番号を残す
* 保存する量：対象の語（yaml の名前、名前の括弧を除いた形、任意の aliases・keywords）を含む段落と、その前後1段落だけ。
  1資料あたり最大6,000字。語が見つからない資料は、見つからなかった印を付け、先頭の1,500字だけを残す
* 保存先は R2 の bundles/explainer/{kind}-{slug}.json（schema_version 1）。同じ対象で2回動かすと上書きする。
  R2 の4つの環境変数は、--dry-run のときは要らない（--dry-run でも取得はする。保存だけをしない）
* **取得した本文は、リポジトリに置かない。画面、--summary、例外のメッセージにも出さない**（リポジトリ、Actionsのログは公開。CLAUDE.md 2章10）。
  出すのは、資料の番号、役割、取得の成否、失敗の理由、段落の数、文字数だけ

終了コード: 0 すべての資料を取得して保存した / 1 失敗（承認済みの資料がすべて失敗した、保存に失敗したなど。何も保存しない）/
2 使い方・設定の誤り / 4 一部の資料が失敗した（取得できた資料だけで、保存した）
"""

from __future__ import annotations

import argparse
import hashlib
import html.parser
import io
import json
import os
import re
import sys
import time
import unicodedata
import urllib.error
import urllib.parse
import urllib.request
import urllib.robotparser
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

import yaml

REPO_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO_ROOT / "scripts" / "bundle"))
sys.path.insert(0, str(REPO_ROOT / "scripts" / "validate"))

import make_bundle  # noqa: E402
import validate_data  # noqa: E402

SCHEMA_VERSION = 1
KEY_PREFIX = "bundles/explainer/"
CONFIG_PATH = REPO_ROOT / "config" / "explainer-sources.yaml"
SUPPLY_PATH = REPO_ROOT / "data" / "supply-chain.yaml"
KINDS = ("process", "term")
JST = ZoneInfo("Asia/Tokyo")

USER_AGENT = "SemiCompass/1.0 (+https://semicompass.com/contact/)"
ROBOTS_TOKEN = "SemiCompass"
MIN_INTERVAL_SECONDS = 1.0  # 同じドメインへの間隔
TIMEOUT_SECONDS = 20.0
MAX_BYTES = 10 * 1024 * 1024  # 1資料の大きさの上限
MAX_REDIRECTS = 5
MAX_PDF_PAGES = 300
KEEP_CHARS = 6000  # 1資料に残す文字数の上限
NOT_FOUND_CHARS = 1500  # 語が見つからなかった資料の先頭から残す文字数
MIN_PARAGRAPH_CHARS = 2

EXIT_OK, EXIT_FAILURE, EXIT_USAGE, EXIT_PARTIAL = 0, 1, 2, 4
MASK = make_bundle.MASK


class ExplainerError(Exception):
    """原資料束の作成の失敗。メッセージは、本文と認証情報を含まない。"""

    def __init__(self, message: str, exit_code: int = EXIT_FAILURE):
        super().__init__(message)
        self.exit_code = exit_code


class FetchFailure(Exception):
    """1つの資料の取得の失敗。reason は、本文を含まない短い説明。"""

    def __init__(self, reason: str):
        super().__init__(reason)
        self.reason = reason


# ---- 設定 ---------------------------------------------------------------------------------

def object_key(kind: str, slug: str) -> str:
    return f"{KEY_PREFIX}{kind}-{slug}.json"


def load_config(path: Path = CONFIG_PATH, supply_path: Path = SUPPLY_PATH) -> dict:
    """config/explainer-sources.yaml を読み、形を検査する（検査の中身は validate_data.check_explainer_sources）。"""
    try:
        config = yaml.safe_load(path.read_text(encoding="utf-8"))
        supply = yaml.safe_load(supply_path.read_text(encoding="utf-8"))
    except (OSError, yaml.YAMLError):
        raise ExplainerError(f"{path.name} か {supply_path.name} を読めなかった", EXIT_USAGE) from None
    errors = [p for p in validate_data.check_explainer_sources(config, supply) if p.severity == "error"]
    if errors:
        raise ExplainerError(f"{path.name} の形が正しくない（{len(errors)}件。validate_data.py で場所を確かめる）", EXIT_USAGE)
    return config


def find_entry(config: dict, kind: str, slug: str) -> dict:
    table = config["terms" if kind == "term" else "processes"]
    entry = table.get(slug)
    if not isinstance(entry, dict):
        raise ExplainerError(f"{kind} {slug} が config/explainer-sources.yaml にない", EXIT_USAGE)
    return entry


def entry_name(kind: str, entry: dict) -> str:
    return entry["term" if kind == "term" else "process"]


_SUFFIXES = ("の製造", "の工程", "工程")


def target_words(kind: str, entry: dict) -> list[str]:
    """対象の語：名前、名前の括弧を除いた形、末尾の「の製造」「の工程」を除いた形、任意の aliases と keywords。"""
    name = unicodedata.normalize("NFKC", entry_name(kind, entry))
    words = [name]
    base = re.sub(r"\([^)]*\)", "", name).strip()
    words.append(base)
    for suffix in _SUFFIXES:
        if base.endswith(suffix) and len(base) > len(suffix) + 1:
            words.append(base[: -len(suffix)])
    for key in ("aliases", "keywords"):
        words += [w for w in entry.get(key) or [] if isinstance(w, str)]
    seen: list[str] = []
    for word in words:
        word = unicodedata.normalize("NFKC", word).strip()
        if len(word) >= 2 and word.casefold() not in {s.casefold() for s in seen}:
            seen.append(word)
    return seen


def approved_sources(entry: dict) -> list[dict]:
    """承認済み（approved）の資料。番号 S1、S2… は、yaml の並び順（承認済みだけを数える）。"""
    rows = [s for s in entry["sources"] if s.get("status") == "approved"]
    return [{"id": f"S{i}", **s} for i, s in enumerate(rows, start=1)]


# ---- 取得（HTTP。テストでは transport を差し替える） ------------------------------------------

@dataclass
class HttpResponse:
    status: int
    headers: dict[str, str] = field(default_factory=dict)  # キーは小文字
    body: bytes = b""
    too_large: bool = False


class _NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, *args, **kwargs):  # noqa: D401 - リダイレクトは、自分で、行き先を確かめてから辿る
        return None


def urllib_transport(url: str, headers: dict[str, str], timeout: float, max_bytes: int) -> HttpResponse:
    """標準ライブラリだけで、1回のGETをする。リダイレクトは辿らない。大きさの上限を超えたら、読むのをやめる。"""
    opener = urllib.request.build_opener(_NoRedirect())
    request = urllib.request.Request(url, headers=headers, method="GET")
    try:
        response = opener.open(request, timeout=timeout)
    except urllib.error.HTTPError as error:  # 3xx、4xx、5xx
        response = error
    with response:
        body = response.read(max_bytes + 1)
        return HttpResponse(response.status if hasattr(response, "status") else response.code,
                            {k.lower(): v for k, v in response.headers.items()}, body[:max_bytes], len(body) > max_bytes)


def host_key(url: str) -> str:
    """ドメインの比較に使う形（小文字、先頭の www. は同じとみなす）。"""
    host = (urllib.parse.urlsplit(url).hostname or "").lower()
    return host[4:] if host.startswith("www.") else host


class PoliteFetcher:
    """robots.txt に従い、同じドメインへの間隔を空け、リダイレクト先を確かめて、取得する。"""

    def __init__(self, transport=urllib_transport, sleep=time.sleep, monotonic=time.monotonic):
        self.transport = transport
        self.sleep = sleep
        self.monotonic = monotonic
        self.last_request: dict[str, float] = {}
        self.robots: dict[str, urllib.robotparser.RobotFileParser | None] = {}  # None は、取得できない（すべて不可）

    def _request(self, url: str) -> HttpResponse:
        key = host_key(url)
        if key in self.last_request:
            wait = MIN_INTERVAL_SECONDS - (self.monotonic() - self.last_request[key])
            if wait > 0:
                self.sleep(wait)
        try:
            return self.transport(url, {"User-Agent": USER_AGENT, "Accept": "text/html,application/xhtml+xml,application/pdf;q=0.9,*/*;q=0.1",
                                        "Accept-Language": "ja,en;q=0.5"}, TIMEOUT_SECONDS, MAX_BYTES)
        except FetchFailure:
            raise
        except TimeoutError:
            raise FetchFailure("タイムアウトした") from None
        except (urllib.error.URLError, OSError) as error:
            reason = getattr(error, "reason", error)
            raise FetchFailure(f"通信に失敗した（{type(reason).__name__}）") from None
        finally:
            self.last_request[key] = self.monotonic()

    def _robots_for(self, url: str) -> urllib.robotparser.RobotFileParser | None:
        parts = urllib.parse.urlsplit(url)
        origin = f"{parts.scheme}://{parts.netloc}"
        if origin not in self.robots:
            self.robots[origin] = self._load_robots(origin)
        return self.robots[origin]

    def _load_robots(self, origin: str) -> urllib.robotparser.RobotFileParser | None:
        """robots.txt。4xx（ない）はすべて可、5xxや通信の失敗はすべて不可（RFC 9309）。"""
        rp = urllib.robotparser.RobotFileParser()
        try:
            response = self._request(f"{origin}/robots.txt")
        except FetchFailure:
            return None
        if 300 <= response.status < 400:  # robots.txt の移動は、辿らない。ない扱い（すべて可）にはせず、不可にする
            return None
        if 400 <= response.status < 500:
            rp.parse([])
            rp.modified()
            return rp
        if response.status != 200 or response.too_large:
            return None
        rp.parse(response.body.decode("utf-8", errors="replace").splitlines())
        rp.modified()
        return rp

    def get(self, url: str) -> HttpResponse:
        """url を取得する。リダイレクトは、ドメインが同じで https のときだけ辿る。失敗は FetchFailure。"""
        origin_host = host_key(url)
        current = url
        for _ in range(MAX_REDIRECTS + 1):
            parts = urllib.parse.urlsplit(current)
            if parts.scheme != "https":
                raise FetchFailure("https でないURLには行かない")
            if host_key(current) != origin_host:
                raise FetchFailure("リダイレクト先のドメインが、承認したURLと違う")
            robots = self._robots_for(current)
            if robots is None:
                raise FetchFailure("robots.txt を確かめられないため、取得しない")
            if not robots.can_fetch(ROBOTS_TOKEN, current):
                raise FetchFailure("robots.txt で許可されていない")
            response = self._request(current)
            if response.status in (301, 302, 303, 307, 308):
                location = response.headers.get("location")
                if not location:
                    raise FetchFailure("リダイレクトの行き先がない")
                current = urllib.parse.urljoin(current, location)
                continue
            if response.too_large:
                raise FetchFailure(f"大きさの上限（{MAX_BYTES // (1024 * 1024)}MB）を超えた")
            if response.status != 200:
                raise FetchFailure(f"HTTP {response.status}")
            return response
        raise FetchFailure(f"リダイレクトが{MAX_REDIRECTS}回を超えた")


# ---- 本文の抽出 -----------------------------------------------------------------------------

_CJK = r"[　-ヿ㐀-鿿＀-￯]"
_SPACE_BETWEEN_CJK = re.compile(rf"(?<={_CJK})\s+(?={_CJK})")


def clean_text(text: str) -> str:
    text = re.sub(r"[\s 　]+", " ", text).strip()
    return _SPACE_BETWEEN_CJK.sub("", text)


def decode_html(body: bytes, content_type: str) -> str:
    """文字コードを、Content-Type、meta、UTF-8、日本語の旧い文字コードの順に試す。"""
    declared = re.search(r"charset=([\w-]+)", content_type, re.I)
    head = body[:4096].decode("ascii", errors="replace")
    meta = re.search(r"<meta[^>]+charset=[\"']?([\w-]+)", head, re.I)
    for name in [declared.group(1) if declared else None, meta.group(1) if meta else None, "utf-8", "cp932", "euc-jp"]:
        if not name:
            continue
        try:
            return body.decode(name)
        except (LookupError, UnicodeDecodeError):
            continue
    return body.decode("utf-8", errors="replace")


_VOID = {"br", "img", "meta", "link", "input", "hr", "wbr", "source", "area", "base", "col", "embed", "param", "track"}
_BLOCK = {"p", "div", "section", "article", "main", "li", "ul", "ol", "dl", "dt", "dd", "h1", "h2", "h3", "h4", "h5", "h6",
          "table", "tr", "blockquote", "pre", "figure", "figcaption", "details", "summary", "address", "br", "hr"}
_ALWAYS_SKIP = {"script", "style", "noscript", "template", "svg", "iframe", "form", "nav", "aside", "footer", "select",
                "button", "dialog", "head", "object", "canvas", "audio", "video"}
_SKIP_ROLES = {"navigation", "banner", "contentinfo", "complementary", "search", "dialog"}
_SKIP_WORDS = {"nav", "navi", "navigation", "gnav", "menu", "breadcrumb", "breadcrumbs", "sidebar", "footer", "cookie",
               "advert", "ad", "ads", "banner", "sns", "share", "pagetop", "skip"}


class _Node:
    __slots__ = ("tag", "attrs", "children")

    def __init__(self, tag: str, attrs: dict[str, str]):
        self.tag, self.attrs, self.children = tag, attrs, []


class _TreeBuilder(html.parser.HTMLParser):
    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.root = _Node("#root", {})
        self.stack = [self.root]

    def handle_starttag(self, tag, attrs):
        node = _Node(tag, {k: (v or "") for k, v in attrs})
        self.stack[-1].children.append(node)
        if tag not in _VOID:
            self.stack.append(node)

    def handle_startendtag(self, tag, attrs):
        self.stack[-1].children.append(_Node(tag, {k: (v or "") for k, v in attrs}))

    def handle_endtag(self, tag):
        for i in range(len(self.stack) - 1, 0, -1):
            if self.stack[i].tag == tag:
                del self.stack[i:]
                return

    def handle_data(self, data):
        self.stack[-1].children.append(data)


def _find(node, tags: set[str]) -> "_Node | None":
    for child in node.children:
        if isinstance(child, _Node):
            if child.tag in tags or child.attrs.get("role") == "main":
                return child
            found = _find(child, tags)
            if found is not None:
                return found
    return None


def _contains(node: "_Node", tags: set[str]) -> bool:
    return any(isinstance(c, _Node) and (c.tag in tags or _contains(c, tags)) for c in node.children)


def _is_noise(node: "_Node") -> bool:
    if node.tag in _ALWAYS_SKIP or node.attrs.get("role") in _SKIP_ROLES or "hidden" in node.attrs \
            or node.attrs.get("aria-hidden") == "true":
        return True
    words = set(re.split(r"[^a-z0-9]+", f"{node.attrs.get('class', '')} {node.attrs.get('id', '')}".lower()))
    if words & _SKIP_WORDS and not _contains(node, {"main", "article"}):
        return True
    return False  # header は、見出しを含むことがあるため、除かない（nav、footer などは、上で個別に除く）


def _walk(node: "_Node", out: list[str]) -> None:
    for child in node.children:
        if isinstance(child, str):
            out.append(child.replace("\n", " "))  # 改行は段落の区切りに使うため、ソースの改行は空白にする
            continue
        if _is_noise(child):
            continue
        if child.tag in _BLOCK:
            out.append("\n")
            _walk(child, out)
            out.append("\n")
        elif child.tag in ("td", "th"):
            _walk(child, out)
            out.append(" ")
        else:
            _walk(child, out)


def html_paragraphs(text: str) -> list[dict]:
    """HTML から、本文の段落の一覧を作る。main か article があれば、その中だけを使う。"""
    builder = _TreeBuilder()
    builder.feed(text)
    builder.close()
    root = _find(builder.root, {"main", "article"}) or builder.root
    pieces: list[str] = []
    _walk(root, pieces)
    paragraphs: list[dict] = []
    for block in "".join(pieces).split("\n"):
        block = clean_text(block)
        if len(block) >= MIN_PARAGRAPH_CHARS and (not paragraphs or paragraphs[-1]["text"] != block):
            paragraphs.append({"text": block, "page": 1})
    return paragraphs


_SENTENCE_END = ("。", "．", "！", "？")


def pdf_page_paragraphs(text: str, page: int) -> list[dict]:
    """PDF の1ページの文字列を、段落に分ける。空行、または「。」で終わる行で区切る。"""
    paragraphs: list[dict] = []
    current = ""

    def flush() -> None:
        nonlocal current
        block = clean_text(current)
        if len(block) >= MIN_PARAGRAPH_CHARS:
            paragraphs.append({"text": block, "page": page})
        current = ""

    for line in text.splitlines():
        line = line.strip()
        if not line:
            flush()
            continue
        if current and not (re.match(_CJK, current[-1]) and re.match(_CJK, line[0])):
            current += " "
        current += line
        if line.endswith(_SENTENCE_END):
            flush()
    flush()
    return paragraphs


def pdf_paragraphs(body: bytes) -> list[dict]:
    try:
        from pypdf import PdfReader
        reader = PdfReader(io.BytesIO(body))
        if reader.is_encrypted:
            raise FetchFailure("PDFが暗号化されている")
        paragraphs: list[dict] = []
        for number, page in enumerate(reader.pages[:MAX_PDF_PAGES], start=1):
            paragraphs += pdf_page_paragraphs(page.extract_text() or "", number)
        return paragraphs
    except FetchFailure:
        raise
    except Exception as error:  # noqa: BLE001 - 本文を含みうるため、種類だけ示す
        raise FetchFailure(f"PDFを読めなかった（{type(error).__name__}）") from None


def extract_paragraphs(response: HttpResponse, url: str) -> tuple[str, list[dict]]:
    """(形式 "html" か "pdf"、段落の一覧)。対応しない形式は FetchFailure。"""
    content_type = response.headers.get("content-type", "")
    if "pdf" in content_type.lower() or response.body[:5] == b"%PDF-" or urllib.parse.urlsplit(url).path.lower().endswith(".pdf"):
        return "pdf", pdf_paragraphs(response.body)
    if "html" in content_type.lower() or not content_type:
        return "html", html_paragraphs(decode_html(response.body, content_type))
    safe = re.sub(r"[^\w/+.-]", "", content_type.split(";")[0])[:60]
    raise FetchFailure(f"対応しない形式（{safe}）")


# ---- 残す段落の選択 ------------------------------------------------------------------------------

def _plain(text: str) -> str:
    return re.sub(r"\s+", " ", unicodedata.normalize("NFKC", text).casefold()).strip()


def make_matcher(words: list[str]):
    """段落が対象の語を含むか。英数字だけの語は、語の境界で照合する（EDA が別の語の中に当たらないように）。"""
    patterns = []
    for word in words:
        key = _plain(word)
        if re.fullmatch(r"[a-z0-9 .+\-]+", key):
            patterns.append(re.compile(rf"(?<![a-z0-9]){re.escape(key)}(?![a-z0-9])"))
        else:
            patterns.append(re.compile(re.escape(key.replace(" ", ""))))

    def matches(text: str) -> bool:
        spaced = _plain(text)
        packed = spaced.replace(" ", "")
        return any(p.search(spaced) or p.search(packed) for p in patterns)
    return matches


def select_paragraphs(paragraphs: list[dict], words: list[str]) -> tuple[list[dict], bool]:
    """(残す段落の一覧（元の順）、語が見つからなかったか)。

    語を含む段落を先に、前後1段落を後に、合計 KEEP_CHARS 字まで残す。語が見つからなければ、先頭から NOT_FOUND_CHARS 字。
    """
    matches = make_matcher(words)
    hits = [i for i, p in enumerate(paragraphs) if matches(p["text"])]
    if not hits:
        kept, used = [], 0
        for p in paragraphs:
            room = NOT_FOUND_CHARS - used
            if room <= 0:
                break
            kept.append({**p, "text": p["text"][:room]})
            used += len(kept[-1]["text"])
        return kept, True
    chosen: dict[int, str] = {}
    used = 0

    def add(index: int, must: bool) -> None:
        nonlocal used
        if index in chosen or not 0 <= index < len(paragraphs):
            return
        text = paragraphs[index]["text"]
        room = KEEP_CHARS - used
        if len(text) > room:
            if not must or room < 200:
                return
            text = text[:room]
        chosen[index] = text
        used += len(text)

    for i in hits:
        add(i, True)
    for i in hits:
        add(i - 1, False)
        add(i + 1, False)
    return [{**paragraphs[i], "text": chosen[i]} for i in sorted(chosen)], False


# ---- 原資料束の組み立て ----------------------------------------------------------------------------

def collect_source(fetcher: PoliteFetcher, source: dict, words: list[str], fetched_at: str) -> dict:
    row = {"id": source["id"], "url": source["url"], "publisher": source["publisher"], "title": source["title"],
           "role": source["role"], "kind": source["kind"], "fetched_at": fetched_at, "content_sha256": None,
           "format": None, "paragraphs": [], "not_found": False, "failure": None}
    try:
        response = fetcher.get(source["url"])
        row["content_sha256"] = hashlib.sha256(response.body).hexdigest()
        row["format"], paragraphs = extract_paragraphs(response, source["url"])
        if not paragraphs:
            raise FetchFailure("本文を取り出せなかった")
        row["paragraphs"], row["not_found"] = select_paragraphs(paragraphs, words)
    except FetchFailure as failure:
        row["failure"] = failure.reason
        row["paragraphs"] = []
    except Exception as error:  # noqa: BLE001 - 想定外の例外も、その資料の失敗とし、ほかの資料は続ける（本文を含みうるため、種類だけ記録する）
        row["failure"] = f"想定外のエラー（{type(error).__name__}）"
        row["paragraphs"] = []
    return row


def build_bundle(kind: str, slug: str, name: str, words: list[str], sources: list[dict], moment: datetime) -> dict:
    return {"schema_version": SCHEMA_VERSION, "kind": kind, "slug": slug, "name": name, "target_words": words,
            "fetched_on": moment.astimezone(JST).date().isoformat(), "sources": sources}


def serialize(bundle: dict) -> bytes:
    return json.dumps(bundle, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8")


def summary_lines(bundle: dict, dry_run: bool, bucket: str | None, key: str) -> list[str]:
    """要約（本文なし）。"""
    lines = [f"## 原資料束（解説）{bundle['kind']}-{bundle['slug']}", "",
             f"* 保存先: {'保存しない（dry-run）' if dry_run else f'バケット {bucket} / キー {key}'}", "",
             "| 番号 | 役割 | 形式 | 結果 | 段落 | 文字数 | 語 | 失敗の理由 |", "| :--- | :--- | :--- | :--- | ---: | ---: | :--- | :--- |"]
    for s in bundle["sources"]:
        chars = sum(len(p["text"]) for p in s["paragraphs"])
        found = "—" if s["failure"] else ("見つからず" if s["not_found"] else "あり")
        lines.append(f"| {s['id']} | {s['role']} | {s['format'] or '—'} | {'失敗' if s['failure'] else '取得'} | "
                     f"{len(s['paragraphs'])} | {chars:,} | {found} | {s['failure'] or ''} |")
    return lines


def parse_args(argv: list[str]) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="工程・用語の解説（AG-14）の原資料束を作り、R2の非公開バケットに保存する")
    parser.add_argument("--kind", required=True, choices=KINDS)
    parser.add_argument("--slug", required=True, metavar="SLUG")
    parser.add_argument("--dry-run", action="store_true", help="取得はするが、R2に書かない")
    parser.add_argument("--summary", type=Path, metavar="FILE", help="結果の要約（本文なし）を、追記で書くファイル")
    return parser.parse_args(argv)


def main(argv: list[str] | None = None, *, env=None, transport=urllib_transport, sleep=time.sleep,
         monotonic=time.monotonic, now=lambda: datetime.now(JST), r2_factory=make_bundle.make_r2_client,
         config_path: Path = CONFIG_PATH, supply_path: Path = SUPPLY_PATH) -> int:
    args = parse_args(sys.argv[1:] if argv is None else argv)
    env = os.environ if env is None else env
    secrets = [(env.get(n) or "").strip() for n in (make_bundle.ENV_ACCOUNT, make_bundle.ENV_ACCESS_KEY, make_bundle.ENV_SECRET_KEY)]
    try:
        if not make_bundle.SLUG_PATTERN.match(args.slug):
            raise ExplainerError("slug の形が正しくない", EXIT_USAGE)
        config = load_config(config_path, supply_path)
        entry = find_entry(config, args.kind, args.slug)
        creds = None
        if not args.dry_run:
            try:
                creds = make_bundle.read_r2_env(env)
            except make_bundle.BundleError as error:
                raise ExplainerError(str(error), error.exit_code) from None
        if entry.get("basis") == "reviewed":
            raise ExplainerError("basis: reviewed（運営者が確かめる方式）の対象は、公開資料の原資料束を使わない。取得しない", EXIT_USAGE)
        sources = approved_sources(entry)
        if not sources:
            raise ExplainerError("承認済み（approved）の資料がない", EXIT_USAGE)
        words = target_words(args.kind, entry)
        moment = now()
        fetcher = PoliteFetcher(transport, sleep, monotonic)
        fetched_at = moment.astimezone(JST).replace(microsecond=0).isoformat()
        rows = [collect_source(fetcher, s, words, fetched_at) for s in sources]
        bundle = build_bundle(args.kind, args.slug, entry_name(args.kind, entry), words, rows, moment)
        failed = [s for s in rows if s["failure"]]
        key = object_key(args.kind, args.slug)
        bucket = None if creds is None else creds[make_bundle.ENV_BUCKET]
        lines = summary_lines(bundle, args.dry_run, bucket, key)
        print("\n".join(lines))
        if args.summary is not None:
            with args.summary.open("a", encoding="utf-8") as handle:
                handle.write("\n".join(lines) + "\n")
        if len(failed) == len(rows):
            raise ExplainerError(f"承認済みの資料{len(rows)}件が、すべて失敗した。何も保存しない")
        if not args.dry_run:
            make_bundle.put_bundle(r2_factory(creds), bucket, key, serialize(bundle))
            print(f"保存した: バケット {bucket} / キー {key}")
        if failed:
            print("失敗した資料: " + ", ".join(f"{s['id']}（{s['failure']}）" for s in failed), file=sys.stderr)
            return EXIT_PARTIAL
        return EXIT_OK
    except ExplainerError as error:
        print(f"error: {make_bundle.mask_secrets(str(error), secrets)}", file=sys.stderr)
        return error.exit_code
    except make_bundle.BundleError as error:
        print(f"error: {make_bundle.mask_secrets(str(error), secrets)}", file=sys.stderr)
        return error.exit_code
    except Exception as error:  # noqa: BLE001 - 想定外の例外は、本文と認証情報を含みうるため、種類だけ示す
        print(f"error: 想定外のエラー（{make_bundle.describe_error(error, secrets)}）", file=sys.stderr)
        return EXIT_FAILURE


if __name__ == "__main__":
    sys.exit(main())
