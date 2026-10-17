"""AG-12（IR分析エージェント）の出力を検査し、IR重要ポイントのファイル（content/ir-points/）に書き直す部品。

* 出力の形式は schemas/agents/AG-12.output.schema.json（データ定義書 9.5）。ファイルの形式は
  schemas/content/ir-point.schema.json（データ定義書 6.3）。本文は「## 業績の要点」「## 今期見通し」「## 注目材料」の3つの見出し
* 出典の番号は、出力の source_ids から、各項目の文の後に [S1] の形で付ける（AG-12 は本文に番号を書かない）
* 検査は、本文を含まない理由の一覧を返す（Actionsのログと変更案は公開のため。CLAUDE.md 2章10）
* 原資料束の取得、AIの呼び出し、変更案の作成は、この部品の外（draft_ir.py）で行う
"""

from __future__ import annotations

import json
import re
import sys
from pathlib import Path

import yaml
from jsonschema import Draft202012Validator

REPO_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO_ROOT / "scripts" / "textcheck"))

import reprint  # noqa: E402

OUTPUT_SCHEMA = REPO_ROOT / "schemas" / "agents" / "AG-12.output.schema.json"
FILE_SCHEMA = REPO_ROOT / "schemas" / "content" / "ir-point.schema.json"

# (出力の項目, 本文の見出し, 字数の上限)。字数の上限は要求定義書 FR-307
FIELDS = (
    ("performance_summary", "業績の要点", 100),
    ("outlook", "今期見通し", 80),
    ("highlights", "注目材料", 70),
)

# CLAUDE.md 5.2 の不合格になる言葉と、IR重要ポイントで使わない書き方（CLAUDE.md 6.2）
PROHIBITED = (
    "買い", "売り", "買い時", "狙い目", "推奨銘柄", "注目銘柄", "本命", "出遅れ", "割安", "割高", "急騰", "爆上げ",
    "必ず上がる", "確実に", "儲かる", "テンバガー", "衝撃", "激震", "暴落", "緊急", "危機", "ヤバい", "知らないと損",
    "株価", "買い材料", "好材料", "悪材料", "サプライズ",
)
# 「売り上げ」「売上」は、投資の言葉ではない
ALLOWED_AROUND = ("売上", "売り上げ", "売り手", "売り場")
WARNINGS = (
    "革新的", "画期的", "次世代", "最先端", "シームレス", "飛躍的", "圧倒的", "鍵を握る", "重要な役割を果たしている",
    "注目を集めている", "今後の動向が注目される", "と言えるでしょう",
)
EMOJI = re.compile("[\U0001F300-\U0001FAFF☀-➿]")
MARKUP = re.compile(r"\[S[0-9]+\]|^#|\*\*|`", re.MULTILINE)


def load_output_schema(path: Path = OUTPUT_SCHEMA) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def file_path(slug: str, fiscal_period_end: str, quarter: int) -> str:
    """content/ir-points/{slug}/{fiscal_period_end}-q{quarter}.md（データ定義書 6.3）"""
    return f"content/ir-points/{slug}/{fiscal_period_end}-q{quarter}.md"


def _prohibited_in(text: str) -> list[str]:
    masked = text
    for ok in ALLOWED_AROUND:
        masked = masked.replace(ok, "＿" * len(ok))
    return sorted({w for w in PROHIBITED if w in masked})


def check_output(output: dict, source_ids: list[str], schema: dict | None = None) -> tuple[list[str], list[str]]:
    """出力の検査。(不合格の理由, 警告) を返す。理由には本文を含めない（言葉の一覧のような短い語だけ）。"""
    errors: list[str] = []
    warnings: list[str] = []
    validator = Draft202012Validator(schema or load_output_schema())
    problems = sorted(validator.iter_errors(output), key=lambda e: list(e.absolute_path))
    if problems:
        for e in problems[:5]:
            where = "/".join(str(p) for p in e.absolute_path) or "(全体)"
            errors.append(f"出力の形式に合わない：{where}（{e.validator}）")
        return errors, warnings
    known = set(source_ids)
    for key, heading, limit in FIELDS:
        item = output[key]
        text = item["text"]
        outside = [s for s in item["source_ids"] if s not in known]
        if outside:
            errors.append(f"{key} の source_ids に、渡した資料にない番号がある（{', '.join(sorted(outside))}）")
        if len(text) > limit:
            errors.append(f"{key}（{heading}）が {len(text)}字で、上限（{limit}字）を超えている")
        bad = _prohibited_in(text)
        if bad:
            errors.append(f"{key} に、使わない言葉がある（{'、'.join(bad)}）")
        if EMOJI.search(text):
            errors.append(f"{key} に、絵文字がある")
        if MARKUP.search(text):
            errors.append(f"{key} に、出典の番号・見出し・Markdownの装飾がある（プログラムが付ける）")
        warn = sorted({w for w in WARNINGS if w in text})
        if warn:
            warnings.append(f"{key} に、警告になる言葉がある（{'、'.join(warn)}）")
    return errors, warnings


def reprint_check(output: dict, source_texts: list[str], min_run: int) -> tuple[list[str], int]:
    """転載の検査（scripts/textcheck/reprint.py）。(不合格の理由, 最長一致の長さ) を返す。"""
    fields = {key: output[key]["text"] for key, _, _ in FIELDS}
    results = reprint.check_reprint(source_texts, fields, min_run)
    errors = [f"転載の検査に不合格：{r.field} で、{r.longest}字（基準 {min_run}字）連続して同じ"
              for r in reprint.failures(results, min_run)]
    return errors, reprint.longest_overall(results)


def render(output: dict, meta: dict) -> str:
    """IR重要ポイントのファイル（先頭の項目と本文）を作る。

    meta：company、fiscal_period_end、quarter、announced_on、published_at、sources（ファイルの sources の形の一覧）。
    下書きは draft: true、ai_generated: true にする（運営者が決算短信と見比べてから外す）。
    """
    front = {
        "company": meta["company"],
        "fiscal_period_end": meta["fiscal_period_end"],
        "quarter": meta["quarter"],
        "announced_on": meta["announced_on"],
        "uses_quarterly_figures": bool(output["uses_quarterly_figures"]),
        "published_at": meta["published_at"],
        "draft": True,
        "ai_generated": True,
        "sources": meta["sources"],
    }
    parts = []
    for key, heading, _ in FIELDS:
        item = output[key]
        cites = "".join(f"[{s}]" for s in item["source_ids"])
        parts.append(f"## {heading}\n\n{item['text'].strip()}{cites}\n")
    head = yaml.safe_dump(front, allow_unicode=True, sort_keys=False)
    return "---\n" + head + "---\n\n" + "\n".join(parts)


def check_file(front: dict, schema_path: Path = FILE_SCHEMA) -> list[str]:
    """ファイルの先頭の項目を、schemas/content/ir-point.schema.json で検査する。"""
    schema = json.loads(schema_path.read_text(encoding="utf-8"))
    return [f"ファイルの形式に合わない：{'/'.join(str(p) for p in e.absolute_path) or '(全体)'}（{e.validator}）"
            for e in Draft202012Validator(schema).iter_errors(front)]
