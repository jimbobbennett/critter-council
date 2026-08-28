"""The single seam between the council and the Claude API.

Design notes worth knowing before editing:

* Model default is `claude-opus-5`. Thinking is ON by default on Opus 5, and
  `max_tokens` is a hard cap on thinking *plus* visible text — so the budgets
  here look generous for two-sentence quips on purpose. Lowballing them
  truncates mid-thought.
* `effort` lives inside `output_config`, not top-level. Low/medium effort is
  unusually strong on Opus 5 and is the real latency lever, so the banter runs
  at "low" and only the Minutes go to "medium".
* `temperature` / `top_p` are rejected on Opus 5, so variety comes from the
  rotating flavour noun in the user message.
* Character system prompts are stable across rounds and carry a cache
  breakpoint; the volatile per-turn content goes in the user message, after it.
* Web search is the server-side `web_search_20260209` tool — real results, and
  ANTHROPIC_API_KEY is the only credential needed.
"""

from __future__ import annotations

import json
import os
import time
from typing import Any, TypeVar

from pydantic import BaseModel

# Two models on purpose. The character turns are short, voice-critical, and
# cheap, so they get Opus. The research turns pull whole web pages into context
# — measured at ~20k input tokens per search and ~55k per fetch, because the
# _20260209 tools run dynamic-filtering code-execution rounds — so they go to
# Sonnet, which costs less per token and only needs to summarise accurately.
MODEL = os.environ.get("COUNCIL_MODEL", "claude-opus-5")
RESEARCH_MODEL = os.environ.get("COUNCIL_RESEARCH_MODEL", "claude-sonnet-5")

# max_uses must exceed the number of queries handed over, with headroom: the
# model reformulates and follows up, and every attempt past the cap comes back as
# a max_uses_exceeded error result. Those wasted attempts cost tokens AND poison
# the digest — a capped-out model writes "I cannot run additional searches"
# instead of findings, which the rest of the council then reasons over.
SEARCH_BUDGET = 6
FETCH_BUDGET = 4

WEB_SEARCH = {
    "type": "web_search_20260209",
    "name": "web_search",
    "max_uses": SEARCH_BUDGET,
}
WEB_FETCH = {
    "type": "web_fetch_20260209",
    "name": "web_fetch",
    "max_uses": FETCH_BUDGET,
    "max_content_tokens": 4000,
}

# Public list prices, $ per million tokens, for the sitting-cost readout.
PRICES = {
    "claude-opus-5": (5.0, 25.0),
    "claude-opus-4-8": (5.0, 25.0),
    "claude-sonnet-5": (3.0, 15.0),
    "claude-sonnet-4-6": (3.0, 15.0),
    "claude-haiku-4-5": (1.0, 5.0),
}


class Ledger:
    """Running token/cost total for the sitting. Cache reads are billed at
    about a tenth of the input rate, which is why they are counted separately."""

    def __init__(self) -> None:
        self.reset()
        self.session_cost = 0.0

    def reset(self) -> None:
        """Called at the start of each sitting so the Minutes report that
        sitting's spend rather than a running session total."""
        self.calls = 0
        self.input = 0
        self.cache_read = 0
        self.cache_write = 0
        self.output = 0
        self.searches = 0
        self.fetches = 0
        self.cost = 0.0

    def add(self, model: str, usage) -> None:
        rate_in, rate_out = PRICES.get(model, (5.0, 25.0))
        i = getattr(usage, "input_tokens", 0) or 0
        cr = getattr(usage, "cache_read_input_tokens", 0) or 0
        cw = getattr(usage, "cache_creation_input_tokens", 0) or 0
        o = getattr(usage, "output_tokens", 0) or 0
        self.calls += 1
        self.input += i
        self.cache_read += cr
        self.cache_write += cw
        self.output += o
        spend = (
            i * rate_in + cw * rate_in * 1.25 + cr * rate_in * 0.1 + o * rate_out
        ) / 1_000_000
        self.cost += spend
        self.session_cost += spend
        stu = getattr(usage, "server_tool_use", None)
        if stu is not None:
            self.searches += getattr(stu, "web_search_requests", 0) or 0
            self.fetches += getattr(stu, "web_fetch_requests", 0) or 0

    def summary(self) -> str:
        total_in = self.input + self.cache_read + self.cache_write
        return (
            f"{self.calls} model calls · {total_in:,} in "
            f"({self.cache_read:,} cached) · {self.output:,} out · "
            f"{self.searches} searches, {self.fetches} fetches · ~${self.cost:.2f}"
        )


