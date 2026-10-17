"""IR重要ポイントの下書きを作る（AG-12）。

R2 の原資料束（scripts/bundle/make_ir_bundle.py が作る bundles/ir/{slug}-{決算期}-q{四半期}.json）を読み、
AG-12 を呼んで、content/ir-points/{slug}/{決算期}-q{四半期}.md（draft: true）と、決算発表の行（announcement.json。
data/auto/{slug}.json の announcements、データ定義書 5.6）と、変更案の説明（pr-body.md）を --out-dir に書く。

使い方:
    python3 scripts/draft/draft_ir.py --company advantest --fiscal-period-end 2027-03 --quarter 2 \\
        --out-dir out --ledger-dir ledger --run-id 123 [--summary FILE]

* 出力の検査と書き直しは scripts/draft/ir_point.py。転載の検査に不合格のときだけ、1回だけ書き直させる
* ログ、要約、変更案の説明には、原資料束の本文も、AIの出力の本文も出さない（CLAUDE.md 2章10）
* 同じファイルが content/ir-points/ にあれば、上書きしない

終了コード: 0 成功 / 1 失敗 / 2 設定・引数の誤り / 3 呼ばなかった（休止・予算）
"""

from __future__ import annotations

import argparse
import json
import os
import re
import sys
import time
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

import yaml

REPO_ROOT = Path(__file__).resolve().parents[2]
for sub in ("bundle", "llm", "textcheck", "draft"):
    sys.path.insert(0, str(REPO_ROOT / "scripts" / sub))

import agent_call  # noqa: E402
import draft_company  # noqa: E402
import ir_point  # noqa: E402
import make_bundle  # noqa: E402
import make_ir_bundle  # noqa: E402
import reprint  # noqa: E402

AGENT = "AG-12"
BUNDLE_SCHEMA_VERSION = make_ir_bundle.SCHEMA_VERSION
JST = ZoneInfo("Asia/Tokyo")
EXIT_OK, EXIT_FAILURE, EXIT_USAGE, EXIT_SKIPPED = 0, 1, 2, 3
DraftError = draft_company.DraftError


def parse_args(argv: list[str]) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="IR重要ポイントの下書きを作る（AG-12）")
    parser.add_argument("--company", required=True, metavar="SLUG")
    parser.add_argument("--fiscal-period-end", required=True, metavar="YYYY-MM")
    parser.add_argument("--quarter", required=True, type=int, choices=(1, 2, 3, 4))
    parser.add_argument("--out-dir", required=True, type=Path)
    parser.add_argument("--ledger-dir", required=True, type=Path)
    parser.add_argument("--run-id", required=True)
    parser.add_argument("--summary", type=Path, metavar="FILE")
    return parser.parse_args(argv)


def period_label(fiscal_period_end: str, quarter: int) -> str:
    """「2027年3月期第2四半期」の形。4（通期）は「2027年3月期」。"""
    match = re.fullmatch(r"(\d{4})-(\d{2})", fiscal_period_end)
    base = f"{match.group(1)}年{int(match.group(2))}月期" if match else fiscal_period_end
    return base if quarter == 4 else f"{base}第{quarter}四半期"


def semiconductor_segments(root: Path, slug: str) -> list[str]:
    """セグメント対応表で semiconductor（半導体関連）の区分の名前。総合メーカーでは、ここに触れさせる（CLAUDE.md 6.2）。"""
    path = root / "data" / "segments" / f"{slug}.yaml"
    try:
        data = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    except (OSError, yaml.YAMLError):
        return []
    return [s["name"] for s in data.get("segments") or [] if isinstance(s, dict) and s.get("classification") == "semiconductor"]


def check_bundle(bundle: object, slug: str, fiscal_period_end: str, quarter: int) -> dict:
    if not isinstance(bundle, dict) or bundle.get("schema_version") != BUNDLE_SCHEMA_VERSION:
        raise DraftError("原資料束の形が正しくない（schema_version）")
    if (bundle.get("company"), bundle.get("fiscal_period_end"), bundle.get("quarter")) != (slug, fiscal_period_end, quarter):
        raise DraftError("原資料束の企業・決算期・四半期が、指定と違う")
    documents = bundle.get("documents")
    if not isinstance(documents, list) or not documents or not all(isinstance(d, dict) and d.get("paragraphs") for d in documents):
        raise DraftError("原資料束に資料がない")
    return bundle


