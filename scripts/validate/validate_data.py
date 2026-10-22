"""データの形式の検証（アーキテクチャ設計書 P10）の最初の版。

引数なしで、リポジトリ全体を検査する。--path で、1ファイルだけも検査できる。

対象と、使うスキーマ（jsonschema Draft 2020-12、format の検査を有効にする）：
* data/companies/*.yaml        schemas/data/company.schema.json
* data/auto/*.json             schemas/data/auto-company.schema.json
* data/supply-chain.yaml       schemas/data/supply-chain.schema.json
* config/xbrl-map.yaml         schemas/config/xbrl-map.schema.json
* data/segments/*.yaml         schemas/data/segment-map.schema.json
* content/companies/*.md       schemas/content/company-overview.schema.json（先頭の項目 front matter だけ）
  ファイルがなければ、何もせずに合格にする

スキーマで確かめられない整合（データ定義書 13章の検証規則）：
* V-01 スキーマに合う（format の date、date-time の検査を含む）
* V-02 ファイル名と識別子が一致する（data/companies の slug、data/auto の company）
* V-03 識別子が重複しない（企業の slug、edinet_code、securities_code、sources の id、
  supply-chain の slug、data/auto の filings の doc_id、financials・employees の期間）。
  data/auto の financials・employees が古い順であること（データ定義書 5.1）も、ここで確かめる
* V-04 参照の先が存在する（data/auto の company が企業マスタにあり、edinet_code が一致する、
  selection.source・parent.source・history[].source が同じファイルの sources にある、
  categories・processes が supply-chain.yaml にある、revisions の path が実在する値を指す、
  revisions の doc_id・supersedes が filings にある、financials・employees の doc_id が filings にある）。
  ただし、取り除いた ordinary_income・segment_adjustment（会計基準の切り替え）の履歴（new が null）の path は、
  その行が実在すれば許す
* セグメント対応表（D02、データ定義書 4.2）：ファイル名と company が同じ（V-02）。company が企業マスタにある、
  based_on が data/auto/{slug}.json の filings にある、xbrl_members が data/auto の financials のセグメントの
  member にある、rationale.source と reference_values の source が sources の id にある、sources の id が重複しない
  （V-04、V-03）。data/auto/{slug}.json がなければ、突き合わせられないためエラー
* 企業の事業概要（D13、6.4）：ファイル名と company が同じ（V-02）。company が企業マスタにある（V-04）。
  本文の見出しが「## 事業概要」「## 工程上の位置づけ」の2つだけで、この順。`#` がない（V-10）。
  本文の [S1] などの番号がすべて sources の id にある（V-07）。sources の資料で本文に出てこないものは警告（V-08）。
  「事業概要」の文字数が300〜500字（データ定義書 2.6 の数え方）を外れたら警告（V-12）
* テーマ（D16、データ定義書 6.7）：content/themes/*.md の front matter は schemas/content/theme.schema.json。
  ファイル名と theme が同じ（V-02）。groups の企業・工程、processes、terms、learn の参照先がある（V-04）。
  根拠（basis）の番号が sources にある、1社がテーマの中で重複しない、others が10社まで（V-25。10社を超えるのは警告）。
  本文は「要旨」「市場の動き」「バリューチェーン」「日本企業の位置」「論点と今後の注目点」の5つの中見出しと、
  最後の見出しの下の「発表元の見方」「本サイトの見方」の小見出し、要旨の3つの箇条書き（V-10）。3,000〜5,000字（V-12、警告）。
  図 src/figures/theme/{slug}-market.astro と {slug}-value-chain.astro がある（V-25。draft: true のときは警告）。
  ニュースの tags.themes が content/themes/ にある（V-04）
* ニュース（D11、データ定義書 6.2）と config/news.yaml（7.3）：content/news/*.md の front matter は
  news.schema.json、config/news.yaml は schemas/config/news.schema.json で検査する（draft: true も検査する）。
  ファイル名が {yyyy}-{mm}-{slug} の形で、年月が published_at と一致する（V-02、V-09）。
  本文の見出しが「## 何が起きたか」「## なぜ重要か」「## 関係する企業・工程とサプライチェーン上の位置」の3つだけで、この順（V-10）。
  本文が400〜700字の目安を外れたら警告（V-12）。overseas が true のとき tags.companies が1件以上で、3つ目の見出しの下に
  その企業の略称か正式名称が1社以上ある（V-13）。tags の企業・工程が存在する（V-04）。
  x_post が140字以内（URLは23字）で、ハッシュタグが2つまで（V-11）。
  config/news.yaml は、weekly_targets の min が max 以下、sources の id が重複しない（V-03）、sources の company が企業マスタにある（V-04）
* YAMLの落とし穴：引用符なしの日付（YAMLが日付型に変える）、yes・no・on・off など（YAML 1.1 では真偽値）

実装していない規則：V-05、V-06、V-09、V-11、V-13〜V-21（公開済みの識別子の削除、必須項目の充足、日付の前後、拠点、予算など）。
V-07、V-08、V-10、V-12 は、事業概要（content/companies）だけに実装している。

* V-04 の検査のうち、superseded の書類が、failed でないどれかの書類の supersedes から指されていること
  （訂正報告書の連鎖が切れていないこと）は、エラーにしている。警告（severity="warning"）の仕組みと --strict は、
  V-08、V-12 の警告に使う

出力は、エラーと警告の一覧（ファイル、場所、規則、内容）。終了コードは、エラーがあれば1、なければ0。
--path が対象外のファイルのときは2。
"""

from __future__ import annotations

import argparse
import datetime
import json
import os
from datetime import date, timedelta
import re
import urllib.parse
import sys
import unicodedata
from dataclasses import dataclass
from pathlib import Path

import yaml
from jsonschema import Draft202012Validator

REPO_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO_ROOT / "scripts" / "edinet"))

from ingest_company import format_checker  # noqa: E402  date-time の検査は、取り込みと同じ内容にする

SCHEMAS = {
    "company": "schemas/data/company.schema.json",
    "auto": "schemas/data/auto-company.schema.json",
    "supply-chain": "schemas/data/supply-chain.schema.json",
    "xbrl-map": "schemas/config/xbrl-map.schema.json",
    "segment-map": "schemas/data/segment-map.schema.json",
    "overview": "schemas/content/company-overview.schema.json",
    "term": "schemas/content/term.schema.json",
    "process": "schemas/content/process.schema.json",
    "news": "schemas/content/news.schema.json",
    "news-config": "schemas/config/news.schema.json",
    "learn": "schemas/content/learn.schema.json",
    "events": "schemas/data/events.schema.json",
    "learn-path": "schemas/content/learn-path.schema.json",
    "ir-point": "schemas/content/ir-point.schema.json",
    "theme": "schemas/content/theme.schema.json",
}
OVERVIEW_HEADINGS = ["事業概要", "工程上の位置づけ"]  # データ定義書 6.4
OVERVIEW_LENGTH = (300, 500)  # 「事業概要」の文字数の目安（V-12）
FRONT_MATTER_FENCE = "---"
PLAIN_NON_STANDARD_BOOL = {"yes", "no", "on", "off", "y", "n"}
BOOL_TAG = "tag:yaml.org,2002:bool"
TIMESTAMP_TAG = "tag:yaml.org,2002:timestamp"


@dataclass(frozen=True)
class Problem:
    file: str
    path: str
    rule: str
    message: str
    severity: str = "error"  # "error" か "warning"。警告は、終了コードを1にしない（--strict で、エラーとして扱う）

    def __str__(self) -> str:
        mark = "警告 " if self.severity == "warning" else ""
        return f"{mark}{self.file}: {self.path or '(全体)'}: [{self.rule}] {self.message}"


def pointer(parts) -> str:
    return "".join("/" + str(p).replace("~", "~0").replace("/", "~1") for p in parts)


# ---- 読み込み ----

def load_yaml(path: Path) -> tuple[object, list[tuple[str, str, str]]]:
    """YAMLを読む。(内容、YAMLの落とし穴の一覧 [(path, rule, message)])。読めなければ ValueError。"""
    return parse_yaml(path.read_text(encoding="utf-8"))


def parse_yaml(text: str) -> tuple[object, list[tuple[str, str, str]]]:
    try:
        node = yaml.compose(text)
        data = yaml.safe_load(text)
    except yaml.YAMLError as error:
        raise ValueError(f"YAMLとして読めない（{str(error).splitlines()[0] if str(error) else type(error).__name__}）") from None
    pitfalls: list[tuple[str, str, str]] = []
    if node is not None:
        _scan_nodes(node, [], pitfalls)
    return data, pitfalls


def _scan_nodes(node, parts: list, out: list) -> None:
    if isinstance(node, yaml.MappingNode):
        for key_node, value_node in node.value:
            key = key_node.value if isinstance(key_node, yaml.ScalarNode) else "?"
            _scan_nodes(value_node, parts + [key], out)
    elif isinstance(node, yaml.SequenceNode):
        for i, item in enumerate(node.value):
            _scan_nodes(item, parts + [i], out)
    elif isinstance(node, yaml.ScalarNode) and node.style is None:  # 引用符なし
        line = node.start_mark.line + 1
        if node.tag == TIMESTAMP_TAG:
            out.append((pointer(parts), "YAML", f"{line}行目: 引用符なしの日付 {node.value} は、YAMLが日付型に変える。"
                        "引用符で囲んで文字列にする"))
        elif node.tag == BOOL_TAG and node.value.lower() in PLAIN_NON_STANDARD_BOOL:
            out.append((pointer(parts), "YAML", f"{line}行目: 引用符なしの {node.value} は、YAML 1.1 では真偽値になる。"
                        "文字列なら引用符で囲み、真偽値なら true／false と書く"))


def load_markdown(path: Path) -> tuple[object, list[tuple[str, str, str]], str]:
    """Markdownを、先頭の項目（front matter）と本文に分けて読む。(front matter の内容、YAMLの落とし穴、本文)。

    先頭の行が `---` で、閉じる `---` の行がなければ ValueError。行番号を、ファイルの行と合わせるため、
    開く `---` の行は、コメントの行に置き換えてから読む。
    """
    try:
        text = path.read_text(encoding="utf-8-sig")
    except UnicodeDecodeError:
        raise ValueError("UTF-8として読めない") from None
    lines = text.split("\n")
    if not lines or lines[0].rstrip() != FRONT_MATTER_FENCE:
        raise ValueError("先頭に front matter（`---` で囲んだ項目）がない")
    end = next((i for i in range(1, len(lines)) if lines[i].rstrip() == FRONT_MATTER_FENCE), None)
    if end is None:
        raise ValueError("front matter を閉じる `---` の行がない")
    data, pitfalls = parse_yaml("#\n" + "\n".join(lines[1:end]))
    return data, pitfalls, "\n".join(lines[end + 1:])


def load_json(path: Path) -> object:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (ValueError, UnicodeDecodeError) as error:
        raise ValueError(f"JSONとして読めない（{type(error).__name__}）") from None


# ---- スキーマ（V-01） ----