LEDGER = Ledger()

T = TypeVar("T", bound=BaseModel)

# --- demo mode -------------------------------------------------------------------

DEMO = False
_FIXTURES: dict[str, Any] = {}


def enable_demo(fixtures: dict[str, Any]) -> None:
    """Run the whole sitting from canned data: no API calls, no key, no waiting."""
    global DEMO, _FIXTURES
    DEMO = True
    _FIXTURES = fixtures


def demo_motion() -> str:
    """The one question the canned fixtures actually answer."""
    return _FIXTURES.get("motion", "")


# --- client ----------------------------------------------------------------------

_client = None

# Set when a call has failed outright, so the UI can say so in character.
FAILURES: list[str] = []


def client():
    global _client
    if _client is None:
        import anthropic

        # The search and fetch turns run server-side tool loops that can take
        # minutes, which is long enough for a connection to be dropped. More
        # retries than the default 2, and a generous timeout.
        _client = anthropic.Anthropic(max_retries=5, timeout=900.0)
    return _client


def preflight() -> str | None:
    """Return an error string if a live run can't possibly work.

    An unset ANTHROPIC_API_KEY does not by itself mean there are no
    credentials — the SDK also reads ANTHROPIC_AUTH_TOKEN and an `ant auth
    login` profile on disk. Blocking on the env var alone would lock out anyone
    authenticated that way, so check all three.
    """
    if DEMO:
        return None
    from pathlib import Path

    if os.environ.get("ANTHROPIC_API_KEY") or os.environ.get("ANTHROPIC_AUTH_TOKEN"):
        return None

    config_dir = Path(
        os.environ.get("ANTHROPIC_CONFIG_DIR", Path.home() / ".config" / "anthropic")
    )
    if (config_dir / "credentials").exists():
        return None

    return (
        "No Anthropic credentials found.\n\n"
        "Add your key to critter_council/.env:\n"
        "    ANTHROPIC_API_KEY=sk-ant-...\n\n"
        "Or run a canned sitting with no API calls at all:\n"
        "    council --demo"
    )


# --- request helpers -------------------------------------------------------------


def _system(prompt: str) -> list[dict]:
    """System prompt with a cache breakpoint, so repeat rounds read at ~0.1x."""
    return [
        {
            "type": "text",
            "text": prompt,
            "cache_control": {"type": "ephemeral"},
        }
    ]


def _one_call(messages: list, stream: bool, kwargs: dict) -> Any:
    """A single request, streamed or not.

    Long server-tool turns are streamed: it keeps bytes moving so an idle
    connection is less likely to be dropped mid-flight, which is exactly the
    failure that used to kill a sitting.
    """
    if stream:
        with client().messages.stream(messages=messages, **kwargs) as s:
            return s.get_final_message()
    return client().messages.create(messages=messages, **kwargs)


