# The Right Honourable Council of Critters

A LangGraph research agent that behaves like a shambolic English parish committee.

You put a question to the council. Five woodland animals then research it, argue
about it, file the correct paperwork, and produce Minutes — in a live terminal
chamber, with real web search.

```bash
council "why do cats knock things off tables?"   # put a motion directly
council                                           # let the Chairman ask you
```

Run it with no arguments and the chamber assembles, the critters take their
seats, and Chairman Toad puts the question to you himself. After each sitting he
calls for any other business, so one invocation can run several motions; a blank
answer adjourns.

## What it looks like

The chamber, mid-sitting. Nigel is searching, Owlsworth has filed his assessment,
Buzzwick is on his fifth form, and the tea is going down. The header carries a
live cost meter straight off the API usage figures.

```
╔═════════════════════════════════════════════════════════════════════════════════════════════════╗
║ THE RIGHT HONOURABLE COUNCIL OF CRITTERS                                 🫖 TEA ▓▓▓▓▓▓▓░░░  68% ║
║ Sitting #447                                                     round 2/3   3 searches  ~$0.21 ║
║ MOTION: "why do cats knock things off tables?"                                                  ║
╚═════════════════════════════════════════════════════════════════════════════════════════════════╝
╭─ 🐿 NIGEL (Scout) ──────────────────────────────╮╭─ 🦉 PROF. OWLSWORTH ──────────────────────────╮
│   (\__/)    ● ○ ○                              ││    ,___,    ✓ ✓ ✓                             │
│   ( o.o )   searching the internet             ││   ( O,O )   assessment filed                  │
│    c( )>                                       ││    /)_)                                       │
│ ╭────────────────────────────────────────────╮ ││ ╭───────────────────────────────────────────╮ │
│ │ I have a cunning plan, m'lord: we type the │ ││ │ Two sources of substance and one that has │ │
│ │ question into the internet.                │ ││ │ clearly given up on life entirely.        │ │
│ │                                            │ ││ │                                           │ │
│ │                                            │ ││ │                                           │ │
│ ╰────────────────────────────────────────────╯ ││ ╰───────────────────────────────────────────╯ │
│ Cunning Rating: 2/10    sources found: 9       ││ findings: 3    clashes: 1    deceased: 1      │
╰────────────────────────────────────────────────╯╰───────────────────────────────────────────────╯
╭─ 🐝 SGT. BUZZWICK ─────────────────────────────╮╭─ 🦊 FOXY (Clerk) ─────────────────────────────╮
│    \ | /    ○ ○ ○                              ││   /\ _ /\   ○ ○ ○                             │
│   ( o.o )   in triplicate                      ││  (  ^.^  )  waiting                           │
│   (#####)                                      ││    > ^ <                                      │
│ ╭────────────────────────────────────────────╮ ││ ╭───────────────────────────────────────────╮ │
│ │ I've drawn up a timetable. The first four  │ ││ │ Wake me when there is something worth     │ │
│ │ hours are for drawing up the timetable.    │ ││ │ writing, darlings.                        │ │
│ │                                            │ ││ │                                           │ │
│ │                                            │ ││ │                                           │ │
│ ╰────────────────────────────────────────────╯ ││ ╰───────────────────────────────────────────╯ │
│ forms filed: 5    verified: 4    blocked: 1    ││                                               │
╰────────────────────────────────────────────────╯╰───────────────────────────────────────────────╯
╭─ 🐸 CHAIRMAN TOAD, presiding ───────────────────────────────────────────────────────────────────╮
│    @..@      "A cunning plan of two out of ten, Nigel, which is generous of you.         __/\   │
│   (-oo-)     Professor, assess whatever it is he has dragged in."                       /___/   │
│  ( >__< )                                                                              ___|__   │
╰─────────────────────────────────────────────────────────────────────────────────────────────────╯
```

When two sources genuinely disagree, a conditional edge fires and Cardinal
Ximenez takes over the chamber for a few seconds:

```
╔══════════════════════════════════════ ⚠  CARDINAL XIMENEZ ══════════════════════════════════════╗
║                                                                                                 ║
║      _+_                                                                                        ║
║    ( O.O )                                                                                      ║
║    </|_|\>                                                                                      ║
║                                                                                                 ║
║  NOBODY EXPECTS THE CONTRADICTORY SOURCE!                                                       ║
║                                                                                                 ║
║  Our three chief weapons are citation, cross-reference, and a fanatical devotion to the         ║
║  footnote!                                                                                      ║
║                                                                                                 ║
║  ON THE SUBJECT OF: whether the behaviour is deliberate attention-seeking                       ║
║    One source maintains: the cat has learned that knocking things over summons a human          ║
║    Another insists:     the cat has no such theory of mind                                      ║
║                                                                                                 ║
║  Fetch... THE COMFY CHAIR. And a second opinion.                                                ║
╚═════════════════════════════════════════════════════════════════════════════════════════════════╝
```

Then Foxy's Minutes, rendered as Markdown and opened in your pager:

```
                                    Minutes of the 447th Sitting

Motion: "why do cats knock things off tables?"

Resolved

 1 That cats bat at and displace small objects primarily as tactile investigation. The paw pads
   carry dense mechanoreceptors, so a push returns information about an object's weight, texture and
   stability that the eye alone cannot supply.
 2 That the same motion reproduces a fragment of a predatory sequence — an object that skitters when
   struck rewards the strike, and a rewarded strike is repeated.

Noted

 1 That one source was pronounced deceased mid-sitting and eulogised at length by Professor
   Owlsworth, who appeared to enjoy it.

The Division


 Member         Vote     Reason
 ──────────────────────────────────────────────────────────────────────────
 Nigel          Aye      Voting with the Chairman, as is my cunning custom.
 Sgt. Buzzwick  Abstain  Pending receipt of a stamped Form 27B/6.


Ayes 1, Noes 0, Abstentions 1. The motion is carried.

----------------------------------------------------------------------------------------------------

Sources consulted 0 · deceased 0 · forms filed 5 · tea remaining 54%

6 model calls · 0 in (0 cached) · 0 out · 3 searches, 2 fetches · ~$0.21
```

Every frame above is captured from the real renderer at 100 columns rather than
drawn by hand — generating them is how the stats line was found to wrap and
break the grid alignment.

## Reading the result

When the sitting ends, Foxy's Minutes are written as Markdown, rendered by Rich,
and opened in your system pager — so scrolling, searching (`/`) and window
resizing all work the way they do in `less`, because they *are* `less`.

They are also saved to `minutes/sitting-<n>.md`, so the research survives the
terminal. Piped or non-interactive runs skip the pager and print straight
through.

`## Resolved` is the substance: numbered findings that answer the motion, each
attributed. Then `## Noted` (what went wrong procedurally), `## Any Other
Business`, the division as a table, `Schedule A` of every source consulted,
`Schedule B` of any that died mid-sitting, and the sitting's token/cost ledger.

### Why it works this way

An earlier version hand-rolled the text wrapping, a scrollable panel, a
scrollbar and the terminal width arithmetic. All of it was wrong, in several
different ways at once: `textwrap` counts characters where terminals count
cells, a fixed-width Rich column pads rows with trailing spaces, a row of
exactly the terminal width wraps by one, and Rich prefers a possibly-stale
`COLUMNS` over the terminal itself.

So none of that code exists now. Markdown is the format, Rich owns the
rendering, the pager owns the scrolling, and the terminal owns the wrapping.
Each of those already does its job correctly. If the Minutes ever look wrong
again, the bug belongs to one of them and not to this repository — which is the
whole point of the arrangement.

## The cast, which is also the graph

| Critter | Node | What it does |
|---|---|---|
| The Rt Hon. Reginald Toad MP | `chairman` | The supervisor. Routes every turn. Bangs a gavel. Insults the members. |
| Nigel, a squirrel | `nigel_search` | Runs real web search. Announces each one as a Cunning Plan, rated out of ten. |
| Prof. Twitchett-Owlsworth | `owlsworth_analyse` | Fetches pages, extracts findings, rates sources with withering similes. |
| Sgt. Buzzwick, a bee | `buzzwick_verify` | Fact-checks. Issues a form number per claim. Blocks on Form 27B/6. |
| Foxtrot Delacroix-Vane | `foxy_minutes` | Writes the Minutes. Vain. Actually the best writer in the room. |
| Cardinal Ximenez | `inquisition` | Bursts in unannounced when sources contradict each other. |

Every worker returns to the Chairman, who decides what happens next — a true
supervisor topology. The active critter is shown by their panel border lighting
up, so you can follow the routing without a debug readout cluttering the screen.

## Every joke is a real code path

This is the part worth reading before you change anything:

