"""One question to Sonnet 5.5 with web search, through the Messages API.

The request code is Craig's, from craigmmills/gnw-baseline-eval branch
``api-transport`` (PR #1): the request is the whole of the model's context,
one system line and the question, so nothing from this machine (working
directory, budget, email) leaks in, as it did under ``claude -p``. Changes
for the plan (AJ, 2026-10-30): Sonnet 5.5; today's date in the system line,
as claude.ai gives it, so "this month" means the run's month; at most 10
searches and 10 fetches; and a question stops at $1.

The $1 stop can only act between requests: the server runs the search loop
inside one request and pauses (``pause_turn``) after ten iterations, so a
question is stopped when it pauses with $1 already spent. A stopped question
has no reply and counts as no reply, as Horizon's timeouts do. The caps keep
one request's overshoot small.

With the newer web tools a turn can also end ``tool_use`` on a server tool
call (the filtering code still running): it resumes like ``pause_turn``.
Any other unfinished turn has no reply the user would see, and the harness
cannot score it, so it is marked ``incomplete`` and left out, as BENCHMARK
leaves out an attempt it could not score.
"""

from __future__ import annotations

import threading
import time
from typing import Any

MODEL = "claude-sonnet-5-5"
SYSTEM_PROMPT = "You are Claude, a helpful assistant. Today's date is {today}."
MAX_TOKENS = 16_000  # generous ceiling; a reply is a few hundred tokens

# List prices, USD per million tokens (platform.claude.com pricing, checked
# 2026-10-30). Cache reads 0.1x input, 5-minute cache writes 1.25x input. Web
# search is $10 per 1,000 searches; web fetch costs only the tokens it adds.
PRICE_IN, PRICE_OUT = 2.0, 10.0
CACHE_READ_MULT, CACHE_WRITE_MULT = 0.1, 1.25
WEB_SEARCH_USD = 0.01

MAX_SEARCHES = 10
MAX_FETCHES = 10
FETCH_TOKEN_CAP = 12_000
MAX_CONTINUATIONS = 5
STOP_USD = 1.0

# The server-side tool loop re-reads its growing context every iteration;
# automatic caching turns those re-reads into cache hits (September: $1.84 a
# question uncached, $0.18 to $0.33 cached).
CACHE_CONTROL = {"type": "ephemeral"}

# "basic" puts each fetched page into context whole; "dynamic" filters pages
# with code first (built into the 20260209 versions, no extra tool). AJ chose
# the newer, dynamic tools on 2026-10-30, as closer to what users get. Measured
# in September on one Sonnet 5 question: basic $0.18 and 35 s, dynamic $0.33
# and 388 s, with tool-retry chatter in the reply.
WEB_TOOL_VERSIONS = {
    "basic": ("web_search_20250305", "web_fetch_20250910"),
    "dynamic": ("web_search_20260209", "web_fetch_20260209"),
}
DEFAULT_WEB_TOOLS = "dynamic"

# The case store is public on GitHub, so the expected answers are one fetch
# away. Both hosts GitHub serves files from are blocked.
BLOCKED_DOMAINS = ["github.com", "githubusercontent.com"]


def web_tools(versions: str = DEFAULT_WEB_TOOLS) -> list[dict[str, Any]]:
    search_type, fetch_type = WEB_TOOL_VERSIONS[versions]
    return [
        {"type": search_type, "name": "web_search", "max_uses": MAX_SEARCHES,
         "blocked_domains": BLOCKED_DOMAINS},
        {"type": fetch_type, "name": "web_fetch", "max_uses": MAX_FETCHES,
         "blocked_domains": BLOCKED_DOMAINS, "max_content_tokens": FETCH_TOKEN_CAP},
    ]


def zero_usage() -> dict[str, int]:
    return {"input": 0, "output": 0, "cache_read": 0, "cache_write": 0,
            "searches": 0, "fetches": 0, "requests": 0}


def add_usage(total: dict[str, int], usage: Any) -> None:
    """Fold one response's usage in; fields the API leaves unset count 0."""
    def g(obj: Any, name: str) -> int:
        return (getattr(obj, name, None) or 0) if obj is not None else 0

    total["input"] += g(usage, "input_tokens")
    total["output"] += g(usage, "output_tokens")
    total["cache_read"] += g(usage, "cache_read_input_tokens")
    total["cache_write"] += g(usage, "cache_creation_input_tokens")
    server = getattr(usage, "server_tool_use", None)
    total["searches"] += g(server, "web_search_requests")
    total["fetches"] += g(server, "web_fetch_requests")
    total["requests"] += 1


