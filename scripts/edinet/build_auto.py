"""1社分の data/auto/{slug}.json（データ定義書5章）を、書類の一覧と、取り出しの結果から組み立てる。

純粋な関数だけで、ネットワークも、ファイルも使わない。J01の段階3b。

入力：企業の slug と edinet_code、既存の data/auto ファイルの内容（なければ None）、取り込む書類のリスト、
現在の日時、書類の種類の対応（config/xbrl-map.yaml の doc_types）。
書類は、{"filing": 一覧の行（API の項目名のまま）, "result": extract.extract の結果 または None, "error": 取得の失敗の種類 または None}。
出力：(新しい内容の辞書, 変更の一覧)。変更の一覧の行は {"kind": ..., "doc_id": ..., "message": ...} で、kind は
added（取り込んだ）、replaced（値の置き換え）、superseded（元の書類の状態を変えた）、anomaly（使わなかった一覧の行）、
failed（取り込みに失敗した）、not_recorded（filings に書けず、記録しなかった）。

実装で決めたこと（運営者の規則のほかに）：
* 置き換える元の書類は、一覧の parentDocID（EDINET API の項目。あれば）を先に使い、なければ、同じ
  fiscal_period_end・period_type で、提出が前の ingested の書類のうち、最も新しいもの
* 同じ期間（財務は fiscal_period_end と period_type、従業員は fiscal_period_end）の行は、その行の値を出した書類より
  提出が新しい書類のときだけ置き換える。古い書類があとから届いたときは、その書類を superseded にして、値は変えない
* 置き換えで、新しい行が前の行と値（/value）の点で違うときだけ、revisions に加える。セグメントは member で対応づける
* 行の並びが変わるときは、既存の revisions の path の添字を、同じ行を指すように直す
* 取得に失敗した、または異常のある書類の filings の行の期間は、一覧の periodStart、periodEnd から作る
  （半期の fiscal_period_end は、periodStart の1年後の前日の年月）。作れない書類は、filings に書かず not_recorded にする
* 訂正の書類で、置き換える元が決まらないときは、取り込まず（failed で記録もできないため）not_recorded にする
* 変更がなければ、既存の内容をそのまま返す（updated_at も変えない）
"""

from __future__ import annotations

import copy
import re
from datetime import date, datetime, timedelta
from decimal import Decimal
from zoneinfo import ZoneInfo

JST = ZoneInfo("Asia/Tokyo")
DOC_URL = "https://disclosure2dl.edinet-fsa.go.jp/searchdocument/pdf/{doc_id}.pdf"
DOC_ID = re.compile(r"^S100[0-9A-Z]{4}$")
SUBMITTED = re.compile(r"^(\d{4}-\d{2}-\d{2})[ T](\d{2}:\d{2})(:\d{2})?$")
AMENDED = {"amended_annual_report", "amended_semiannual_report"}
PERIOD_OF_TYPE = {"annual_report": "annual", "amended_annual_report": "annual",
                  "semiannual_report": "half", "amended_semiannual_report": "half"}
TOP_KEYS = ("schema_version", "company", "edinet_code", "updated_at", "filings", "financials", "employees",
            "announcements", "revisions")
TRANSIENT = "transient"  # 取得の error の値。通信の一時的な失敗（filings に記録しない）
FILING_KEYS = ("doc_id", "doc_type", "edinet_doc_type_code", "fiscal_period_end", "period_type", "period_start",
               "period_end", "submitted_at", "url", "status", "supersedes", "ingested_at", "error")


def jst_text(moment: datetime) -> str:
    return moment.astimezone(JST).replace(microsecond=0).isoformat()


def submitted_at(text) -> str | None:
    match = SUBMITTED.match(str(text or "").strip())
    if not match:
        return None
    seconds = match.group(3) or ":00"
    value = f"{match.group(1)}T{match.group(2)}{seconds}+09:00"
    try:
        datetime.fromisoformat(value)
    except ValueError:
        return None
    return value