class SchemaSet:
    def __init__(self, schema_root: Path):
        self.validators = {}
        self.documents = {}
        for kind, rel in SCHEMAS.items():
            schema = json.loads((schema_root / rel).read_text(encoding="utf-8"))
            Draft202012Validator.check_schema(schema)
            self.documents[kind] = schema
            self.validators[kind] = Draft202012Validator(schema, format_checker=format_checker())

    def errors(self, kind: str, data: object, file: str) -> list[Problem]:
        found = sorted(self.validators[kind].iter_errors(data), key=lambda e: [str(p) for p in e.absolute_path])
        return [Problem(file, pointer(e.absolute_path), "V-01", e.message[:300]) for e in found]


# ---- 検査の本体 ----

def kind_of(path: Path, root: Path) -> str | None:
    try:
        rel = path.resolve().relative_to(root.resolve()).as_posix()
    except ValueError:
        return None
    if rel.startswith("data/companies/") and rel.endswith(".yaml") and rel.count("/") == 2:
        return "company"
    if rel.startswith("data/auto/") and rel.endswith(".json") and rel.count("/") == 2:
        return "auto"
    if rel.startswith("data/segments/") and rel.endswith(".yaml") and rel.count("/") == 2:
        return "segment-map"
    if rel.startswith("content/companies/") and rel.endswith(".md") and rel.count("/") == 2:
        return "overview"
    if rel.startswith("content/glossary/") and rel.endswith(".md") and rel.count("/") == 2:
        return "term"
    if rel.startswith("content/processes/") and rel.endswith(".md") and rel.count("/") == 2:
        return "process"
    if rel.startswith("content/news/") and rel.endswith(".md") and rel.count("/") == 2:
        return "news"
    if rel.startswith("content/learn/") and rel.endswith(".md") and rel.count("/") == 3:
        return "learn"
    if rel.startswith("content/ir-points/") and rel.endswith(".md") and rel.count("/") == 3:
        return "ir-point"
    if rel.startswith("content/themes/") and rel.endswith(".md") and rel.count("/") == 2:
        return "theme"
    if rel == "content/learn/path.yaml":
        return "learn-path"
    if rel == "data/events.yaml":
        return "events"
    if rel == "config/news.yaml":
        return "news-config"
    if rel == "config/explainer-sources.yaml":
        return "explainer-sources"
    if rel == "data/supply-chain.yaml":
        return "supply-chain"
    if rel == "config/xbrl-map.yaml":
        return "xbrl-map"
    return None


def collect_files(root: Path) -> list[tuple[str, Path]]:
    files: list[tuple[str, Path]] = []
    files += [("company", p) for p in sorted((root / "data" / "companies").glob("*.yaml"))]
    files += [("auto", p) for p in sorted((root / "data" / "auto").glob("*.json"))]
    files += [("segment-map", p) for p in sorted((root / "data" / "segments").glob("*.yaml"))]
    files += [("overview", p) for p in sorted((root / "content" / "companies").glob("*.md"))]
    files += [("term", p) for p in sorted((root / "content" / "glossary").glob("*.md"))]
    files += [("process", p) for p in sorted((root / "content" / "processes").glob("*.md"))]
    files += [("news", p) for p in sorted((root / "content" / "news").glob("*.md"))]
    files += [("learn", p) for p in sorted((root / "content" / "learn").glob("*/*.md"))]
    files += [("ir-point", p) for p in sorted((root / "content" / "ir-points").glob("*/*.md"))]
    files += [("theme", p) for p in sorted((root / "content" / "themes").glob("*.md"))]
    for kind, rel in (("learn-path", "content/learn/path.yaml"), ("events", "data/events.yaml"), ("supply-chain", "data/supply-chain.yaml"), ("xbrl-map", "config/xbrl-map.yaml"),
                      ("explainer-sources", "config/explainer-sources.yaml"), ("news-config", "config/news.yaml")):
        if (root / rel).is_file():
            files.append((kind, root / rel))
    return files


def validate(root: Path = REPO_ROOT, schema_root: Path = REPO_ROOT, only: Path | None = None, today: date | None = None) -> list[Problem]:
    """root の下のデータを検査する。only を指定すると、そのファイルのエラーだけを返す。"""
    schemas = SchemaSet(schema_root)
    problems: list[Problem] = []
    loaded: dict[str, tuple[str, Path, object]] = {}
    bodies: dict[str, str] = {}
    for kind, path in collect_files(root):
        rel = path.relative_to(root).as_posix()
        try:
            if kind == "auto":
                data, pitfalls = load_json(path), []
            elif kind in ("overview", "term", "process", "news", "learn", "ir-point", "theme"):
                data, pitfalls, bodies[rel] = load_markdown(path)
            else:
                data, pitfalls = load_yaml(path)
        except ValueError as error:
            problems.append(Problem(rel, "", "V-01", str(error)))
            continue
        loaded[rel] = (kind, path, data)
        problems += [Problem(rel, p, rule, msg) for p, rule, msg in pitfalls]
        if kind != "explainer-sources":  # 出典の設定は、スキーマがない。コードで検査する（check_explainer_sources）
            problems += schemas.errors(kind, data, rel)

    supply = next((d for k, _, d in loaded.values() if k == "supply-chain"), None)
    problems += check_supply_chain(loaded, supply, schemas)
    companies = {rel: d for rel, (k, _, d) in loaded.items() if k == "company" and isinstance(d, dict)}
    problems += check_companies(companies, supply)
    autos = {rel: d for rel, (k, _, d) in loaded.items() if k == "auto" and isinstance(d, dict)}
    problems += check_auto(autos, companies)
    problems += check_segment_maps({rel: d for rel, (k, _, d) in loaded.items() if k == "segment-map" and isinstance(d, dict)},
                                   companies, autos)
    problems += check_overviews({rel: (d, bodies[rel]) for rel, (k, _, d) in loaded.items()
                                 if k == "overview" and isinstance(d, dict)}, companies)
    explainer = next((d for k, _, d in loaded.values() if k == "explainer-sources"), None)
    if explainer is not None:
        problems += [Problem("config/explainer-sources.yaml", p.path, p.rule, p.message, p.severity)
                     for p in check_explainer_sources(explainer, supply)]
    terms = {rel: (d, bodies[rel]) for rel, (k, _, d) in loaded.items() if k == "term" and isinstance(d, dict)}
    processes = {rel: (d, bodies[rel]) for rel, (k, _, d) in loaded.items() if k == "process" and isinstance(d, dict)}
    names = company_names(companies)
    problems += check_terms(terms, supply, explainer, names)
    problems += check_process_pages(processes, supply, explainer, terms, names)
    themes = {rel: (d, bodies[rel]) for rel, (k, _, d) in loaded.items() if k == "theme" and isinstance(d, dict)}
    problems += check_news({rel: (d, bodies[rel]) for rel, (k, _, d) in loaded.items() if k == "news" and isinstance(d, dict)},
                           companies, supply, {Path(rel).stem for rel in themes})
    ir_points = {rel: (d, bodies[rel]) for rel, (k, _, d) in loaded.items() if k == "ir-point" and isinstance(d, dict)}
    if ir_points:
        segments = {rel: d for rel, (k, _, d) in loaded.items() if k == "segment-map" and isinstance(d, dict)}
        problems += check_ir_points(ir_points, companies, segments, autos, (load_yaml(root / "config" / "sources.yaml")[0] if (root / "config" / "sources.yaml").is_file() else None))
    learn_pages = {rel: (d, bodies[rel]) for rel, (k, _, d) in loaded.items() if k == "learn" and isinstance(d, dict)}
    learn_path = next((d for k, _, d in loaded.values() if k == "learn-path"), None)
    problems += check_learn(learn_pages, learn_path, supply, terms, companies, explainer, names, root)
    problems += check_themes(themes, companies, supply, terms, learn_pages, root)
    for rel, (_, body) in {**terms, **processes, **learn_pages}.items():  # V-24：理解度チェックの形
        problems += check_quiz(rel, body)
    events = next((d for k, _, d in loaded.values() if k == "events"), None)
    if isinstance(events, dict):
        problems += check_events(events, today=today)
    news_config = next((d for k, _, d in loaded.values() if k == "news-config"), None)
    if isinstance(news_config, dict):
        problems += check_news_config(news_config, companies)
    if only is not None:
        target = only.resolve().relative_to(root.resolve()).as_posix()
        problems = [p for p in problems if p.file == target]
    return problems


def _slugs(supply, key) -> set[str] | None:
    if not isinstance(supply, dict) or not isinstance(supply.get(key), list):
        return None
    return {i["slug"] for i in supply[key] if isinstance(i, dict) and isinstance(i.get("slug"), str)}


def check_supply_chain(loaded, supply, schemas: SchemaSet) -> list[Problem]:
    out: list[Problem] = []
    if not isinstance(supply, dict):
        return out
    file = "data/supply-chain.yaml"
    for key in ("categories", "processes"):
        items = supply.get(key)
        if not isinstance(items, list):
            continue
        seen: dict = {}
        for i, item in enumerate(items):
            if isinstance(item, dict) and isinstance(item.get("slug"), str):
                if item["slug"] in seen:
                    out.append(Problem(file, pointer([key, i, "slug"]), "V-03", f"slug {item['slug']} が重複している"))
                seen[item["slug"]] = i
    categories = _slugs(supply, "categories")
    if categories is not None and isinstance(supply.get("processes"), list):
        for i, item in enumerate(supply["processes"]):
            if isinstance(item, dict) and item.get("stage") in {"design", "materials", "front-end", "back-end"} \
                    and item["stage"] not in categories:
                out.append(Problem(file, pointer(["processes", i, "stage"]), "V-04",
                                   f"stage {item['stage']} が categories にない"))
    # スキーマの値の一覧（company.schema.json）と、supply-chain.yaml の整合
    props = schemas.documents["company"]["properties"]
    for key, enum_path in (("categories", props["categories"]["items"]["enum"]),
                           ("processes", props["processes"]["items"]["enum"])):
        slugs = _slugs(supply, key)
        if slugs is not None and slugs != set(enum_path):
            out.append(Problem(file, f"/{key}", "V-04", "company.schema.json の値の一覧と一致しない"
                               f"（スキーマにだけある：{sorted(set(enum_path) - slugs)}、"
                               f"supply-chain.yaml にだけある：{sorted(slugs - set(enum_path))}）"))
    return out