- **The Dead Parrot sketch fires from the `web_fetch` error branch.** When a page
  genuinely can't be retrieved (`url_not_accessible` — paywalled, blocked, 404),
  Owlsworth delivers the eulogy. It is an error handler in a costume. Because it
  is real, it only fires when a fetch actually fails: expect it on some live
  sittings and not others. `--demo` always fires it.
- **The Inquisition is a conditional edge** on Owlsworth actually finding two
  sources that disagree. It is capped at one appearance per sitting.
- **The tea break is a node.** Tea drains per node; at zero the router sends the
  council to `tea_break`, which refills the urn and returns to the chair. All
  business genuinely stops.
- **"Referred to the Sub-Committee"** is the loop-limit guard.
- **Buzzwick's abstention** is enforced in Python, not left to the model, because
  the gag has to land every single sitting.

## If the layout looks wrong

```bash
council --doctor
```

It reports the terminal size three ways — the ioctl (authoritative), the
`COLUMNS`/`LINES` environment variables, and what Rich is using — then checks the
layout invariants. A stale `COLUMNS` is the classic cause of text wrapping by a
character: lines get computed for one width and rendered at another. The app now
prefers the ioctl for exactly that reason, so a mismatch is reported rather than
silently breaking the output.

## Requirements

- Python 3.11+
- An Anthropic API key
- A terminal at least 92 columns wide and ~40 rows tall
- macOS or Linux. The scrollable Minutes panel reads single keypresses via
  `termios`/`tty`, so key handling does not work on Windows — WSL is fine.

## Setup

```bash
git clone https://github.com/jimbobbennett/critter-council.git
cd critter-council
uv sync
cp .env.example .env      # then paste your key into .env
```

Web search runs server-side on Anthropic's infrastructure, so that key is the
only credential you need — no Tavily, no second signup. If you have no key yet,
`council --demo` runs a full canned sitting with no API calls at all.

## Usage

```bash
council                               # Toad asks you for the motion
council "why is the sky blue?"        # or put one directly
council --demo                        # canned sitting: no API calls, no key
council --demo --speed 1.4            # animation speed multiplier
council --seed 447                    # reproducible sketches, for retakes
council --quick                       # one search round, about half the cost
council --model claude-sonnet-5       # cheaper voice model
council --research-model claude-opus-5  # spend more on the research turns
council --cast                        # introduce the cast and exit
council --doctor                      # check terminal detection and pager
council --once                        # adjourn after one motion, no AOB
```

`--demo` is the one to film with. A live sitting takes 60–120 seconds because the
searches are real, and the pauses are dead air on video. Demo mode replays a
canned sitting with perfect timing, makes zero API calls, and never rate-limits.

**The demo fixtures use fictional `.example.org` citations on purpose**, so canned
demo data can never be mistaken for real sources. The behavioural claims in them
are accurate; the URLs are not real. For genuine cited research, run without `--demo`.

Terminal wants 92+ columns and about 40 rows. Below that you get a warning, but
it degrades gracefully — Rich does all the wrapping.

## Model notes

**Two models, on purpose.** Character turns are short and voice-critical, so they
run on `claude-opus-5`. The research turns pull whole web pages into context —
measured at ~20k input tokens per search and up to ~55k per fetch, because the
`_20260209` tools run dynamic-filtering code-execution rounds internally — so
those go to `claude-sonnet-5`, which costs less per token and only has to
summarise accurately. Override either with `--model` / `--research-model`.

A few other things in `llm.py` are deliberate:

- **Thinking is on by default on Opus 5**, and `max_tokens` caps thinking *plus*
  visible text. The budgets look generous for two-sentence quips on purpose —
  lowballing them truncates mid-thought.
- **`effort` lives inside `output_config`**, not top-level. The banter runs at
  `low` (fast, and low effort is unusually strong on Opus 5); only the Minutes go
  to `medium`.
- **`temperature` is rejected on Opus 5**, so comedic variety comes from a
  rotating flavour noun injected into the *user* message — after the cached
  system prefix, so it costs nothing in cache hits.
- **Character system prompts carry a cache breakpoint.** Multi-round sittings
  re-read them at about a tenth of the price.
- **Verdicts are matched back by index, never by string equality.** The model
  restates claims in its own words; exact-match would silently drop verdicts.

