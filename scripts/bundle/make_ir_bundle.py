"""IR重要ポイント（AG-12）の原資料束を作り、R2の非公開バケットに保存する。

決算短信（と、あれば決算説明資料）のPDFを取得し、ページごとの本文を取り出して、1つのJSONにまとめる。

使い方（R2の認証情報は環境変数だけ。コマンドの引数では受け取らない）:
    python3 scripts/bundle/make_ir_bundle.py --company advantest --fiscal-period-end 2027-03 --quarter 2 \\
        --announced-on 2026-10-28 --tanshin-url https://www.release.tdnet.info/... [--presentation-url https://...] \\
        [--dry-run] [--summary FILE]

* 取得してよいのは、IR用の許可の一覧（config/sources.yaml の ir）のドメインと、企業マスタの ir_url・website_url の
  ドメインだけ（データ定義書 7.4、LG-06）。https だけ。robots.txt に従う（make_explainer_bundle.py の PoliteFetcher）
* 画面とログに出すのは、資料ごとのページ数と文字数だけ。**本文は出さない**（Actionsのログは公開のため。CLAUDE.md 2章10）
* 保存先：bundles/ir/{slug}-{決算期}-q{四半期}.json（同じ決算発表で作り直すと、上書きする）

終了コード: 0 成功 / 1 取得・保存の失敗 / 2 設定・引数の誤り
"""

from __future__ import annotations

import argparse
import json
import os
import re
import sys
import urllib.parse
from datetime import date, datetime
from pathlib import Path
from zoneinfo import ZoneInfo

import yaml

sys.path.insert(0, str(Path(__file__).resolve().parent))

import make_bundle  # noqa: E402
import make_explainer_bundle as web  # noqa: E402

REPO_ROOT = Path(__file__).resolve().parents[2]
SOURCES_PATH = REPO_ROOT / "config" / "sources.yaml"
SCHEMA_VERSION = 1
KEY_PREFIX = "bundles/ir/"
JST = ZoneInfo("Asia/Tokyo")
KEEP_CHARS = 40000  # 1資料に残す文字数の上限（決算短信のサマリーと定性的情報は、先頭のページにある）
DOC_TYPES = (("tanshin", "決算短信"), ("presentation", "決算説明資料"))
PERIOD = re.compile(r"^[0-9]{4}-(0[1-9]|1[0-2])$")
EXIT_OK, EXIT_FAILURE, EXIT_USAGE = 0, 1, 2


class IrBundleError(Exception):
    """原資料束の作成の失敗。メッセージは、本文を含まない。"""

    def __init__(self, message: str, exit_code: int = EXIT_FAILURE):
        super().__init__(message)
        self.exit_code = exit_code


def parse_args(argv: list[str]) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="IR重要ポイントの原資料束（決算短信・決算説明資料）を作る")
    parser.add_argument("--company", required=True, metavar="SLUG")
    parser.add_argument("--fiscal-period-end", required=True, metavar="YYYY-MM")
    parser.add_argument("--quarter", required=True, type=int, choices=(1, 2, 3, 4))
    parser.add_argument("--announced-on", required=True, metavar="YYYY-MM-DD")
    parser.add_argument("--tanshin-url", required=True)
    parser.add_argument("--presentation-url")
    parser.add_argument("--dry-run", action="store_true", help="取得と抽出だけ行い、R2には保存しない")
    parser.add_argument("--summary", type=Path, metavar="FILE")
    return parser.parse_args(argv)


def bundle_id_of(slug: str, fiscal_period_end: str, quarter: int) -> str:
    return f"{slug}-{fiscal_period_end}-q{quarter}"


def object_key(bundle_id: str) -> str:
    return f"{KEY_PREFIX}{bundle_id}.json"


def _host(url_or_host: str) -> str:
    text = url_or_host if "://" in url_or_host else f"https://{url_or_host}"
    return (urllib.parse.urlsplit(text).hostname or "").lower()


