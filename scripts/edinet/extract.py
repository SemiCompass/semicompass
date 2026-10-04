"""EDINETの書類（CSV）の行から、データ定義書5章の形（5.4 financials、5.5 employees）の値を取り出す。

純粋な関数だけで、ネットワークも、ファイルも使わない。規則は config/xbrl-map.yaml の先頭のコメント
（段階3で使う規則）が正で、ここに実装で決めたことを足している。

入力：CSVの行（列名のままの値の辞書の並び。文章の行、DEIの行も含める）、doc_id、ingested_at（日本時間の文字列）、
config/xbrl-map.yaml の内容（辞書）。
出力：financial（1行）、employee（1行。有価証券報告書のときだけ）、anomalies（異常の一覧）、
notes（使わなかった行などの情報）、trace（画面に出す、取り出した値の元の値と換算後の値）、dei（読んだDEIの値）、
stopped（DEIが読めず、取り出しを止めたか）。

実装で決めたこと：
* DEIの値が未知（会計基準、期間の種類）、読めない（連結の有無、日付）、欠けている、食い違うときは、
  異常にして、取り出しを止める（推測で続けない）
* 売上高などの当期の値は、コンテキストIDが当期の期間（CurrentYearDuration、InterimDuration）に完全に
  一致する行から、会計基準の候補の要素を先頭から順に探して、最初の行を使う。連結か単体かは、DEIの連結の有無で決め、
  行の選び方は変えない（連結の値も、連結財務諸表がない会社の値も、Member を含まないコンテキストの行）
* 見つからない項目は value を null にし、element と context は "(not_found)" にする（スキーマが、
  reported_value の element と context を必須にしているため）。expected_absent の項目は異常にしない
* 同じ要素・コンテキストの数値の行が、違う値で複数あるときは、先頭の行を使い、異常にする
* 単位：金額は、CSVの「単位」の列（円など）から original_unit を決め、百万円に換算する（Decimalで、丸めない）。
  平均年間給与は円のまま。人と年は、単位の列が空の行なので、要素の種類で決める。未知の単位は、異常にして null にする
"""

from __future__ import annotations

import re
from datetime import date
from decimal import Decimal, InvalidOperation

NOT_FOUND = "(not_found)"
DEI_KEYS = ("accounting_standard", "consolidated", "period_type", "fiscal_year_start", "period_end",
            "fiscal_year_end")
# CSVの列名（実際のヘッダー行の見出し）の候補。inspect_document.COLUMN_ALIASES と同じ（テストで一致を確かめる）
COLUMN_ALIASES = {
    "element": ("要素ID", "elementid"),
    "label": ("項目名",),
    "context": ("コンテキストID", "contextid"),
    "consolidated_column": ("連結・個別", "連結個別"),
    "unit": ("単位", "unit"),
    "value": ("値", "value"),
}
UNIT_ID_COLUMN = ("ユニットID", "unitid")
ORIGINAL_UNITS = {"円": "yen", "千円": "thousand_yen", "百万円": "million_yen"}
UNIT_IDS = {"JPY": "yen"}
SCALE_TO_MILLION = {"yen": -6, "thousand_yen": -3, "million_yen": 0}  # 百万円にするための、10のべき
SCALE_TO_YEN = {"yen": 0, "thousand_yen": 3, "million_yen": 6}
PREFIX_PATTERN = re.compile(r"^jpcrp\d+-[a-z]+_E\d{5}-\d{3}")  # 会社固有の前置き
MEMBER_PATTERN = re.compile(r"^[A-Za-z0-9]+Member$")
TOTAL_MEMBER = "TotalOfReportableSegmentsAndOthersMember"
REPORTABLE_MEMBER = "ReportableSegmentsMember"  # IFRSの、報告セグメントの合計（ソニー）
RECONCILING_MEMBER = "ReconcilingItemsMember"
# セグメントの一覧から除くメンバー。名前の完全一致で判定する（OtherReportableSegmentsMember などは除かない）
NOT_SEGMENT_MEMBERS = frozenset({TOTAL_MEMBER, REPORTABLE_MEMBER, RECONCILING_MEMBER})
NON_CONSOLIDATED_MEMBER = "NonConsolidatedMember"
NUMBER_PATTERN = re.compile(r"^[+-]?(\d+(\.\d*)?|\.\d+)$")
LABEL_NOISE = re.compile(r"[（(](IFRS|US ?GAAP)[）)]")
CONTEXTS = {  # period_type → (期間のコンテキスト、時点のコンテキスト)
    "annual": ("CurrentYearDuration", "CurrentYearInstant"),
    "half": ("InterimDuration", "InterimInstant"),
}
PRIOR_CONTEXTS = {  # 前期の列。period_type → (期間のコンテキスト、時点のコンテキスト)
    "annual": ("Prior1YearDuration", "Prior1YearInstant"),
    "half": ("Prior1InterimDuration", "Prior1InterimInstant"),
}


