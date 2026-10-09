"""ニュース解説の下書き（J03。運用ルール書 3.4、3.5）。

使い方:
    python3 scripts/news/draft_news.py --scored FILE --id c11 [--url URL] --out-dir DIR --ledger-dir DIR --run-id ID [--summary FILE]

流れ:
  1. 候補（scored.json の id）と、元記事のURLを決める。--url がなければ、候補が一次情報（企業・官公庁・業界団体）のとき、候補のURLを使う。
     報道の候補で --url がないときは、作らない（運用ルール書 3.1：一次情報を優先する。報道の本文は読まない）
  2. 元記事を取得する（fetch_source。本文は、AIに渡す資料としてだけ使い、保存しない）
  3. AG-11 が下書きを作る。形式、出典の番号、企業・工程の一覧、転載（30字以上の連続一致）を検査し、不合格なら1回だけ書き直させる
  4. AG-13 が校閲する。error があれば、AG-11 に1回だけ書き直させ、もう一度校閲する
  5. content/news/{yyyy}-{mm}-{slug}.md を組み立て、スキーマと validate_data.py の検査にかける
     校閲で error が残ったときは、draft: true にして作る（取り込んでも公開されない）
出力: DIR/content/news/*.md、DIR/pr-body.md、DIR/ledger/{yyyy-mm}.jsonl
終了コード: 0 作った／3 休止中か予算の上限で呼ばなかった／2 入力の誤り（取得できない、報道でURLなし、など）／1 失敗
本文の資料と、AIの出力の生の文字列は、ログ、要約、例外に出さない。
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

import yaml

ROOT = Path(__file__).resolve().parents[2]
for sub in ("llm", "textcheck", "validate", "edinet", "news", "draft"):
    sys.path.insert(0, str(ROOT / "scripts" / sub))
import agent_call  # noqa: E402
import fetch_source  # noqa: E402
import reprint  # noqa: E402
import validate_data  # noqa: E402

JST = ZoneInfo("Asia/Tokyo")
EXIT_OK, EXIT_FAILED, EXIT_INPUT, EXIT_SKIPPED = 0, 1, 2, 3
SITE = "https://semicompass.com"
HEADINGS = validate_data.NEWS_HEADINGS
CITATION = re.compile(r"\[S[0-9]+\]")
ID = re.compile(r"^c[0-9]{2,3}$")
PRIMARY_KINDS = ("company", "government", "association")
X_URL_LENGTH = validate_data.X_URL_LENGTH


def load_candidate(scored: dict, cid: str) -> dict | None:
    return next((c for c in [*scored.get("ranked", []), *scored.get("observed", [])] if c.get("id") == cid), None)


def listed_companies(root: Path) -> list[dict]:
    result = []
    for path in sorted((root / "data" / "companies").glob("*.yaml")):
        data = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
        slug = data.get("slug") or path.stem
        names = data.get("short_names") or [data.get("name", slug)]
        result.append({"slug": slug, "name": names[0]})
    return result


def selectable_processes(root: Path) -> list[dict]:
    supply = yaml.safe_load((root / "data" / "supply-chain.yaml").read_text(encoding="utf-8"))
    return [{"slug": p["slug"], "name": p.get("name", p["slug"])} for p in supply.get("processes") or []]


def build_task(c: dict, url: str, today: str, companies: list[dict], processes: list[dict]) -> str:
    value = {"candidate_headline": c["title"], "candidate_published_on": c["published_on"], "category": c["category"],
             "overseas": c["overseas"], "source_url": url, "today": today,
             "selectable_companies": companies, "selectable_processes": processes}
    return "## 入力（プログラムが渡す値）\n" + json.dumps(value, ensure_ascii=False, indent=1)


def build_materials(doc: dict) -> str:
    return f"【S1 見出し】{doc['title']}\n【S1 URL】{doc['url']}\n【S1 本文】\n{doc['text']}"


def body_of(output: dict) -> str:
    return "\n\n".join(f"## {h}\n\n{output[k].strip()}" for h, k in zip(HEADINGS, ("what_happened", "why_important", "position"))) + "\n"


def body_chars(output: dict) -> int:
    return validate_data.count_characters([output[k] for k in ("what_happened", "why_important", "position")])


def fields_of(output: dict) -> dict[str, str]:
    return {k: output[k] for k in ("title", "description", "what_happened", "why_important", "position", "x_text")}


def check_output(output: dict, c: dict, companies: list[dict], processes: list[dict], source_text: str, min_run: int):
    """(不合格の理由（本文を含まない）、転載の検査の結果)。"""
    errors: list[str] = []
    for name in ("what_happened", "why_important", "position"):
        bad = sorted({m for m in CITATION.findall(output[name]) if m != "[S1]"})
        if bad:
            errors.append(f"{name} に、[S1] 以外の出典の番号がある")
    if not any("[S1]" in output[n] for n in ("what_happened", "why_important", "position")):
        errors.append("本文に、出典の番号 [S1] がない")
    if any(CITATION.search(output[n]) for n in ("title", "description", "x_text")):
        errors.append("title、description、x_text に、出典の番号がある（本文だけに付ける）")
    if set(output["companies"]) - {x["slug"] for x in companies}:
        errors.append("companies に、渡した一覧にない slug がある")
    if set(output["processes"]) - {x["slug"] for x in processes}:
        errors.append("processes に、渡した一覧にない slug がある")
    if c["overseas"] and not output["companies"]:
        errors.append("海外の出来事なのに、companies が空である（関係する日本企業を1社以上選ぶ）")
    if output["x_text"].count("#") > 2 or "http" in output["x_text"]:
        errors.append("x_text に、URLがある、またはハッシュタグが3つ以上ある")
    results = reprint.check_reprint([source_text], fields_of(output), min_run)
    for r in reprint.failures(results, min_run):
        errors.append(f"転載の検査に不合格：{r.field} で、{r.longest}字（基準 {min_run}字）連続して同じ")
    return errors, results


def rewrite_request(output: dict, problems: list[str], extra: str = "") -> str:
    return ("## 書き直しの依頼\n前回の下書きに、次の問題がある。直して、同じ形式で全体を返す。資料にない事実を足さない。\n"
            + "\n".join(f"* {p}" for p in problems) + (f"\n{extra}" if extra else "")
            + f"\n<前回の出力>\n{json.dumps(output, ensure_ascii=False)}\n</前回の出力>")


def front_matter(c: dict, output: dict, url: str, today: str, unresolved: bool) -> dict:
    front = {
        "title": output["title"], "description": output["description"], "published_at": today,
        "draft": unresolved, "ai_generated": True, "category": c["category"],
        "source_article": {"title": output["source_title"], "publisher": output["source_publisher"], "url": url,
                           "published_on": output["source_published_on"], "reporting": output["reporting"]},
        "score": {**c["score"], "reliability": {"primary": 3, "press": 2, "speculative": 1}[output["reporting"]]},
        "overseas": c["overseas"],
        "tags": {"companies": output["companies"], "processes": output["processes"], "themes": []},
    }
    if output["reporting"] == "speculative":
        front["score"]["reliability"] = min(front["score"]["reliability"], 1)
    if output["unlisted_companies"]:
        front["tags"]["unlisted_companies"] = [{"name": n} for n in output["unlisted_companies"]]
    return front


def x_post(output: dict, page_url: str) -> str:
    return f"{output['x_text'].strip()} {page_url}"


def render(front: dict, body: str) -> str:
    return "---\n" + yaml.safe_dump(front, allow_unicode=True, sort_keys=False, width=1000) + "---\n\n" + body


def validate_news(rel: str, front: dict, body: str, root: Path) -> tuple[list[str], list]:
    schemas = validate_data.SchemaSet(root)
    problems = schemas.errors("news", front, rel)
    companies = {}
    for path in (root / "data" / "companies").glob("*.yaml"):
        companies[f"data/companies/{path.name}"] = yaml.safe_load(path.read_text(encoding="utf-8"))
    supply = yaml.safe_load((root / "data" / "supply-chain.yaml").read_text(encoding="utf-8"))
    problems += validate_data.check_news({rel: (front, body)}, companies, supply)
    return ([f"{p.file}: {p.path or '(全体)'}: [{p.rule}] {p.message[:120]}" for p in problems if p.severity == "error"],
            [p for p in problems if p.severity == "warning"])


def pr_body(c: dict, front: dict, output: dict, issues: list[dict], unresolved: bool, warnings: list, cost: float, run_id: str, longest: int, min_run: int) -> str:
    src = front["source_article"]
    lines = [f"## ニュース解説の下書き（{c['id']}）", "",
             f"* 候補：{c['title']}（{c['publisher']}、{c['published_on']}）",
             f"* 元記事（出典）：[{src['title']}]({src['url']})（{src['publisher']}、{src['published_on']}、区分 {src['reporting']}）",
             f"* 種別：{c['category']}　海外：{'はい' if c['overseas'] else 'いいえ'}　点：{front['score']}",
             f"* 本文：{body_chars(output)}字　転載の検査：最長 {longest}字連続（基準 {min_run}字）　AIの利用額：{cost:.2f}円", ""]
    if unresolved:
        lines += ["### ⚠ 校閲（AG-13）の指摘が残っている（`draft: true` のため、取り込んでも公開されない）", ""]
    errors = [i for i in issues if i["severity"] == "error"]
    if errors or issues:
        lines += ["| 部分 | 区分 | 重さ | 指摘 |", "| :--- | :--- | :--- | :--- |"]
        lines += [f"| {i['part']} | {i['kind']} | {i['severity']} | {i['note']} |" for i in issues]
        lines.append("")
    else:
        lines += ["校閲（AG-13）の指摘：なし", ""]
    if output["uncertain"]:
        lines += ["### AG-11 が、確かでない・言い方が分かれるとした点", ""] + [f"* {u}" for u in output["uncertain"]] + [""]
    if warnings:
        lines += ["### 検査の警告", ""] + [f"* {w.file}: [{w.rule}] {w.message[:120]}" for w in warnings] + [""]
    lines += ["### 取り込む前に、運営者が確かめること", "",
              "- [ ] 元記事を開き、数値・日付・固有名詞が、下書きと合っている",
              "- [ ] 元記事の見出し、発信元、公表日が、`source_article` と合っている",
              "- [ ] 企業・工程のタグが、元記事から読み取れる関わりだけである",
              "- [ ] 評価・見通し・あおる言葉がない",
              "- [ ] 海外の出来事なら、日本企業への影響が書かれている",
              "- [ ] `draft` の値（校閲の指摘が残っているときは `true`。直したら `false` にする）", "",
              "AIの校閲（AG-13）は、元記事との照合を補助するもので、運営者の確認の代わりではない。",
              f"実行 {run_id}"]
    return "\n".join(lines) + "\n"


def write_text(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")


def write_ledger(out_dir: Path, rows: list[dict]) -> None:
    by_month: dict[str, list[dict]] = {}
    for row in rows:
        by_month.setdefault(row["at"][:7], []).append(row)
    for month, items in by_month.items():
        write_text(out_dir / "ledger" / f"{month}.jsonl", "".join(json.dumps(r, ensure_ascii=False, sort_keys=True) + "\n" for r in items))


def run(args, *, now, client_factory, fetcher, root: Path, budgets_path, operations_path, agents_dir, textcheck_path, summary: list[str]) -> int:
    if not ID.match(args.id):
        summary.append("id の形が正しくない")
        return EXIT_INPUT
    scored = json.loads(args.scored.read_text(encoding="utf-8"))
    c = load_candidate(scored, args.id)
    if c is None:
        summary.append(f"候補 {args.id} が、点付けの結果にない")
        return EXIT_INPUT
    url = args.url or (c["url"] if c["kind"] in PRIMARY_KINDS else None)
    if not url:
        summary.append(f"{args.id} は報道の候補である。一次情報（企業・官公庁・業界団体の発表）のURLを、`/draft {args.id} https://…` の形で指定する")
        return EXIT_INPUT
    try:
        doc = fetcher(url)
    except fetch_source.FetchError as error:
        summary.append(f"元記事を取得できなかった：{error}。別のURL（一次情報）を指定するか、取得できる形で用意する")
        return EXIT_INPUT
    today = now().date().isoformat()
    companies, processes = listed_companies(root), selectable_processes(root)
    task, materials = build_task(c, url, today, companies, processes), build_materials(doc)
    min_run = reprint.load_min_run(textcheck_path)
    rows: list[dict] = []
    get_client = shared(client_factory)
    common = dict(run_id=args.run_id, subject=f"news-{args.id}", ledger_dir=args.ledger_dir, now=now, client_factory=get_client,
                  budgets_path=budgets_path, operations_path=operations_path, agents_dir=agents_dir)

    def cost() -> float:
        return round(sum(r["cost_jpy"] for r in rows), 4)

    def call(agent: str, t: str, followup: str = ""):
        result = agent_call.call_agent(agent, t, materials, followup=followup, prior_cost_jpy=cost(), max_tokens=6000, **common)
        rows.extend(result.rows)
        return result

    def finish(code: int) -> int:
        write_ledger(args.out_dir, rows)
        return code

    def fail(result, label: str) -> int:
        summary.append(f"{label}：{result.status}（{result.reason}）")
        return finish(EXIT_SKIPPED if result.status.startswith("skipped") else EXIT_FAILED)

    result = call("AG-11", task)
    if result.status != agent_call.STATUS_OK:
        return fail(result, "AG-11")
    output = result.output
    errors, results = check_output(output, c, companies, processes, doc["text"], min_run)
    if errors:
        summary.append(f"書き直し（形式・転載の検査）：{len(errors)}件")
        matches = reprint.find_matches([doc["text"]], fields_of(output), min_run) if any("転載" in e for e in errors) else {}
        extra = "\n資料と同じになった箇所（言い換える）：\n" + "\n".join(f"* {k}: {v}" for k, v in matches.items()) if matches else ""
        result = call("AG-11", task, rewrite_request(output, errors, extra))
        if result.status != agent_call.STATUS_OK:
            return fail(result, "AG-11（書き直し）")
        output = result.output
        errors, results = check_output(output, c, companies, processes, doc["text"], min_run)
        if errors:
            summary.append("書き直しても不合格：" + "; ".join(errors))
            return finish(EXIT_FAILED)

    def review(o: dict):
        review_task = "## 入力（プログラムが渡す値）\n" + json.dumps({"draft": {**fields_of(o)}}, ensure_ascii=False, indent=1)
        return call("AG-13", review_task)

    review_result = review(output)
    if review_result.status != agent_call.STATUS_OK:
        return fail(review_result, "AG-13")
    issues = review_result.output["issues"]
    if any(i["severity"] == "error" for i in issues):
        summary.append(f"校閲の error：{sum(i['severity'] == 'error' for i in issues)}件。書き直す")
        notes = [f"{i['part']}：{i['note']}" for i in issues]
        result = call("AG-11", task, rewrite_request(output, notes))
        if result.status != agent_call.STATUS_OK:
            return fail(result, "AG-11（校閲後の書き直し）")
        rewritten = result.output
        errs, results2 = check_output(rewritten, c, companies, processes, doc["text"], min_run)
        if errs:
            summary.append("校閲後の書き直しが、形式・転載の検査に不合格：" + "; ".join(errs))
        else:
            output, results = rewritten, results2
            review_result = review(output)
            if review_result.status != agent_call.STATUS_OK:
                return fail(review_result, "AG-13（再校閲）")
            issues = review_result.output["issues"]
    unresolved = any(i["severity"] == "error" for i in issues)

    year, month = today[:4], today[5:7]
    slug = output["slug"]
    page_url = f"{SITE}/news/{year}/{month}/{slug}/"
    front = front_matter(c, output, url, today, unresolved)
    front["x_post"] = x_post(output, page_url)
    body = body_of(output)
    rel = f"content/news/{year}-{month}-{slug}.md"
    if (root / rel).exists():
        summary.append("同じ名前のファイルが、すでにある（slug が重なった）")
        return finish(EXIT_FAILED)
    errs, warnings = validate_news(rel, front, body, root)
    if errs:
        summary.append("検査に不合格：" + "; ".join(errs))
        return finish(EXIT_FAILED)
    longest = reprint.longest_overall(results)
    write_text(args.out_dir / rel, render(front, body))
    write_text(args.out_dir / "pr-body.md", pr_body(c, front, output, issues, unresolved, warnings, cost(), args.run_id, longest, min_run))
    summary.append(f"## 作った：{rel}（本文 {body_chars(output)}字、校閲の指摘 {len(issues)}件、draft: {str(unresolved).lower()}、利用額 {cost():.2f}円）")
    return finish(EXIT_OK)


def shared(factory):
    holder: list = []

    def get():
        if not holder:
            holder.append(factory())
        return holder[0]
    return get


def main(argv=None, *, now=lambda: datetime.now(JST), client_factory=None, fetcher=fetch_source.fetch_text, root: Path = ROOT,
         budgets_path=agent_call.BUDGETS_PATH, operations_path=agent_call.OPERATIONS_PATH, agents_dir=agent_call.AGENTS_DIR,
         textcheck_path=reprint.CONFIG_PATH) -> int:
    parser = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    parser.add_argument("--scored", required=True, type=Path)
    parser.add_argument("--id", required=True)
    parser.add_argument("--url")
    parser.add_argument("--out-dir", required=True, type=Path)
    parser.add_argument("--ledger-dir", required=True, type=Path)
    parser.add_argument("--run-id", required=True)
    parser.add_argument("--summary", type=Path)
    args = parser.parse_args(argv)
    summary: list[str] = []
    try:
        code = run(args, now=now, client_factory=client_factory or (lambda: agent_call.anthropic.Anthropic()), fetcher=fetcher, root=root,
                   budgets_path=budgets_path, operations_path=operations_path, agents_dir=agents_dir, textcheck_path=textcheck_path, summary=summary)
    except agent_call.LlmError as error:
        summary.append(f"設定の誤り：{error}")
        code = EXIT_FAILED
    for line in summary:
        print(line)
    if args.summary:
        with args.summary.open("a", encoding="utf-8") as f:
            f.write("\n".join(summary) + "\n")
    return code


if __name__ == "__main__":
    sys.exit(main())