def _create(*, stream: bool = False, **kwargs) -> Any | None:
    """messages.create with pause_turn resumption, retries, and cost accounting.

    Returns None if the request could not be completed at all. Callers must
    handle None: one flaky connection should cost the council a turn, not the
    whole sitting and everything already spent on it.
    """
    import anthropic

    messages = list(kwargs.pop("messages"))
    model = kwargs.get("model", MODEL)
    label = "search/fetch" if kwargs.get("tools") else "a council turn"

    for _ in range(4):  # pause_turn resumptions
        resp = None
        # The SDK already retries connection errors; this is a second line of
        # defence for the expensive tool calls, with a longer backoff.
        for attempt in range(3):
            try:
                resp = _one_call(messages, stream, kwargs)
                break
            except (anthropic.APIConnectionError, anthropic.InternalServerError) as exc:
                if attempt == 2:
                    FAILURES.append(f"{label}: {type(exc).__name__}")
                    return None
                time.sleep(2.0 * (attempt + 1))
            except anthropic.RateLimitError as exc:
                if attempt == 2:
                    FAILURES.append(f"{label}: rate limited")
                    return None
                time.sleep(10.0 * (attempt + 1))
            except anthropic.APIStatusError as exc:
                # 4xx: retrying an invalid request just wastes time.
                FAILURES.append(f"{label}: HTTP {exc.status_code}")
                return None

        if resp is None:
            return None
        LEDGER.add(model, resp.usage)
        if resp.stop_reason != "pause_turn":
            return resp
        messages = messages + [{"role": "assistant", "content": resp.content}]
    return resp


def _tool_use_urls(resp: Any) -> dict[str, str]:
    """Map server_tool_use id -> the URL it was asked to fetch.

    Needed because a failed web_fetch result carries error_code but a null url,
    so the only way to name the deceased source is to correlate on tool_use_id.
    """
    out: dict[str, str] = {}
    for block in resp.content:
        if block.type != "server_tool_use":
            continue
        data = block.input if isinstance(block.input, dict) else {}
        url = data.get("url")
        if url:
            out[block.id] = url
    return out


def _first_text(resp: Any) -> str:
    """Thinking blocks precede text, so never index content[0] blindly."""
    if getattr(resp, "stop_reason", None) == "refusal":
        return ""
    for block in resp.content:
        if block.type == "text":
            return block.text
    return ""


def _all_text(resp: Any) -> str:
    if getattr(resp, "stop_reason", None) == "refusal":
        return ""
    return "\n".join(b.text for b in resp.content if b.type == "text")


# --- public API ------------------------------------------------------------------


def structured(
    system: str,
    user: str,
    model_cls: type[T],
    *,
    effort: str = "low",
    max_tokens: int = 4000,
    demo_key: str | None = None,
) -> T | None:
    """One in-character turn, returned as a validated pydantic object."""
    if DEMO:
        data = _FIXTURES.get(demo_key or "", None)
        return model_cls.model_validate(data) if data is not None else None

    resp = _create(
        model=MODEL,
        max_tokens=max_tokens,
        system=_system(system),
        messages=[{"role": "user", "content": user}],
        output_config={
            "effort": effort,
            "format": {
                "type": "json_schema",
                "schema": model_cls.model_json_schema(),
            },
        },
    )
    if resp is None:
        return None
    raw = _first_text(resp)
    if not raw:
        return None
    try:
        return model_cls.model_validate(json.loads(raw))
    except Exception:
        return None


def prose(
    system: str,
    user: str,
    *,
    effort: str = "low",
    max_tokens: int = 6000,
    demo_key: str | None = None,
) -> str:
    """One in-character turn, returned as plain text."""
    if DEMO:
        return _FIXTURES.get(demo_key or "", "")

    resp = _create(
        model=MODEL,
        max_tokens=max_tokens,
        system=_system(system),
        messages=[{"role": "user", "content": user}],
        output_config={"effort": effort},
    )
    return _all_text(resp).strip() if resp is not None else ""