def _norm(name: str) -> str:
    return re.sub(r"\s+", "", name).lstrip("﻿").lower()


def prepare_rows(rows: list[dict]) -> list[dict]:
    """列名のままの辞書を、役割（element、label、context、unit、unit_id、value）の辞書にする。"""
    prepared = []
    roles: dict[str, str] | None = None
    for row in rows:
        if roles is None:
            normalized = {_norm(k): k for k in row}
            roles = {}
            for role, aliases in {**COLUMN_ALIASES, "unit_id": UNIT_ID_COLUMN}.items():
                for alias in aliases:
                    if _norm(alias) in normalized:
                        roles[role] = normalized[_norm(alias)]
                        break
            for needed in ("element", "context", "value"):
                if needed not in roles:
                    raise ValueError(f"列名に {needed}（要素ID、コンテキストID、値）がない。実際の列名: {', '.join(row)}")
        prepared.append({role: (row.get(key) or "") for role, key in roles.items()})
    return prepared


def parse_decimal(text: str) -> Decimal | None:
    """数値の文字列を Decimal にする（桁区切りのカンマを除く）。数値でなければ None。"""
    cleaned = (text or "").strip().replace(",", "")
    if not NUMBER_PATTERN.match(cleaned):
        return None
    try:
        return Decimal(cleaned)
    except InvalidOperation:
        return None


def json_number(value: Decimal) -> tuple[int | float, bool]:
    """Decimal をJSONの数にする。割り切れる値は整数。(数, 精度を失わなかったか) を返す。"""
    if value == value.to_integral_value():
        return int(value), True
    number = float(value)
    return number, Decimal(repr(number)) == value


class _Extraction:
    def __init__(self, doc_id: str, ingested_at: str):
        self.doc_id = doc_id
        self.ingested_at = ingested_at
        self.anomalies: list[dict] = []
        self.notes: list[str] = []
        self.trace: list[dict] = []

    def anomaly(self, code: str, message: str, item: str | None = None) -> None:
        entry = {"code": code, "message": message}
        if item:
            entry["item"] = item
        self.anomalies.append(entry)

    def find(self, rows: list[dict], elements: list[str], context: str, item: str) -> dict | None:
        """elements を先頭から順に探し、コンテキストが完全に一致する数値の行の、最初の行を返す。"""
        for element in elements:
            hits = [r for r in rows if r["element"] == element and r["context"] == context
                    and parse_decimal(r["value"]) is not None]
            if hits:
                values = {parse_decimal(r["value"]) for r in hits}
                if len(values) > 1:
                    self.anomaly("duplicate_conflict", f"{element}（{context}）に、違う値の行が複数ある", item)
                return hits[0]
        return None

    def reported(self, item: str, row: dict | None, kind: str) -> dict:
        """行から reported_value を作る。kind は money（百万円）、salary（円）、persons、years。"""
        unit = {"money": "million_yen", "salary": "yen", "persons": "persons", "years": "years"}[kind]
        original_unit = {"persons": "persons", "years": "years"}.get(kind, "yen")
        if row is None:
            self.trace.append({"item": item, "element": NOT_FOUND, "context": NOT_FOUND, "original_value": None,
                               "original_unit": None, "value": None, "unit": unit})
            return {"value": None, "unit": unit, "original_unit": original_unit, "element": NOT_FOUND,
                    "context": NOT_FOUND, "doc_id": self.doc_id, "ingested_at": self.ingested_at}
        raw, unit_text = row["value"], row["unit"].strip()
        value = parse_decimal(raw)
        number = None
        if kind in ("money", "salary"):
            original = ORIGINAL_UNITS.get(unit_text) if unit_text else UNIT_IDS.get(row.get("unit_id", "").strip())
            if original is None:
                self.anomaly("unit_unknown", f"{item}：単位を決められない（単位の列 {unit_text!r}、"
                             f"ユニットID {row.get('unit_id', '')!r}）", item)
            else:
                original_unit = original
                scale = (SCALE_TO_MILLION if kind == "money" else {k: -v for k, v in SCALE_TO_YEN.items()})[original]
                number = self._number(item, value.scaleb(scale))
        else:
            expected = {"persons": "人", "years": "年"}[kind]
            if unit_text not in ("", expected):
                self.anomaly("unit_unknown", f"{item}：単位が想定と違う（単位の列 {unit_text!r}。想定は空か {expected!r}）", item)
            else:
                number = self._number(item, value)
        self.trace.append({"item": item, "element": row["element"], "context": row["context"],
                           "original_value": raw, "original_unit": unit_text or None, "value": number, "unit": unit})
        return {"value": number, "unit": unit, "original_unit": original_unit, "element": row["element"],
                "context": row["context"], "doc_id": self.doc_id, "ingested_at": self.ingested_at}

    def _number(self, item: str, value: Decimal) -> int | float:
        number, exact = json_number(value)
        if not exact:
            self.anomaly("precision_loss", f"{item}：換算後の値 {value} を、JSONの数で正確に表せない", item)
        return number