def check_companies(companies: dict[str, dict], supply) -> list[Problem]:
    out: list[Problem] = []
    categories, processes = _slugs(supply, "categories"), _slugs(supply, "processes")
    seen: dict[str, dict[str, str]] = {"slug": {}, "edinet_code": {}, "securities_code": {}}
    for rel, data in companies.items():
        slug = data.get("slug")
        if isinstance(slug, str) and Path(rel).stem != slug:
            out.append(Problem(rel, "/slug", "V-02", f"ファイル名（{Path(rel).stem}）と slug（{slug}）が一致しない"))
        for key in seen:
            value = data.get(key)
            if isinstance(value, str):
                if value in seen[key]:
                    out.append(Problem(rel, f"/{key}", "V-03", f"{key} {value} が {seen[key][value]} と重複している"))
                else:
                    seen[key][value] = rel
        source_ids: set[str] = set()
        for i, source in enumerate(data.get("sources") or []):
            if isinstance(source, dict) and isinstance(source.get("id"), str):
                if source["id"] in source_ids:
                    out.append(Problem(rel, pointer(["sources", i, "id"]), "V-03", f"sources の id {source['id']} が重複している"))
                source_ids.add(source["id"])
        refs = []
        if isinstance(data.get("selection"), dict):
            refs.append((["selection", "source"], data["selection"].get("source")))
        if isinstance(data.get("parent"), dict):
            refs.append((["parent", "source"], data["parent"].get("source")))
        for i, item in enumerate(data.get("history") or []):
            if isinstance(item, dict):
                refs.append((["history", i, "source"], item.get("source")))
        for parts, value in refs:
            if isinstance(value, str) and value not in source_ids:
                out.append(Problem(rel, pointer(parts), "V-04", f"出典 {value} が、同じファイルの sources にない"))
        for key, allowed in (("categories", categories), ("processes", processes)):
            if allowed is None or not isinstance(data.get(key), list):
                continue
            for i, value in enumerate(data[key]):
                if isinstance(value, str) and value not in allowed:
                    out.append(Problem(rel, pointer([key, i]), "V-04", f"{key} の {value} が supply-chain.yaml にない"))
    return out


def resolve_pointer(data, path: str):
    """JSON Pointer を解く。見つからなければ KeyError。"""
    node = data
    for raw in path.split("/")[1:]:
        part = raw.replace("~1", "/").replace("~0", "~")
        if isinstance(node, list):
            if not part.isdigit() or int(part) >= len(node):
                raise KeyError(path)
            node = node[int(part)]
        elif isinstance(node, dict) and part in node:
            node = node[part]
        else:
            raise KeyError(path)
    return node


def _removed_item_ok(data, path: str) -> bool:
    """/financials/3/ordinary_income/value のように、項目ごと取り除かれた値の path か（行は実在する）。
    会計基準の切り替えで取り除く ordinary_income と、前期の列にない segment_adjustment が対象。"""
    parts = path.split("/")
    if len(parts) != 5 or parts[1] != "financials" or parts[3] not in ("ordinary_income", "segment_adjustment") \
            or parts[4] != "value":
        return False
    try:
        return isinstance(resolve_pointer(data, "/".join(parts[:3])), dict)
    except KeyError:
        return False


def check_auto(autos: dict[str, dict], companies: dict[str, dict]) -> list[Problem]:
    out: list[Problem] = []
    by_slug = {d["slug"]: d for d in companies.values() if isinstance(d.get("slug"), str)}
    for rel, data in autos.items():
        company = data.get("company")
        if isinstance(company, str):
            if Path(rel).stem != company:
                out.append(Problem(rel, "/company", "V-02", f"ファイル名（{Path(rel).stem}）と company（{company}）が一致しない"))
            master = by_slug.get(company)
            if master is None:
                out.append(Problem(rel, "/company", "V-04", f"company {company} が data/companies にない"))
            elif master.get("edinet_code") != data.get("edinet_code"):
                out.append(Problem(rel, "/edinet_code", "V-04",
                                   f"edinet_code（{data.get('edinet_code')}）が企業マスタ（{master.get('edinet_code')}）と一致しない"))
        doc_ids: set[str] = set()
        for i, f in enumerate(data.get("filings") or []):
            if isinstance(f, dict) and isinstance(f.get("doc_id"), str):
                if f["doc_id"] in doc_ids:
                    out.append(Problem(rel, pointer(["filings", i, "doc_id"]), "V-03", f"doc_id {f['doc_id']} が重複している"))
                doc_ids.add(f["doc_id"])
        for section, key in (("financials", lambda r: (r.get("fiscal_period_end"), r.get("period_type"))),
                             ("employees", lambda r: (r.get("fiscal_period_end"),))):
            rows = data.get(section) or []
            seen: dict = {}
            for i, row in enumerate(rows):
                if not isinstance(row, dict):
                    continue
                k = key(row)
                if k in seen:
                    out.append(Problem(rel, pointer([section, i]), "V-03", f"期間 {'、'.join(map(str, k))} が "
                                       f"/{section}/{seen[k]} と重複している"))
                seen.setdefault(k, i)
                if isinstance(row.get("doc_id"), str) and row["doc_id"] not in doc_ids:
                    out.append(Problem(rel, pointer([section, i, "doc_id"]), "V-04", f"doc_id {row['doc_id']} が filings にない"))
            sort_key = (lambda r: (r.get("fiscal_period_end") or "", r.get("period_end") or "")) if section == "financials" \
                else (lambda r: r.get("fiscal_period_end") or "")
            dict_rows = [r for r in rows if isinstance(r, dict)]
            if any(sort_key(a) > sort_key(b) for a, b in zip(dict_rows, dict_rows[1:])):
                out.append(Problem(rel, f"/{section}", "V-03", f"{section} が期間の古い順になっていない"))
        pointed = {f.get("supersedes") for f in data.get("filings") or []
                   if isinstance(f, dict) and f.get("status") != "failed"}
        for i, f in enumerate(data.get("filings") or []):
            if isinstance(f, dict) and f.get("status") == "superseded" and f.get("doc_id") not in pointed:
                out.append(Problem(rel, pointer(["filings", i, "status"]), "V-04",
                                   f"superseded の書類 {f.get('doc_id')} が、どの書類の supersedes からも指されていない"
                                   "（訂正報告書の連鎖が切れている。取り込み直すと直る）"))
        for i, rev in enumerate(data.get("revisions") or []):
            if not isinstance(rev, dict):
                continue
            path = rev.get("path")
            if isinstance(path, str):
                try:
                    resolve_pointer(data, path)
                except KeyError:
                    if rev.get("new") is None and _removed_item_ok(data, path):
                        continue  # 取り除いた項目（会計基準の切り替えで、ordinary_income を取り除いた）の履歴。new は null
                    out.append(Problem(rel, pointer(["revisions", i, "path"]), "V-04", f"path {path} が、実在する値を指していない"))
            for key in ("supersedes", "doc_id"):
                if isinstance(rev.get(key), str) and rev[key] not in doc_ids:
                    out.append(Problem(rel, pointer(["revisions", i, key]), "V-04", f"{key} {rev[key]} が filings にない"))
    return out


def _source_ids(data: dict, rel: str, out: list[Problem]) -> set[str]:
    """sources の id の集まりを返す。重複は V-03。"""
    ids: set[str] = set()
    for i, source in enumerate(data.get("sources") or []):
        if isinstance(source, dict) and isinstance(source.get("id"), str):
            if source["id"] in ids:
                out.append(Problem(rel, pointer(["sources", i, "id"]), "V-03", f"sources の id {source['id']} が重複している"))
            ids.add(source["id"])
    return ids


def _check_slug_file(rel: str, data: dict, companies: dict[str, dict], out: list[Problem]) -> str | None:
    """ファイル名と company の一致（V-02）、company が企業マスタにあること（V-04）を確かめる。"""
    company = data.get("company")
    if not isinstance(company, str):
        return None
    if Path(rel).stem != company:
        out.append(Problem(rel, "/company", "V-02", f"ファイル名（{Path(rel).stem}）と company（{company}）が一致しない"))
    if company not in {d.get("slug") for d in companies.values()}:
        out.append(Problem(rel, "/company", "V-04", f"company {company} が data/companies にない"))
    return company


def check_segment_maps(maps: dict[str, dict], companies: dict[str, dict], autos: dict[str, dict]) -> list[Problem]:
    out: list[Problem] = []
    auto_by_slug = {Path(rel).stem: d for rel, d in autos.items()}
    for rel, data in maps.items():
        company = _check_slug_file(rel, data, companies, out)
        source_ids = _source_ids(data, rel, out)
        for i, segment in enumerate(data.get("segments") or []):
            ref = (segment.get("rationale") or {}).get("source") if isinstance(segment, dict) \
                and isinstance(segment.get("rationale"), dict) else None
            if isinstance(ref, str) and ref not in source_ids:
                out.append(Problem(rel, pointer(["segments", i, "rationale", "source"]), "V-04",
                                   f"出典 {ref} が、同じファイルの sources にない"))
        for i, value in enumerate(data.get("reference_values") or []):
            if isinstance(value, dict) and isinstance(value.get("source"), str) and value["source"] not in source_ids:
                out.append(Problem(rel, pointer(["reference_values", i, "source"]), "V-04",
                                   f"出典 {value['source']} が、同じファイルの sources にない"))
        if company is None:
            continue
        auto = auto_by_slug.get(company)
        if auto is None:
            out.append(Problem(rel, "/company", "V-04",
                               f"data/auto/{company}.json がない（based_on と xbrl_members を突き合わせられない）"))
            continue
        doc_ids = {f.get("doc_id") for f in auto.get("filings") or [] if isinstance(f, dict)}
        if isinstance(data.get("based_on"), str) and data["based_on"] not in doc_ids:
            out.append(Problem(rel, "/based_on", "V-04", f"based_on {data['based_on']} が data/auto/{company}.json の filings にない"))
        members = {s.get("member") for r in auto.get("financials") or [] if isinstance(r, dict)
                   for s in r.get("segments") or [] if isinstance(s, dict)}
        for i, segment in enumerate(data.get("segments") or []):
            if not isinstance(segment, dict):
                continue
            for j, member in enumerate(segment.get("xbrl_members") or []):
                if isinstance(member, str) and member not in members:
                    out.append(Problem(rel, pointer(["segments", i, "xbrl_members", j]), "V-04",
                                       f"xbrl_members の {member} が、data/auto/{company}.json の financials のセグメントの member にない"))
    return out


_HEADING = re.compile(r"^(#{1,6})[ \t]+(.*?)[ \t]*#*[ \t]*$")
_CITATION = re.compile(r"\[(S[0-9]+)\]")
_FENCE = re.compile(r"^[ \t]{0,3}(```|~~~)")


def split_body(body: str) -> tuple[list[tuple[int, str, list[str]]], list[str]]:
    """本文を、コードブロックの外の見出しで分ける。

    返り値は ([(見出しの段、見出しの文字列、その見出しの下の行)], 本文のすべての行（コードブロックの外）)。
    最初の見出しより前の行は、段 0・空の見出しの区分に入れる。
    """
    sections: list[tuple[int, str, list[str]]] = [(0, "", [])]
    outside: list[str] = []
    in_fence = False
    for line in body.split("\n"):
        if _FENCE.match(line):
            in_fence = not in_fence
            continue
        if in_fence:
            continue
        outside.append(line)
        match = _HEADING.match(line)
        if match:
            sections.append((len(match.group(1)), match.group(2).strip(), []))
        else:
            sections[-1][2].append(line)
    return sections, outside


