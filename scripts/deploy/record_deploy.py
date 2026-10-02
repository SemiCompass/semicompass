"""公開の記録（データ定義書10.6 deploys）の1行を作る雛形。

wranglerの出力ファイル（WRANGLER_OUTPUT_FILE_PATH、ND-JSON）から、`wrangler deploy` の
版のID（version_id）を読み、公開の記録を1行のJSONとして標準出力に出す。

この処理は記録を作るだけである。`ops-log`ブランチへの書き込みは、別の処理が行う。
入力は、版のID、コミット、時刻だけにする（資料の本文、秘密の情報を含めない）。
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

TRIGGERS = ("merge", "j07", "rollback")
POST_CHECKS = ("passed", "failed")
ENVS = ("production",)
COMMIT_PATTERN = re.compile(r"^[0-9a-f]{40}$")


def read_version_id(output_file: Path) -> str:
    """出力ファイルの最後の `deploy` の項目から、版のIDを返す。"""
    version_id = None
    for line in output_file.read_text(encoding="utf-8").splitlines():
        if not line.strip():
            continue
        entry = json.loads(line)
        if entry.get("type") == "deploy" and entry.get("version_id"):
            version_id = entry["version_id"]
    if version_id is None:
        raise ValueError(f"{output_file} に deploy の版のIDがない")
    return version_id


def build_record(
    *,
    at: str,
    env: str,
    commit: str,
    deployment_id: str,
    trigger: str,
    post_check: str | None = None,
    rolled_back_to: str | None = None,
) -> dict:
    """データ定義書10.6の項目の順で、記録を作る。指定のない任意の項目は書かない。"""
    if env not in ENVS:
        raise ValueError(f"env は {ENVS} のいずれか: {env}")
    if not COMMIT_PATTERN.match(commit):
        raise ValueError("commit は40桁の小文字の16進数")
    if trigger not in TRIGGERS:
        raise ValueError(f"trigger は {TRIGGERS} のいずれか: {trigger}")
    if post_check is not None and post_check not in POST_CHECKS:
        raise ValueError(f"post_check は {POST_CHECKS} のいずれか: {post_check}")
    if trigger == "rollback" and rolled_back_to is None:
        raise ValueError("trigger が rollback のときは rolled_back_to が必要")
    record = {
        "at": at,
        "env": env,
        "commit": commit,
        "deployment_id": deployment_id,
        "trigger": trigger,
    }
    if post_check is not None:
        record["post_check"] = post_check
    if rolled_back_to is not None:
        record["rolled_back_to"] = rolled_back_to
    return record


def now_jst() -> str:
    """日本時間の現在の日時（時差 +09:00 付き）。"""
    return datetime.now(ZoneInfo("Asia/Tokyo")).replace(microsecond=0).isoformat()


def parse_args(argv: list[str]) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output-file", type=Path, help="wranglerの出力ファイル（ND-JSON）")
    parser.add_argument("--deployment-id", help="版のID。出力ファイルがない場合（rollbackなど）に指定する")
    parser.add_argument("--commit", required=True)
    parser.add_argument("--trigger", required=True, choices=TRIGGERS)
    parser.add_argument("--env", default="production", choices=ENVS)
    parser.add_argument("--post-check", choices=POST_CHECKS)
    parser.add_argument("--rolled-back-to")
    parser.add_argument("--at", help="日時。指定がなければ現在の日本時間")
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(sys.argv[1:] if argv is None else argv)
    try:
        if args.deployment_id:
            deployment_id = args.deployment_id
        elif args.output_file:
            deployment_id = read_version_id(args.output_file)
        else:
            raise ValueError("--output-file か --deployment-id が必要")
        record = build_record(
            at=args.at or now_jst(),
            env=args.env,
            commit=args.commit,
            deployment_id=deployment_id,
            trigger=args.trigger,
            post_check=args.post_check,
            rolled_back_to=args.rolled_back_to,
        )
    except (ValueError, OSError, json.JSONDecodeError) as error:
        print(f"error: {error}", file=sys.stderr)
        return 1
    print(json.dumps(record, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    sys.exit(main())
