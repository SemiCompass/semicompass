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
import re
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
    for kind, rel in (("supply-chain", "data/supply-chain.yaml"), ("xbrl-map", "config/xbrl-map.yaml")):
        if (root / rel).is_file():
            files.append((kind, root / rel))
    return files


def validate(root: Path = REPO_ROOT, schema_root: Path = REPO_ROOT, only: Path | None = None) -> list[Problem]:
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
            elif kind == "overview":
                data, pitfalls, bodies[rel] = load_markdown(path)
            else:
                data, pitfalls = load_yaml(path)
        except ValueError as error:
            problems.append(Problem(rel, "", "V-01", str(error)))
            continue
        loaded[rel] = (kind, path, data)
        problems += [Problem(rel, p, rule, msg) for p, rule, msg in pitfalls]
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