def search_and_digest(
    system: str, user: str, *, max_tokens: int = 8000, demo_key: str | None = None
) -> tuple[str, list[dict], list[str]]:
    """Run real web search server-side.

    Returns (digest, sources, notes). `sources` comes from the tool result
    blocks; `digest` is the model's own factual summary of what it read, which
    is what the rest of the council reasons over. Search results carry the page
    text in encrypted form, so the model's summary is the only readable form.
    """
    if DEMO:
        canned = _FIXTURES.get(demo_key or "", {}) or {}
        return (
            canned.get("digest", ""),
            canned.get("sources", []),
            canned.get("notes", []),
        )

    resp = _create(
        model=RESEARCH_MODEL,
        max_tokens=max_tokens,
        system=_system(system),
        messages=[{"role": "user", "content": user}],
        tools=[WEB_SEARCH],
        output_config={"effort": "low"},
        stream=True,
    )
    if resp is None:
        return "", [], ["connection_lost"]

    sources: list[dict] = []
    notes: list[str] = []
    for block in resp.content:
        if block.type != "web_search_tool_result":
            continue
        content = block.content
        # Success gives a list of results; failure gives a single error object.
        if isinstance(content, list):
            for r in content:
                url = getattr(r, "url", None)
                if url:
                    sources.append(
                        {
                            "url": url,
                            "title": getattr(r, "title", "") or url,
                            "snippet": "",
                        }
                    )
        else:
            code = getattr(content, "error_code", "search_failed")
            # max_uses_exceeded is not a failure to report — it means the model
            # ran out of budget after already getting results. Only surface it
            # when nothing at all came back.
            notes.append(code)

    # De-duplicate by URL, preserving order.
    seen: set[str] = set()
    unique = []
    for s in sources:
        if s["url"] not in seen:
            seen.add(s["url"])
            unique.append(s)

    digest = _all_text(resp).strip()

    # A digest this short is not a summary of a page of search results — it is
    # the model explaining why it stopped. Passing it downstream is worse than
    # passing nothing, because Owlsworth would treat it as evidence.
    if len(digest) < 200 and unique:
        digest = ""

    return digest, unique, notes


def fetch_pages(
    urls: list[str], *, max_tokens: int = 8000, demo_key: str | None = None
) -> tuple[str, list[str]]:
    """Try to actually retrieve the pages. Failures become dead parrots.

    web_fetch only retrieves URLs already present in the conversation, so the
    list is spelled out in the user message. A genuinely unreachable, blocked,
    or paywalled page comes back as an error result — which is where the Dead
    Parrot sketch fires from. It is a real error handler wearing a costume.
    """
    if DEMO:
        canned = _FIXTURES.get(demo_key or "", {}) or {}
        return canned.get("text", ""), canned.get("dead", [])

    if not urls:
        return "", []

    listed = "\n".join(f"- {u}" for u in urls[:2])
    resp = _create(
        model=RESEARCH_MODEL,
        max_tokens=max_tokens,
        system=_system(
            "You retrieve web pages and report their relevant contents plainly "
            "and accurately. No commentary, no persona, no preamble."
        ),
        messages=[
            {
                "role": "user",
                "content": (
                    "Fetch each of these pages and summarise the parts relevant "
                    "to the question. If a page cannot be retrieved, say so and "
                    "move on.\n\n" + listed
                ),
            }
        ],
        tools=[WEB_FETCH],
        output_config={"effort": "low"},
        stream=True,
    )
    if resp is None:
        # Could not reach the API at all. That is not the source's fault, so it
        # is NOT reported as a dead parrot — the council just has less to go on.
        return "", []

    # A failed fetch reports error_code but a null url, so correlate back to the
    # requested URL through the server_tool_use block that asked for it.
    requested = _tool_use_urls(resp)
    dead: list[str] = []
    for block in resp.content:
        if block.type != "web_fetch_tool_result":
            continue
        content = block.content
        failed = getattr(content, "type", "") == "web_fetch_tool_result_error" or hasattr(
            content, "error_code"
        )
        if failed:
            url = (
                getattr(content, "url", None)
                or requested.get(getattr(block, "tool_use_id", ""), "")
                or "an unnamed source"
            )
            dead.append(url)

    return _all_text(resp).strip(), dead
