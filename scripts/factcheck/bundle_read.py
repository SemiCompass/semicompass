"""原資料束（Cloudflare R2の非公開バケット）の読み取り（P08 第2段階b。アーキテクチャ設計書 9.3、10.2）。

* 変更案の説明の「原資料束」の欄に、`bundle_id` を、バッククォートで囲んで書く（例：`advantest-S100XXXX`）。
  その番号を拾い、bundles/{bundle_id}.json（scripts/bundle/make_bundle.py が保存した形）を読む
* 読み取り専用のキー（Environment bundle-read）だけを使う。環境変数 R2_ACCOUNT_ID、R2_ACCESS_KEY_ID、R2_SECRET_ACCESS_KEY、R2_BUCKET。
  1つでも欠けているときは、読まない（出典のURLからの取得だけで照合する）
* 本文は、画面、ログ、結果の表に出さない。例外のメッセージも、種類だけを返す
"""
from __future__ import annotations

import json
import re

BUNDLE_ID = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]{2,80}$")
TICKS = re.compile(r"`([^`\n]+)`")
HEADING = re.compile(r"^\s{0,3}(#{1,6}\s*)?(原資料束)")
NEXT_HEADING = re.compile(r"^\s{0,3}#{1,6}\s")
ENV_NAMES = ("R2_ACCOUNT_ID", "R2_ACCESS_KEY_ID", "R2_SECRET_ACCESS_KEY", "R2_BUCKET")
MAX_BUNDLES = 10
MAX_BYTES = 12 * 1024 * 1024


def bundle_ids_from_body(body: str) -> list[str]:
    """変更案の説明の「原資料束」の欄（次の見出しまで）から、bundle_id を順に拾う。"""
    ids: list[str] = []
    inside = False
    for line in (body or "").splitlines():
        if not inside:
            if HEADING.match(line):
                inside = True
                line = HEADING.sub("", line, count=1)
            else:
                continue
        elif NEXT_HEADING.match(line):
            break
        for token in TICKS.findall(line):
            token = token.strip()
            if BUNDLE_ID.match(token) and token not in ids:
                ids.append(token)
    return ids[:MAX_BUNDLES]


def r2_env(env) -> dict[str, str] | None:
    values = {name: (env.get(name) or "").strip() for name in ENV_NAMES}
    return values if all(values.values()) else None


def make_client(values: dict[str, str]):
    import boto3
    from botocore.config import Config

    return boto3.client(
        "s3",
        endpoint_url=f"https://{values['R2_ACCOUNT_ID']}.r2.cloudflarestorage.com",
        region_name="auto",
        aws_access_key_id=values["R2_ACCESS_KEY_ID"],
        aws_secret_access_key=values["R2_SECRET_ACCESS_KEY"],
        config=Config(signature_version="s3v4", retries={"max_attempts": 3, "mode": "standard"}, connect_timeout=10, read_timeout=60),
    )


def bundle_text(raw: bytes) -> str:
    """原資料束のJSONから、節の本文をつないだ文章を返す。"""
    data = json.loads(raw.decode("utf-8"))
    sections = data.get("sections") if isinstance(data, dict) else None
    if not isinstance(sections, list):
        raise ValueError("形が正しくない")
    return "\n".join(s["text"] for s in sections if isinstance(s, dict) and isinstance(s.get("text"), str))


def read_bundles(client, bucket: str, ids: list[str]) -> tuple[list[tuple[str, str]], list[str]]:
    """(bundle_id, 文章) の一覧と、読めなかった番号（理由の種類つき）。"""
    texts, failed = [], []
    for bundle_id in ids:
        if not BUNDLE_ID.match(bundle_id):
            failed.append(f"{bundle_id[:20]}（形が正しくない）")
            continue
        try:
            response = client.get_object(Bucket=bucket, Key=f"bundles/{bundle_id}.json")
            raw = response["Body"].read(MAX_BYTES + 1)
            if len(raw) > MAX_BYTES:
                raise ValueError("大きすぎる")
            texts.append((bundle_id, bundle_text(raw)))
        except Exception as error:  # noqa: BLE001（理由は種類だけを出す。本文と認証情報は出さない）
            failed.append(f"{bundle_id}（{type(error).__name__}）")
    return texts, failed
