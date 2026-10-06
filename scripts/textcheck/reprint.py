"""転載の検査（CLAUDE.md 2章の4）。

下書きの文字列と、原資料束の各節の本文を比べ、空白を除いて、min_run_chars（config/textcheck.yaml。既定は30）字以上、
連続して同じ箇所があれば不合格にする。比べる前に、NFKCで正規化し、空白（全角を含む）を除く。

結果には、一致した長さと、場所の種類（下書きのどの項目か）だけを持たせる。**文章は、結果にも例外にも入れない**。
"""

from __future__ import annotations

import re
import unicodedata
from dataclasses import dataclass
from pathlib import Path

import yaml

CONFIG_PATH = Path(__file__).resolve().parents[2] / "config" / "textcheck.yaml"
_SEPARATOR = "\x00"  # 節と節の境目をまたぐ一致を数えないための、本文に現れない文字


@dataclass(frozen=True)
class RunResult:
    field: str  # 下書きの項目の場所（例：overview、segments[0].note）
    longest: int  # 最も長く連続して一致した文字数
    failed: bool


def load_min_run(path: Path = CONFIG_PATH) -> int:
    try:
        value = yaml.safe_load(path.read_text(encoding="utf-8")).get("min_run_chars")
    except (OSError, yaml.YAMLError, AttributeError):
        raise ValueError("config/textcheck.yaml を読めなかった") from None
    if not isinstance(value, int) or isinstance(value, bool) or value < 1:
        raise ValueError("config/textcheck.yaml の min_run_chars は、1以上の整数にする")
    return value


def normalize(text: str) -> str:
    return re.sub(r"\s+", "", unicodedata.normalize("NFKC", text)).replace(_SEPARATOR, "")


class _Automaton:
    """原資料束の本文全体の、サフィックスオートマトン。下書きの文字列との、最長の連続一致を求める。"""

    def __init__(self, text: str):
        self.next: list[dict[str, int]] = [{}]
        self.link = [-1]
        self.length = [0]
        last = 0
        for ch in text:
            cur = len(self.next)
            self.next.append({})
            self.length.append(self.length[last] + 1)
            self.link.append(0)
            p = last
            while p != -1 and ch not in self.next[p]:
                self.next[p][ch] = cur
                p = self.link[p]
            if p != -1:
                q = self.next[p][ch]
                if self.length[p] + 1 == self.length[q]:
                    self.link[cur] = q
                else:
                    clone = len(self.next)
                    self.next.append(dict(self.next[q]))
                    self.length.append(self.length[p] + 1)
                    self.link.append(self.link[q])
                    while p != -1 and self.next[p].get(ch) == q:
                        self.next[p][ch] = clone
                        p = self.link[p]
                    self.link[q] = self.link[cur] = clone
            last = cur

    def longest_common(self, text: str) -> int:
        state = length = best = 0
        for ch in text:
            while state and ch not in self.next[state]:
                state = self.link[state]
                length = self.length[state]
            if ch in self.next[state]:
                state = self.next[state][ch]
                length += 1
            else:
                state = length = 0
            best = max(best, length)
        return best


def check_reprint(sources: list[str], fields: dict[str, str], min_run: int) -> list[RunResult]:
    """fields（場所 → 下書きの文字列）それぞれについて、sources との最長の連続一致を返す。"""
    automaton = _Automaton(_SEPARATOR.join(normalize(s) for s in sources))
    return [RunResult(name, automaton.longest_common(normalize(text)), False) for name, text in fields.items()]


def failures(results: list[RunResult], min_run: int) -> list[RunResult]:
    return [RunResult(r.field, r.longest, True) for r in results if r.longest >= min_run]


def longest_overall(results: list[RunResult]) -> int:
    return max((r.longest for r in results), default=0)