def classify_rows(rows: list[dict], edinet_code: str, doc_types: dict[str, str]) -> tuple[list[tuple[dict, str]], list[dict]]:
    """一覧の行を、使える行（行, doc_type）と、使わない行の変更の一覧に分ける。"""
    usable, rejected = [], []
    for row in rows:
        doc_id = str(row.get("docID") or "")
        if str(row.get("withdrawalStatus", "0")) != "0":
            rejected.append({"kind": "anomaly", "doc_id": doc_id, "message": "取り下げの書類なので使わない"})
        elif row.get("edinetCode") != edinet_code:
            rejected.append({"kind": "anomaly", "doc_id": doc_id,
                             "message": f"一覧の edinetCode（{row.get('edinetCode')}）が企業の edinet_code（{edinet_code}）と違うので使わない"})
        elif not DOC_ID.match(doc_id):
            rejected.append({"kind": "anomaly", "doc_id": doc_id, "message": "doc_id の形が正しくないので使わない"})
        elif doc_types.get(str(row.get("docTypeCode"))) is None:
            rejected.append({"kind": "anomaly", "doc_id": doc_id,
                             "message": f"docTypeCode（{row.get('docTypeCode')}）が doc_types にないので使わない"})
        elif submitted_at(row.get("submitDateTime")) is None:
            rejected.append({"kind": "anomaly", "doc_id": doc_id, "message": "submitDateTime が読めないので使わない"})
        else:
            usable.append((row, doc_types[str(row["docTypeCode"])]))
    return usable, rejected


def anomaly_kinds(result: dict) -> str:
    kinds = []
    for a in result["anomalies"]:
        kind = f"{a['item']}_not_found" if a["code"] == "item_not_found" and a.get("item") else a["code"]
        if kind not in kinds:
            kinds.append(kind)
    return "anomaly:" + ",".join(kinds)


def listing_period(row: dict, doc_type: str) -> tuple[str, str, str, str] | None:
    """一覧の行から (fiscal_period_end, period_type, period_start, period_end) を作る。作れなければ None。"""
    try:
        start, end = date.fromisoformat(str(row["periodStart"])), date.fromisoformat(str(row["periodEnd"]))
    except (KeyError, ValueError):
        return None
    period_type = PERIOD_OF_TYPE[doc_type]
    if period_type == "annual":
        fiscal_end = end
    else:
        try:
            fiscal_end = start.replace(year=start.year + 1) - timedelta(days=1)
        except ValueError:  # 2月29日
            fiscal_end = start.replace(year=start.year + 1, day=28)
    return fiscal_end.isoformat()[:7], period_type, start.isoformat(), end.isoformat()


def _sort_key_financial(row: dict):
    return (row["fiscal_period_end"], row["period_end"])


def _leaves(node, path: str, member_key: bool):
    """値（/value）の点を、(path, value, その値の doc_id, unit) で返す。segments は member で対応づけるため、呼び出し側で扱う。"""
    if isinstance(node, dict):
        if "value" in node and "unit" in node:
            yield path + "/value", node["value"], node.get("doc_id"), node["unit"]
            return
        for key, child in node.items():
            if key == "segments":
                continue
            yield from _leaves(child, f"{path}/{key}", member_key)


def same_amount(unit, old, new) -> bool:
    """同じ値とみなすか。unit が million_yen のときは、差の絶対値が 1 未満なら同じ（表示の単位の丸め。元の精度のある値を残す）。
    yen、persons、years などは、厳密に比べる。"""
    if old == new:
        return True
    if old is None or new is None or unit != "million_yen":
        return False
    return abs(Decimal(str(old)) - Decimal(str(new))) < 1


def segment_values(row: dict, base: str) -> dict[tuple, tuple[str, object, object]]:
    """セグメントの値を、(member, 項目の名前) をキーに {キー: (path, value, doc_id)} にする。"""
    out = {}
    for i, segment in enumerate(row.get("segments", [])):
        for path, value, doc_id, _unit in _leaves(segment, f"{base}/segments/{i}", False):
            out[(segment["member"], path.rsplit(f"/segments/{i}/", 1)[1])] = (path, value, doc_id)
    return out


def value_changes(old: dict | None, new: dict, base_old: str, base_new: str) -> list[tuple[str, object, object, object]]:
    """置き換えで値が変わった点を、(新しい行の path, old, new, 置き換える前の値の doc_id) で返す。"""
    if old is None:
        return []
    changes = []
    old_main = {path: (value, doc) for path, value, doc, _ in _leaves(old, base_old, False)}
    new_main = {path: value for path, value, _, _ in _leaves(new, base_new, False)}
    for path_new, value in new_main.items():
        path_old = base_old + path_new[len(base_new):]
        previous, doc = old_main.get(path_old, (None, None))
        if path_old in old_main and previous != value:
            changes.append((path_new, previous, value, doc))
        elif path_old not in old_main and value is not None:
            changes.append((path_new, None, value, None))
    for path_old, (previous, doc) in old_main.items():
        if base_new + path_old[len(base_old):] not in new_main and previous is not None:
            changes.append((base_new + path_old[len(base_old):], previous, None, doc))
    old_seg, new_seg = segment_values(old, base_old), segment_values(new, base_new)
    for key, (path, value, _doc) in new_seg.items():
        if key in old_seg:
            if old_seg[key][1] != value:
                changes.append((path, old_seg[key][1], value, old_seg[key][2]))
        elif value is not None:
            changes.append((path, None, value, None))
    for key, (path, previous, doc) in old_seg.items():
        if key not in new_seg and previous is not None:
            changes.append((path, previous, None, doc))
    return changes


