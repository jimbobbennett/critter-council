"""The single seam between the council and the model.

The calls go through `langchain-anthropic`'s ChatAnthropic rather than the
Anthropic SDK directly. That is a tracing decision: OpenInference's LangChain
instrumentor builds its span tree from LangChain's own callback metadata and
never attaches spans to the OpenTelemetry context, so an SDK call made inside a
graph node starts a *separate trace* — the graph and its LLM calls arrive in
Arize (or Phoenix) disconnected. Routing through ChatAnthropic means both come
from the same instrumentor, so each LLM span nests under the node that made it
and per-node token cost is attributable. No instrumentation is installed here;
this just means it works if you add some.

Everything the sketches depend on survives the change, which was verified before
making it: web_search result blocks keep their URLs, web_fetch errors keep
`url_not_accessible`, prompt caching still reports cache reads, and streaming
still returns the tool result blocks.

Design notes worth knowing before editing:

* Two models on purpose. Character turns are short and voice-critical, so they
  get Opus. Research turns pull whole pages into context — ~20k input tokens per
  search and up to ~55k per fetch, because the _20260209 tools run
  dynamic-filtering code-execution rounds — so they go to Sonnet, which costs
  less and only has to summarise accurately.
* `effort` is passed as an invoke-time keyword. Putting it in `model_kwargs`
  works but emits a UserWarning, and a warning printed during the live display
  corrupts the frame.
* `usage_metadata["input_tokens"]` is the TOTAL including cached tokens, unlike
  the raw SDK where it excludes them. The ledger subtracts them, or a cached
  sitting would be costed at ten times what it actually cost.
"""

from __future__ import annotations

import os
import time
from typing import Any, TypeVar

from langchain_anthropic import ChatAnthropic
from langchain_core.messages import AIMessage, HumanMessage, SystemMessage
from pydantic import BaseModel

MODEL = os.environ.get("COUNCIL_MODEL", "claude-opus-5")
RESEARCH_MODEL = os.environ.get("COUNCIL_RESEARCH_MODEL", "claude-sonnet-5")

# max_uses must comfortably exceed the number of queries handed over, because the
# model reformulates and follows up. Every attempt past the cap returns a
# max_uses_exceeded error result, which costs tokens AND poisons the digest — a
# capped-out model writes "I cannot run additional searches" where the findings
# should be, and the rest of the council reasons over that as if it were evidence.
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

T = TypeVar("T", bound=BaseModel)


class Ledger:
    """Running token and cost total for the sitting."""

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

    def add(self, model: str, message: AIMessage | None) -> None:
        if message is None:
            return
        usage = getattr(message, "usage_metadata", None) or {}
        details = usage.get("input_token_details") or {}
        cache_read = details.get("cache_read") or 0
        cache_write = details.get("cache_creation") or 0
        # input_tokens is the total here, cached included. Subtracting gives the
        # portion actually charged at the full input rate.
        uncached = max(0, (usage.get("input_tokens") or 0) - cache_read - cache_write)
        output = usage.get("output_tokens") or 0

        rate_in, rate_out = PRICES.get(model, (5.0, 25.0))
        self.calls += 1
        self.input += uncached
        self.cache_read += cache_read
        self.cache_write += cache_write
        self.output += output
        spend = (
            uncached * rate_in
            + cache_write * rate_in * 1.25
            + cache_read * rate_in * 0.1
            + output * rate_out
        ) / 1_000_000
        self.cost += spend
        self.session_cost += spend

        # Server-side tool counts are read from the content blocks, not from
        # response_metadata["usage"]["server_tool_use"]: that is present on a
        # normal reply but absent from a streamed one, and both research turns
        # stream. Counting the blocks works for both. Filtered by name because
        # the _20260209 tools also emit code_execution server_tool_use blocks
        # for their own dynamic filtering.
        content = getattr(message, "content", None)
        if isinstance(content, list):
            for block in content:
                if not isinstance(block, dict) or block.get("type") != "server_tool_use":
                    continue
                name = block.get("name")
                if name == "web_search":
                    self.searches += 1
                elif name == "web_fetch":
                    self.fetches += 1

    def summary(self) -> str:
        total_in = self.input + self.cache_read + self.cache_write
        return (
            f"{self.calls} model calls · {total_in:,} in "
            f"({self.cache_read:,} cached) · {self.output:,} out · "
            f"{self.searches} searches, {self.fetches} fetches · ~${self.cost:.2f}"
        )


