"""AIの呼び出し層（アーキテクチャ設計書 P05、8.1）。AIを呼び出せるのは、この層だけである（CLAUDE.md 9章）。

1回の呼び出しの順番:
  1. config/operations.yaml が paused なら呼ばない（skipped_paused）
  2. 今月（日本時間）の利用額を、ledger の月のファイルの cost_jpy から合計し、エージェントの cap_jpy と
     monthly_cap_jpy の残りを、入力の大きさと max_tokens から見積もった最大の金額が超えるなら呼ばない（skipped_budget）
  3. agents/{ID}/ の指示文（prompt.md）と出力の形式（output.schema.json）を読む
  4. 呼ぶ（SDKの構造化出力。使えなければ、本文のJSONを取り出す）
  5. 出力を jsonschema で検証する。合わなければ1回だけやり直し、2回目も合わなければ invalid_output
  6. 呼び出しごとに ledger の行（データ定義書 10.3）を作る。ops-log には書かない（呼び出し側が行う）

* モデルと単価は config/budgets.yaml から読む（コードに書かない）
* 認証は Workload Identity Federation。anthropic.Anthropic() を引数なしで作り、環境変数
  （ANTHROPIC_IDENTITY_TOKEN_FILE、ANTHROPIC_FEDERATION_RULE_ID など）はSDKが読む。APIキーは使わない
* 資料（原資料束の本文）は、指示の区画と分けた「資料」の区画に入れる（アーキテクチャ設計書 8.4）
* 資料の本文と、AIの出力の生の文字列を、例外のメッセージ、ログに出さない（リポジトリ、Actionsのログは公開）
"""

from __future__ import annotations

import json
import math
import re
import time
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

import anthropic
import yaml
from jsonschema import Draft202012Validator

REPO_ROOT = Path(__file__).resolve().parents[2]
BUDGETS_PATH = REPO_ROOT / "config" / "budgets.yaml"
OPERATIONS_PATH = REPO_ROOT / "config" / "operations.yaml"
AGENTS_DIR = REPO_ROOT / "agents"
JST = ZoneInfo("Asia/Tokyo")

DEFAULT_MAX_TOKENS = 4096
TIMEOUT_SECONDS = 120  # 1回の呼び出しの時間の上限
RETRY_WAITS = (5.0, 20.0)  # 通信の失敗は、間を空けて2回まで再試行する
TOKENS_PER_CHAR = 1.5  # 入力のトークン数の見積もり（日本語は、1文字あたり多めに見る）

STATUS_OK = "ok"
STATUS_INVALID = "invalid_output"
STATUS_FAILED = "failed"
STATUS_SKIP_BUDGET = "skipped_budget"
STATUS_SKIP_PAUSED = "skipped_paused"

_RETRYABLE = (anthropic.APIConnectionError, anthropic.APITimeoutError, anthropic.RateLimitError,
              anthropic.InternalServerError)


class LlmError(Exception):
    """設定の誤りなど。メッセージは、本文を含まない。"""


@dataclass
class AgentResult:
    status: str
    output: dict | None = None
    rows: list[dict] = field(default_factory=list)  # この呼び出しの ledger の行
    reason: str = ""  # 呼ばなかった、または失敗した理由（本文を含まない）

    @property
    def cost_jpy(self) -> float:
        return round(sum(r["cost_jpy"] for r in self.rows), 4)


# ---- 設定 ---------------------------------------------------------------------------------

def _load_yaml(path: Path, what: str) -> dict:
    try:
        data = yaml.safe_load(path.read_text(encoding="utf-8"))
    except (OSError, yaml.YAMLError):
        raise LlmError(f"{what} を読めなかった") from None
    if not isinstance(data, dict):
        raise LlmError(f"{what} の形が正しくない")
    return data


def load_budgets(path: Path = BUDGETS_PATH) -> dict:
    return _load_yaml(path, "config/budgets.yaml")


def load_operations(path: Path = OPERATIONS_PATH) -> dict:
    data = _load_yaml(path, "config/operations.yaml")
    if data.get("status") not in ("active", "paused"):
        raise LlmError("config/operations.yaml の status は active か paused にする")
    return data


def model_and_prices(budgets: dict, agent: str) -> tuple[str, dict]:
    entry = (budgets.get("agents") or {}).get(agent)
    if not isinstance(entry, dict):
        raise LlmError(f"config/budgets.yaml に、エージェント {agent} がない")
    model = entry.get("model")
    prices = next((m for m in budgets.get("models") or [] if isinstance(m, dict) and m.get("id") == model), None)
    if prices is None:
        raise LlmError(f"config/budgets.yaml の models に、{model} の単価がない")
    return model, prices