def count_characters(lines: list[str]) -> int:
    """文字数（データ定義書 2.6）：Markdownの記法、出典の番号、改行、行頭と行末の空白を除き、NFKCの後の文字を1字と数える。"""
    cleaned = []
    for line in lines:
        line = _CITATION.sub("", line)
        line = re.sub(r"!?\[([^\]]*)\]\([^)]*\)", r"\1", line)  # 画像・リンクは、表示される文字だけ
        line = re.sub(r"^[ \t]*(?:>+[ \t]*|[-*+][ \t]+|[0-9]+[.)][ \t]+)", "", line)  # 引用、箇条書きの記号
        line = re.sub(r"(\*\*|__|~~|\*|`)", "", line)
        line = re.sub(r"(?<![A-Za-z0-9])_([^_]+)_(?![A-Za-z0-9])", r"\1", line)
        line = line.replace("|", "")
        line = line.strip()
        if line and not re.fullmatch(r"[-: ]+", line):  # 表の区切り行などは除く
            cleaned.append(line)
    return len(unicodedata.normalize("NFKC", "".join(cleaned)))


def check_overviews(overviews: dict[str, tuple[dict, str]], companies: dict[str, dict]) -> list[Problem]:
    out: list[Problem] = []
    for rel, (data, body) in overviews.items():
        _check_slug_file(rel, data, companies, out)
        source_ids = _source_ids(data, rel, out)
        sections, outside = split_body(body)
        headings = [(level, text) for level, text, _ in sections[1:]]
        if any(level == 1 for level, _ in headings):
            out.append(Problem(rel, "(本文)", "V-10", "`#`（大見出し）がある。本文は `##` から始める"))
        if [t for _, t in headings] != OVERVIEW_HEADINGS or any(level != 2 for level, _ in headings):
            found = " / ".join("#" * level + " " + text for level, text in headings) or "なし"
            out.append(Problem(rel, "(本文)", "V-10",
                               "本文の見出しは「## 事業概要」「## 工程上の位置づけ」の2つだけで、この順にする"
                               f"（実際：{found[:200]}）"))
        cited = set(_CITATION.findall("\n".join(outside)))
        for number in sorted(cited - source_ids, key=lambda n: int(n[1:])):
            out.append(Problem(rel, "(本文)", "V-07", f"本文の [{number}] が、sources にない"))
        for i, source in enumerate(data.get("sources") or []):
            if isinstance(source, dict) and isinstance(source.get("id"), str) and source["id"] not in cited:
                out.append(Problem(rel, pointer(["sources", i, "id"]), "V-08",
                                   f"sources の {source['id']} が、本文で使われていない", "warning"))
        overview = next((lines for level, text, lines in sections[1:] if text == OVERVIEW_HEADINGS[0] and level == 2), None)
        if overview is not None:
            count = count_characters(overview)
            low, high = OVERVIEW_LENGTH
            if not low <= count <= high:
                out.append(Problem(rel, "(本文)", "V-12", f"「事業概要」が {count}字で、目安（{low}〜{high}字）を外れている",
                                   "warning"))
    return out


# ---- 工程・用語の解説と、出典の設定（config/explainer-sources.yaml） ----

EXPLAINER_STATUS = ("candidate", "approved", "rejected")
EXPLAINER_ROLES = ("primary", "supplementary")
EXPLAINER_KINDS = ("edinet", "tanshin", "presentation", "timely_disclosure", "press_release", "government", "association",
                   "press", "web")  # データ定義書 8.2 の kind
TERM_LENGTH = (200, 400)  # 用語の本文の文字数の目安（V-12、データ定義書 6.6）
DESCRIPTION_LENGTH = (50, 120)  # description の文字数の目安（暫定。V-12）
TITLE_MAX = 60  # 工程の title の文字数の目安（暫定。V-12）


def check_explainer_sources(config, supply) -> list[Problem]:
    """config/explainer-sources.yaml の検査（スキーマがないため、コードで書く）。"""
    rel = "config/explainer-sources.yaml"
    out: list[Problem] = []
    if not isinstance(config, dict):
        return [Problem(rel, "", "V-01", "オブジェクトではない")]
    if config.get("schema_version") != 1:
        out.append(Problem(rel, "/schema_version", "V-01", "schema_version は 1"))
    supply_slugs = _slugs(supply, "processes")
    mvp = {i["slug"] for i in (supply or {}).get("processes", []) if isinstance(i, dict) and i.get("mvp") is True
           and isinstance(i.get("slug"), str)} if isinstance(supply, dict) else set()
    for section, name_key in (("terms", "term"), ("processes", "process"), ("learn", "title")):
        table = config.get(section)
        if section == "learn" and table is None:  # 学習のページ（データ定義書 6.8）は、運営者が指定したときだけ書く
            continue
        if not isinstance(table, dict):
            out.append(Problem(rel, f"/{section}", "V-01", "slug をキーとするオブジェクトではない"))
            continue
        for slug, entry in table.items():
            base = [section, slug]
            if not isinstance(slug, str) or not re.fullmatch(r"[a-z0-9]+(-[a-z0-9]+)*", slug):
                out.append(Problem(rel, pointer(base), "V-01", "slug の形が正しくない（英小文字・数字・ハイフン）"))
            if not isinstance(entry, dict):
                out.append(Problem(rel, pointer(base), "V-01", "オブジェクトではない"))
                continue
            if not isinstance(entry.get(name_key), str) or not entry[name_key].strip():
                out.append(Problem(rel, pointer(base + [name_key]), "V-01", f"{name_key}（名前）がない"))
            if "basis" in entry and entry["basis"] != "reviewed":  # 運営者が確かめる方式（CLAUDE.md 6.4 の例外）だけ。ほかの値は、ない
                out.append(Problem(rel, pointer(base + ["basis"]), "V-01", "basis は reviewed だけ（省略すると、出典から書く）"))
            reviewed = entry.get("basis") == "reviewed"
            for key in ("aliases", "keywords"):
                if key in entry and not (isinstance(entry[key], list) and all(isinstance(w, str) and w.strip() for w in entry[key])):
                    out.append(Problem(rel, pointer(base + [key]), "V-01", "文字列の一覧ではない"))
            if section == "learn" and not reviewed:  # 学習のページは、運営者が確かめる方式（CLAUDE.md 6.4）を指定するためだけに書く
                out.append(Problem(rel, pointer(base + ["basis"]), "V-01", "learn の項目は basis: reviewed を指定する"))
            if section == "processes" and supply_slugs is not None and slug not in supply_slugs:
                out.append(Problem(rel, pointer(base), "V-04", f"工程 {slug} が data/supply-chain.yaml にない"))
            sources = entry.get("sources", [] if reviewed else None)
            if not isinstance(sources, list):
                out.append(Problem(rel, pointer(base + ["sources"]), "V-01", "sources が一覧ではない"))
                continue
            if not sources and reviewed:  # 運営者が確かめる方式は、公開資料の原資料束を使わない。sources が空でよい
                continue
            if not sources:  # 「公式の出典が未確認」の対象。下書きは作れない（承認済みの資料がない）。形の誤りではないため、警告
                out.append(Problem(rel, pointer(base + ["sources"]), "V-01", "sources が空（承認済みの出典がないため、下書きは作れない）",
                                   "warning"))
                continue
            approved_urls: set[str] = set()
            for i, source in enumerate(sources):
                at = base + ["sources", i]
                if not isinstance(source, dict):
                    out.append(Problem(rel, pointer(at), "V-01", "オブジェクトではない"))
                    continue
                for key, allowed in (("status", EXPLAINER_STATUS), ("role", EXPLAINER_ROLES), ("kind", EXPLAINER_KINDS)):
                    if source.get(key) not in allowed:
                        out.append(Problem(rel, pointer(at + [key]), "V-01", f"{key} は {' / '.join(allowed)} のどれか"))
                for key in ("publisher", "title"):
                    if not isinstance(source.get(key), str) or not source[key].strip():
                        out.append(Problem(rel, pointer(at + [key]), "V-01", f"{key} がない"))
                url = source.get("url")
                if isinstance(url, str) and re.fullmatch(r"http://[^\s/]+\S*", url):
                    # 取得は https だけ。http のURLは取得できない。運営者が直すまでは警告（--strict でエラー）
                    out.append(Problem(rel, pointer(at + ["url"]), "V-01", "url が https:// でなく http:// で始まる（取得できない）",
                                       "warning"))
                elif not isinstance(url, str) or not re.fullmatch(r"https://[^\s/]+\S*", url):
                    out.append(Problem(rel, pointer(at + ["url"]), "V-01", "url が https:// で始まる形ではない"))
                elif source.get("status") == "approved":
                    if url in approved_urls:
                        out.append(Problem(rel, pointer(at + ["url"]), "V-03", "承認済み（approved）のURLが、同じ対象の中で重複している"))
                    approved_urls.add(url)
    if mvp and isinstance(config.get("processes"), dict):
        for slug in sorted(mvp - set(config["processes"])):
            out.append(Problem(rel, "/processes", "V-04", f"mvp: true の工程 {slug} の定義（出典）がない"))
    return out


def _source_roles(config, section: str, slug: str) -> dict[str, str]:
    """URL → 役割（その対象の承認済みの出典）。"""
    entry = ((config or {}).get(section) or {}).get(slug) if isinstance(config, dict) else None
    if not isinstance(entry, dict):
        return {}
    return {s["url"]: s["role"] for s in entry.get("sources") or []
            if isinstance(s, dict) and isinstance(s.get("url"), str) and s.get("role") in EXPLAINER_ROLES}


def _body_checks(rel: str, data: dict, body: str, roles: dict[str, str], out: list[Problem], reviewed: bool = False) -> list[str]:
    """工程・用語の本文の共通の検査（V-07、V-08、V-10、補助の出典だけを引いていないか）。本文の行（コードブロックの外）を返す。"""
    source_ids = _source_ids(data, rel, out)
    sections, outside = split_body(body)
    levels = [level for level, _, _ in sections[1:]]
    if 1 in levels:
        out.append(Problem(rel, "(本文)", "V-10", "`#`（大見出し）がある。本文は `##` から始める"))
    previous = 1
    for level in levels:
        if level > previous + 1:
            out.append(Problem(rel, "(本文)", "V-10", "見出しの段が飛んでいる（`##` の次に `####` など）"))
            break
        previous = level
    cited = set(_CITATION.findall("\n".join(outside)))
    for number in sorted(cited - source_ids, key=lambda n: int(n[1:])):
        out.append(Problem(rel, "(本文)", "V-07", f"本文の [{number}] が、sources にない"))
    if reviewed:  # 運営者が確かめる方式：本文に出典の番号は付けない。sources は、運営者が確かめに使った資料（本文では引かない）
        return outside
    for i, source in enumerate(data.get("sources") or []):
        if isinstance(source, dict) and isinstance(source.get("id"), str) and source["id"] not in cited:
            out.append(Problem(rel, pointer(["sources", i, "id"]), "V-08", f"sources の {source['id']} が、本文で使われていない",
                               "warning"))
    cited_roles = {roles.get(s.get("url")) for s in data.get("sources") or []
                   if isinstance(s, dict) and s.get("id") in cited}
    if cited and cited_roles and cited_roles <= {"supplementary", None} and "supplementary" in cited_roles:
        out.append(Problem(rel, "(本文)", "V-08", "本文が、補助（supplementary）の出典だけを引いている。定義は、primary の出典で裏付ける",
                           "warning"))
    return outside


