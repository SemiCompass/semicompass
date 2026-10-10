"""変更案の事実確認を動かす（P08 第2段階）。アーキテクチャ設計書 9.3。

* 対象は、変更案で追加・変更された本文の行だけ（変わらない行は照合し直さない）
* 原資料は、各ファイルの出典の一覧（sources、source_article）のURLから取得する（取得できなかった資料は「確認不能」に回す）
* 判定の部品は factcheck.py。ここは、差分の取り出し、資料の取得、結果の表の組み立てだけを行う
* 原資料の本文を、画面、ログ、結果の表に出さない（リポジトリ、Actionsのログ、変更案のコメントは公開）
* 取得するURLは、公開のホストだけ（内部のアドレスは取りに行かない）。転送のたびに確かめる
終了コード：0 合格、1 不合格、2 入力・実行の誤り
"""
from __future__ import annotations

import argparse
import difflib
import html.parser
import io
import ipaddress
import json
import re
import socket
import subprocess
import sys
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path

import yaml

sys.path.insert(0, str(Path(__file__).resolve().parent))
import factcheck as fc  # noqa: E402

ROOT = Path(__file__).resolve().parents[2]
MARKER = "<!-- semicompass-factcheck -->"
MAX_BYTES = 12 * 1024 * 1024
MAX_FILES = 20
USER_AGENT = "SemiCompassBot/1.0 (+https://github.com/SemiCompass/semicompass)"


# ---- 差分 ----

def git(*args: str, root: Path = ROOT) -> str:
    return subprocess.run(["git", *args], cwd=root, check=True, capture_output=True, text=True).stdout


def changed_files(base: str, head: str, prefixes: list[str], root: Path = ROOT) -> list[str]:
    out = git("diff", "--name-only", "--diff-filter=AM", base, head, "--", *prefixes, root=root)
    return sorted(p for p in out.splitlines() if p.endswith(".md"))


def show(rev: str, path: str, root: Path = ROOT) -> str | None:
    try:
        return git("show", f"{rev}:{path}", root=root)
    except subprocess.CalledProcessError:
        return None


def changed_text(old_body: str, new_body: str) -> str:
    """新しい本文のうち、追加・変更された行を、改行でつないで返す。"""
    old = old_body.splitlines()
    new = new_body.splitlines()
    out: list[str] = []
    for tag, _i1, _i2, j1, j2 in difflib.SequenceMatcher(a=old, b=new, autojunk=False).get_opcodes():
        if tag in ("insert", "replace"):
            out.extend(new[j1:j2])
    return "\n".join(out)


# ---- 資料の取得 ----

def is_public_host(host: str) -> bool:
    try:
        infos = socket.getaddrinfo(host, None)
    except OSError:
        return False
    for info in infos:
        ip = ipaddress.ip_address(info[4][0])
        if ip.is_private or ip.is_loopback or ip.is_link_local or ip.is_reserved or ip.is_multicast or ip.is_unspecified:
            return False
    return bool(infos)


class _Redirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        check_url_allowed(newurl)
        return super().redirect_request(req, fp, code, msg, headers, newurl)


def check_url_allowed(url: str) -> None:
    parts = urllib.parse.urlsplit(url)
    if parts.scheme != "https" or not parts.hostname or parts.username or parts.password:
        raise ValueError("httpsの公開URLではない")
    if parts.port not in (None, 443):
        raise ValueError("443以外のポートは取りに行かない")
    if not is_public_host(parts.hostname):
        raise ValueError("公開のホストではない")


def fetch_bytes(url: str) -> tuple[bytes, str]:
    check_url_allowed(url)
    opener = urllib.request.build_opener(_Redirect)
    request = urllib.request.Request(url, headers={"User-Agent": USER_AGENT, "Accept": "text/html,application/pdf,text/plain,*/*;q=0.5"})
    with opener.open(request, timeout=30) as response:  # noqa: S310（https の公開URLだけ。上で確かめた）
        data = response.read(MAX_BYTES + 1)
        if len(data) > MAX_BYTES:
            raise ValueError("大きすぎる")
        return data, response.headers.get("Content-Type", "")


def safe_url_status(url: str) -> int:
    """出典以外のURLの到達確認（HEAD）。公開のホストだけ、転送のたびに確かめる。"""
    check_url_allowed(url)
    opener = urllib.request.build_opener(_Redirect)
    request = urllib.request.Request(url, method="HEAD", headers={"User-Agent": USER_AGENT})
    try:
        with opener.open(request, timeout=15) as response:  # noqa: S310
            return response.status
    except urllib.error.HTTPError as error:
        return error.code


class _Text(html.parser.HTMLParser):
    SKIP = {"script", "style", "noscript", "template", "svg"}

    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.parts: list[str] = []
        self.depth = 0

    def handle_starttag(self, tag, attrs):
        if tag in self.SKIP:
            self.depth += 1
        elif tag in ("p", "br", "li", "tr", "div", "h1", "h2", "h3", "h4"):
            self.parts.append("\n")

    def handle_endtag(self, tag):
        if tag in self.SKIP and self.depth:
            self.depth -= 1

    def handle_data(self, data):
        if not self.depth:
            self.parts.append(data)


def to_text(data: bytes, content_type: str) -> str:
    if data[:5] == b"%PDF-" or "pdf" in content_type.lower():
        from pypdf import PdfReader
        reader = PdfReader(io.BytesIO(data))
        return "\n".join((page.extract_text() or "") for page in reader.pages)
    charset = "utf-8"
    m = re.search(r"charset=([\w-]+)", content_type, re.I)
    if m:
        charset = m[1]
    text = data.decode(charset, errors="replace")
    if "html" in content_type.lower() or "<html" in text[:2000].lower():
        parser = _Text()
        parser.feed(text)
        return "".join(parser.parts)
    return text