def load_agent(agent: str, agents_dir: Path = AGENTS_DIR) -> tuple[str, dict]:
    """agents/{ID}/ の指示文と、出力の形式（スキーマ）を読む。出力の形式が $ref だけなら、参照先を読む。"""
    directory = agents_dir / agent
    try:
        prompt = (directory / "prompt.md").read_text(encoding="utf-8")
        schema_path = directory / "output.schema.json"
        schema = json.loads(schema_path.read_text(encoding="utf-8"))
        if isinstance(schema, dict) and set(schema) <= {"$ref", "$schema", "title", "description"} and "$ref" in schema:
            schema = json.loads((schema_path.parent / schema["$ref"]).resolve().read_text(encoding="utf-8"))
        Draft202012Validator.check_schema(schema)
    except (OSError, ValueError):
        raise LlmError(f"agents/{agent}/ の指示文か出力の形式を読めなかった") from None
    return prompt, schema


# ---- 利用額 -------------------------------------------------------------------------------

def month_of(moment: datetime) -> str:
    return moment.astimezone(JST).strftime("%Y-%m")


def month_usage_jpy(ledger_dir: Path, month: str, agent: str) -> tuple[float, float]:
    """今月の利用額を、(全体, 指定のエージェント) の円で返す。ファイルがなければ 0。"""
    path = ledger_dir / f"{month}.jsonl"
    total = per_agent = 0.0
    if not path.is_file():
        return total, per_agent
    try:
        lines = path.read_text(encoding="utf-8").splitlines()
    except (OSError, UnicodeDecodeError):
        raise LlmError(f"ledger {path.name} を読めなかった") from None
    for number, line in enumerate(lines, 1):
        if not line.strip():
            continue
        try:
            row = json.loads(line)
            cost = float(row["cost_jpy"])
        except (ValueError, KeyError, TypeError):
            raise LlmError(f"ledger {path.name} の {number} 行目を読めなかった") from None
        total += cost
        if row.get("agent") == agent:
            per_agent += cost
    return total, per_agent


def cost_usd(prices: dict, input_tokens: int, output_tokens: int, cache_write: int, cache_read: int) -> float:
    return (input_tokens * prices["input"] + output_tokens * prices["output"]
            + cache_write * prices["cache_write"] + cache_read * prices["cache_read"]) / 1_000_000


def estimate_max_cost_jpy(budgets: dict, prices: dict, input_chars: int, max_tokens: int) -> float:
    """入力の大きさと max_tokens から、1回の呼び出しの最大の金額（円）を見積もる。"""
    input_tokens = math.ceil(input_chars * TOKENS_PER_CHAR)
    input_price = max(prices["input"], prices["cache_write"])
    usd = (input_tokens * input_price + max_tokens * prices["output"]) / 1_000_000
    return usd * budgets["usd_jpy"]


def make_row(moment: datetime, run_id: str, agent: str, model: str, status: str, subject: str | None,
             prices: dict | None, usd_jpy: float, usage: dict | None = None) -> dict:
    usage = usage or {}
    tokens = {k: int(usage.get(k) or 0) for k in
              ("input_tokens", "output_tokens", "cache_write_tokens", "cache_read_tokens")}
    usd = cost_usd(prices, tokens["input_tokens"], tokens["output_tokens"],
                   tokens["cache_write_tokens"], tokens["cache_read_tokens"]) if prices else 0.0
    row = {"at": moment.astimezone(JST).replace(microsecond=0).isoformat(), "run_id": run_id, "agent": agent,
           "model": model, **tokens, "cost_usd": round(usd, 6), "cost_jpy": round(usd * usd_jpy, 4), "status": status}
    if subject:
        row["subject"] = subject
    return row


# ---- 出力の取り出しと検証 ---------------------------------------------------------------

def extract_json(text: str) -> object | None:
    """応答の文字列から、JSONを取り出す。コードブロックの囲みがあれば外す。取り出せなければ None。"""
    text = text.strip()
    fenced = re.match(r"^```[A-Za-z]*\n(.*)\n```$", text, re.DOTALL)
    if fenced:
        text = fenced.group(1)
    try:
        return json.loads(text)
    except ValueError:
        pass
    start, end = text.find("{"), text.rfind("}")
    if start != -1 and end > start:
        try:
            return json.loads(text[start:end + 1])
        except ValueError:
            return None
    return None


def schema_problems(schema: dict, output: object) -> list[str]:
    """形式の不合格を、場所と規則の名前だけで返す（メッセージには、出力の文字が入りうるため、使わない）。"""
    validator = Draft202012Validator(schema)
    found = sorted(validator.iter_errors(output), key=lambda e: [str(p) for p in e.absolute_path])
    return [f"{'/'.join(str(p) for p in e.absolute_path) or '(全体)'}: {e.validator}" for e in found[:10]]


def _usage_of(response) -> dict:
    usage = getattr(response, "usage", None)
    return {
        "input_tokens": getattr(usage, "input_tokens", 0),
        "output_tokens": getattr(usage, "output_tokens", 0),
        "cache_write_tokens": getattr(usage, "cache_creation_input_tokens", 0),
        "cache_read_tokens": getattr(usage, "cache_read_input_tokens", 0),
    }


def _text_of(response) -> str:
    return "".join(getattr(b, "text", "") for b in getattr(response, "content", []) if getattr(b, "type", "") == "text")