def read_dei(rows: list[dict], xbrl_map: dict, work: _Extraction) -> dict | None:
    """DEIの行から、会計基準、連結の有無、期間を読む。読めない・未知のときは、異常にして None を返す。"""
    dei = xbrl_map["dei"]
    raw: dict[str, str] = {}
    for key in DEI_KEYS:
        element = dei["elements"][key]
        values = {r["value"].strip() for r in rows if r["element"] == element}
        if not values:
            work.anomaly("dei_missing", f"DEIの {element} の行がない", key)
        elif len(values) > 1:
            work.anomaly("dei_conflict", f"DEIの {element} に、違う値が複数ある", key)
        else:
            raw[key] = values.pop()
    if len(raw) < len(DEI_KEYS):
        return None
    result: dict = {"accounting_standard_raw": raw["accounting_standard"], "period_type_raw": raw["period_type"]}
    ok = True
    standard = dei["accounting_standards"].get(raw["accounting_standard"])
    if standard is None:
        work.anomaly("dei_unknown_accounting_standard", f"DEIの会計基準の値が未知: {raw['accounting_standard']!r}",
                     "accounting_standard")
        ok = False
    period_type = dei["period_types"].get(raw["period_type"])
    if period_type is None:
        work.anomaly("dei_unknown_period_type", f"DEIの期間の種類の値が未知: {raw['period_type']!r}", "period_type")
        ok = False
    consolidated = {"true": True, "false": False}.get(raw["consolidated"].lower())
    if consolidated is None:
        work.anomaly("dei_unknown_consolidated", f"DEIの連結財務諸表の作成の有無の値が読めない: {raw['consolidated']!r}",
                     "consolidated")
        ok = False
    dates = {}
    for key in ("fiscal_year_start", "period_end", "fiscal_year_end"):
        try:
            dates[key] = date.fromisoformat(raw[key])
        except ValueError:
            work.anomaly("dei_bad_date", f"DEIの {key} が日付（YYYY-MM-DD）として読めない: {raw[key]!r}", key)
            ok = False
    if not ok:
        return None
    result.update(accounting_standard=standard, period_type=period_type, consolidated=consolidated,
                  fiscal_year_start=raw["fiscal_year_start"], period_end=raw["period_end"],
                  fiscal_year_end=raw["fiscal_year_end"])
    if not dates["fiscal_year_start"] <= dates["period_end"] <= dates["fiscal_year_end"]:
        work.anomaly("period_mismatch", "DEIの period_end が、fiscal_year_start と fiscal_year_end の間にない")
    elif period_type == "annual" and dates["period_end"] != dates["fiscal_year_end"]:
        work.anomaly("period_mismatch", "年次なのに、DEIの period_end が fiscal_year_end と違う")
    return result


def net_sales_label(label: str) -> str:
    """項目名から、（IFRS）、（US GAAP）、「、経営指標等」を除く。例：「売上収益（IFRS）」→「売上収益」。"""
    return LABEL_NOISE.sub("", label).replace("、経営指標等", "").strip()


def segment_member(context: str, duration: str) -> str | None:
    """当期の期間_{前置き}{メンバー名} の形のコンテキストから、前置きを除いたメンバー名を返す。使えなければ None。"""
    if not context.startswith(duration + "_") or NON_CONSOLIDATED_MEMBER in context:
        return None
    rest = context[len(duration) + 1:]
    prefix = PREFIX_PATTERN.match(rest)
    member = rest[prefix.end():] if prefix else rest
    return member if MEMBER_PATTERN.match(member) else None


