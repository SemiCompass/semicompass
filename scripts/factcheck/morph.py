"""形態素解析による一般語の判定（アーキテクチャ設計書 9.3）。SudachiPy が入っているときだけ使う（なければ、何も一般語としない）。

辞書の語（企業マスタ・用語集）と1文字違いの語が、実は一般の語（例：「アクセス」と「アクセル」）のとき、書き間違いの指摘にしない。
一般語とするのは、辞書に載っている1語の普通名詞だけ（未知の語は、一般語としない。書き間違いは、未知の語になりやすい）。
"""
from __future__ import annotations

from functools import lru_cache

_tokenizer = None
_loaded = False


def _get():
    global _tokenizer, _loaded
    if not _loaded:
        _loaded = True
        try:
            from sudachipy import dictionary, tokenizer  # noqa: F401
            _tokenizer = (dictionary.Dictionary(dict="core").create(), tokenizer.Tokenizer.SplitMode.C)
        except Exception:  # noqa: BLE001（入っていない、辞書がない：使わない）
            _tokenizer = None
    return _tokenizer


def available() -> bool:
    return _get() is not None


@lru_cache(maxsize=4096)
def is_common_word(word: str) -> bool:
    got = _get()
    if got is None:
        return False
    tok, mode = got
    morphemes = tok.tokenize(word, mode)
    if len(morphemes) != 1:
        return False
    m = morphemes[0]
    pos = m.part_of_speech()
    return m.surface() == word and not m.is_oov() and pos[0] == "名詞" and pos[1] in ("普通名詞", "副詞可能")