def cost_usd(usage: dict[str, int]) -> float:
    tokens = (usage["input"] * PRICE_IN + usage["output"] * PRICE_OUT
              + usage["cache_read"] * PRICE_IN * CACHE_READ_MULT
              + usage["cache_write"] * PRICE_IN * CACHE_WRITE_MULT) / 1_000_000
    return round(tokens + usage["searches"] * WEB_SEARCH_USD, 6)


def reply_text(content: list[Any]) -> str:
    """Every text block in order: thinking and tool blocks are not read."""
    return "".join(b.text for b in content if getattr(b, "type", None) == "text").strip()


def tool_trail(content: list[Any]) -> list[dict[str, Any]]:
    """What it searched and fetched, for the leakage audit."""
    trail: list[dict[str, Any]] = []
    for b in content:
        kind = getattr(b, "type", None)
        if kind == "server_tool_use":
            trail.append({"tool": b.name, "input": dict(b.input) if b.input else {}})
        elif kind == "web_search_tool_result":
            c = b.content
            trail.append({"results": [getattr(r, "url", None) for r in c]} if isinstance(c, list)
                         else {"search_error": getattr(c, "error_code", str(c))})
        elif kind == "web_fetch_tool_result":
            url = getattr(b.content, "url", None)
            trail.append({"fetched": url} if url
                         else {"fetch_error": getattr(b.content, "error_code", str(b.content))})
    return trail


_client = None
_client_lock = threading.Lock()


def client() -> Any:
    global _client
    with _client_lock:
        if _client is None:
            import anthropic
            # The SDK retries 429s and 5xx with back-off; hundreds of calls
            # want more headroom than the default two.
            _client = anthropic.Anthropic(max_retries=6, timeout=600.0)
    return _client


def resumable(response: Any) -> bool:
    """The server's own tool loop is unfinished: resend and it resumes."""
    if response.stop_reason == "pause_turn":
        return True
    last = response.content[-1] if response.content else None
    return response.stop_reason == "tool_use" and getattr(last, "type", None) == "server_tool_use"


def ask(query: str, today: str, versions: str = DEFAULT_WEB_TOOLS,
        api: Any = None) -> dict[str, Any]:
    """One question. Returns the reply ("" when stopped or incomplete), the
    trail, each response's stop reason and blocks, and the summed usage with
    its cost."""
    api = api or client()
    system = SYSTEM_PROMPT.format(today=today)
    tools = web_tools(versions)
    messages: list[dict[str, Any]] = [{"role": "user", "content": query}]
    usage = zero_usage()
    trail: list[dict[str, Any]] = []
    responses: list[dict[str, Any]] = []
    started = time.time()
    for _ in range(MAX_CONTINUATIONS + 1):
        response = api.messages.create(
            model=MODEL, max_tokens=MAX_TOKENS, system=system, messages=messages,
            tools=tools, cache_control=CACHE_CONTROL,
        )
        add_usage(usage, response.usage)
        trail.extend(tool_trail(response.content))
        responses.append({"stop_reason": response.stop_reason,
                          "blocks": [getattr(b, "type", None) for b in response.content]})
        if not resumable(response) or cost_usd(usage) >= STOP_USD:
            break
        messages = [{"role": "user", "content": query},
                    {"role": "assistant", "content": response.content}]
    # Still resumable means stopped: at $1, or after every continuation allowed.
    stopped = resumable(response)
    # Ended waiting on a tool this request never offered: nothing to read.
    incomplete = not stopped and response.stop_reason == "tool_use"
    usage_out: dict[str, Any] = dict(usage)
    usage_out.update({
        "wall_s": round(time.time() - started, 1),
        "stop_reason": response.stop_reason,
        "served_model": response.model,
        "cost_usd": cost_usd(usage),
    })
    return {
        "reply": "" if stopped or incomplete else reply_text(response.content),
        "stopped": stopped,
        "incomplete": incomplete,
        "trail": trail,
        "responses": responses,
        "usage": usage_out,
        "request": {"model": MODEL, "system": system, "max_tokens": MAX_TOKENS,
                    "tools": tools, "caching": "automatic", "thinking": "model default",
                    "effort": "model default", "stop_usd": STOP_USD},
    }


class Spend:
    """Running spend across threads, checked before each question starts."""

    def __init__(self, cap_usd: float):
        self.cap = cap_usd
        self.spent = 0.0
        self._lock = threading.Lock()

    def exhausted(self) -> bool:
        with self._lock:
            return self.spent >= self.cap

    def add(self, usd: float) -> None:
        with self._lock:
            self.spent += usd