def _segments(rows: list[dict], items: dict, duration: str, work: _Extraction) -> tuple[list[dict], dict | None]:
    external = items.get("segment_external_sales", [])
    if not external:
        return [], None
    totals, profits = items.get("segment_total_sales", []), items.get("segment_profit", [])

    def by_member(elements: list[str]) -> dict[str, list[dict]]:
        # 候補を先頭から順に探し、メンバー付きの行がある最初の要素だけを使う（候補どうしの行を混ぜない）
        for element in elements:
            found: dict[str, list[dict]] = {}
            for r in rows:
                if r["element"] == element and parse_decimal(r["value"]) is not None:
                    member = segment_member(r["context"], duration)
                    if member is not None:
                        found.setdefault(member, []).append(r)
            if found:
                return found
        return {}

    skipped = sorted({r["context"] for r in rows if r["element"] in external and r["context"].startswith(duration + "_")
                      and parse_decimal(r["value"]) is not None and segment_member(r["context"], duration) is None})
    if skipped:
        work.notes.append("セグメントとして使わなかったコンテキスト（単体、またはメンバー名を読めないもの）: "
                          + "、".join(skipped[:10]) + ("…" if len(skipped) > 10 else ""))
    ext, tot, prof = by_member(external), by_member(totals), by_member(profits)
    segments = []
    for member, member_rows in ext.items():
        if member in NOT_SEGMENT_MEMBERS:
            continue
        segment = {"name": member, "member": member,
                   "net_sales_external": work.reported(f"segment:{member}:net_sales_external", member_rows[0], "money")}
        if member in tot:
            segment["net_sales_total"] = work.reported(f"segment:{member}:net_sales_total", tot[member][0], "money")
        if member in prof:
            segment["profit"] = work.reported(f"segment:{member}:profit", prof[member][0], "money")
        segments.append(segment)
    adjustment = None
    if RECONCILING_MEMBER in prof:
        adjustment = work.reported("segment_adjustment", prof[RECONCILING_MEMBER][0], "money")
    return segments, adjustment


def extract(rows: list[dict], doc_id: str, ingested_at: str, xbrl_map: dict) -> dict:
    """書類のCSVの行から、financial、employee、異常の一覧などを取り出す。"""
    work = _Extraction(doc_id, ingested_at)
    prepared = prepare_rows(rows)
    dei = read_dei(prepared, xbrl_map, work)
    result = {"doc_id": doc_id, "financial": None, "employee": None, "anomalies": work.anomalies, "notes": work.notes,
              "trace": work.trace, "dei": dei, "stopped": dei is None}
    if dei is None:
        return result
    standard, period_type = dei["accounting_standard"], dei["period_type"]
    duration, instant = CONTEXTS[period_type]
    spec = xbrl_map["standards"][standard]
    items = spec["items"]

    values: dict[str, dict] = {}
    labels = ""
    for item in ("net_sales", "operating_income", "ordinary_income", "net_income"):
        if item == "ordinary_income" and standard != "jgaap":
            continue  # 日本基準以外では、項目を書かない
        row = work.find(prepared, items.get(item, []), duration, item)
        values[item] = work.reported(item, row, "money")
        if item == "net_sales" and row is not None:
            labels = net_sales_label(row["label"])
        if row is None and item not in spec["expected_absent"]:
            work.anomaly("item_not_found", f"{item}：当期（{duration}）の行が見つからない", item)
    segments, adjustment = ([], None) if standard == "usgaap" else _segments(prepared, items, duration, work)
    financial = {
        "fiscal_period_end": dei["fiscal_year_end"][:7], "period_type": period_type,
        "period_start": dei["fiscal_year_start"], "period_end": dei["period_end"],
        "accounting_standard": standard, "consolidated": dei["consolidated"], "doc_id": doc_id,
        "net_sales_label": labels or "不明",
        "net_sales": values["net_sales"], "operating_income": values["operating_income"],
    }
    if "ordinary_income" in values:
        financial["ordinary_income"] = values["ordinary_income"]
    financial["net_income"] = values["net_income"]
    financial["segments"] = segments
    if adjustment is not None:
        financial["segment_adjustment"] = adjustment
    financial["regions"] = []
    result["financial"] = financial
    if period_type == "annual":
        result["employee"] = _employee(prepared, xbrl_map, dei, doc_id, instant, work)
    result["comparative"] = _comparative(prepared, xbrl_map, dei, doc_id, ingested_at)
    return result