def allowed_domains(sources: dict, master: dict) -> set[str]:
    """IR用の許可の一覧のドメインと、企業マスタの ir_url・website_url のドメイン。"""
    fixed = {str(e["domain"]).lower() for e in (sources or {}).get("ir") or [] if isinstance(e, dict) and e.get("domain")}
    own = {_host(master[k]) for k in ("ir_url", "website_url") if isinstance(master.get(k), str)}
    return {d for d in fixed | own if d}


def is_allowed(url: str, domains: set[str]) -> bool:
    host = _host(url)
    return any(host == d or host.endswith("." + d) for d in domains)


def check_inputs(args, master: dict, sources: dict, today: date) -> list[tuple[str, str]]:
    """引数を確かめ、取得する (type, url) の一覧を返す。"""
    if not make_bundle.SLUG_PATTERN.match(args.company):
        raise IrBundleError("slug の形が正しくない", EXIT_USAGE)
    if master.get("listing") != "detailed":
        raise IrBundleError("IR重要ポイントは、詳細掲載の企業だけに作る", EXIT_USAGE)
    if master.get("type") == "foreign_subsidiary":
        raise IrBundleError("外資系日本法人には、IR重要ポイントを作らない", EXIT_USAGE)
    if not PERIOD.match(args.fiscal_period_end):
        raise IrBundleError("--fiscal-period-end は YYYY-MM の形にする", EXIT_USAGE)
    try:
        announced = date.fromisoformat(args.announced_on)
    except ValueError:
        raise IrBundleError("--announced-on は YYYY-MM-DD の形にする", EXIT_USAGE) from None
    if announced > today:
        raise IrBundleError("--announced-on が、今日より後になっている", EXIT_USAGE)
    domains = allowed_domains(sources, master)
    targets = [("tanshin", args.tanshin_url)] + ([("presentation", args.presentation_url)] if args.presentation_url else [])
    for kind, url in targets:
        if not url.startswith("https://"):
            raise IrBundleError(f"{kind} のURLは https にする", EXIT_USAGE)
        if not is_allowed(url, domains):
            raise IrBundleError(f"{kind} のURLのドメイン（{_host(url)}）が、IR用の許可の一覧と企業のドメインにない", EXIT_USAGE)
    return targets


def extract_document(fetcher, kind: str, url: str, number: int, fetched_at: str) -> dict:
    """1資料を取得し、PDFの本文をページごとに取り出す。PDFでなければ失敗にする。"""
    try:
        response = fetcher.get(url)
    except web.FetchFailure as failure:
        raise IrBundleError(f"S{number}（{kind}）を取得できなかった：{failure}") from None
    if not response.body.startswith(b"%PDF"):
        raise IrBundleError(f"S{number}（{kind}）がPDFではない")
    try:
        paragraphs = web.pdf_paragraphs(response.body)
    except web.FetchFailure as failure:  # 暗号化、壊れたPDFなど。理由は本文を含まない
        raise IrBundleError(f"S{number}（{kind}）：{failure}") from None
    kept, total = [], 0
    for paragraph in paragraphs:
        text = paragraph.get("text") or ""
        if total + len(text) > KEEP_CHARS:
            break
        kept.append({"page": paragraph.get("page"), "text": text})
        total += len(text)
    if total == 0:
        raise IrBundleError(f"S{number}（{kind}）から本文を取り出せなかった（画像だけのPDFの可能性）")
    pages = len({p["page"] for p in kept})
    return {"id": f"S{number}", "type": kind, "title": dict(DOC_TYPES)[kind], "url": url, "fetched_at": fetched_at,
            "pages": pages, "chars": total, "truncated": len(kept) < len(paragraphs), "paragraphs": kept}