REPORTED_ITEMS = ("net_sales", "operating_income", "ordinary_income", "net_income")
SEGMENT_FIELDS = ("net_sales_external", "net_sales_total", "profit")
FINANCIAL_ORDER = ("fiscal_period_end", "period_type", "period_start", "period_end", "accounting_standard", "consolidated",
                   "doc_id", "net_sales_label", "net_sales", "operating_income", "ordinary_income", "net_income",
                   "segments", "segment_adjustment", "regions")


def _slot_keys(node, prefix=()):
    """行の中の reported_value（dict）の、キーの並びの一覧。segments は含めない。"""
    for key, child in node.items():
        if key in ("segments", "segment_adjustment") or not isinstance(child, dict):
            continue  # セグメントと調整額は、まとめて扱う（merge、apply_comparative_segments）
        if "value" in child and "unit" in child:
            yield prefix + (key,)
        else:
            yield from _slot_keys(child, prefix + (key,))


def _get(node, keys):
    for key in keys:
        if not isinstance(node, dict) or key not in node:
            return None
        node = node[key]
    return node


def _set(node, keys, value):
    for key in keys[:-1]:
        node = node[key]
    node[keys[-1]] = value


def _reorder(row: dict) -> None:
    """財務の行のキーを、データ定義書の表の順にそろえる。"""
    ordered = {k: row[k] for k in FINANCIAL_ORDER if k in row}
    row.clear()
    row.update(ordered)


def _restamp(reported: dict, doc_id: str, ingested_at: str) -> dict:
    """前期の列から置き換える値の、doc_id と ingested_at を、新しい書類のものにする。"""
    return {**reported, "doc_id": doc_id, "ingested_at": ingested_at}


def _shift_revision_paths(revisions: list[dict], section: str, old_rows: list[dict], new_rows: list[dict], key) -> None:
    """行の並びが変わったとき、既存の revisions の path の添字を、同じ行を指すように直す。"""
    mapping = {i: next(j for j, n in enumerate(new_rows) if key(n) == key(o)) for i, o in enumerate(old_rows)
               if any(key(n) == key(o) for n in new_rows)}
    prefix = f"/{section}/"
    for revision in revisions:
        path = revision["path"]
        if path.startswith(prefix):
            head, _, rest = path[len(prefix):].partition("/")
            if head.isdigit() and int(head) in mapping:
                revision["path"] = f"{prefix}{mapping[int(head)]}/{rest}"