def _length_warning(rel: str, path: str, label: str, count: int, low: int, high: int, out: list[Problem]) -> None:
    if not low <= count <= high:
        out.append(Problem(rel, path, "V-12", f"{label}が {count}字で、目安（{low}〜{high}字）を外れている", "warning"))


def company_names(companies: dict[str, dict]) -> set[str]:
    """企業マスタの名前（正式名称、略称、英語表記）。2字以上のものだけ。"""
    names: set[str] = set()
    for data in companies.values():
        if isinstance(data, dict):
            for value in [data.get("name"), data.get("name_en"), *(data.get("short_names") or [])]:
                if isinstance(value, str) and len(value.strip()) >= 2:
                    names.add(value.strip())
    return names


def _reviewed_checks(rel: str, section: str, slug: str, data: dict, body: str, config, names: set[str], out: list[Problem]) -> None:
    """basis: reviewed（運営者が確かめる方式。CLAUDE.md 6.4 の例外）の用語・工程の検査。"""
    entry = ((config or {}).get(section) or {}).get(slug) if isinstance(config, dict) else None
    if isinstance(config, dict):
        if not isinstance(entry, dict) or entry.get("basis") != "reviewed":  # 運営者が指定したものだけ（自分の判断でこの方式にしない）
            out.append(Problem(rel, "/basis", "V-04", "basis: reviewed だが、config/explainer-sources.yaml で basis: reviewed と指定されていない"))
    if data.get("draft") is not True:
        for key in ("reviewed_on", "review_methods"):
            if not data.get(key):
                out.append(Problem(rel, f"/{key}", "V-01", f"basis: reviewed で公開する（draft: true でない）には、{key} が必要"))
    _, outside = split_body(quiz_split(body)[0])  # 理解度チェックの番号（選択肢と答え）は、数値として数えない
    text = "\n".join(outside)
    if _CITATION.search(text):
        out.append(Problem(rel, "(本文)", "V-07", "basis: reviewed の本文に、出典の番号 [S1] などがある（付けない。出典は、運営者が sources に書く）",
                           "warning"))
    flat = unicodedata.normalize("NFKC", _CITATION.sub("", text))  # 出典の番号 [S1] の数字は、数値ではない
    if re.search(r"[0-9]", flat):
        out.append(Problem(rel, "(本文)", "V-12", "basis: reviewed の本文に、半角の数字（年・数値）がある（書かない決まり）", "warning"))
    found = sorted(n for n in names if unicodedata.normalize("NFKC", n).casefold() in flat.casefold())
    if found:
        out.append(Problem(rel, "(本文)", "V-12", f"basis: reviewed の本文に、企業名がある（書かない決まり）：{'、'.join(found[:5])}", "warning"))


def _name_key(text: str) -> str:
    return unicodedata.normalize("NFKC", text).casefold().strip()


def check_terms(terms: dict[str, tuple[dict, str]], supply, config, names: set[str] | None = None) -> list[Problem]:
    out: list[Problem] = []
    config_terms = (config or {}).get("terms") if isinstance(config, dict) else None
    known = set(config_terms) if isinstance(config_terms, dict) else None
    process_slugs = _slugs(supply, "processes")
    file_slugs = {Path(rel).stem for rel in terms}
    owners: dict[str, list[str]] = {}
    for rel, (data, body) in terms.items():
        slug = Path(rel).stem
        if known is not None and slug not in known:
            out.append(Problem(rel, "", "V-02", f"ファイル名（{slug}）が config/explainer-sources.yaml の用語の slug にない"))
        if known is not None and slug in known and isinstance(config_terms[slug], dict) \
                and isinstance(data.get("term"), str) and data["term"] != config_terms[slug].get("term"):
            out.append(Problem(rel, "/term", "V-02", "term が config/explainer-sources.yaml の用語の名前と違う", "warning"))
        for name in [data.get("term"), *(data.get("aliases") or [])]:
            if isinstance(name, str):
                owners.setdefault(_name_key(name), []).append(rel)
        if process_slugs is not None:
            for i, ref in enumerate(data.get("processes") or []):
                if ref not in process_slugs:
                    out.append(Problem(rel, pointer(["processes", i]), "V-04", f"工程 {ref} が data/supply-chain.yaml にない"))
        for i, ref in enumerate(data.get("related_terms") or []):
            if ref == slug:
                out.append(Problem(rel, pointer(["related_terms", i]), "V-04", "自分自身を参照している"))
            elif ref not in file_slugs and (known is None or ref not in known):
                out.append(Problem(rel, pointer(["related_terms", i]), "V-04", f"用語 {ref} が、用語集にも config/explainer-sources.yaml にもない"))
            elif ref not in file_slugs:
                out.append(Problem(rel, pointer(["related_terms", i]), "V-04", f"用語 {ref} は、まだ原稿（content/glossary/）がない。公開の前にそろえる",
                                   "warning"))
        roles = _source_roles(config, "terms", slug)
        reviewed = data.get("basis") == "reviewed"
        if reviewed:
            _reviewed_checks(rel, "terms", slug, data, body, config, names or set(), out)
        elif isinstance(config, dict) and ((config.get("terms") or {}).get(slug) or {}).get("basis") == "reviewed":
            out.append(Problem(rel, "/basis", "V-04", "config/explainer-sources.yaml では basis: reviewed だが、ファイルは basis: reviewed でない", "warning"))
        _body_checks(rel, data, body, roles, out, reviewed)
        _length_warning(rel, "(本文)", "本文", count_characters(split_body(quiz_split(body)[0])[1]), *TERM_LENGTH, out)
        if isinstance(data.get("description"), str):
            _length_warning(rel, "/description", "description", count_characters([data["description"]]), *DESCRIPTION_LENGTH, out)
    for key, files in sorted(owners.items()):  # V-16：term と aliases の語は、用語集の全体で重複させない（同じファイルの中も含む）
        if len(files) > 1:
            out.append(Problem(files[1], "(term / aliases)", "V-16",
                               f"同じ語が、{len(files)}か所の term・aliases にある（{', '.join(Path(f).stem for f in files)}）"))
    return out


def check_process_pages(pages: dict[str, tuple[dict, str]], supply, config, terms: dict[str, tuple[dict, str]],
                        names: set[str] | None = None) -> list[Problem]:
    out: list[Problem] = []
    process_slugs = _slugs(supply, "processes")
    config_terms = (config or {}).get("terms") if isinstance(config, dict) else None
    known = set(config_terms) if isinstance(config_terms, dict) else None
    term_files = {Path(rel).stem for rel in terms}
    for rel, (data, body) in pages.items():
        slug = Path(rel).stem
        if data.get("process") != slug:
            out.append(Problem(rel, "/process", "V-02", f"ファイル名（{slug}）と process（{data.get('process')}）が一致しない"))
        if process_slugs is not None and slug not in process_slugs:
            out.append(Problem(rel, "/process", "V-04", f"工程 {slug} が data/supply-chain.yaml にない"))
        for i, ref in enumerate(data.get("terms") or []):
            if ref not in term_files and (known is None or ref not in known):
                out.append(Problem(rel, pointer(["terms", i]), "V-04", f"用語 {ref} が、用語集にも config/explainer-sources.yaml にもない"))
            elif ref not in term_files:
                out.append(Problem(rel, pointer(["terms", i]), "V-04", f"用語 {ref} は、まだ原稿（content/glossary/）がない。公開の前にそろえる",
                                   "warning"))
        reviewed = data.get("basis") == "reviewed"
        if reviewed:
            _reviewed_checks(rel, "processes", slug, data, body, config, names or set(), out)
        elif isinstance(config, dict) and ((config.get("processes") or {}).get(slug) or {}).get("basis") == "reviewed":
            out.append(Problem(rel, "/basis", "V-04", "config/explainer-sources.yaml では basis: reviewed だが、ファイルは basis: reviewed でない", "warning"))
        _body_checks(rel, data, body, _source_roles(config, "processes", slug), out, reviewed)
        if isinstance(data.get("title"), str) and len(data["title"]) > TITLE_MAX:
            out.append(Problem(rel, "/title", "V-12", f"title が {len(data['title'])}字で、目安（{TITLE_MAX}字以内）を外れている", "warning"))
        if isinstance(data.get("description"), str):
            _length_warning(rel, "/description", "description", count_characters([data["description"]]), *DESCRIPTION_LENGTH, out)
    return out


# ---- 理解度チェック（データ定義書 6.11、V-24）と、半導体を学ぶ（データ定義書 6.8） ----

QUIZ_HEADING = "理解度チェック"
QUIZ_MAX = 3
LEARN_LENGTH = (2000, 3000)  # 学習のページの本文の文字数の目安（V-12、データ定義書 6.8）
_QUESTION = re.compile(r"^###[ \t]+問[0-9０-９]+[ \t]*$")
_CHOICE = re.compile(r"^([1-4])\.[ \t]+(\S.*)$")
_ANSWER = re.compile(r"^答え[：:][ \t]*([1-4])$")
_EXPLANATION = re.compile(r"^解説[：:][ \t]*(\S.*)$")


def quiz_split(body: str) -> tuple[str, list[str] | None]:
    """本文を、理解度チェックより前の部分と、チェックの行（見出しの次の行から）に分ける。チェックがなければ None。"""
    lines = body.split("\n")
    for i, line in enumerate(lines):
        if line.strip() == f"## {QUIZ_HEADING}":
            return "\n".join(lines[:i]), lines[i + 1:]
    return body, None


def check_quiz(rel: str, body: str) -> list[Problem]:
    """V-24：理解度チェックの形（1〜3問、選択肢4つ、答えが1〜4、解説がある、見出しが本文の最後）。"""
    _, lines = quiz_split(body)
    if lines is None:
        return []
    out: list[Problem] = []
    at = f"(本文 {QUIZ_HEADING})"
    questions: list[dict] = []
    for raw in lines:
        line = raw.strip()
        if not line:
            continue
        if line.startswith("## ") or line.startswith("# "):
            out.append(Problem(rel, at, "V-24", f"「{QUIZ_HEADING}」の後に見出し（{line}）がある。チェックは本文の最後に置く"))
            return out
        if _QUESTION.match(line):
            questions.append({"prompt": [], "choices": [], "answer": None, "explanation": None})
            continue
        if not questions:
            out.append(Problem(rel, at, "V-24", "最初の問いの前に、`### 問1` の見出しがない"))
            return out
        q = questions[-1]
        if m := _CHOICE.match(line):
            q["choices"].append(int(m.group(1)))
        elif m := _ANSWER.match(line):
            q["answer"] = int(m.group(1))
        elif m := _EXPLANATION.match(line):
            q["explanation"] = m.group(1)
        elif not q["choices"]:
            q["prompt"].append(line)
        else:
            out.append(Problem(rel, at, "V-24", f"問{len(questions)}に、形の決まっていない行がある（{line[:20]}）"))
    if not 1 <= len(questions) <= QUIZ_MAX:
        out.append(Problem(rel, at, "V-24", f"問いが {len(questions)}問ある（1〜{QUIZ_MAX}問）"))
    for n, q in enumerate(questions, 1):
        if not q["prompt"]:
            out.append(Problem(rel, at, "V-24", f"問{n}に、問いの文がない"))
        if q["choices"] != [1, 2, 3, 4]:
            out.append(Problem(rel, at, "V-24", f"問{n}の選択肢が、1〜4の4つになっていない"))
        if q["answer"] is None:
            out.append(Problem(rel, at, "V-24", f"問{n}に「答え：1〜4」がない"))
        if not q["explanation"]:
            out.append(Problem(rel, at, "V-24", f"問{n}に「解説：」がない"))
    return out


