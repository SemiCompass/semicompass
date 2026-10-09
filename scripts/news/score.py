"""ニュース候補の点付けと並べ替え、Issue の本文づくり（J02の後半。運用ルール書 3.2、3.3）。

使い方:
    python3 scripts/news/score.py --candidates candidates.json --out-dir DIR --ledger-dir DIR --run-id ID [--dry-run]

* AG-10 を1回呼び（scripts/llm/ の呼び出し層だけを使う）、候補ごとの点と種別を受け取る。候補の見出しは「資料」の区画に入れる。
* 情報源の確かさの点は、AG-10 の reporting から、このプログラムが付ける（primary＝3、press＝2、speculative＝1）。
* 並べ方：半導体に関係する候補だけ。優先の基準に当たるものを先に、次に合計点（12点満点）の高い順、同点は公表日の新しい順。
  観測報道（speculative）は、原則として扱わないので、別の欄に分ける。1週間の同じ種別の上限（weekly_max_per_category）に
  達した種別は、印を付けて、下に下げる。
* 出力：DIR/scored.json（機械が読む）、DIR/issue-body.md（Issue の本文）、DIR/ledger/{yyyy-mm}.jsonl（AIの利用額）。
* 元記事の本文は持たない。Issue に出るのは、見出し、発信元、URL、公表日、点、理由だけ。
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from datetime import date, datetime, timedelta
from pathlib import Path
from zoneinfo import ZoneInfo

import yaml

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "scripts" / "llm"))
import agent_call  # noqa: E402

JST = ZoneInfo("Asia/Tokyo")
AGENT = "AG-10"
RELIABILITY = {"primary": 3, "press": 2, "speculative": 1}
CATEGORY_LABEL = {"investment": "投資", "policy": "政策・規制", "m_and_a": "M&A", "earnings": "決算", "technology": "技術", "supply_demand": "供給・需要"}
EXIT_OK, EXIT_SKIPPED, EXIT_FAILED = 0, 3, 1


def listed_companies(companies_dir: Path) -> dict[str, str]:
    """掲載企業の slug → 表示名。ファイル名が slug。名前は front matter の name があれば使い、なければ slug。"""
    result: dict[str, str] = {}
    if companies_dir.is_dir():
        for path in sorted(companies_dir.glob("*.md")):
            result[path.stem] = path.stem
    return result


def week_counts(content_dir: Path, today: date) -> dict[str, int]:
    """今週（月曜から）に公開した記事の、種別ごとの件数。"""
    monday = today - timedelta(days=today.weekday())
    counts: dict[str, int] = {}
    if content_dir.is_dir():
        for path in content_dir.glob("*.md"):
            m = re.search(r"^---\n(.*?)\n---", path.read_text(encoding="utf-8"), re.S)
            try:
                front = (yaml.safe_load(m[1]) if m else None) or {}
            except yaml.YAMLError:
                continue
            published = str(front.get("published_at", ""))[:10]
            if front.get("draft") or not published or date.fromisoformat(published) < monday:
                continue
            counts[front.get("category", "")] = counts.get(front.get("category", ""), 0) + 1
    return counts


def build_inputs(candidates: list[dict], config: dict, companies: dict[str, str]) -> tuple[str, str]:
    task_input = {
        "candidates": [c["id"] for c in candidates],
        "listed_company_slugs": sorted(companies),
        "priority_rules": config["priority_rules"],
    }
    task = "## 入力（プログラムが渡す値）\n" + json.dumps(task_input, ensure_ascii=False, indent=1)
    lines = []
    for c in candidates:
        lines.append(f'<候補 id="{c["id"]}" source_kind="{c["kind"]}" publisher="{c["publisher"]}" published_on="{c["published_on"]}">{c["title"]}</候補>')
    return task, "\n".join(lines)


def merge(candidates: list[dict], output: dict) -> list[dict]:
    """AG-10 の出力を、候補に合わせる。返ってこなかった候補は、除く（点を作らない）。重複した id は最初のものだけ。"""
    by_id = {c["id"]: c for c in candidates}
    merged, used = [], set()
    for item in output["items"]:
        c = by_id.get(item["id"])
        if c is None or item["id"] in used:
            continue
        used.add(item["id"])
        reporting = "primary" if c["kind"] in ("company", "government", "association") else item["reporting"]
        score = {"impact": item["impact"], "supply_chain": item["supply_chain"], "novelty": item["novelty"], "reliability": RELIABILITY[reporting]}
        merged.append({**c, **{k: item[k] for k in ("semiconductor_related", "category", "overseas", "priority_hit", "listed_companies", "reason")},
                       "reporting": reporting, "score": score, "total": sum(score.values())})
    return merged


def rank(scored: list[dict], config: dict, counts: dict[str, int]) -> dict:
    related = [s for s in scored if s["semiconductor_related"]]
    observed = [s for s in related if s["reporting"] == "speculative"]
    regular = [s for s in related if s["reporting"] != "speculative"]
    cap = config["weekly_max_per_category"]
    for s in regular:
        s["category_full"] = counts.get(s["category"], 0) >= cap
    regular.sort(key=lambda s: (s["category_full"], not s["priority_hit"], -s["total"], -date.fromisoformat(s["published_on"]).toordinal(), s["id"]))
    observed.sort(key=lambda s: (-s["total"], s["id"]))
    return {"ranked": regular, "observed": observed, "excluded": len(scored) - len(related)}


def md_escape(text: str) -> str:
    return re.sub(r"[|`\r\n]+", " ", text).strip()


def issue_body(result: dict, config: dict, collected_on: str, counts: dict[str, int], limit: int) -> str:
    out = [f"## ニュース候補（{collected_on}）", "",
           f"上位 {limit} 件が、1日の上限（{config['daily_limit']}件）を踏まえた目安。解説を書く候補は、下の `/draft` で指定する。", ""]
    if counts:
        out.append("今週の公開済み：" + "、".join(f"{CATEGORY_LABEL.get(k, k)} {v}件" for k, v in sorted(counts.items())))
        out.append("")
    out += ["| 選ぶ | id | 種別 | 合計 | 影響/波及/新しさ/確かさ | 見出し（発信元・公表日） | 理由 |", "| :--- | :--- | :--- | ---: | :--- | :--- | :--- |"]

    def row(s: dict, mark: str) -> str:
        sc = s["score"]
        flags = ("★" if s["priority_hit"] else "") + ("海外" if s["overseas"] else "") + ("（週の上限）" if s.get("category_full") else "")
        return (f"| {mark} | {s['id']} | {CATEGORY_LABEL[s['category']]}{flags} | {s['total']} | {sc['impact']}/{sc['supply_chain']}/{sc['novelty']}/{sc['reliability']} | "
                f"[{md_escape(s['title'])}]({s['url']})（{md_escape(s['publisher'])}、{s['published_on']}） | {md_escape(s['reason'])} |")

    for i, s in enumerate(result["ranked"]):
        out.append(row(s, "☑ 目安" if i < limit and not s.get("category_full") else "☐"))
    out.append("")
    if result["observed"]:
        out += ["### 観測報道（原則として扱わない）", ""]
        out += [f"* {s['id']} [{md_escape(s['title'])}]({s['url']})（{md_escape(s['publisher'])}、{s['published_on']}）" for s in result["observed"]]
        out.append("")
    out += ["### 解説を書くとき", "", "コメントに `/draft c01 c03` のように、id を書く（運営者だけ）。★は種別ごとの優先の基準に当たるもの。",
            f"半導体に関係しないと判断した候補は {result['excluded']}件（表に出さない）。", ""]
    return "\n".join(out)


def main(argv=None, *, client_factory=None, now=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    parser.add_argument("--candidates", required=True, type=Path)
    parser.add_argument("--out-dir", required=True, type=Path)
    parser.add_argument("--ledger-dir", required=True, type=Path)
    parser.add_argument("--run-id", required=True)
    parser.add_argument("--config", type=Path, default=ROOT / "config" / "news.yaml")
    parser.add_argument("--content-dir", type=Path, default=ROOT / "content" / "news")
    parser.add_argument("--companies-dir", type=Path, default=ROOT / "content" / "companies")
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args(argv)
    config = yaml.safe_load(args.config.read_text(encoding="utf-8"))
    data = json.loads(args.candidates.read_text(encoding="utf-8"))
    candidates = data["candidates"]
    args.out_dir.mkdir(parents=True, exist_ok=True)
    if not candidates:
        (args.out_dir / "issue-body.md").write_text(f"## ニュース候補（{data['collected_on']}）\n\n新しい候補はなかった。取得に失敗した情報源: {[f['source'] for f in data['failed']] or 'なし'}\n", encoding="utf-8")
        print("候補が0件のため、AIは呼ばない")
        return EXIT_OK
    companies = listed_companies(args.companies_dir)
    task, materials = build_inputs(candidates, config, companies)
    if args.dry_run:
        print(f"dry-run: 候補 {len(candidates)}件。AG-10 は呼ばない（入力 {len(task) + len(materials):,}字）")
        return EXIT_OK
    kwargs = {"client_factory": client_factory} if client_factory else {}
    if now:
        kwargs["now"] = now
    result = agent_call.call_agent(AGENT, task, materials, run_id=args.run_id, subject="news-candidates",
                                   ledger_dir=args.ledger_dir, max_tokens=8000, **kwargs)
    ledger_out = args.out_dir / "ledger"
    ledger_out.mkdir(exist_ok=True)
    for row in result.rows:
        with (ledger_out / f"{row['at'][:7]}.jsonl").open("a", encoding="utf-8") as f:
            f.write(json.dumps(row, ensure_ascii=False) + "\n")
    if result.status != agent_call.STATUS_OK or result.output is None:
        print(f"AG-10 の結果: {result.status}（{result.reason}）")
        return EXIT_SKIPPED if result.status.startswith("skipped") else EXIT_FAILED
    today = datetime.fromisoformat(data["collected_on"]).date()
    counts = week_counts(args.content_dir, today)
    ranked = rank(merge(candidates, result.output), config, counts)
    limit = config["daily_limit"] * 3  # 候補の目安は、1日の上限の3倍まで（運営者が選ぶ）
    (args.out_dir / "scored.json").write_text(json.dumps(ranked, ensure_ascii=False, indent=1) + "\n", encoding="utf-8")
    (args.out_dir / "issue-body.md").write_text(issue_body(ranked, config, data["collected_on"], counts, limit), encoding="utf-8")
    print(f"点付け: 候補 {len(candidates)}件 → 表 {len(ranked['ranked'])}件、観測報道 {len(ranked['observed'])}件、AIの利用額 {result.cost_jpy:.2f}円")
    return EXIT_OK


if __name__ == "__main__":
    sys.exit(main())
