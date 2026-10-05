"""有価証券報告書の本文（事業の内容、セグメント情報など）を取り出し、Cloudflare R2 の非公開バケットに保存する（原資料束）。

使い方:
    EDINET_API_KEY=... R2_ACCOUNT_ID=... R2_ACCESS_KEY_ID=... R2_SECRET_ACCESS_KEY=... R2_BUCKET=... \\
        python3 scripts/bundle/make_bundle.py --company advantest [--sections 要素ID ...] [--dry-run]
    python3 scripts/bundle/make_bundle.py --doc-id S100XXXX ...

* --company は、data/auto/{slug}.json の filings から、最新の通期（annual_report）の ingested の書類を選ぶ。
  --doc-id を足すと、その書類を使う（その企業の filings にあるものだけ）。--doc-id だけのときは、
  data/auto/ の filings にある書類から、企業を決める
* --sections は、取り出す要素ID。省略すると config/bundle-sections.yaml の既定を使う
* キーは、環境変数だけで受け取る（引数にしない）。R2 の4つの変数は、--dry-run のときは要らない
* オブジェクトのキーは bundles/{bundle_id}.json。bundle_id は {slug}-{doc_id}。同じ書類で2回動かすと、同じキーを上書きする
* **本文は、画面にも、--summary にも、例外のメッセージにも出さない**（リポジトリ、Actionsのログは公開。CLAUDE.md 2章10）。
  出すのは、節ごとの要素ID、項目名、文字数、保存したキー、バケット名だけ。認証情報は、例外のメッセージでも伏せ字にする
* 指定した節が書類にないときは、何も書かずに終了コード1（一部だけの原資料束を作らない）

終了コード: 0 成功 / 1 取得・解析・保存の失敗 / 2 設定・引数の誤り
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import sys
import time
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

import yaml

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "edinet"))
sys.path.insert(0, str(Path(__file__).resolve().parent))

import client  # noqa: E402
from client import DOC_ID_PATTERN, ENV_KEY, EXIT_FAILURE, EXIT_OK, EXIT_USAGE, MASK, EdinetError, redact  # noqa: E402
from csv_reader import document_rows  # noqa: E402
from extract_document import document_edinet_code  # noqa: E402
from list_filings import REPO_ROOT, SLUG_PATTERN  # noqa: E402
from sections import TextRow, text_rows_from_zip  # noqa: E402

AUTO_DIR = REPO_ROOT / "data" / "auto"
SECTIONS_CONFIG = REPO_ROOT / "config" / "bundle-sections.yaml"
SCHEMA_VERSION = 1
KEY_PREFIX = "bundles/"
MAX_REQUESTS = 4  # 書類取得の呼び出し1回と、429の再試行（最大3回）
R2_REGION = "auto"
ENV_ACCOUNT, ENV_ACCESS_KEY, ENV_SECRET_KEY, ENV_BUCKET = (
    "R2_ACCOUNT_ID", "R2_ACCESS_KEY_ID", "R2_SECRET_ACCESS_KEY", "R2_BUCKET")
ACCOUNT_PATTERN = re.compile(r"^[0-9a-f]{32}$")
BUCKET_PATTERN = re.compile(r"^[a-z0-9][a-z0-9.-]{1,61}[a-z0-9]$")
ELEMENT_PATTERN = re.compile(r"^[A-Za-z0-9_-]+:[A-Za-z0-9_.-]*TextBlock$")
LABEL_MAX_LENGTH = 60
ANNUAL_TYPES = ("annual_report", "amended_annual_report")


class BundleError(Exception):
    """原資料束の作成の失敗。メッセージは、本文と認証情報を含まない文だけを持つ。"""

    def __init__(self, message: str, exit_code: int = EXIT_FAILURE):
        super().__init__(message)
        self.exit_code = exit_code


# ---- 対象の書類を決める ----------------------------------------------------------------------

def load_auto(slug: str, auto_dir: Path = AUTO_DIR) -> dict:
    if not SLUG_PATTERN.match(slug):
        raise BundleError(f"slug の形が正しくない: {slug[:40]!r}", EXIT_USAGE)
    path = auto_dir / f"{slug}.json"
    if not path.is_file():
        raise BundleError(f"data/auto/ に、その企業のファイルがない: {slug}", EXIT_USAGE)
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        raise BundleError(f"data/auto/{slug}.json を読めなかった", EXIT_USAGE) from None


def latest_annual_report(filings: list[dict]) -> dict:
    """filings から、最新の通期（doc_type が annual_report）で、status が ingested の書類を選ぶ。

    決算期（fiscal_period_end）の新しい順、同じなら提出日時（submitted_at）の新しい順。
    それより新しい決算期の通期の書類（訂正報告書を含む）があるのに、その期の annual_report が
    ingested でない（訂正で置き換えられた、取り込めなかった）ときは、古い期を黙って選ばず、止める。
    """
    ordered = sorted(
        (f for f in filings if f.get("doc_type") == "annual_report" and f.get("status") == "ingested"),
        key=lambda f: (f.get("fiscal_period_end", ""), f.get("submitted_at", "")),
        reverse=True,
    )
    if not ordered:
        raise BundleError("取り込み済み（ingested）の有価証券報告書が、data/auto/ の filings にない")
    chosen = ordered[0]
    newer = sorted(
        {f["doc_id"] for f in filings
         if f.get("doc_type") in ANNUAL_TYPES and f.get("fiscal_period_end", "") > chosen.get("fiscal_period_end", "")}
    )
    if newer:
        raise BundleError(
            f"より新しい決算期の通期の書類がある（{', '.join(newer)}）が、有価証券報告書として取り込まれていない。"
            "使う書類を --doc-id で指定する")
    return chosen


def resolve_target(company: str | None, doc_id: str | None, auto_dir: Path = AUTO_DIR) -> tuple[str, dict, dict]:
    """(slug, data/auto の内容, 対象の filings の行) を返す。"""
    if doc_id is not None and not DOC_ID_PATTERN.match(doc_id):
        raise BundleError(f"doc_id の形が正しくない: {doc_id[:30]!r}（S100 と英数字4文字）", EXIT_USAGE)
    if company is None and doc_id is None:
        raise BundleError("--company か --doc-id を指定する", EXIT_USAGE)
    if company is not None:
        auto = load_auto(company, auto_dir)
        slug = company
    else:
        matches = []
        for path in sorted(auto_dir.glob("*.json")):
            try:
                data = json.loads(path.read_text(encoding="utf-8"))
            except (OSError, ValueError):
                continue
            if any(f.get("doc_id") == doc_id for f in data.get("filings", [])):
                matches.append((path.stem, data))
        if len(matches) != 1:
            raise BundleError(
                f"data/auto/ の filings に、{doc_id} の書類がない" if not matches
                else f"{doc_id} が複数の企業の filings にある。--company を指定する", EXIT_USAGE)
        slug, auto = matches[0]
    filings = auto.get("filings", [])
    if doc_id is None:
        filing = latest_annual_report(filings)
    else:
        filing = next((f for f in filings if f.get("doc_id") == doc_id), None)
        if filing is None:
            raise BundleError(f"{slug} の filings に、{doc_id} の書類がない", EXIT_USAGE)
    return slug, auto, filing


def load_default_sections(path: Path = SECTIONS_CONFIG) -> list[str]:
    try:
        data = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    except (OSError, yaml.YAMLError):
        raise BundleError("config/bundle-sections.yaml を読めなかった", EXIT_USAGE) from None
    value = data.get("sections") if isinstance(data, dict) else None
    if not isinstance(value, list) or not all(isinstance(v, str) for v in value):
        raise BundleError("config/bundle-sections.yaml の sections は、要素IDの文字列のリストにする", EXIT_USAGE)
    return value


def choose_sections(cli_values: list[str] | None, default_path: Path = SECTIONS_CONFIG) -> list[str]:
    """--sections（カンマ区切りも可）か、設定ファイルの既定から、要素IDのリストを決める。重複は除く。"""
    if cli_values:
        values = [v.strip() for item in cli_values for v in item.split(",") if v.strip()]
    else:
        values = load_default_sections(default_path)
    values = list(dict.fromkeys(values))
    if not values:
        raise BundleError(
            "取り出す節の要素IDがない。--sections で指定するか、config/bundle-sections.yaml に書く"
            "（要素IDは、inspect_sections.py で確かめる）", EXIT_USAGE)
    for value in values:
        if not ELEMENT_PATTERN.match(value):
            raise BundleError(f"要素IDの形が正しくない（接頭辞:名前TextBlock の形）: {value[:60]!r}", EXIT_USAGE)
    return values


# ---- 原資料束の組み立て -----------------------------------------------------------------------

def select_rows(rows: list[TextRow], wanted: list[str]) -> tuple[list[TextRow], list[str]]:
    """指定の要素IDの行を、指定の順で返す（同じ要素IDの行は、CSVの順）。返り値は (行, 見つからなかった要素ID)。"""
    selected = []
    missing = []
    for element in wanted:
        found = [r for r in rows if r.element_id == element]
        if found:
            selected += found
        else:
            missing.append(element)
    return selected, missing


def bundle_id_of(slug: str, doc_id: str) -> str:
    return f"{slug}-{doc_id}"


def object_key(bundle_id: str) -> str:
    return f"{KEY_PREFIX}{bundle_id}.json"


def build_bundle(slug: str, auto: dict, filing: dict, rows: list[TextRow], extracted_at: str) -> dict:
    """保存するJSONを作る。同じ入力（と extracted_at）には、同じ結果を返す。"""
    doc_id = filing["doc_id"]
    return {
        "schema_version": SCHEMA_VERSION,
        "bundle_id": bundle_id_of(slug, doc_id),
        "company": slug,
        "document": {
            "doc_id": doc_id,
            "doc_type": filing.get("doc_type"),
            "submitted_at": filing.get("submitted_at"),
            "fiscal_period_end": filing.get("fiscal_period_end"),
            "edinet_code": auto.get("edinet_code"),
        },
        "extracted_at": extracted_at,
        "sections": [
            {"element_id": r.element_id, "label": r.label, "context_id": r.context_id,
             "file": r.file, "chars": r.chars, "text": r.text}
            for r in rows
        ],
    }


def serialize(bundle: dict) -> bytes:
    return json.dumps(bundle, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8")


def verify_edinet_code(raw: bytes, expected: str | None) -> None:
    """書類のDEIのEDINETコードが、data/auto の edinet_code と同じことを確かめる（違う企業の書類を保存しない）。"""
    try:
        code = document_edinet_code(document_rows(raw))
    except ValueError:
        raise BundleError("書類のEDINETコードを確かめられなかった（DEIの行を読めない）") from None
    if not expected or code != expected:
        raise BundleError("書類のEDINETコードが、data/auto/ の edinet_code と違う。保存しない")


# ---- R2 ----------------------------------------------------------------------------------------

def read_r2_env(env) -> dict[str, str]:
    values = {name: (env.get(name) or "").strip()
              for name in (ENV_ACCOUNT, ENV_ACCESS_KEY, ENV_SECRET_KEY, ENV_BUCKET)}
    missing = [name for name, value in values.items() if not value]
    if missing:
        raise BundleError(f"環境変数が設定されていない: {', '.join(missing)}", EXIT_USAGE)
    if not ACCOUNT_PATTERN.match(values[ENV_ACCOUNT]):
        raise BundleError(f"環境変数 {ENV_ACCOUNT} の形が正しくない（英小文字と数字の32文字）", EXIT_USAGE)
    if not BUCKET_PATTERN.match(values[ENV_BUCKET]):
        raise BundleError(f"環境変数 {ENV_BUCKET} の形が正しくない", EXIT_USAGE)
    return values


def make_r2_client(creds: dict[str, str]):
    """R2のS3互換APIのクライアント（エンドポイント https://{R2_ACCOUNT_ID}.r2.cloudflarestorage.com、リージョン auto）。"""
    import boto3
    from botocore.config import Config

    return boto3.client(
        "s3",
        endpoint_url=f"https://{creds[ENV_ACCOUNT]}.r2.cloudflarestorage.com",
        region_name=R2_REGION,
        aws_access_key_id=creds[ENV_ACCESS_KEY],
        aws_secret_access_key=creds[ENV_SECRET_KEY],
        config=Config(signature_version="s3v4", retries={"max_attempts": 3, "mode": "standard"},
                      connect_timeout=10, read_timeout=60),
    )