def build_bundle(args, documents: list[dict], extracted_at: str) -> dict:
    return {"schema_version": SCHEMA_VERSION, "bundle_id": bundle_id_of(args.company, args.fiscal_period_end, args.quarter),
            "company": args.company, "fiscal_period_end": args.fiscal_period_end, "quarter": args.quarter,
            "announced_on": args.announced_on, "extracted_at": extracted_at, "documents": documents}


def run(args, env, *, now, fetcher, r2_factory, root: Path, summary: list[str]) -> int:
    master_path = root / "data" / "companies" / f"{args.company}.yaml"
    try:
        master = yaml.safe_load(master_path.read_text(encoding="utf-8")) if make_bundle.SLUG_PATTERN.match(args.company) else None
        sources = yaml.safe_load((root / "config" / "sources.yaml").read_text(encoding="utf-8"))
    except (OSError, yaml.YAMLError):
        raise IrBundleError("企業マスタか config/sources.yaml を読めなかった", EXIT_USAGE) from None
    if not isinstance(master, dict):
        raise IrBundleError("企業マスタを読めなかった", EXIT_USAGE)
    moment = now().astimezone(JST)
    targets = check_inputs(args, master, sources, moment.date())
    creds = None if args.dry_run else make_bundle.read_r2_env(env)
    stamp = moment.isoformat(timespec="seconds")
    documents = [extract_document(fetcher, kind, url, i, stamp) for i, (kind, url) in enumerate(targets, start=1)]
    bundle = build_bundle(args, documents, stamp)
    key = object_key(bundle["bundle_id"])
    summary += [f"## IRの原資料束 {bundle['bundle_id']}", "", "| 資料 | 種類 | ページ | 文字数 | 打ち切り |",
                "| :--- | :--- | ---: | ---: | :--- |"]
    summary += [f"| {d['id']} | {d['title']} | {d['pages']} | {d['chars']:,} | {'あり' if d['truncated'] else 'なし'} |"
                for d in documents]
    for d in documents:
        print(f"{d['id']} {d['title']}: {d['pages']}ページ、{d['chars']:,}文字")
    if args.dry_run:
        print(f"保存しない（--dry-run）: {key}")
        return EXIT_OK
    r2 = r2_factory(creds)
    make_bundle.put_bundle(r2, creds[make_bundle.ENV_BUCKET], key, make_bundle.serialize(bundle))
    print(f"保存した: {key}")
    return EXIT_OK


def main(argv: list[str] | None = None, *, env=None, now=lambda: datetime.now(JST), fetcher=None,
         r2_factory=make_bundle.make_r2_client, root: Path = REPO_ROOT) -> int:
    args = parse_args(sys.argv[1:] if argv is None else argv)
    env = os.environ if env is None else env
    secrets = [(env.get(n) or "").strip() for n in (make_bundle.ENV_ACCOUNT, make_bundle.ENV_ACCESS_KEY,
                                                      make_bundle.ENV_SECRET_KEY)]
    summary: list[str] = []
    code = EXIT_FAILURE
    try:
        code = run(args, env, now=now, fetcher=fetcher or web.PoliteFetcher(), r2_factory=r2_factory, root=root,
                   summary=summary)
    except (IrBundleError, make_bundle.BundleError) as error:
        message = make_bundle.mask_secrets(str(error), secrets)
        print(f"error: {message}", file=sys.stderr)
        summary += ["", f"* 失敗: {message[:500]}"]
        code = error.exit_code
    except Exception as error:  # noqa: BLE001 - 想定外の例外は、本文と認証情報を含みうるため、種類だけ示す
        print(f"error: 想定外のエラー（{type(error).__name__}）", file=sys.stderr)
        code = EXIT_FAILURE
    if args.summary is not None:
        try:
            with args.summary.open("a", encoding="utf-8") as handle:
                handle.write("\n".join(summary) + "\n")
        except OSError:
            print("error: 要約を書けなかった", file=sys.stderr)
    return code


if __name__ == "__main__":
    sys.exit(main())
