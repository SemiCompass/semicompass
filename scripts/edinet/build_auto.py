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
    """値（/value）の点を、(path, value) で返す。segments は member で対応づけるため、呼び出し側で扱う。"""
    if isinstance(node, dict):
        if "value" in node and "unit" in node:
            yield path + "/value", node["value"]
            return
        for key, child in node.items():
            if key == "segments":
                continue
            yield from _leaves(child, f"{path}/{key}", member_key)


def segment_values(row: dict, base: str) -> dict[tuple, tuple[str, object]]:
    """セグメントの値を、(member, 項目の名前) をキーに {キー: (path, value)} にする。"""
    out = {}
    for i, segment in enumerate(row.get("segments", [])):
        for path, value in _leaves(segment, f"{base}/segments/{i}", False):
            out[(segment["member"], path.rsplit(f"/segments/{i}/", 1)[1])] = (path, value)
    return out


def value_changes(old: dict | None, new: dict, base_old: str, base_new: str) -> list[tuple[str, object, object]]:
    """置き換えで値が変わった点を、(新しい行の path, old, new) で返す。"""
    if old is None:
        return []
    changes = []
    old_main = dict(_leaves(old, base_old, False))
    new_main = dict(_leaves(new, base_new, False))
    for path_new, value in new_main.items():
        path_old = base_old + path_new[len(base_new):]
        previous = old_main.get(path_old)
        if path_old in old_main and previous != value:
            changes.append((path_new, previous, value))
        elif path_old not in old_main and value is not None:
            changes.append((path_new, None, value))
    for path_old, previous in old_main.items():
        if base_new + path_old[len(base_old):] not in new_main and previous is not None:
            changes.append((base_new + path_old[len(base_old):], previous, None))
    old_seg, new_seg = segment_values(old, base_old), segment_values(new, base_new)
    for key, (path, value) in new_seg.items():
        if key in old_seg:
            if old_seg[key][1] != value:
                changes.append((path, old_seg[key][1], value))
        elif value is not None:
            changes.append((path, None, value))
    for key, (path, previous) in old_seg.items():
        if key not in new_seg and previous is not None:
            changes.append((path, previous, None))
    return changes


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

    def supersedes_of(self, row, fpe, ptype, submitted):
        parent = str(row.get("parentDocID") or "")
        if DOC_ID.match(parent) and parent != row["docID"]:
            return parent
        earlier = [f for f in self.data["filings"] if f["status"] == "ingested" and f["fiscal_period_end"] == fpe
                   and f["period_type"] == ptype and f["submitted_at"] < submitted and f["doc_id"] != row["docID"]]
        return max(earlier, key=lambda f: (f["submitted_at"], f["doc_id"]))["doc_id"] if earlier else None

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
            for path, old, new in value_changes(old_row, new_row, f"/{section}/{index}", f"/{section}/{index}"):
                self.data["revisions"].append({"at": self.now_text, "doc_id": filing["doc_id"],
                                               "supersedes": old_row["doc_id"], "path": path, "old": old, "new": new})
                self.changes.append({"kind": "replaced", "doc_id": filing["doc_id"],
                                     "message": f"{path}: {old} → {new}（置き換え元 {old_row['doc_id']}）"})
            rows[index] = new_row
        else:  # 古い書類があとから届いた。値は変えない
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
    data = builder.data
    data["filings"].sort(key=lambda f: (f["submitted_at"], f["doc_id"]))
    data["filings"] = [{k: f[k] for k in FILING_KEYS if k in f} for f in data["filings"]]
    if existing is not None and data == existing:
        return copy.deepcopy(existing), builder.changes  # 変更なし。updated_at も変えない
    data["updated_at"] = builder.now_text
    return {key: data[key] for key in TOP_KEYS}, builder.changes