def put_bundle(r2, bucket: str, key: str, body: bytes) -> None:
    response = r2.put_object(Bucket=bucket, Key=key, Body=body, ContentType="application/json; charset=utf-8")
    status = (response or {}).get("ResponseMetadata", {}).get("HTTPStatusCode")
    if status is not None and status != 200:
        raise BundleError(f"R2への保存が成功しなかった（HTTP {status}）")


# ---- 出力 --------------------------------------------------------------------------------------

def mask_secrets(text: str, secrets: list[str]) -> str:
    for secret in sorted((s for s in secrets if s), key=len, reverse=True):
        text = text.replace(secret, MASK)
    return text


def describe_error(error: BaseException, secrets: list[str]) -> str:
    """例外を、本文と認証情報を含まない1行にする。自分たちが書いたメッセージ以外は、種類（とエラーコード）だけを示す。"""
    if isinstance(error, (BundleError, EdinetError)):
        return mask_secrets(redact(str(error), secrets[0] if secrets else None), secrets)
    text = type(error).__name__
    code = getattr(error, "response", None)
    code = code.get("Error", {}).get("Code") if isinstance(code, dict) else None
    if isinstance(code, str) and re.fullmatch(r"[A-Za-z0-9_]{1,60}", code):
        text += f"（{code}）"
    return text