def fetch_text(url: str) -> str:
    data, content_type = fetch_bytes(url)
    return to_text(data, content_type)


def sources_of(front: dict) -> list[tuple[str, str]]:
    """(資料の番号, URL)。ニュースは source_article を S1 とする。"""
    out: list[tuple[str, str]] = []
    for s in front.get("sources") or []:
        if isinstance(s, dict) and isinstance(s.get("id"), str) and isinstance(s.get("url"), str):
            out.append((s["id"], s["url"]))
    article = front.get("source_article")
    if isinstance(article, dict) and isinstance(article.get("url"), str) and not out:
        out.append(("S1", article["url"]))
    return out


def gather(front: dict, fetch=fetch_text) -> tuple[list[fc.Source], list[str]]:
    """資料を取得する。取得できなかった資料の番号と理由（種類だけ）を返す。本文は返さない。"""
    sources, failed = [], []
    for sid, url in sources_of(front):
        try:
            sources.append(fc.make_source(sid, fetch(url)))
        except Exception as error:  # noqa: BLE001（理由は種類だけを出す）
            failed.append(f"{sid}（{type(error).__name__}）")
    return sources, failed


# ---- 1ファイルの確認 ----

def check_file(front: dict, body_diff: str, dictionary: set[str], sources: list[fc.Source], failed: list[str],
               fetcher=None) -> list[fc.Result]:
    results = fc.check_claims(body_diff, sources, dictionary, fc.listed_urls_of(front), fetcher)
    if failed:
        # 取得できなかった資料があるときは、その資料にあるはずの値を「根拠なし」と断定しない
        for r in results:
            if r.result == fc.UNSUPPORTED and r.claim.kind != "url":
                r.result = fc.UNVERIFIABLE
                r.note = f"原資料を取得できなかった：{'、'.join(failed)}"
    return results


def load_acks(path: Path | None, file: str) -> set[str]:
    if not path or not path.is_file():
        return set()
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return set()
    acks = data.get("acks") if isinstance(data, dict) else data
    out = set()
    for a in acks or []:
        if isinstance(a, str):
            out.add(a)
        elif isinstance(a, dict) and isinstance(a.get("fingerprint"), str) and a.get("file") in (None, file):
            out.add(a["fingerprint"])
    return out


def run(base: str, head: str, acks_path: Path | None = None, root: Path = ROOT, fetch=fetch_text, fetcher=None) -> tuple[str, int, dict]:
    config = yaml.safe_load((root / "config/operations.yaml").read_text(encoding="utf-8")) or {}
    prefixes = config.get("factcheck_paths") or ["content/"]
    files = changed_files(base, head, prefixes, root)
    dictionary = fc.load_dictionary(root)
    sections, bad_total, summary = [], 0, {"files": [], "failures": 0}
    if len(files) > MAX_FILES:
        return f"{MARKER}\n## 事実確認の結果：不合格\n\n変更したファイルが{MAX_FILES}件を超えている（{len(files)}件）。変更案を分ける。\n", 1, {"files": files, "failures": -1}
    for path in files:
        new = show(head, path, root)
        if new is None:
            continue
        old = show(base, path, root) or ""
        front, new_body = fc.split_front_matter(new)
        _, old_body = fc.split_front_matter(old)
        diff = changed_text(old_body, new_body)
        if not diff.strip():
            continue
        sources, failed = gather(front, fetch)
        results = check_file(front, diff, dictionary, sources, failed, fetcher)
        acks = load_acks(acks_path, path)
        bad = fc.failures(results, acks)
        bad_total += len(bad)
        text = fc.report(results, acks).replace("## 事実確認の結果", f"### `{path}`", 1)
        if failed:
            text += f"\n取得できなかった資料：{'、'.join(failed)}\n"
        sections.append(text)
        summary["files"].append({"path": path, "claims": len(results), "failures": len(bad)})
    summary["failures"] = bad_total
    head_line = f"## 事実確認の結果：{'不合格' if bad_total else '合格'}"
    if not sections:
        body = f"{MARKER}\n{head_line}\n\n本文が変わったファイルがない（照合の対象なし）。\n"
    else:
        body = f"{MARKER}\n{head_line}\n\n" + "\n".join(sections)
    return body, 1 if bad_total else 0, summary


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    parser.add_argument("--base", required=True)
    parser.add_argument("--head", required=True)
    parser.add_argument("--acks", type=Path)
    parser.add_argument("--root", type=Path, default=ROOT)
    parser.add_argument("--comment", type=Path, help="PRコメントの本文の出力先")
    parser.add_argument("--summary", type=Path, help="件数のJSONの出力先")
    parser.add_argument("--url-check", action="store_true")
    args = parser.parse_args(argv)
    try:
        body, code, summary = run(args.base, args.head, args.acks, args.root, fetcher=safe_url_status if args.url_check else None)
    except (subprocess.CalledProcessError, OSError, ValueError, yaml.YAMLError) as error:
        print(f"実行の誤り：{type(error).__name__}")
        return 2
    print(body)
    if args.comment:
        args.comment.write_text(body, encoding="utf-8")
    if args.summary:
        args.summary.write_text(json.dumps(summary, ensure_ascii=False) + "\n", encoding="utf-8")
    return code


if __name__ == "__main__":
    sys.exit(main())