# ---- 呼び出し -----------------------------------------------------------------------------

def call_agent(
    agent: str,
    task: str,
    materials: str,
    *,
    run_id: str,
    subject: str | None = None,
    ledger_dir: Path,
    max_tokens: int = DEFAULT_MAX_TOKENS,
    now=lambda: datetime.now(JST),
    sleep=time.sleep,
    client_factory=lambda: anthropic.Anthropic(),
    budgets_path: Path = BUDGETS_PATH,
    operations_path: Path = OPERATIONS_PATH,
    agents_dir: Path = AGENTS_DIR,
) -> AgentResult:
    """エージェントを1回呼ぶ。task は指示の区画（プログラムが作った入力）、materials は資料の区画（外から届いた文章）。

    設定の誤りは LlmError。呼ばなかった、形式に合わなかった、通信に失敗したときは、例外にせず、status で返す
    （どの場合も、ledger の行を rows に入れる）。
    """
    budgets = load_budgets(budgets_path)
    operations = load_operations(operations_path)
    model, prices = model_and_prices(budgets, agent)
    usd_jpy = budgets["usd_jpy"]
    result = AgentResult(STATUS_OK)

    def add(status: str, usage: dict | None = None) -> None:
        result.rows.append(make_row(now(), run_id, agent, model, status, subject, prices, usd_jpy, usage))

    if operations["status"] == "paused":
        add(STATUS_SKIP_PAUSED)
        result.status, result.reason = STATUS_SKIP_PAUSED, "config/operations.yaml が paused のため、呼ばなかった"
        return result

    prompt, schema = load_agent(agent, agents_dir)
    system = prompt
    task_block = {"type": "text", "text": task}
    materials_block = {"type": "text", "cache_control": {"type": "ephemeral"},
                       "text": "<資料>\n" + materials.replace("<", "＜") + "\n</資料>"}
    input_chars = len(system) + len(task) + len(materials_block["text"]) + len(json.dumps(schema, ensure_ascii=False))
    estimate = estimate_max_cost_jpy(budgets, prices, input_chars, max_tokens)
    cap = budgets["agents"][agent]["cap_jpy"]
    client = None
    attempt_note = ""  # やり直しのときに、形式の不合格の場所を伝える
    use_structured = True

    for attempt in (1, 2):
        total, per_agent = month_usage_jpy(ledger_dir, month_of(now()), agent)
        spent_now = sum(r["cost_jpy"] for r in result.rows)  # この呼び出しの中の、まだ ledger に入っていない分
        remaining = min(cap - per_agent - spent_now, budgets["monthly_cap_jpy"] - total - spent_now)
        if estimate > remaining:
            add(STATUS_SKIP_BUDGET)
            result.status = STATUS_SKIP_BUDGET
            result.reason = (f"見積もりの最大 {estimate:.1f}円が、残りの予算 {max(remaining, 0):.1f}円を超えるため、呼ばなかった")
            return result
        if client is None:
            client = client_factory().with_options(max_retries=0)
        content = [task_block, materials_block] + ([{"type": "text", "text": attempt_note}] if attempt_note else [])
        response = None
        failure = ""
        tries = 0
        while True:
            kwargs = dict(model=model, max_tokens=max_tokens, system=system, timeout=TIMEOUT_SECONDS,
                          messages=[{"role": "user", "content": content}])
            if use_structured:
                kwargs["output_config"] = {"format": {"type": "json_schema", "schema": schema}}
            try:
                response = client.messages.create(**kwargs)
                break
            except anthropic.BadRequestError:
                if use_structured:  # 構造化出力が使えない（形式の機能の制限など）。本文のJSONを取り出す方式に切り替える
                    use_structured = False
                    content = content + [{"type": "text", "text": "出力は、指定の形式のJSONだけにする（説明の文章を付けない）。"}]
                    continue
                failure = "BadRequestError"
                break
            except _RETRYABLE as error:
                failure = type(error).__name__
                if tries >= len(RETRY_WAITS):
                    break
                sleep(RETRY_WAITS[tries])
                tries += 1
            except anthropic.APIError as error:  # 認証の失敗など。再試行しない
                failure = type(error).__name__
                break
        if response is None:
            add(STATUS_FAILED)
            result.status, result.reason = STATUS_FAILED, f"AIの呼び出しに失敗した（{failure}）"
            return result
        usage = _usage_of(response)
        output = extract_json(_text_of(response))
        problems = schema_problems(schema, output) if output is not None else ["(全体): json"]
        if not problems:
            add(STATUS_OK, usage)
            result.status, result.output = STATUS_OK, output
            return result
        add(STATUS_INVALID, usage)  # 1回目の形式の不合格も、呼んだ分は ledger に残す
        if attempt == 2:
            result.status = STATUS_INVALID
            result.reason = "出力が形式に合わなかった（やり直しても同じ）: " + "; ".join(problems)
            return result
        attempt_note = "前回の出力は、出力の形式に合わなかった。次の場所を直して、もう一度、形式のとおりに返す: " + "; ".join(problems)
    return result  # 到達しない