def build_task(master: dict, bundle: dict, segments: list[str]) -> str:
    task = {
        "company_name": master["name"],
        "fiscal_period": period_label(bundle["fiscal_period_end"], bundle["quarter"]),
        "quarter": bundle["quarter"],
        "semiconductor_segments": segments,
        "sources": [{"id": d["id"], "title": d["title"], "pages": d.get("pages"), "chars": d.get("chars")}
                    for d in bundle["documents"]],
    }
    return "## 入力（プログラムが渡す値）\n" + json.dumps(task, ensure_ascii=False, indent=1)


def document_text(document: dict) -> str:
    return "\n".join(p["text"] for p in document["paragraphs"] if isinstance(p, dict) and p.get("text"))


def build_materials(bundle: dict) -> str:
    """資料の区画（呼び出し層が <資料> で囲む）の中を、文書ごとに <文書 id="S1"> で分ける。"""
    return "\n".join(f'<文書 id="{d["id"]}" type="{d["type"]}">\n{document_text(d).replace("</文書>", "＜/文書＞")}\n</文書>'
                     for d in bundle["documents"])


def build_sources(master: dict, bundle: dict, today: str) -> list[dict]:
    """ファイルの sources。発行元は企業名（決算短信・決算説明資料は、会社が公表する資料）。"""
    out = []
    for d in bundle["documents"]:
        out.append({"id": d["id"], "title": f"{period_label(bundle['fiscal_period_end'], bundle['quarter'])} {d['title']}",
                    "publisher": master["name"], "url": d["url"], "published_on": bundle["announced_on"],
                    "accessed_on": today})
    return out


def build_announcement(bundle: dict, detected_at: str) -> dict:
    """data/auto の announcements の1行（データ定義書 5.6）。published_at は、発表日の0時（時刻は分からないため）。"""
    return {"fiscal_period_end": bundle["fiscal_period_end"], "quarter": bundle["quarter"],
            "announced_on": bundle["announced_on"], "detected_at": detected_at,
            "documents": [{"type": d["type"], "title": d["title"], "url": d["url"],
                           "published_at": f"{bundle['announced_on']}T00:00:00+09:00"} for d in bundle["documents"]]}


def pr_body(slug: str, bundle: dict, rel: str, cost: float, longest: int, min_run: int, first_longest: int | None,
            warnings: list[str], run_id: str) -> str:
    docs = "\n".join(f"{i}. {d['title']}（{d['url']}）" for i, d in enumerate(bundle["documents"], start=1))
    reprint_line = (f"最長の一致 {longest}字（基準 {min_run}字）" if first_longest is None
                    else f"1回目 {first_longest}字 → 書き直し後 {longest}字（基準 {min_run}字）")
    warn = "\n".join(f"- {w}" for w in warnings) or "- なし"
    return f"""## 変更の種類
- [x] IR重要ポイント

## 概要
{slug} の {period_label(bundle['fiscal_period_end'], bundle['quarter'])}（発表日 {bundle['announced_on']}）のIR重要ポイントの下書き（AG-12、実行 {run_id}）。
`{rel}` は draft: true。運営者が決算短信と見比べて確かめてから、draft を外す。
data/auto/{slug}.json の announcements に、この決算発表の行を加えた（「最新の決算は未反映」の表示に使う）。

確かめる観点
- 3項目の数値（金額、増減、期）が決算短信と一致するか
- 今期見通しが、会社の予想（修正の有無を含む）のとおりか
- 注目材料が、会社が示した材料か（株価や投資の判断の書き方がないか）
- 総合メーカーでは、半導体関連の事業区分に触れているか

## 原資料束
{docs}

## 事実確認の結果


## 確認項目
- [x] 外部の送信先を増やしていない
- [x] 訂正の表示が必要な変更ではない
- [x] AIが書いた本文には `ai_generated: true` を付けた

## AIの呼び出し
- 利用額：{cost:.2f}円
- 転載の検査：{reprint_line}
- 警告：
{warn}
"""