def prior_fiscal_period_end(fiscal_year_end: str) -> str:
    """DEIの fiscal_year_end（YYYY-MM-DD）の1年前の年月（YYYY-MM）。"""
    return f"{int(fiscal_year_end[:4]) - 1:04d}{fiscal_year_end[4:7]}"


def _comparative(rows: list[dict], xbrl_map: dict, dei: dict, doc_id: str, ingested_at: str) -> dict:
    """前期の列の値を、当期と同じ規則で取り出す。前期の列にない項目は、入れない（異常にしない）。

    財務は、連結の値（売上高など）、セグメント、調整額。従業員は、連結と単体の従業員数だけ。
    換算できない項目や、違う値の行が重なる項目は、入れずに notes に書く。
    """
    standard, period_type = dei["accounting_standard"], dei["period_type"]
    duration, instant = PRIOR_CONTEXTS[period_type]
    spec = xbrl_map["standards"][standard]
    items = spec["items"]
    work = _Extraction(doc_id, ingested_at)
    prior = prior_fiscal_period_end(dei["fiscal_year_end"])
    notes: list[str] = []

    def taken(name: str, element_list: list[str], context: str, kind: str):
        before = len(work.anomalies)
        row = work.find(rows, element_list, context, name)
        if row is None:
            return None
        value = work.reported(name, row, kind)
        if len(work.anomalies) > before or value["value"] is None:
            notes.append(f"前期の列の {name} は、取り出せないため使わない")
            return None
        return value

    financial: dict = {"fiscal_period_end": prior, "period_type": period_type}
    for item in ("net_sales", "operating_income", "ordinary_income", "net_income"):
        if item == "ordinary_income" and standard != "jgaap":
            continue
        value = taken(item, items.get(item, []), duration, "money")
        if value is not None:
            financial[item] = value
    if standard != "usgaap":
        before = len(work.anomalies)
        segments, adjustment = _segments(rows, items, duration, work)
        if len(work.anomalies) > before:
            notes.append("前期の列のセグメントは、取り出せない値があるため使わない")
        elif segments:
            financial["segments"] = segments
            if adjustment is not None:
                financial["segment_adjustment"] = adjustment
    employee = None
    if period_type == "annual":
        spec_e = xbrl_map["employees"]
        employee = {"fiscal_period_end": prior}
        consolidated = taken("employees_consolidated", spec_e["employees_consolidated"], instant, "persons")
        if consolidated is not None:
            employee["consolidated"] = {"employees": consolidated}
        single = taken("employees_non_consolidated", spec_e["employees_non_consolidated"],
                       f"{instant}_{NON_CONSOLIDATED_MEMBER}", "persons")
        if single is not None:
            employee["non_consolidated"] = {"employees": single}
        if len(employee) == 1:
            employee = None
    return {"financial": financial, "employee": employee, "notes": notes + work.notes}


def _employee(rows: list[dict], xbrl_map: dict, dei: dict, doc_id: str, instant: str, work: _Extraction) -> dict:
    spec = xbrl_map["employees"]
    single = f"{instant}_{NON_CONSOLIDATED_MEMBER}"
    employee: dict = {"fiscal_period_end": dei["fiscal_year_end"][:7], "as_of": dei["period_end"], "doc_id": doc_id}
    row = work.find(rows, spec["employees_consolidated"], instant, "employees_consolidated")
    if row is not None:
        employee["consolidated"] = {"employees": work.reported("employees_consolidated", row, "persons")}
    elif dei["consolidated"]:
        work.anomaly("item_not_found", f"連結の従業員数（{instant}）の行が見つからない", "employees_consolidated")
    employee["non_consolidated"] = {}
    for key, kind in (("employees", "persons"), ("average_age", "years"), ("average_length_of_service", "years"),
                      ("average_annual_salary", "salary")):
        name = "employees_non_consolidated" if key == "employees" else key
        row = work.find(rows, spec[name], single, f"non_consolidated.{key}")
        employee["non_consolidated"][key] = work.reported(f"non_consolidated.{key}", row, kind)
        if row is None:
            work.anomaly("item_not_found", f"単体の {key}（{single}）の行が見つからない", f"non_consolidated.{key}")
    return employee