PHYSICS_HEADINGS = ["式", "式のどこを見るか", "数値例"]  # 深掘り編のページの本文の見出し（運用ルール書 4.2。4つ目の「基礎編のどこに効くか」は applies_to から作る）


def check_learn(pages: dict[str, tuple[dict, str]], path, supply, terms: dict[str, tuple[dict, str]],
                companies: dict[str, dict], config, names: set[str], root: Path) -> list[Problem]:
    """学習のページ（content/learn/{分野}/{slug}.md）と、並び（content/learn/path.yaml）の検査（データ定義書 6.8）。

    path.yaml は二段で持つ：基礎編の分野（fields）と、深掘り編「半導体の物理」のカード（physics.cards）。
    """
    out: list[Problem] = []
    fields = [f for f in (path or {}).get("fields") or [] if isinstance(f, dict)] if isinstance(path, dict) else []
    physics = (path or {}).get("physics") if isinstance(path, dict) else None
    cards = [c for c in (physics or {}).get("cards") or [] if isinstance(c, dict)] if isinstance(physics, dict) else []
    physics_slugs = {c.get("slug") for c in cards}
    process_slugs = _slugs(supply, "processes")
    term_slugs = {Path(rel).stem for rel in terms}
    company_slugs = {Path(rel).stem for rel in companies}
    page_keys = {(Path(rel).parent.name, Path(rel).stem) for rel in pages}
    if pages and path is None:
        out.append(Problem("content/learn/path.yaml", "", "V-04", "学習のページがあるのに、content/learn/path.yaml がない"))
    labels = [c.get("label") for c in cards]
    if labels != [chr(ord("A") + i) for i in range(len(cards))]:
        out.append(Problem("content/learn/path.yaml", "/physics/cards", "V-02", "physics のカードの label は、並びの順に A、B、C… と付ける"))
    listed: set[tuple[str, str]] = set()  # path.yaml に並べた学習のページ（フォルダ、slug）
    listed_in_physics: set[tuple[str, str]] = set()
    seen: set[tuple[str, str, str]] = set()
    groups_of_path = [(["fields", i], field) for i, field in enumerate(fields)] + [(["physics", "cards", i], card) for i, card in enumerate(cards)]
    for base_at, field in groups_of_path:
        in_physics = base_at[0] == "physics"
        # 分野の units と、小分け（sections）の units を、この順で見る（データ定義書 6.8）
        groups = [([*base_at, "units"], field.get("units") or [])]
        section_slugs: set[str] = set()
        for k, section in enumerate(field.get("sections") or []):
            if not isinstance(section, dict):
                continue
            if section.get("slug") in section_slugs:
                out.append(Problem("content/learn/path.yaml", pointer([*base_at, "sections", k, "slug"]), "V-03",
                                   f"同じ小分けの slug（{section.get('slug')}）が重複している"))
            section_slugs.add(section.get("slug"))
            groups.append(([*base_at, "sections", k, "units"], section.get("units") or []))
        for base, units in groups:
            for j, unit in enumerate(units):
                if not isinstance(unit, dict):
                    continue
                kind, ref = unit.get("type"), unit.get("ref")
                folder = unit.get("folder") or field.get("slug")
                key = (kind, folder if kind == "learn" else "", ref)
                at = pointer([*base, j])
                if key in seen:
                    out.append(Problem("content/learn/path.yaml", at, "V-03", f"同じ単元（{kind} {ref}）が重複している（1つの単元は1か所にだけ並べる）"))
                seen.add(key)
                if in_physics and (kind != "learn" or folder not in physics_slugs):
                    out.append(Problem("content/learn/path.yaml", at, "V-02",
                                       "physics のカードには、深掘り編のフォルダ（physics のカードの slug）にある学習のページだけを並べる"))
                if kind == "learn":
                    listed.add((folder, ref))
                    if in_physics:
                        listed_in_physics.add((folder, ref))
                    if (folder, ref) not in page_keys:
                        out.append(Problem("content/learn/path.yaml", at, "V-04", f"学習のページ content/learn/{folder}/{ref}.md がない"))
                elif kind == "process" and process_slugs is not None and ref not in process_slugs:
                    out.append(Problem("content/learn/path.yaml", at, "V-04", f"工程 {ref} が data/supply-chain.yaml にない"))
                elif kind == "term" and ref not in term_slugs:
                    out.append(Problem("content/learn/path.yaml", at, "V-04", f"用語 {ref} の原稿（content/glossary/）がない"))
    for rel, (data, body) in pages.items():
        folder, slug = Path(rel).parent.name, Path(rel).stem
        is_physics = folder in physics_slugs or (folder, slug) in listed_in_physics
        applies = [a for a in data.get("applies_to") or [] if isinstance(a, dict)]
        if is_physics:
            # 深掘り編のページ：本文は「式／式のどこを見るか／数値例」の3つの見出し、基礎編への接続（applies_to）を必ず持つ（運用ルール書 4.2）
            if folder not in physics_slugs:
                out.append(Problem(rel, "", "V-02", "深掘り編のページは、physics のカードの slug と同じフォルダに置く"))
            headings = [h for level, h, _ in split_body(quiz_split(body)[0])[0][1:] if level == 2]
            if headings != PHYSICS_HEADINGS:
                out.append(Problem(rel, "(本文)", "V-10", "深掘り編のページの本文の見出しは、「" + "」「".join(PHYSICS_HEADINGS) + "」の順の3つにする"))
            if not applies:
                out.append(Problem(rel, "/applies_to", "V-04", "深掘り編のページには、基礎編のどこに効くか（applies_to）を1件以上書く"))
            if data.get("basis") == "reviewed":
                out.append(Problem(rel, "/basis", "V-01", "深掘り編のページは、数値例に出典が要るため、basis: reviewed にしない"))
        elif applies:
            out.append(Problem(rel, "/applies_to", "V-01", "applies_to は、深掘り編のページだけが持つ"))
        for k, a in enumerate(applies):
            kind, ref, at = a.get("type"), a.get("ref"), pointer(["applies_to", k])
            if kind == "learn":
                target = a.get("folder")
                if not target:
                    out.append(Problem(rel, at, "V-04", "applies_to の learn には、相手のページのフォルダ（folder）を書く"))
                elif (target, ref) not in page_keys:
                    out.append(Problem(rel, at, "V-04", f"学習のページ content/learn/{target}/{ref}.md がない"))
                elif target in physics_slugs:
                    out.append(Problem(rel, at, "V-02", "applies_to には、基礎編のページを書く（深掘り編のページどうしは指さない）"))
            elif kind == "process" and process_slugs is not None and ref not in process_slugs:
                out.append(Problem(rel, at, "V-04", f"工程 {ref} が data/supply-chain.yaml にない"))
            elif kind == "term" and ref not in term_slugs:
                out.append(Problem(rel, at, "V-04", f"用語 {ref} の原稿（content/glossary/）がない"))
        if data.get("field") != folder:
            out.append(Problem(rel, "/field", "V-02", f"置き場所のフォルダ（{folder}）と field（{data.get('field')}）が一致しない"))
        if (folder, slug) not in listed:
            out.append(Problem(rel, "", "V-04", "content/learn/path.yaml の units に、このページがない（一覧に出ない）", "warning"))
        for key, known, label in (("processes", process_slugs, "工程"), ("related_terms", term_slugs, "用語"), ("companies", company_slugs, "企業")):
            for k, ref in enumerate(data.get(key) or []):
                if known is not None and ref not in known:
                    out.append(Problem(rel, pointer([key, k]), "V-04", f"{label} {ref} がない"))
        if not (root / "src" / "figures" / "learn" / folder / f"{slug}.astro").is_file():
            out.append(Problem(rel, "(図)", "V-24", f"図（src/figures/learn/{folder}/{slug}.astro）がない。学習のページには図を1つ以上置く"))
        if quiz_split(body)[1] is None:
            out.append(Problem(rel, "(本文)", "V-24", f"本文の最後に「{QUIZ_HEADING}」がない"))
        reviewed = data.get("basis") == "reviewed"
        if reviewed:
            _reviewed_checks(rel, "learn", slug, data, body, config, names, out)
        _body_checks(rel, data, body, _source_roles(config, "learn", slug), out, reviewed)
        _length_warning(rel, "(本文)", "本文", count_characters(split_body(quiz_split(body)[0])[1]), *LEARN_LENGTH, out)
        if isinstance(data.get("description"), str):
            _length_warning(rel, "/description", "description", count_characters([data["description"]]), *DESCRIPTION_LENGTH, out)
    return out


# ---- IR重要ポイント（データ定義書 6.3、要求定義書 FR-307、LG-06） ----

IR_HEADINGS = [("業績の要点", 100), ("今期見通し", 80), ("注目材料", 70)]  # 見出しと字数の上限（CLAUDE.md 6.2）
IR_FILE = re.compile(r"([0-9]{4}-[0-9]{2})-q([1-4])")


def _domain(url: str) -> str:
    return urllib.parse.urlsplit(url).hostname or ""


def _allowed(domain: str, allowed: set[str]) -> bool:
    return any(domain == d or domain.endswith("." + d) for d in allowed)


