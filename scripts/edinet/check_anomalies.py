"""取り込みの前後の data/auto/ を比べて、異常値を検知する（J01、要件定義書 7.9）。

使い方: python3 scripts/edinet/check_anomalies.py --before 取り込み前のフォルダ --after data/auto [--out 結果.md]

* 取り込みで追加・変わった期（financials）だけを調べる（前から入っている期は、毎回調べ直さない）
* 検知：売上高の前年同期比が±50%超／営業利益・純利益の符号の変化／前の期と1,000倍前後の差（単位の誤り）／
  前の期にあった項目の欠け／セグメントの外部売上の合計と全社の売上の差が5%超／取得の失敗（filings の failed）
* 基準の値は config/edinet-anomaly.yaml。結果には、企業、期、項目、値の比だけを出す（資料の本文は扱わない）
終了コード: 0 異常なし／10 異常あり／2 引数・入力の誤り
"""
from __future__ import annotations

import argparse
import json
import sys
from datetime import date
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parents[2]
FIELDS = (("net_sales", "売上高"), ("operating_income", "営業利益"), ("net_income", "純利益"))
EXIT_ANOMALY = 10


def load_config(path: Path | None = None) -> dict:
    return yaml.safe_load((path or ROOT / "config" / "edinet-anomaly.yaml").read_text(encoding="utf-8"))


def val(entry: dict, key: str):
    v = entry.get(key)
    return v.get("value") if isinstance(v, dict) else None


def key_of(entry: dict) -> tuple:
    return (entry.get("period_type"), entry.get("period_end"), entry.get("doc_id"))


def previous(entry: dict, entries: list[dict]) -> dict | None:
    """同じ種類（通期・半期）で、約1年前に終わる期。"""
    try:
        end = date.fromisoformat(entry["period_end"])
    except (KeyError, ValueError, TypeError):
        return None
    best = None
    for e in entries:
        if e.get("period_type") != entry.get("period_type"):
            continue
        try:
            gap = (end - date.fromisoformat(e["period_end"])).days
        except (KeyError, ValueError, TypeError):
            continue
        if 350 <= gap <= 380 and (best is None or e.get("doc_id") == entry.get("doc_id") or best.get("doc_id") != entry.get("doc_id")):
            best = e
    return best


def changed_entries(before: dict | None, after: dict) -> list[dict]:
    old = {key_of(e): e for e in (before or {}).get("financials", [])}
    out = []
    for e in after.get("financials", []):
        o = old.get(key_of(e))
        if o is None or any(val(o, k) != val(e, k) for k, _ in FIELDS):
            out.append(e)
    return out


def check_company(slug: str, before: dict | None, after: dict, cfg: dict) -> list[str]:
    msgs: list[str] = []
    entries = after.get("financials", [])
    for e in changed_entries(before, after):
        label = f"{slug} {e.get('period_end')}（{e.get('period_type')}）"
        prev = previous(e, entries)
        for k, name in FIELDS:
            now = val(e, k)
            if prev is None:
                continue
            was = val(prev, k)
            if was is not None and now is None:
                msgs.append(f"欠け：{label} の{name}が、前の期にはあるが、ない")
                continue
            if was is None or now is None:
                continue
            if k == "net_sales" and was:
                change = now / was - 1
                if abs(change) > cfg["sales_change_ratio"]:
                    msgs.append(f"前の期からの急変：{label} の売上高が前年同期比{change * 100:+.1f}%")
            if k in ("operating_income", "net_income") and was and now and (was > 0) != (now > 0):
                msgs.append(f"前の期からの急変：{label} の{name}の符号が変わった")
            if was and now:
                ratio = abs(now / was)
                lo, hi = cfg["unit_ratio_low"], cfg["unit_ratio_high"]
                if lo <= ratio <= hi or lo <= 1 / ratio <= hi:
                    msgs.append(f"単位の誤り：{label} の{name}が、前の期の約{ratio:g}倍")
        if prev is not None and prev.get("segments") and not e.get("segments"):
            msgs.append(f"欠け：{label} のセグメントが、前の期にはあるが、ない")
        sales = val(e, "net_sales")
        parts = [val(s, "net_sales_external") for s in e.get("segments") or []]
        if e.get("period_type") == "annual" and sales and parts and all(p is not None for p in parts):  # 半期は、セグメントの期間が全社と違うことがあり、比べない
            gap = abs(sum(parts) - sales) / abs(sales)
            if gap > cfg["segment_sales_gap_ratio"]:
                msgs.append(f"合計の不一致：{label} のセグメントの外部売上の合計と全社の売上の差が{gap * 100:.1f}%")
    old_status = {f.get("doc_id"): f.get("status") for f in (before or {}).get("filings", [])}
    for f in after.get("filings", []):
        if f.get("status") == "failed" and old_status.get(f.get("doc_id")) != "failed":
            msgs.append(f"取得の失敗：{slug} の書類 {f.get('doc_id')} を取得できなかった")
    return msgs


def run(before_dir: Path, after_dir: Path, cfg: dict) -> dict[str, list[str]]:
    result: dict[str, list[str]] = {}
    for path in sorted(after_dir.glob("*.json")):
        after = json.loads(path.read_text(encoding="utf-8"))
        bpath = before_dir / path.name
        before = json.loads(bpath.read_text(encoding="utf-8")) if bpath.is_file() else None
        if before is not None and before == after:
            continue
        msgs = check_company(path.stem, before, after, cfg)
        if msgs:
            result[path.stem] = msgs
    return result


def render(result: dict[str, list[str]]) -> str:
    if not result:
        return "## 異常値の検知\n\n異常なし（要件定義書7.9の基準）。\n"
    lines = ["## 異常値の検知：異常あり", "", "自動の取り込みはしない。内容を確かめてから、運営者が判断する。", ""]
    for slug, msgs in result.items():
        lines += [f"### {slug}", *[f"* {m}" for m in msgs], ""]
    return "\n".join(lines)


def main(argv=None) -> int:
    p = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    p.add_argument("--before", required=True, type=Path)
    p.add_argument("--after", required=True, type=Path)
    p.add_argument("--out", type=Path)
    p.add_argument("--config", type=Path)
    a = p.parse_args(argv)
    try:
        result = run(a.before, a.after, load_config(a.config))
    except (OSError, ValueError, KeyError, yaml.YAMLError) as error:
        print(f"入力の誤り：{type(error).__name__}")
        return 2
    text = render(result)
    print(text)
    if a.out:
        a.out.write_text(text, encoding="utf-8")
    return EXIT_ANOMALY if result else 0


if __name__ == "__main__":
    sys.exit(main())