LEDGER = Ledger()

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


# --- models ----------------------------------------------------------------------

_CHATS: dict[tuple[str, int], ChatAnthropic] = {}

# Set when a call has failed outright, so the UI can say so in character.
FAILURES: list[str] = []


def chat(model: str, max_tokens: int) -> ChatAnthropic:
    """A cached ChatAnthropic. Instances are stateless, so sharing is safe.

    The generous timeout is for the research turns: a server-side tool loop can
    run for minutes, which is long enough for a connection to be dropped.
    """
    key = (model, max_tokens)
    if key not in _CHATS:
        _CHATS[key] = ChatAnthropic(
            model=model,
            max_tokens=max_tokens,
            max_retries=5,
            timeout=900.0,
        )
    return _CHATS[key]


def preflight() -> str | None:
    """Return an error string if a live run can't possibly work.

    An unset ANTHROPIC_API_KEY does not by itself mean there are no credentials —
    the SDK also reads ANTHROPIC_AUTH_TOKEN and an `ant auth login` profile on
    disk. Blocking on the env var alone would lock out anyone authenticated that
    way, so check all three.
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


def _system(prompt: str) -> SystemMessage:
    """System prompt with a cache breakpoint, so repeat rounds read at ~0.1x."""
    return SystemMessage(
        content=[
            {"type": "text", "text": prompt, "cache_control": {"type": "ephemeral"}}
        ]
    )


def _blocks(message: AIMessage | None) -> list[dict]:
    """Content blocks, as dicts. A plain-text reply has none."""
    if message is None:
        return []
    content = message.content
    return [b for b in content if isinstance(b, dict)] if isinstance(content, list) else []


def _text(message: AIMessage | None) -> str:
    """Every text block joined. Thinking blocks and tool results are skipped."""
    if message is None:
        return ""
    content = message.content
    if isinstance(content, str):
        return content.strip()
    parts = [
        b.get("text", "")
        for b in content
        if isinstance(b, dict) and b.get("type") == "text"
    ]
    return "\n".join(p for p in parts if p).strip()


def _run(
    runnable: Any,
    messages: list,
    *,
    model: str,
    effort: str = "low",
    stream: bool = False,
    label: str = "a council turn",
) -> Any:
    """Invoke with retries, pause_turn resumption and cost accounting.

    Returns None if the request could not be completed at all. Callers must
    handle None: one flaky connection should cost the council a turn, not the
    whole sitting and everything already spent on it.
    """
    import anthropic

    kwargs = {"output_config": {"effort": effort}}
    history = list(messages)

    for _ in range(4):  # pause_turn resumptions
        result = None
        for attempt in range(3):
            try:
                if stream:
                    chunks = list(runnable.stream(history, **kwargs))
                    if not chunks:
                        result = None
                        break
                    merged = chunks[0]
                    for chunk in chunks[1:]:
                        merged = merged + chunk
                    result = merged
                else:
                    result = runnable.invoke(history, **kwargs)
                break
            except (anthropic.APIConnectionError, anthropic.InternalServerError) as exc:
                if attempt == 2:
                    FAILURES.append(f"{label}: {type(exc).__name__}")
                    return None
                time.sleep(2.0 * (attempt + 1))
            except anthropic.RateLimitError:
                if attempt == 2:
                    FAILURES.append(f"{label}: rate limited")
                    return None
                time.sleep(10.0 * (attempt + 1))
            except anthropic.APIStatusError as exc:
                # 4xx: retrying an invalid request only wastes time.
                FAILURES.append(f"{label}: HTTP {exc.status_code}")
                return None
            except Exception as exc:  # noqa: BLE001 — never kill the sitting
                if attempt == 2:
                    FAILURES.append(f"{label}: {type(exc).__name__}")
                    return None
                time.sleep(2.0 * (attempt + 1))

        if result is None:
            return None

        # with_structured_output(include_raw=True) yields a dict, not a message.
        message = result.get("raw") if isinstance(result, dict) else result
        LEDGER.add(model, message if isinstance(message, AIMessage) else None)

        stop = (getattr(message, "response_metadata", None) or {}).get("stop_reason")
        if stop != "pause_turn":
            return result
        # A long server-tool turn can pause; append it and continue.
        history = history + [message]
    return result


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

    runnable = chat(MODEL, max_tokens).with_structured_output(
        model_cls, include_raw=True
    )
    result = _run(
        runnable,
        [_system(system), HumanMessage(user)],
        model=MODEL,
        effort=effort,
    )
    if not isinstance(result, dict):
        return None
    parsed = result.get("parsed")
    return parsed if isinstance(parsed, model_cls) else None


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

    result = _run(
        chat(MODEL, max_tokens),
        [_system(system), HumanMessage(user)],
        model=MODEL,
        effort=effort,
    )
    return _text(result)


def search_and_digest(
    system: str, user: str, *, max_tokens: int = 8000, demo_key: str | None = None
) -> tuple[str, list[dict], list[str]]:
    """Run real web search server-side.

    Returns (digest, sources, notes). `sources` comes from the tool result
    blocks; `digest` is the model's own factual summary of what it read, which is
    what the rest of the council reasons over. Search results carry the page text
    in encrypted form, so the model's summary is the only readable form.
    """
    if DEMO:
        canned = _FIXTURES.get(demo_key or "", {}) or {}
        return (
            canned.get("digest", ""),
            canned.get("sources", []),
            canned.get("notes", []),
        )

    runnable = chat(RESEARCH_MODEL, max_tokens).bind_tools([WEB_SEARCH])
    result = _run(
        runnable,
        [_system(system), HumanMessage(user)],
        model=RESEARCH_MODEL,
        stream=True,
        label="search",
    )
    if result is None:
        return "", [], ["connection_lost"]

    sources: list[dict] = []
    notes: list[str] = []
    for block in _blocks(result):
        if block.get("type") != "web_search_tool_result":
            continue
        content = block.get("content")
        # Success gives a list of results; failure gives a single error object.
        if isinstance(content, list):
            for item in content:
                url = item.get("url") if isinstance(item, dict) else None
                if url:
                    sources.append(
                        {
                            "url": url,
                            "title": item.get("title") or url,
                            "snippet": "",
                        }
                    )
        elif isinstance(content, dict):
            notes.append(content.get("error_code", "search_failed"))

    seen: set[str] = set()
    unique = []
    for source in sources:
        if source["url"] not in seen:
            seen.add(source["url"])
            unique.append(source)

    digest = _text(result)
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
    list is spelled out in the user message. A genuinely unreachable, blocked or
    paywalled page comes back as an error result — which is where the Dead Parrot
    sketch fires from. It is a real error handler wearing a costume.
    """
    if DEMO:
        canned = _FIXTURES.get(demo_key or "", {}) or {}
        return canned.get("text", ""), canned.get("dead", [])

    if not urls:
        return "", []

    listed = "\n".join(f"- {u}" for u in urls[:2])
    runnable = chat(RESEARCH_MODEL, max_tokens).bind_tools([WEB_FETCH])
    result = _run(
        runnable,
        [
            _system(
                "You retrieve web pages and report their relevant contents plainly "
                "and accurately. No commentary, no persona, no preamble."
            ),
            HumanMessage(
                "Fetch each of these pages and summarise the parts relevant to the "
                "question. If a page cannot be retrieved, say so and move on.\n\n"
                + listed
            ),
        ],
        model=RESEARCH_MODEL,
        stream=True,
        label="fetch",
    )
    if result is None:
        # Could not reach the API at all. That is not the source's fault, so it is
        # NOT reported as a dead parrot — the council just has less to go on.
        return "", []

    blocks = _blocks(result)
    # A failed fetch reports error_code but no url, so correlate back to the URL
    # through the server_tool_use block that asked for it.
    requested = {
        b.get("id"): (b.get("input") or {}).get("url")
        for b in blocks
        if b.get("type") == "server_tool_use" and isinstance(b.get("input"), dict)
    }

    dead: list[str] = []
    for block in blocks:
        if block.get("type") != "web_fetch_tool_result":
            continue
        content = block.get("content")
        if isinstance(content, dict) and content.get("error_code"):
            dead.append(
                content.get("url")
                or requested.get(block.get("tool_use_id"))
                or "an unnamed source"
            )

    return _text(result), dead
