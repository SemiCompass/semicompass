"""EDINETの書類（type=5、CSV形式のZIP）から、文章の行（要素IDが TextBlock で終わる行）を取り出す純粋な関数。

通信もファイルの読み書きもしない。ZIPの展開、文字コードの判定、ヘッダーの読み方は、
scripts/edinet/inspect_document.py の関数をそのまま使う（csv_reader.py と同じ読み方を共有するため）。

文章の行の「値」はHTMLの断片である。標準ライブラリの html.parser で、プレーンテキストに直す。
  * script、style の中身は捨てる
  * 段落、見出し、表の行、箇条書きの項目などは、改行で区切る
  * 表のセルは、空白で区切る
  * 実体参照（&amp; など）は、文字に戻す
  * 連続する空白は1つにまとめ、空の行は残さない

注意：このモジュールの例外のメッセージには、本文を入れない（リポジトリは公開）。
"""

from __future__ import annotations

import csv
import re
import sys
from dataclasses import dataclass
from html.parser import HTMLParser
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "edinet"))

import inspect_document as inspector  # noqa: E402

TEXT_BLOCK_SUFFIX = "TextBlock"

_SKIPPED_TAGS = {"script", "style"}
_LINE_BREAK_TAGS = {
    "p", "div", "br", "hr", "li", "ul", "ol", "dl", "dt", "dd", "tr", "table", "thead", "tbody", "tfoot",
    "caption", "h1", "h2", "h3", "h4", "h5", "h6", "section", "article", "header", "footer", "blockquote",
    "pre", "figure", "figcaption",
}
_CELL_TAGS = {"td", "th"}
_SPACES = re.compile(r"[ \t\r\n\f\v\xa0]+")


@dataclass(frozen=True)
class TextRow:
    """文章の行1つ。text は、HTMLをプレーンテキストに直したもの。"""

    element_id: str
    label: str
    context_id: str
    text: str
    file: str  # ZIPの中のCSVの名前

    @property
    def chars(self) -> int:
        return len(self.text)


class _TextExtractor(HTMLParser):
    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self._lines: list[str] = []
        self._buffer: list[str] = []
        self._skip_depth = 0

    def _flush(self) -> None:
        line = _SPACES.sub(" ", "".join(self._buffer)).strip()
        self._buffer = []
        if line:
            self._lines.append(line)

    def handle_starttag(self, tag: str, attrs) -> None:  # noqa: D102
        if tag in _SKIPPED_TAGS:
            self._skip_depth += 1
        elif self._skip_depth == 0 and tag in _LINE_BREAK_TAGS:
            self._flush()

    def handle_startendtag(self, tag: str, attrs) -> None:  # noqa: D102
        if tag in _SKIPPED_TAGS:
            return  # <script/> のように中身がないものは、深さを増やさない
        self.handle_starttag(tag, attrs)

    def handle_endtag(self, tag: str) -> None:  # noqa: D102
        if tag in _SKIPPED_TAGS:
            self._skip_depth = max(self._skip_depth - 1, 0)
        elif self._skip_depth == 0:
            if tag in _LINE_BREAK_TAGS:
                self._flush()
            elif tag in _CELL_TAGS:
                self._buffer.append(" ")

    def handle_data(self, data: str) -> None:  # noqa: D102
        if self._skip_depth == 0:
            self._buffer.append(data)

    def text(self) -> str:
        self.close()
        self._flush()
        return "\n".join(self._lines)


def html_to_text(html: str) -> str:
    """HTMLの断片を、プレーンテキストにする。同じ入力には、同じ結果を返す。"""
    parser = _TextExtractor()
    parser.feed(html)
    return parser.text()


def text_rows_from_csv(data: bytes, file: str = "") -> list[TextRow]:
    """CSV1ファイルのバイト列から、文章の行を、CSVに現れる順で返す。

    要素IDが TextBlock で終わる行だけを取る。HTMLを直した後に空になる行は除く。
    ヘッダー行に、要素ID・値の列がなければ ValueError。
    """
    text, _encoding = inspector.decode_csv(data)
    header, rows = inspector.parse_csv(text)
    positions = inspector.map_columns(header)
    if any(role not in positions for role in inspector.REQUIRED_COLUMNS):
        raise ValueError("ヘッダー行に、要素ID・値の列が見つからない")
    width = max(positions.values()) + 1
    result = []
    for row in rows:
        padded = row + [""] * (width - len(row))
        element = padded[positions["element"]].strip()
        if not element.endswith(TEXT_BLOCK_SUFFIX):
            continue
        body = html_to_text(padded[positions["value"]])
        if not body:
            continue
        result.append(TextRow(
            element_id=element,
            label=padded[positions["label"]].strip() if "label" in positions else "",
            context_id=padded[positions["context"]].strip() if "context" in positions else "",
            text=body,
            file=file,
        ))
    return result


def text_rows_from_zip(raw: bytes) -> tuple[list[TextRow], list[str]]:
    """書類のZIPの、すべてのCSVから文章の行を取り出す。返り値は (行, 読めなかったCSVの記録)。

    ZIPはメモリの中だけで展開する。ZIPが読めないときは ValueError。
    読めないCSVの記録には、CSVの名前と理由の種類だけを入れる（本文は入れない）。
    """
    rows: list[TextRow] = []
    problems: list[str] = []
    for name, _size, data in inspector.read_zip(raw):
        if data is None:
            continue
        shown = inspector._printable(name)
        try:
            rows += text_rows_from_csv(data, shown)
        except ValueError as error:
            problems.append(f"{shown}: {error}")
        except csv.Error:
            problems.append(f"{shown}: CSVとして読めなかった")
    return rows, problems