class _Builder:
    def __init__(self, slug, edinet_code, existing, now, doc_types):
        self.slug, self.edinet_code, self.now_text = slug, edinet_code, jst_text(now)
        self.doc_types = doc_types
        self.data = copy.deepcopy(existing) if existing else {
            "schema_version": 1, "company": slug, "edinet_code": edinet_code, "updated_at": self.now_text,
            "filings": [], "financials": [], "employees": [], "announcements": [], "revisions": []}
        if self.data["company"] != slug or self.data["edinet_code"] != edinet_code:
            raise ValueError("既存のファイルの company・edinet_code が、指定の企業と違う")
        self.changes: list[dict] = []

    def filing(self, doc_id):
        return next((f for f in self.data["filings"] if f["doc_id"] == doc_id), None)

    def previous_version(self, fpe, ptype, submitted, doc_id):
        """同じ期間（fiscal_period_end と period_type）の、(submitted, doc_id) がこの書類より前の書類のうち、
        最も新しいもの（元の書類、または前の訂正報告書）。failed の書類は数えない。"""
        earlier = [f for f in self.data["filings"] if f["status"] != "failed" and f["fiscal_period_end"] == fpe
                   and f["period_type"] == ptype and f["doc_id"] != doc_id
                   and (f["submitted_at"], f["doc_id"]) < (submitted, doc_id)]
        return max(earlier, key=lambda f: (f["submitted_at"], f["doc_id"]))["doc_id"] if earlier else None

    def supersedes_of(self, row, fpe, ptype, submitted):
        """訂正報告書の supersedes：同じ期間の、より前に提出された書類のうち、最も新しいもの。一覧の parentDocID が
        連鎖の途中を飛ばして元の書類を指していても、この規則を優先する。前の書類が見つからないときだけ、parentDocID。"""
        previous = self.previous_version(fpe, ptype, submitted, row["docID"])
        if previous is not None:
            return previous
        parent = str(row.get("parentDocID") or "")
        return parent if DOC_ID.match(parent) and parent != row["docID"] else None

    def normalize_chain(self):
        """訂正報告書の連鎖をそろえる（既存のファイルの supersedes も、再実行で直る）。

        各訂正報告書の supersedes を、同じ期間の、その書類より前に提出された書類のうち、最も新しいものにする。
        前の版（ingested）は superseded にする。連鎖の最後の書類だけが ingested のままになる。
        failed の訂正報告書の supersedes も直すが、前の版の status は変えない（値を置き換えていないため）。
        前の書類が見つからないときは、supersedes を変えない。
        """
        for f in sorted(self.data["filings"], key=lambda x: (x["submitted_at"], x["doc_id"])):
            if f["doc_type"] not in AMENDED:
                continue
            previous = self.previous_version(f["fiscal_period_end"], f["period_type"], f["submitted_at"], f["doc_id"])
            if previous is None:
                continue
            if f.get("supersedes") != previous:
                self.changes.append({"kind": "supersedes_fixed", "doc_id": f["doc_id"],
                                     "message": f"supersedes を {f.get('supersedes')} から {previous} に直した"
                                                "（同じ期間の、前に提出された書類のうち最も新しいもの）"})
                f["supersedes"] = previous
            if f["status"] != "failed":
                self.mark_superseded(previous, f["doc_id"])

    def drop_failed(self, doc_id):
        """再取得の結果で置き換えるため、同じ doc_id の failed の行を除く。"""
        self.data["filings"] = [f for f in self.data["filings"] if not (f["doc_id"] == doc_id and f["status"] == "failed")]

    def add(self, doc):
        row = doc["filing"]
        doc_id = row["docID"]
        if doc.get("error") == TRANSIENT:
            self.changes.append({"kind": "not_recorded", "doc_id": doc_id, "reason": "transient",
                                 "message": "transient: 通信の一時的な失敗。filings に記録せず、次の実行で再取得される"})
            return
        doc_type = self.doc_types[str(row["docTypeCode"])]
        submitted = submitted_at(row["submitDateTime"])
        result, error = doc.get("result"), doc.get("error")
        status_error = error
        dei = result.get("dei") if result else None
        if result is not None and status_error is None:
            expected = PERIOD_OF_TYPE[doc_type]
            if result["stopped"] or result["anomalies"]:
                status_error = anomaly_kinds(result)
            elif result["financial"]["period_type"] != expected:
                status_error = "anomaly:doc_type_mismatch"
            elif result["financial"]["doc_id"] != doc_id:
                status_error = "anomaly:doc_id_mismatch"
        if dei:
            period = (dei["fiscal_year_end"][:7], dei["period_type"], dei["fiscal_year_start"], dei["period_end"])
        else:
            period = listing_period(row, doc_type)
        if period is None:
            self.changes.append({"kind": "not_recorded", "doc_id": doc_id, "reason": "period_unknown",
                                 "message": "対象の期間を決められず、filings に書けない（一覧の periodStart、periodEnd が読めない）"})
            return
        fpe, ptype, pstart, pend = period
        filing = {"doc_id": doc_id, "doc_type": doc_type, "edinet_doc_type_code": str(row["docTypeCode"]),
                  "fiscal_period_end": fpe, "period_type": ptype, "period_start": pstart, "period_end": pend,
                  "submitted_at": submitted, "url": DOC_URL.format(doc_id=doc_id)}
        supersedes = None
        if doc_type in AMENDED:
            supersedes = self.supersedes_of(row, fpe, ptype, submitted)
            if supersedes is None:
                self.changes.append({"kind": "not_recorded", "doc_id": doc_id, "reason": "supersedes_unknown",
                                     "message": "訂正の書類だが、置き換える元の書類が決まらず、filings に書けない"})
                return
        if status_error is not None:
            filing["status"] = "failed"
            if supersedes:
                filing["supersedes"] = supersedes
            filing["error"] = status_error
            self.drop_failed(doc_id)
            self.data["filings"].append(filing)
            self.changes.append({"kind": "failed", "doc_id": doc_id, "message": status_error})
            if result is not None:
                for a in result["anomalies"]:
                    self.changes.append({"kind": "anomaly", "doc_id": doc_id, "message": f"[{a['code']}] {a['message']}"})
            return
        filing["status"] = "ingested"
        if supersedes:
            filing["supersedes"] = supersedes
        filing["ingested_at"] = self.now_text
        self.drop_failed(doc_id)
        self.data["filings"].append(filing)
        self.changes.append({"kind": "added", "doc_id": doc_id,
                             "message": f"{fpe} {ptype}（{doc_type}）を取り込んだ"})
        self.place("financials", result["financial"], filing, supersedes,
                   lambda r: (r["fiscal_period_end"], r["period_type"]))
        if result["employee"] is not None:
            self.place("employees", result["employee"], filing, supersedes, lambda r: r["fiscal_period_end"])
        if supersedes:
            self.mark_superseded(supersedes, doc_id)
        self.apply_comparative(filing, result.get("comparative"))

    def submitted_key(self, doc_id):
        f = self.filing(doc_id) if doc_id else None
        return (f["submitted_at"], f["doc_id"]) if f else None

    def newer_than(self, filing, doc_id):
        """filing が、doc_id の書類より新しい（提出日時）か。書類が filings にないときは、新しいとする。"""
        other = self.submitted_key(doc_id)
        return other is None or (filing["submitted_at"], filing["doc_id"]) > other

    def merge(self, old_row, new_row, filing):
        """新しい行に、古い行の値のうち、filing より新しい書類（前期の列で置き換えた値など）のもの、
        および差が表示の単位の丸め（1百万円未満）の値を残す。"""
        merged = copy.deepcopy(new_row)
        for keys in _slot_keys(old_row):
            old_leaf = _get(old_row, keys)
            if _get(merged, keys) is not None and not self.newer_than(filing, old_leaf.get("doc_id")):
                _set(merged, keys, copy.deepcopy(old_leaf))
        group_docs = [d for seg in old_row.get("segments", []) for _, _, d, _ in _leaves(seg, "", False)]
        if old_row.get("segment_adjustment"):
            group_docs.append(old_row["segment_adjustment"].get("doc_id"))
        if any(not self.newer_than(filing, d) for d in group_docs if d):
            merged["segments"] = copy.deepcopy(old_row.get("segments", []))
            merged.pop("segment_adjustment", None)
            if "segment_adjustment" in old_row:
                merged["segment_adjustment"] = copy.deepcopy(old_row["segment_adjustment"])
        self.keep_rounded(old_row, merged)
        return merged

    @staticmethod
    def keep_rounded(old_row, merged):
        """値が厳密には違うが、同じとみなせる（差が1百万円未満）leaf は、元の精度のある値（古い方）を残す。"""
        for keys in _slot_keys(merged):
            old_leaf, new_leaf = _get(old_row, keys), _get(merged, keys)
            if old_leaf and new_leaf and old_leaf["value"] != new_leaf["value"] \
                    and same_amount(new_leaf.get("unit"), old_leaf["value"], new_leaf["value"]):
                _set(merged, keys, copy.deepcopy(old_leaf))
        old_map = {s["member"]: s for s in old_row.get("segments", [])}
        for segment in merged.get("segments", []):
            before = old_map.get(segment["member"])
            for field in SEGMENT_FIELDS:
                if before and field in before and field in segment and before[field]["value"] != segment[field]["value"] \
                        and same_amount(segment[field].get("unit"), before[field]["value"], segment[field]["value"]):
                    segment[field] = copy.deepcopy(before[field])
        old_adj, new_adj = old_row.get("segment_adjustment"), merged.get("segment_adjustment")
        if old_adj and new_adj and old_adj["value"] != new_adj["value"] \
                and same_amount(new_adj.get("unit"), old_adj["value"], new_adj["value"]):
            merged["segment_adjustment"] = copy.deepcopy(old_adj)

    def add_revision(self, filing, supersedes, path, old, new, message):
        self.data["revisions"].append({"at": self.now_text, "doc_id": filing["doc_id"], "supersedes": supersedes,
                                       "path": path, "old": old, "new": new})
        self.changes.append({"kind": "replaced", "doc_id": filing["doc_id"], "message": message})

    def apply_comparative(self, filing, comparative):
        """後の書類の前期の列の値が、取り込み済みの前期の値と違うとき、前期の値を置き換える（組替え・遡及修正）。

        前期に当たる行（fiscal_period_end が1年前で、period_type が同じ）がなければ、何もしない。
        提出日時が新しい書類の値を残す。net_sales_label、accounting_standard、consolidated は、
        会計基準が同じなら置き換えない（会計基準が切り替わったときは、switch_accounting_standard）。
        unit が million_yen の値は、差が1百万円未満なら同じとみなす。
        """
        if not comparative:
            return
        financial, employee = comparative.get("financial"), comparative.get("employee")
        if financial:
            self.apply_comparative_financial(filing, financial)
        if employee:
            self.apply_comparative_employee(filing, employee)

    def apply_comparative_financial(self, filing, comp):
        rows = self.data["financials"]
        index = next((i for i, r in enumerate(rows) if r["fiscal_period_end"] == comp["fiscal_period_end"]
                      and r["period_type"] == comp["period_type"]), None)
        if index is None:
            return
        row, base = rows[index], f"/financials/{index}"
        if comp.get("accounting_standard") and row["accounting_standard"] != comp["accounting_standard"]:
            self.switch_accounting_standard(filing, comp, row, base)
            return
        for item in REPORTED_ITEMS:
            if item not in comp or item not in row:
                continue
            old, new = row[item], comp[item]
            if not same_amount(old.get("unit"), old["value"], new["value"]) and self.newer_than(filing, old.get("doc_id")):
                row[item] = _restamp(new, filing["doc_id"], self.now_text)
                self.add_revision(filing, old.get("doc_id") or row["doc_id"], f"{base}/{item}/value", old["value"],
                                  new["value"], f"{base}/{item}/value: {old['value']} → {new['value']}"
                                  f"（前期の列による置き換え。置き換え元 {old.get('doc_id')}）")
        if "segments" in comp:
            self.apply_comparative_segments(filing, comp, row, base)
        elif row.get("segments"):
            self.changes.append({"kind": "segments_missing_in_comparative", "doc_id": filing["doc_id"],
                                 "message": f"前期の列にセグメントがない（既存を残した）。{base}"})

    def apply_comparative_segments(self, filing, comp, row, base):
        old_segments = row.get("segments", [])
        old_map = {s["member"]: s for s in old_segments}
        new_map = {s["member"]: s for s in comp["segments"]}

        def differs(m, field):
            if (field in old_map[m]) != (field in new_map[m]):
                return True
            return field in old_map[m] and not same_amount(old_map[m][field].get("unit"), old_map[m][field]["value"],
                                                            new_map[m][field]["value"])

        changed = set(old_map) != set(new_map) or any(differs(m, f) for m in new_map for f in SEGMENT_FIELDS)
        old_adj, new_adj = row.get("segment_adjustment"), comp.get("segment_adjustment")
        if new_adj is not None and (old_adj is None or not same_amount(old_adj.get("unit"), old_adj["value"], new_adj["value"])):
            changed = True
        if not changed:
            return
        group_docs = [d for s in old_segments for _, _, d, _ in _leaves(s, "", False)]
        if old_adj:
            group_docs.append(old_adj.get("doc_id"))
        if any(not self.newer_than(filing, d) for d in group_docs if d):
            return  # 提出日時が新しい書類の値を残す
        self.replace_segments(filing, row, base, comp["segments"], new_adj,
                              next(iter(group_docs), None) or row["doc_id"], "前期の列による置き換え")

    def replace_segments(self, filing, row, base, new_segments, new_adj, fallback_doc, reason):
        """segments と segment_adjustment を、新しい内容に丸ごと置き換える。名前が同じメンバーの値の変化は、
        revisions に値ごとに1件。メンバーの追加・削除は revisions に書けないので、変更の一覧に出す。
        値の差が1百万円未満（表示の単位の丸め）の leaf は、元の精度のある値を残す。"""
        old_segments = row.get("segments", [])
        old_map = {s["member"]: s for s in old_segments}
        old_adj = row.get("segment_adjustment")
        result = []
        for segment in new_segments:
            fresh = {k: (_restamp(v, filing["doc_id"], self.now_text) if isinstance(v, dict) else v)
                     for k, v in segment.items()}
            before = old_map.get(segment["member"])
            for field in SEGMENT_FIELDS:
                if before and field in before and field in segment and before[field]["value"] != segment[field]["value"] \
                        and same_amount(segment[field].get("unit"), before[field]["value"], segment[field]["value"]):
                    fresh[field] = copy.deepcopy(before[field])
            result.append(fresh)
        for j, segment in enumerate(result):
            before = old_map.get(segment["member"])
            if before is None:
                continue
            for field in SEGMENT_FIELDS:
                old_v = before[field]["value"] if field in before else None
                new_v = segment[field]["value"] if field in segment else None
                if old_v != new_v:
                    doc = (before[field].get("doc_id") if field in before else None) or fallback_doc
                    path = f"{base}/segments/{j}/{field}/value"
                    self.add_revision(filing, doc, path, old_v, new_v,
                                      f"{path}: {old_v} → {new_v}（{reason}。置き換え元 {doc}）")
        adjustment = None
        if new_adj is not None:
            adjustment = _restamp(new_adj, filing["doc_id"], self.now_text)
            if old_adj and old_adj["value"] != new_adj["value"] \
                    and same_amount(new_adj.get("unit"), old_adj["value"], new_adj["value"]):
                adjustment = copy.deepcopy(old_adj)
        old_v = old_adj["value"] if old_adj else None
        new_v = adjustment["value"] if adjustment else None
        if old_v != new_v:
            path = f"{base}/segment_adjustment/value"
            doc = (old_adj or {}).get("doc_id") or fallback_doc
            self.add_revision(filing, doc, path, old_v, new_v, f"{path}: {old_v} → {new_v}（{reason}。置き換え元 {doc}）")
        row["segments"] = result
        row.pop("segment_adjustment", None)
        if adjustment is not None:
            row["segment_adjustment"] = adjustment
        _reorder(row)
        added = sorted(set(s["member"] for s in result) - set(old_map))
        removed = sorted(set(old_map) - set(s["member"] for s in result))
        if added or removed:
            parts = ([f"追加：{'、'.join(added)}"] if added else []) + ([f"削除：{'、'.join(removed)}"] if removed else [])
            self.changes.append({"kind": "segments_changed", "doc_id": filing["doc_id"],
                                 "message": f"セグメントの区分が変わった（{'、'.join(parts)}）。{base} は、"
                                            f"{filing['doc_id']} の前期の列で置き換えた"})

    def switch_accounting_standard(self, filing, comp, row, base):
        """会計基準が切り替わったとき、その行の財務の値を、前期の列の内容で丸ごと置き換える。

        net_sales、operating_income、ordinary_income、net_income、net_sales_label、segments、segment_adjustment、
        accounting_standard を置き換え、行の doc_id を新しい書類にする。consolidated は置き換えない。
        ordinary_income が新しい会計基準（ifrs、usgaap）にないときは、行から取り除く。
        提出日時が新しい書類の値は残す（その行に、より新しい書類の値があれば、何もしない）。
        """
        standard, old_standard = comp["accounting_standard"], row["accounting_standard"]
        docs = [row.get("doc_id")] + [row[i].get("doc_id") for i in REPORTED_ITEMS if isinstance(row.get(i), dict)]
        docs += [d for s in row.get("segments", []) for _, _, d, _ in _leaves(s, "", False)]
        if row.get("segment_adjustment"):
            docs.append(row["segment_adjustment"].get("doc_id"))
        if any(not self.newer_than(filing, d) for d in docs if d):
            return
        reason = "会計基準の切り替えによる置き換え"
        for item in REPORTED_ITEMS:
            path = f"{base}/{item}/value"
            old = row.get(item)
            if item == "ordinary_income" and standard != "jgaap":
                if old is not None:
                    row.pop(item)
                    if old["value"] is not None:
                        self.add_revision(filing, old.get("doc_id") or row["doc_id"], path, old["value"], None,
                                          f"{path}: {old['value']} → null（{reason}。{item} を取り除いた。置き換え元 {old.get('doc_id')}）")
                continue
            if item not in comp:
                continue
            new = comp[item]
            if old is not None and same_amount(old.get("unit"), old["value"], new["value"]) and old["value"] != new["value"]:
                continue  # 差が1百万円未満（表示の単位の丸め）。元の精度のある値を残す
            row[item] = _restamp(new, filing["doc_id"], self.now_text)
            if (old["value"] if old is not None else None) != new["value"]:
                doc = (old or {}).get("doc_id") or row["doc_id"]
                self.add_revision(filing, doc, path, old["value"] if old is not None else None, new["value"],
                                  f"{path}: {old['value'] if old is not None else None} → {new['value']}（{reason}。置き換え元 {doc}）")
        if comp.get("net_sales_label"):
            row["net_sales_label"] = comp["net_sales_label"]
        row["accounting_standard"] = standard
        row["doc_id"] = filing["doc_id"]
        group_docs = [d for s in row.get("segments", []) for _, _, d, _ in _leaves(s, "", False)]
        self.replace_segments(filing, row, base, comp.get("segments", []), comp.get("segment_adjustment"),
                              next(iter(group_docs), None) or docs[0] or filing["doc_id"], reason)
        _reorder(row)
        self.changes.append({"kind": "accounting_standard_changed", "doc_id": filing["doc_id"],
                             "message": f"会計基準が変わった（{old_standard} → {standard}）。{base} を、"
                                        f"{filing['doc_id']} の前期の列で置き換えた"})

    def apply_comparative_employee(self, filing, comp):
        rows = self.data["employees"]
        index = next((i for i, r in enumerate(rows) if r["fiscal_period_end"] == comp["fiscal_period_end"]), None)
        if index is None:
            return
        row = rows[index]
        for section in ("consolidated", "non_consolidated"):
            new = _get(comp, (section, "employees"))
            old = _get(row, (section, "employees"))
            if new is None or old is None:
                continue
            if not same_amount(old.get("unit"), old["value"], new["value"]) and self.newer_than(filing, old.get("doc_id")):
                row[section]["employees"] = _restamp(new, filing["doc_id"], self.now_text)
                path = f"/employees/{index}/{section}/employees/value"
                self.add_revision(filing, old.get("doc_id") or row["doc_id"], path, old["value"], new["value"],
                                  f"{path}: {old['value']} → {new['value']}（前期の列による置き換え。"
                                  f"置き換え元 {old.get('doc_id')}）")

    def place(self, section, new_row, filing, supersedes, key):
        rows = self.data[section]
        index = next((i for i, r in enumerate(rows) if key(r) == key(new_row)), None)
        if index is None:
            self.insert(section, rows, new_row, key)
            return
        old_row = rows[index]
        source = self.filing(old_row["doc_id"])
        old_submitted = source["submitted_at"] if source else ""
        if source is None or (filing["submitted_at"], filing["doc_id"]) > (old_submitted, source["doc_id"]):
            self.mark_superseded(old_row["doc_id"], filing["doc_id"])
            if supersedes and supersedes != old_row["doc_id"]:
                self.mark_superseded(supersedes, filing["doc_id"])
            merged = self.merge(old_row, new_row, filing)  # 前期の列による、より新しい値は残す
            for path, old, new, doc in value_changes(old_row, merged, f"/{section}/{index}", f"/{section}/{index}"):
                source_doc = doc or old_row["doc_id"]
                self.add_revision(filing, source_doc, path, old, new, f"{path}: {old} → {new}（置き換え元 {source_doc}）")
            rows[index] = merged
        else:  # 古い書類があとから届いた。値は変えない
            # 値を出した書類が、同じ期間の書類のときだけ、この書類を superseded にする（別の期の書類の前期の列による
            # 値のときは、この書類は、その期の連鎖の中の書類のままで、前の版との関係は normalize_chain が決める）
            if source is not None and (source["fiscal_period_end"], source["period_type"]) == (
                    filing["fiscal_period_end"], filing["period_type"]):
                self.mark_superseded(filing["doc_id"], old_row["doc_id"])

    def insert(self, section, rows, new_row, key):
        before = copy.deepcopy(rows)
        rows.append(new_row)
        if section == "financials":
            rows.sort(key=_sort_key_financial)
        else:
            rows.sort(key=lambda r: r["fiscal_period_end"])
        _shift_revision_paths(self.data["revisions"], section, before, rows, key)

    def mark_superseded(self, doc_id, by):
        target = self.filing(doc_id)
        if target is not None and target["status"] == "ingested":
            target["status"] = "superseded"
            self.changes.append({"kind": "superseded", "doc_id": doc_id, "message": f"{by} に置き換えられた"})


