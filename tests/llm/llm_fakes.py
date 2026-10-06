"""AIの呼び出し層と下書きのテストで使う、APIの偽物。実際の書類の文章は使わない。"""

import json
import sys
from datetime import datetime
from pathlib import Path
from types import SimpleNamespace
from zoneinfo import ZoneInfo

ROOT = Path(__file__).resolve().parents[2]
for sub in ("llm", "textcheck", "bundle", "validate", "edinet", "draft"):
    sys.path.insert(0, str(ROOT / "scripts" / sub))

import httpx2 as httpx  # noqa: E402  anthropic が使う HTTP の部品

import agent_call  # noqa: E402

JST = ZoneInfo("Asia/Tokyo")
NOW = datetime(2026, 10, 6, 12, 0, 0, tzinfo=JST)
SOURCE_WORD = "ゼータ合成語アルファ"  # 資料の本文にだけある語。出力のどこにも出ない
OUTPUT_WORD = "イータ合成語ベータ"  # AIの出力にだけある語。ログ、要約、例外に出ない


def usage(i=1000, o=500, w=0, r=0):
    return SimpleNamespace(input_tokens=i, output_tokens=o, cache_creation_input_tokens=w, cache_read_input_tokens=r)


def reply(output, **kw):
    text = output if isinstance(output, str) else json.dumps(output, ensure_ascii=False)
    return SimpleNamespace(content=[SimpleNamespace(type="text", text=text)], usage=usage(**kw))


class FakeClient:
    """messages.create の呼び出しを記録し、steps を順に返す（例外ならそれを投げる）。"""

    def __init__(self, *steps):
        self.steps = list(steps)
        self.calls = []
        self.options = []
        self.messages = self

    def with_options(self, **kw):
        self.options.append(kw)
        return self

    def create(self, **kwargs):
        self.calls.append(kwargs)
        step = self.steps.pop(0) if len(self.steps) > 1 else self.steps[0]
        if isinstance(step, Exception):
            raise step
        return step


def conn_error():
    return agent_call.anthropic.APIConnectionError(request=httpx.Request("POST", "https://example.invalid"))


def bad_request():
    return agent_call.anthropic.BadRequestError("x", response=httpx.Response(400, request=httpx.Request("POST", "https://x")), body=None)


def cjk(n, start=0x4E00):
    """資料（ひらがな）と重ならない、合成の文字列。"""
    return "".join(chr(start + i) for i in range(n))


def valid_output(members=("AlphaReportableSegmentsMember",), overview_len=350):
    return {
        "overview": cjk(overview_len - 1, 0x4E00) + "。[S1]",
        "process_position": cjk(120, 0x5000) + f"。{OUTPUT_WORD}[S1]",
        "segments": [{"name": "合成セグメント甲", "xbrl_members": list(members), "classification": "semiconductor",
                      "basis": "segment_information"}],
    }
