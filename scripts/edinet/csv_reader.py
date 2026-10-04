"""EDINETの書類（CSV形式のZIP）を、列名のままの辞書の行にする（取り出し用の読み取り）。

文字コードの判定、ヘッダー、ZIPの展開は、inspect_document.py の関数をそのまま使う
（調査用スクリプトを変えずに、同じ読み方を共有するため）。inspect_document.extract_numeric_rows は
数値の行だけを返すが、取り出しにはDEIの文章の行（会計基準など）も要るため、
数値の行、DEIの行を残し、TextBlock の行と、その他の文章の行を除く。
"""

from __future__ import annotations

import csv
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

import inspect_document as inspector  # noqa: E402

DEI_EDINET_CODE = "jpdei_cor:EDINETCodeDEI"


def rows_from_csv(data: bytes) -> list[dict]:
    """CSV1ファイルのバイト列を、列名のままの辞書の行にする（数値の行とDEIの行だけ）。"""
    text, _encoding = inspector.decode_csv(data)
    header, rows = inspector.parse_csv(text)
    positions = inspector.map_columns(header)
    missing = [role for role in inspector.REQUIRED_COLUMNS if role not in positions]
    if missing:
        raise ValueError("ヘッダー行に、要素ID・値の列が見つからない")
    names = inspector.unique_headers(header)
    kept = []
    for row in rows:
        padded = row + [""] * (len(names) - len(row))
        element = padded[positions["element"]].strip()
        if element.endswith("TextBlock"):
            continue
        if inspector.is_numeric(padded[positions["value"]]) or element.startswith(inspector.DEI_PREFIX):
            kept.append({names[i]: padded[i] for i in range(len(names))})
    return kept


def document_rows(raw: bytes) -> list[dict]:
    """書類のZIPから、DEIの行を持つCSV（本文のCSV）の行を返す。ZIPはメモリの中だけで展開する。

    DEIの行を持つCSVが、ちょうど1つでなければ ValueError（どれを使うか、推測しない）。
    """
    candidates = []
    for name, _size, data in inspector.read_zip(raw):
        if data is None:
            continue
        try:
            rows = rows_from_csv(data)
        except (ValueError, csv.Error):
            continue
        element_key = next((k for k in rows[0] if inspector._normalize(k) in ("要素id", "elementid")), None) if rows else None
        if element_key and any(r[element_key].strip().startswith(inspector.DEI_PREFIX) for r in rows):
            candidates.append((name, rows))
    if not candidates:
        raise ValueError("DEIの行を持つCSVがZIPの中にない")
    if len(candidates) > 1:
        raise ValueError(f"DEIの行を持つCSVが複数ある（{len(candidates)}個）。どれを使うか決められない")
    return candidates[0][1]