def build(slug: str, edinet_code: str, existing: dict | None, documents: list[dict], now: datetime,
          doc_types: dict[str, str], retry_failed: bool = False) -> tuple[dict, list[dict]]:
    """既存の内容に、書類を取り込んだ新しい内容と、変更の一覧を返す。変更がなければ、既存の内容をそのまま返す。"""
    builder = _Builder(slug, edinet_code, existing, now, doc_types)
    # retry_failed のときは、failed の書類を既知としない（取り込み直して、failed の行を置き換える）
    known = {f["doc_id"] for f in builder.data["filings"] if not (retry_failed and f["status"] == "failed")}
    pairs = []
    seen: set[str] = set()
    for doc in documents:
        usable, rejected = classify_rows([doc["filing"]], edinet_code, doc_types)
        builder.changes += rejected
        doc_id = str(doc["filing"].get("docID") or "")
        if usable and doc_id not in known and doc_id not in seen:
            seen.add(doc_id)
            pairs.append(doc)
    pairs.sort(key=lambda d: (submitted_at(d["filing"]["submitDateTime"]), d["filing"]["docID"]))
    for doc in pairs:
        builder.add(doc)
    builder.normalize_chain()
    data = builder.data
    data["filings"].sort(key=lambda f: (f["submitted_at"], f["doc_id"]))
    data["filings"] = [{k: f[k] for k in FILING_KEYS if k in f} for f in data["filings"]]
    if existing is not None and data == existing:
        return copy.deepcopy(existing), builder.changes  # 変更なし。updated_at も変えない
    data["updated_at"] = builder.now_text
    return {key: data[key] for key in TOP_KEYS}, builder.changes