def check_ir_points(points: dict[str, tuple[dict, str]], companies: dict[str, dict], segments: dict[str, dict],
                    autos: dict[str, dict], sources_config) -> list[Problem]:
    """IR重要ポイントの検査（スキーマで確かめられない整合）。draft: true も検査する。"""
    out: list[Problem] = []
    by_slug = {(d.get("slug") if isinstance(d.get("slug"), str) else Path(rel).stem): d for rel, d in companies.items() if isinstance(d, dict)}
    seg_by = {d.get("company"): d for d in segments.values()}
    auto_by = {Path(rel).stem: d for rel, d in autos.items() if isinstance(d, dict)}
    ir_list = (sources_config or {}).get("ir") if isinstance(sources_config, dict) else None
    fixed = {e.get("domain") for e in ir_list or [] if isinstance(e, dict) and e.get("domain")}
    if sources_config is None:
        out.append(Problem("config/sources.yaml", "", "V-04", "IR重要ポイントがあるのに、config/sources.yaml（IR用の許可の一覧）がない"))
    for rel, (data, body) in points.items():
        folder, stem = Path(rel).parent.name, Path(rel).stem
        match = IR_FILE.fullmatch(stem)
        if not match:
            out.append(Problem(rel, "", "V-02", "ファイル名は {fiscal_period_end}-q{quarter}.md の形にする（例：2026-03-q2.md）"))
        else:
            if data.get("fiscal_period_end") != match.group(1):
                out.append(Problem(rel, "/fiscal_period_end", "V-02", f"ファイル名の決算期（{match.group(1)}）と fiscal_period_end が一致しない"))
            if data.get("quarter") != int(match.group(2)):
                out.append(Problem(rel, "/quarter", "V-02", f"ファイル名の四半期（q{match.group(2)}）と quarter が一致しない"))
        if data.get("company") != folder:
            out.append(Problem(rel, "/company", "V-02", f"置き場所のフォルダ（{folder}）と company（{data.get('company')}）が一致しない"))
        company = by_slug.get(data.get("company"))
        if company is None:
            out.append(Problem(rel, "/company", "V-04", f"企業 {data.get('company')} が企業マスタにない"))
        else:
            if company.get("listing") != "detailed":
                out.append(Problem(rel, "/company", "V-04", "IR重要ポイントは、詳細掲載の企業だけに作る"))
            if company.get("type") == "foreign_subsidiary":
                out.append(Problem(rel, "/company", "V-04", "外資系日本法人には、IR重要ポイントを作らない"))
        announcements = (auto_by.get(folder) or {}).get("announcements") or []
        same = [a for a in announcements if isinstance(a, dict) and a.get("fiscal_period_end") == data.get("fiscal_period_end")
                and a.get("quarter") == data.get("quarter")]
        if same and data.get("announced_on") not in {a.get("announced_on") for a in same}:
            out.append(Problem(rel, "/announced_on", "V-09", "announced_on が、自動取得のデータの announcements（同じ決算期・四半期）の決算発表日と一致しない"))

        sections, _ = split_body(body)
        headings = [(level, text) for level, text, _ in sections[1:]]
        expected = [h for h, _ in IR_HEADINGS]
        if [t for _, t in headings] != expected or any(level != 2 for level, _ in headings):
            found = " / ".join("#" * level + " " + text for level, text in headings) or "なし"
            out.append(Problem(rel, "(本文)", "V-10", "本文の見出しは「## 業績の要点」「## 今期見通し」「## 注目材料」の3つだけで、この順にする"
                               f"（実際：{found[:200]}）"))
        if any(line.strip() for line in sections[0][2]):
            out.append(Problem(rel, "(本文)", "V-10", "最初の見出しより前に文章がある。本文は3つの見出しの下だけに書く"))
        limits = dict(IR_HEADINGS)
        for level, text, lines in sections[1:]:
            if text in limits:
                n = count_characters(lines)
                if n == 0:
                    out.append(Problem(rel, "(本文)", "V-12", f"「{text}」の下に文章がない"))
                elif n > limits[text]:
                    out.append(Problem(rel, "(本文)", "V-12", f"「{text}」が {n}字で、上限（{limits[text]}字）を超えている（FR-307）"))

        allowed = set(fixed)
        if company:
            allowed |= {_domain(company[k]) for k in ("ir_url", "website_url") if isinstance(company.get(k), str)}
        for k, src in enumerate(data.get("sources") or []):
            url = (src or {}).get("url") if isinstance(src, dict) else None
            if isinstance(url, str) and not _allowed(_domain(url), allowed):
                out.append(Problem(rel, pointer(["sources", k, "url"]), "V-04",
                                   f"出典の発行元（{_domain(url)}）が、IR用の許可の一覧（config/sources.yaml の ir と、企業の ir_url・website_url）にない（LG-06）"))

        if company and company.get("type") == "conglomerate":
            names = [sg.get("name") for sg in (seg_by.get(folder) or {}).get("segments") or []
                     if isinstance(sg, dict) and sg.get("classification") in ("semiconductor", "partial") and sg.get("name")]
            if names and not any(n in body for n in names):
                out.append(Problem(rel, "(本文)", "V-12", f"総合メーカーのIR重要ポイントで、半導体関連のセグメント（{'、'.join(names[:3])}）に触れていない（FR-307）",
                                   "warning"))
    return out


# ---- 技術系のイベント（データ定義書 4.6、V-22、V-23） ----

EVENT_RECHECK_DAYS = 90  # 開催の90日前に、公式ページで日程の変更を確かめる（運用ルール書 4.9）


def build_date() -> date:
    """検査の基準の日。環境変数 BUILD_DATE（YYYY-MM-DD）があればその日、なければ今日（日本時間）。"""
    value = os.environ.get("BUILD_DATE", "")
    try:
        return date.fromisoformat(value)
    except ValueError:
        return datetime.datetime.now(datetime.timezone(datetime.timedelta(hours=9))).date()


def check_events(data: dict, today: date | None = None) -> list[Problem]:
    rel = "data/events.yaml"
    out: list[Problem] = []
    today = today or build_date()
    source_ids = _source_ids(data, rel, out)
    seen: set[str] = set()
    for i, event in enumerate(data.get("events") or []):
        if not isinstance(event, dict):
            continue
        at = ["events", i]
        if event.get("id") in seen:
            out.append(Problem(rel, pointer(at + ["id"]), "V-22", f"id {event.get('id')} が重複している"))
        seen.add(event.get("id"))
        try:
            start, end = date.fromisoformat(str(event.get("start_date"))), date.fromisoformat(str(event.get("end_date")))
            checked = date.fromisoformat(str(event.get("checked_on")))
        except ValueError:
            continue  # 日付の形は、スキーマ（V-01）が見る
        if end < start:
            out.append(Problem(rel, pointer(at + ["end_date"]), "V-22", "end_date が start_date より前"))
        if event.get("source") not in source_ids:
            out.append(Problem(rel, pointer(at + ["source"]), "V-07", f"source {event.get('source')} が sources にない"))
        recheck = start - timedelta(days=EVENT_RECHECK_DAYS)
        if today >= recheck and checked < recheck and end >= today:
            out.append(Problem(rel, pointer(at + ["checked_on"]), "V-23",
                               f"開催の{EVENT_RECHECK_DAYS}日前を過ぎたが、日程を確かめた日（{checked}）がそれより前のまま", "warning"))
    return out


# ---- ニュースと、config/news.yaml（データ定義書 6.2、7.3） ----

# ---- テーマ（データ定義書 6.7、運用ルール書 4.6） ----

THEME_HEADINGS = ["要旨", "市場の動き", "バリューチェーン", "日本企業の位置", "論点と今後の注目点"]  # 6.7（V-10）
THEME_VIEW_HEADINGS = ["発表元の見方", "本サイトの見方"]  # 「論点と今後の注目点」の小見出し（V-10）
THEME_SUMMARY_ITEMS = 3  # 要旨の箇条書きの数（V-10）
THEME_FIGURES = ("market", "value-chain")  # src/figures/theme/{slug}-{名前}.astro（V-25）
THEME_LENGTH = (3000, 5000)  # 本文の文字数の目安（V-12）
THEME_OTHERS_MAX = 10  # 掲載企業の外の企業の上限（暫定。V-25）


def check_themes(themes: dict[str, tuple[dict, str]], companies: dict[str, dict], supply,
                 terms: dict[str, tuple[dict, str]], learn_pages: dict[str, tuple[dict, str]], root: Path | None = None) -> list[Problem]:
    """テーマの検査（V-02、V-04、V-07、V-08、V-10、V-12、V-25）。draft: true も検査する。"""
    out: list[Problem] = []
    company_slugs = {(d.get("slug") if isinstance(d.get("slug"), str) else Path(rel).stem) for rel, d in companies.items()}
    process_slugs = _slugs(supply, "processes")
    term_slugs = {Path(rel).stem for rel in terms}
    learn_keys = {(Path(rel).parent.name, Path(rel).stem) for rel in learn_pages}
    for rel, (data, body) in themes.items():
        slug = Path(rel).stem
        if data.get("theme") != slug:
            out.append(Problem(rel, "/theme", "V-02", f"ファイル名（{slug}）と theme（{data.get('theme')}）が一致しない"))
        source_ids = _source_ids(data, rel, out)
        seen: set[str] = set()
        others = 0
        groups = data.get("groups") if isinstance(data.get("groups"), list) else []
        for g, group in enumerate(groups):
            if not isinstance(group, dict):
                continue
            ref = group.get("process")
            if isinstance(ref, str) and process_slugs is not None and ref not in process_slugs:
                out.append(Problem(rel, pointer(["groups", g, "process"]), "V-04", f"工程 {ref} が data/supply-chain.yaml にない"))
            for key in ("companies", "others"):
                for i, entry in enumerate(group.get(key) or []):
                    if not isinstance(entry, dict):
                        continue
                    if key == "companies":
                        name = entry.get("company")
                        if isinstance(name, str) and name not in company_slugs:
                            out.append(Problem(rel, pointer(["groups", g, key, i, "company"]), "V-04", f"企業 {name} が企業マスタにない"))
                    else:
                        others += 1
                        name = entry.get("name")
                    if isinstance(name, str):
                        if name in seen:
                            out.append(Problem(rel, pointer(["groups", g, key, i]), "V-25", f"{name} が、テーマの中で2回以上載っている"))
                        seen.add(name)
                    for b, basis in enumerate(entry.get("basis") or []):
                        if isinstance(basis, str) and basis not in source_ids:
                            out.append(Problem(rel, pointer(["groups", g, key, i, "basis", b]), "V-25", f"根拠の {basis} が sources にない"))
        if others > THEME_OTHERS_MAX:
            out.append(Problem(rel, "/groups", "V-25", f"掲載企業の外の企業が {others}社で、目安（{THEME_OTHERS_MAX}社まで）を超えている", "warning"))
        for i, ref in enumerate(data.get("processes") or []):
            if isinstance(ref, str) and process_slugs is not None and ref not in process_slugs:
                out.append(Problem(rel, pointer(["processes", i]), "V-04", f"工程 {ref} が data/supply-chain.yaml にない"))
        for i, ref in enumerate(data.get("terms") or []):
            if isinstance(ref, str) and ref not in term_slugs:
                out.append(Problem(rel, pointer(["terms", i]), "V-04", f"用語 {ref} が content/glossary/ にない"))
        for i, unit in enumerate(data.get("learn") or []):
            if isinstance(unit, dict) and (unit.get("folder"), unit.get("ref")) not in learn_keys:
                out.append(Problem(rel, pointer(["learn", i]), "V-04", f"学習のページ {unit.get('folder')}/{unit.get('ref')} が content/learn/ にない"))

        sections, outside = split_body(body)
        headings = [(level, text) for level, text, _ in sections[1:]]
        if [t for level, t in headings if level == 2] != THEME_HEADINGS or any(level not in (2, 3) for level, _ in headings):
            found = " / ".join("#" * level + " " + text for level, text in headings) or "なし"
            out.append(Problem(rel, "(本文)", "V-10", "本文の中見出しは「## 要旨」「## 市場の動き」「## バリューチェーン」「## 日本企業の位置」"
                               f"「## 論点と今後の注目点」の5つで、この順にする（実際：{found[:200]}）"))
        subs = [text for level, text in headings if level == 3]
        last = next((i for i, (level, text) in enumerate(headings) if level == 2 and text == THEME_HEADINGS[-1]), None)
        view_subs = [text for level, text in headings[last + 1:] if level == 3] if last is not None else []
        if view_subs != THEME_VIEW_HEADINGS or len(subs) != len(view_subs):
            out.append(Problem(rel, "(本文)", "V-10", "小見出し（###）は、「論点と今後の注目点」の下の「発表元の見方」「本サイトの見方」の2つだけで、この順にする"))
        summary = next((lines for level, text, lines in sections[1:] if level == 2 and text == THEME_HEADINGS[0]), None)
        if summary is not None:
            items = [line for line in summary if line.strip()]
            if len(items) != THEME_SUMMARY_ITEMS or not all(re.match(r"^\s*[-*]\s+\S", line) for line in items):
                out.append(Problem(rel, "(本文)", "V-10", f"要旨は、{THEME_SUMMARY_ITEMS}つの箇条書き（`- `）だけにする"))
        if any(line.strip() for line in sections[0][2]):
            out.append(Problem(rel, "(本文)", "V-10", "最初の見出しより前に文章がある。本文は5つの中見出しの下だけに書く"))
        if root is not None:
            for name in THEME_FIGURES:
                if not (root / "src" / "figures" / "theme" / f"{slug}-{name}.astro").is_file():
                    out.append(Problem(rel, "(図)", "V-25", f"図 src/figures/theme/{slug}-{name}.astro がない",
                                       "warning" if data.get("draft") is True else "error"))
        count = count_characters([line for _, _, lines in sections[1:] for line in lines])
        _length_warning(rel, "(本文)", "本文", count, *THEME_LENGTH, out)
        cited = set(_CITATION.findall("\n".join(outside)))
        for number in sorted(cited - source_ids, key=lambda n: int(n[1:])):
            out.append(Problem(rel, "(本文)", "V-07", f"本文の [{number}] が、sources にない"))
        used = cited | {b for group in groups if isinstance(group, dict) for key in ("companies", "others")
                        for entry in group.get(key) or [] if isinstance(entry, dict) for b in entry.get("basis") or []}
        for i, source in enumerate(data.get("sources") or []):
            if isinstance(source, dict) and isinstance(source.get("id"), str) and source["id"] not in used:
                out.append(Problem(rel, pointer(["sources", i, "id"]), "V-08", f"sources の {source['id']} が、本文でも企業の根拠でも使われていない",
                                   "warning"))
        if isinstance(data.get("description"), str):
            _length_warning(rel, "/description", "description", count_characters([data["description"]]), *DESCRIPTION_LENGTH, out)
    return out