def run(args, env, *, now, r2_factory, client_factory, sleep, root: Path, budgets_path, operations_path, agents_dir,
        textcheck_path, summary: list[str]) -> int:
    slug, fpe, quarter = args.company, args.fiscal_period_end, args.quarter
    if not make_bundle.SLUG_PATTERN.match(slug) or not make_ir_bundle.PERIOD.match(fpe):
        raise DraftError("slug か決算期の形が正しくない", EXIT_USAGE)
    moment = now().astimezone(JST)
    today = moment.date().isoformat()
    rel = ir_point.file_path(slug, fpe, quarter)
    if (root / rel).exists():
        raise DraftError(f"{rel} が、もうある。上書きしない")
    master = draft_company.load_yaml(root / "data" / "companies" / f"{slug}.yaml", f"data/companies/{slug}.yaml")
    if not isinstance(master, dict) or master.get("slug") != slug:
        raise DraftError(f"data/companies/{slug}.yaml の形が正しくない", EXIT_USAGE)
    creds = make_bundle.read_r2_env(env)
    bundle_id = make_ir_bundle.bundle_id_of(slug, fpe, quarter)
    bundle = check_bundle(draft_company.fetch_json(creds, make_ir_bundle.object_key(bundle_id), r2_factory,
                                                   "先に make_ir_bundle.py で原資料束を作る"), slug, fpe, quarter)
    segments = semiconductor_segments(root, slug)
    source_ids = [d["id"] for d in bundle["documents"]]
    summary += [f"## IR重要ポイントの下書き {bundle_id}", "", "| 資料 | 種類 | 文字数 |", "| :--- | :--- | ---: |"]
    summary += [f"| {d['id']} | {d['title']} | {d.get('chars') or 0:,} |" for d in bundle["documents"]]

    all_rows: list[dict] = []
    client_factory = draft_company.shared_client_factory(client_factory)
    calls = dict(run_id=args.run_id, subject=bundle_id, ledger_dir=args.ledger_dir, now=now, sleep=sleep,
                 client_factory=client_factory, budgets_path=budgets_path, operations_path=operations_path,
                 agents_dir=agents_dir)
    task, materials = build_task(master, bundle, segments), build_materials(bundle)

    def cost() -> float:
        return round(sum(r["cost_jpy"] for r in all_rows), 4)

    def call(followup: str = ""):
        result = agent_call.call_agent(AGENT, task, materials, followup=followup, prior_cost_jpy=cost(), **calls)
        all_rows.extend(result.rows)
        draft_company.write_ledger(args.out_dir, all_rows)
        summary.append(f"* AIの利用額: {cost():.2f}円（呼び出し {len(all_rows)}回、状態: {result.status}）")
        if result.status in (agent_call.STATUS_SKIP_PAUSED, agent_call.STATUS_SKIP_BUDGET):
            summary.append(f"* {result.reason}")
            print(result.reason, file=sys.stderr)
            return None
        if result.status != agent_call.STATUS_OK:
            raise DraftError(result.reason)
        return result

    source_texts = [document_text(d) for d in bundle["documents"]]
    min_run = reprint.load_min_run(textcheck_path)
    result = call()
    if result is None:
        return EXIT_SKIPPED
    output = result.output
    errors, warnings = ir_point.check_output(output, source_ids)
    first_longest = None
    if not errors:
        copied, longest = ir_point.reprint_check(output, source_texts, min_run)
        if copied:
            first_longest = longest
            fields = {key: output[key]["text"] for key, _, _ in ir_point.FIELDS}
            matches = {k: v for k, v in reprint.find_matches(source_texts, fields, min_run).items() if v}
            summary.append(f"* 転載の検査に不合格（{', '.join(sorted(matches))}）。AG-12 に1回だけ書き直させる")
            request = draft_company.build_rewrite_request(output, matches, min_run).replace(
                "出典の番号は [S1] だけを使う。", "本文に出典の番号を書かない（source_ids に書く）。")
            rewritten = call(request)
            if rewritten is None:
                return EXIT_SKIPPED
            output = rewritten.output
            errors, warnings = ir_point.check_output(output, source_ids)
        if not errors:
            copied, longest = ir_point.reprint_check(output, source_texts, min_run)
            errors += copied
    if errors:
        summary += ["* 検査に不合格（ファイルは書かない）："] + [f"  * {e}" for e in errors]
        raise DraftError("検査に不合格のため、ファイルを書かない: " + " / ".join(errors))
    text = ir_point.render(output, {"company": slug, "fiscal_period_end": fpe, "quarter": quarter,
                                    "announced_on": bundle["announced_on"], "published_at": today,
                                    "sources": build_sources(master, bundle, today)})
    front = yaml.safe_load(text.split("---\n", 2)[1])
    file_errors = ir_point.check_file(front)
    if file_errors:
        raise DraftError("ファイルの形式に合わない: " + " / ".join(file_errors))
    summary += [f"* 転載の検査: 最長の一致 {longest}字（基準 {min_run}字）", f"* 警告: {len(warnings)}件"]
    draft_company.write_text(args.out_dir / rel, text)
    draft_company.write_text(args.out_dir / "announcement.json",
                             json.dumps(build_announcement(bundle, moment.isoformat(timespec="seconds")), ensure_ascii=False, indent=1) + "\n")
    draft_company.write_text(args.out_dir / "pr-body.md",
                             pr_body(slug, bundle, rel, cost(), longest, min_run, first_longest, warnings, args.run_id))
    print(f"下書きを作った: {rel}（警告 {len(warnings)}件、利用額 {cost():.2f}円）")
    return EXIT_OK