def describe_sections(rows: list[TextRow]) -> list[str]:
    return [
        f"  {r.element_id}  {_short(r.label)}  {r.context_id}  {r.chars:,}文字"
        for r in rows
    ]


def _short(label: str) -> str:
    cleaned = "".join(ch if ch.isprintable() else "?" for ch in label)
    return cleaned if len(cleaned) <= LABEL_MAX_LENGTH else cleaned[:LABEL_MAX_LENGTH] + "…"


def summary_markdown(bundle_id: str, doc_id: str, rows: list[TextRow], dry_run: bool,
                     bucket: str | None, key: str | None) -> str:
    lines = [f"## 原資料束 {bundle_id}", "", f"* 書類: {doc_id}", f"* 実行: {'dry-run（保存しない）' if dry_run else '保存した'}"]
    if not dry_run:
        lines += [f"* バケット: {bucket}", f"* キー: {key}"]
    lines += ["", "| 要素ID | 項目名 | コンテキストID | 文字数 |", "| :--- | :--- | :--- | ---: |"]
    lines += [f"| {r.element_id} | {_short(r.label).replace('|', '/')} | {r.context_id} | {r.chars:,} |" for r in rows]
    return "\n".join(lines) + "\n"


def parse_args(argv: list[str]) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="有価証券報告書の節を取り出し、R2の非公開バケットに保存する（原資料束）")
    parser.add_argument("--company", metavar="SLUG", help="企業の slug。最新の通期の書類を使う")
    parser.add_argument("--doc-id", metavar="DOC_ID", help="書類管理番号（S100XXXX）")
    parser.add_argument("--sections", nargs="+", metavar="ELEMENT_ID",
                        help="取り出す要素ID（カンマ区切りも可）。省略時は config/bundle-sections.yaml の既定")
    parser.add_argument("--dry-run", action="store_true", help="R2に書かず、取り出せた節の要素IDと文字数だけを出す")
    parser.add_argument("--summary", type=Path, metavar="FILE",
                        help="結果の要約（節ごとの要素ID、項目名、文字数、キー、バケット名。本文なし）を、追記で書くファイル")
    return parser.parse_args(argv)