**Measured cost: $0.28–$0.79 per live sitting**, and the spread is real — it
depends on how many sources come back and how many rounds the chair calls, not
on the length of your question. Three measured sittings: cats $0.43 (22
sources), sky $0.28 (26 sources), onions $0.79 (48 sources, 6 searches, 4
fetches). Most input tokens are cache reads.

`--quick` lowers the evidence bar but does not cap spend — a question that
returns 48 sources is expensive at any bar. Don't trust the estimate: the header
carries a live cost meter straight off the API usage figures, and the ledger is
printed under every set of Minutes.

Verified working against the live API: structured outputs (`output_config.format`
+ `effort`), `web_search_20260209`, and `web_fetch_20260209` including its error
branch.

## When the API misbehaves

The search and fetch turns run server-side tool loops that can take minutes,
which is long enough for a connection to be dropped. Three things guard against
losing a whole sitting to one bad call:

- **Both tool calls are streamed.** Keeping bytes moving makes an idle-connection
  drop far less likely than a multi-minute silent POST.
- **`llm.*` returns `None`/empty instead of raising**, with 3 attempts and
  backoff on top of the SDK's own 5 retries. A failed turn costs that turn; the
  council carries on with what it has, and Foxy is told to minute the gap in
  `NOTED` rather than imply the research was complete.
- **A dropped line is not blamed on the source.** It gets its own joke (the
  parish telephone) rather than being reported as a dead parrot, because an
  unreachable API and an unreachable page are different facts.

Every routing branch also has a give-up path — a search that keeps failing used
to ping-pong the chair and Nigel until the recursion cap.

**Tool budgets need headroom.** `max_uses` on `web_search` / `web_fetch` must
comfortably exceed the number of queries handed over, because the model
reformulates and follows up. Set it too tight and every attempt past the cap
returns a `max_uses_exceeded` error result — which costs tokens *and* poisons the
output, because a capped-out model writes "I cannot run additional searches"
where the digest should be, and the rest of the council then reasons over that as
if it were evidence. `SEARCH_BUDGET` / `FETCH_BUDGET` in `llm.py`; the researcher
prompt is also told the budget exists and told never to write about its own
tools. Fixing this made a sitting both better *and* cheaper.

## LangGraph conventions

Worth knowing if you are reading this as a LangGraph example, because a few
choices are deliberate rather than accidental.

**State.** A `TypedDict` with `Annotated[..., operator.add]` reducers, which is
the canonical typed-state pattern. Append-only channels carry the reducer;
anything that gets cleared or replaced (`contradictions`, `tea`, `round`) is a
plain key, so last-write-wins and the node returns the whole value. Getting that
distinction wrong is how the inquisition ended up unable to clear its own
contradictions in an early version.

**Supervisor.** One router node with `add_conditional_edges`, and every worker
edged back to it — the documented supervisor topology. `Command(goto=...)` would
also work and would let a node route itself, but keeping every routing decision
in one function is worth more here than saving an edge.

**Termination.** `recursion_limit` is a backstop, not a budget. `MAX_STEPS`
bounds the sitting, so the limit should never be reached; if it ever is, that is
a routing bug rather than a number to raise.

**Runtime dependencies.** The live display is injected by closing over
`build_graph`. LangGraph 1.x offers `context_schema` with a `Runtime` argument
per node, which is the more explicit idiom; the closure is used because the
display is a process singleton and the indirection buys nothing.

**No checkpointer**, deliberately. A sitting is one interactive run, so an
`InMemorySaver` would impose a `thread_id` and survive nothing. Add a
`SqliteSaver` if you want sittings that resume after a crash.

## Layout

```
council/
├── state.py      CouncilState + the structured shapes critters speak in
├── graph.py      nodes, edges, and the Chairman's routing logic
├── cast.py       the six system prompts — the actual comedy
├── llm.py        the only place that talks to the Claude API
├── sketches.py   the set pieces: dead parrot, inquisition, tea, forms
└── ui/
    ├── frames.py   ASCII portraits, 3 frames each
    ├── layout.py   the live chamber
    └── minutes.py  the final Minutes and the division
```

## Licence

MIT — see [LICENSE](LICENSE).

## A note on what this is

A demo, built to show off LangGraph's supervisor pattern and Claude's
server-side search tools while being fun to watch. The research is real and
cited, but it is a parish committee of woodland animals: treat the Minutes as a
starting point, not a citation of record. Every source it consulted is listed in
Schedule A so you can check its work.