def main(argv: list[str] | None = None, *, env=None, now=lambda: datetime.now(JST), r2_factory=make_bundle.make_r2_client,
         client_factory=None, sleep=None, root: Path = REPO_ROOT, budgets_path: Path = agent_call.BUDGETS_PATH,
         operations_path: Path = agent_call.OPERATIONS_PATH, agents_dir: Path = agent_call.AGENTS_DIR,
         textcheck_path: Path = reprint.CONFIG_PATH) -> int:
    args = parse_args(sys.argv[1:] if argv is None else argv)
    env = os.environ if env is None else env
    secrets = [(env.get(n) or "").strip() for n in (make_bundle.ENV_ACCOUNT, make_bundle.ENV_ACCESS_KEY,
                                                      make_bundle.ENV_SECRET_KEY)]
    summary: list[str] = []
    code = EXIT_FAILURE
    try:
        code = run(args, env, now=now, r2_factory=r2_factory, root=root, budgets_path=budgets_path,
                   operations_path=operations_path, agents_dir=agents_dir, textcheck_path=textcheck_path,
                   summary=summary, client_factory=client_factory or (lambda: agent_call.anthropic.Anthropic()),
                   sleep=sleep or time.sleep)
    except (DraftError, make_bundle.BundleError) as error:
        message = make_bundle.mask_secrets(str(error), secrets)
        print(f"error: {message}", file=sys.stderr)
        code = error.exit_code
        summary += ["", f"* 失敗: {message[:500]}"]
    except agent_call.LlmError as error:
        print(f"error: {error}", file=sys.stderr)
        code = EXIT_FAILURE
    except Exception as error:  # noqa: BLE001 - 想定外の例外は、本文と認証情報を含みうるため、種類だけ示す
        print(f"error: 想定外のエラー（{type(error).__name__}）", file=sys.stderr)
        code = EXIT_FAILURE
    try:
        draft_company.write_summary(args.summary, summary)
    except OSError:
        print("error: 要約を書けなかった", file=sys.stderr)
    return code


if __name__ == "__main__":
    sys.exit(main())