def main(
    argv: list[str] | None = None,
    *,
    env=None,
    open_url=client._open,
    sleep=time.sleep,
    monotonic=time.monotonic,
    now: datetime | None = None,
    r2_factory=make_r2_client,
    auto_dir: Path = AUTO_DIR,
    sections_config: Path = SECTIONS_CONFIG,
) -> int:
    args = parse_args(sys.argv[1:] if argv is None else argv)
    env = os.environ if env is None else env
    secrets = [(env.get(name) or "").strip()
               for name in (ENV_KEY, ENV_ACCOUNT, ENV_ACCESS_KEY, ENV_SECRET_KEY)]
    try:
        slug, auto, filing = resolve_target(args.company, args.doc_id, auto_dir)
        wanted = choose_sections(args.sections, sections_config)
        key = secrets[0]
        if not key:
            raise BundleError(f"環境変数 {ENV_KEY} が設定されていない", EXIT_USAGE)
        creds = None if args.dry_run else read_r2_env(env)

        doc_id = filing["doc_id"]
        bundle_id = bundle_id_of(slug, doc_id)
        edinet = client.EdinetClient(
            key, open_url=open_url, sleep=sleep, monotonic=monotonic, max_requests=MAX_REQUESTS)
        raw = edinet.get_document(doc_id)
        verify_edinet_code(raw, auto.get("edinet_code"))
        try:
            all_rows, problems = text_rows_from_zip(raw)
        except ValueError as error:
            raise BundleError(f"書類を読めなかった: {error}") from None
        rows, missing = select_rows(all_rows, wanted)
        print(f"対象: {slug} / {doc_id}（{filing.get('doc_type')}、決算期 {filing.get('fiscal_period_end')}、"
              f"status {filing.get('status')}）")
        print(f"bundle_id: {bundle_id}")
        print(f"節 {len(rows)}件")
        print("\n".join(describe_sections(rows)))
        if missing:
            raise BundleError("書類にない要素ID（何も保存しない）: " + ", ".join(missing))

        moment = (now or datetime.now(ZoneInfo("Asia/Tokyo"))).astimezone(ZoneInfo("Asia/Tokyo"))
        bundle = build_bundle(slug, auto, filing, rows, moment.replace(microsecond=0).isoformat())
        body = serialize(bundle)
        object_name = object_key(bundle_id)
        bucket = None
        if args.dry_run:
            print("dry-run: R2には書かない")
        else:
            bucket = creds[ENV_BUCKET]
            put_bundle(r2_factory(creds), bucket, object_name, body)
            print(f"保存した: バケット {bucket} / キー {object_name}（{len(body):,}バイト、sha256 {hashlib.sha256(body).hexdigest()[:12]}）")
        if args.summary is not None:
            with args.summary.open("a", encoding="utf-8") as handle:
                handle.write(summary_markdown(bundle_id, doc_id, rows, args.dry_run, bucket, object_name))
        return EXIT_OK
    except BundleError as error:
        print(f"error: {describe_error(error, secrets)}", file=sys.stderr)
        return error.exit_code
    except EdinetError as error:
        print(f"error: {describe_error(error, secrets)}", file=sys.stderr)
        return error.exit_code
    except Exception as error:  # noqa: BLE001 - 想定外の例外は、本文と認証情報を含みうるため、種類だけ示す
        print(f"error: 想定外のエラー（{describe_error(error, secrets)}）", file=sys.stderr)
        return EXIT_FAILURE


if __name__ == "__main__":
    sys.exit(main())