NEWS_HEADINGS = ["何が起きたか", "なぜ重要か", "関係する企業・工程とサプライチェーン上の位置"]  # 6.2
NEWS_LENGTH = (400, 700)  # 本文の文字数の目安（V-12）
NEWS_FILE = re.compile(r"([0-9]{4})-([0-9]{2})-([a-z0-9]+(?:-[a-z0-9]+)*)")
X_POST_MAX = 140
X_URL_LENGTH = 23  # Xは、URLを23字と数える
X_HASHTAG_MAX = 2
_URL = re.compile(r"https?://\S+")
_HASHTAG = re.compile(r"[#＃](?=[^\s#＃])")


def x_post_length(text: str) -> int:
    """Xの投稿文の字数。URLは、長さにかかわらず23字と数える。"""
    return len(_URL.sub("x" * X_URL_LENGTH, text))


def x_post_hashtags(text: str) -> int:
    return len(_HASHTAG.findall(_URL.sub("", text)))  # URLの中の # は、ハッシュタグではない


def _company_display_names(data: dict) -> set[str]:
    return {_name_key(n) for n in [data.get("name"), *(data.get("short_names") or [])] if isinstance(n, str) and n.strip()}


def check_news(news: dict[str, tuple[dict, str]], companies: dict[str, dict], supply, themes: set[str] | None = None) -> list[Problem]:
    """ニュースの検査（スキーマで確かめられない整合）。draft: true も検査する。themes は content/themes/ のテーマの slug（None は確かめない）。"""
    out: list[Problem] = []
    company_slugs = {(d.get("slug") if isinstance(d.get("slug"), str) else Path(rel).stem): d for rel, d in companies.items()}
    process_slugs = _slugs(supply, "processes")
    for rel, (data, body) in news.items():
        stem = Path(rel).stem
        match = NEWS_FILE.fullmatch(stem)
        if not match:
            out.append(Problem(rel, "", "V-02", "ファイル名は {yyyy}-{mm}-{slug}.md の形にする（slug は英小文字・数字・ハイフン）"))
        published = data.get("published_at")
        if match and isinstance(published, str) and re.fullmatch(r"[0-9]{4}-[0-9]{2}-[0-9]{2}", published) \
                and published[:7] != f"{match.group(1)}-{match.group(2)}":
            out.append(Problem(rel, "/published_at", "V-09",
                               f"ファイル名の年月（{match.group(1)}-{match.group(2)}）と published_at の年月（{published[:7]}）が一致しない"))

        sections, outside = split_body(body)
        headings = [(level, text) for level, text, _ in sections[1:]]
        if any(level == 1 for level, _ in headings):
            out.append(Problem(rel, "(本文)", "V-10", "`#`（大見出し）がある。本文は `##` から始める"))
        if [t for _, t in headings] != NEWS_HEADINGS or any(level != 2 for level, _ in headings):
            found = " / ".join("#" * level + " " + text for level, text in headings) or "なし"
            out.append(Problem(rel, "(本文)", "V-10", "本文の見出しは「## 何が起きたか」「## なぜ重要か」"
                               "「## 関係する企業・工程とサプライチェーン上の位置」の3つだけで、この順にする"
                               f"（実際：{found[:200]}）"))
        if any(line.strip() for line in sections[0][2]):
            out.append(Problem(rel, "(本文)", "V-10", "最初の見出しより前に文章がある。本文は3つの見出しの下だけに書く"))
        count = count_characters([line for _, _, lines in sections[1:] for line in lines])
        low, high = NEWS_LENGTH
        if not low <= count <= high:
            out.append(Problem(rel, "(本文)", "V-12", f"本文が {count}字で、目安（{low}〜{high}字）を外れている", "warning"))

        tags = data.get("tags") if isinstance(data.get("tags"), dict) else {}
        tag_companies = [c for c in tags.get("companies") or [] if isinstance(c, str)]
        for i, ref in enumerate(tags.get("companies") or []):
            if isinstance(ref, str) and ref not in company_slugs:
                out.append(Problem(rel, pointer(["tags", "companies", i]), "V-04", f"企業 {ref} が企業マスタにない"))
        if process_slugs is not None:
            for i, ref in enumerate(tags.get("processes") or []):
                if isinstance(ref, str) and ref not in process_slugs:
                    out.append(Problem(rel, pointer(["tags", "processes", i]), "V-04", f"工程 {ref} が data/supply-chain.yaml にない"))
        if themes is not None:
            for i, ref in enumerate(tags.get("themes") or []):
                if isinstance(ref, str) and ref not in themes:
                    out.append(Problem(rel, pointer(["tags", "themes", i]), "V-04", f"テーマ {ref} が content/themes/ にない"))
        if data.get("overseas") is True:
            if not tag_companies:
                # 資料から日本企業との関わりが言えないときは、企業を無理に付けない。警告にとどめ、運営者が判断する
                out.append(Problem(rel, "/tags/companies", "V-13", "overseas: true だが企業のタグがない。資料から日本企業との関わりが言えるなら、"
                                   "企業のタグと3つ目の見出しの記述を足す", "warning"))
            else:
                third = next((lines for level, text, lines in sections[1:] if text == NEWS_HEADINGS[2] and level == 2), None)
                if third is not None:
                    text = _name_key("\n".join(third))
                    names = {n for c in tag_companies if c in company_slugs for n in _company_display_names(company_slugs[c])}
                    if not any(n in text for n in names):
                        out.append(Problem(rel, "(本文)", "V-13", "overseas: true のニュースは、3つ目の見出しの下に、"
                                           "tags.companies の企業の略称か正式名称を1社以上書く"))

        post = data.get("x_post")
        if isinstance(post, str):
            if x_post_length(post) > X_POST_MAX:
                out.append(Problem(rel, "/x_post", "V-11", f"x_post が {x_post_length(post)}字で、{X_POST_MAX}字（URLは{X_URL_LENGTH}字）を超えている"))
            if x_post_hashtags(post) > X_HASHTAG_MAX:
                out.append(Problem(rel, "/x_post", "V-11", f"x_post のハッシュタグが {x_post_hashtags(post)}個で、{X_HASHTAG_MAX}個までである"))
    return out


def check_news_config(config: dict, companies: dict[str, dict]) -> list[Problem]:
    """config/news.yaml の検査（スキーマで確かめられない整合）。"""
    rel = "config/news.yaml"
    out: list[Problem] = []
    for category, row in (config.get("weekly_targets") or {}).items():
        if isinstance(row, dict) and isinstance(row.get("min"), int) and isinstance(row.get("max"), int) and row["min"] > row["max"]:
            out.append(Problem(rel, pointer(["weekly_targets", category]), "V-01", "min が max より大きい"))
    company_slugs = {(d.get("slug") if isinstance(d.get("slug"), str) else Path(r).stem) for r, d in companies.items()}
    seen: set[str] = set()
    for i, source in enumerate(config.get("sources") or []):
        if not isinstance(source, dict):
            continue
        if isinstance(source.get("id"), str):
            if source["id"] in seen:
                out.append(Problem(rel, pointer(["sources", i, "id"]), "V-03", f"sources の id {source['id']} が重複している"))
            seen.add(source["id"])
        if isinstance(source.get("company"), str) and source["company"] not in company_slugs:
            out.append(Problem(rel, pointer(["sources", i, "company"]), "V-04", f"企業 {source['company']} が企業マスタにない"))
    return out


def parse_args(argv: list[str]) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="データの形式の検証（引数なしで、リポジトリ全体）")
    parser.add_argument("--path", type=Path, metavar="FILE", help="1ファイルだけ検査する")
    parser.add_argument("--strict", action="store_true", help="警告も、エラーとして扱う（終了コードを1にする）")
    return parser.parse_args(argv)


def main(argv: list[str] | None = None, *, root: Path = REPO_ROOT, schema_root: Path = REPO_ROOT) -> int:
    args = parse_args(sys.argv[1:] if argv is None else argv)
    only = None
    if args.path is not None:
        only = args.path if args.path.is_absolute() else Path.cwd() / args.path
        if kind_of(only, root) is None or not only.is_file():
            print(f"error: 検査の対象のファイルではない、またはない: {args.path}", file=sys.stderr)
            return 2
    try:
        problems = validate(root, schema_root, only)
    except (OSError, ValueError) as error:
        print(f"error: 検査を始められない（{type(error).__name__}）", file=sys.stderr)
        return 2
    files = collect_files(root) if only is None else [(kind_of(only, root), only)]
    errors = [p for p in problems if p.severity == "error" or args.strict]
    for problem in problems:
        print(problem)
    print(f"検査したファイル {len(files)}件 / エラー {len([p for p in problems if p.severity == 'error'])}件"
          f" / 警告 {len([p for p in problems if p.severity == 'warning'])}件")
    return 1 if errors else 0


if __name__ == "__main__":
    sys.exit(main())
