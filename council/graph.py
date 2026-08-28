"""The council as a LangGraph supervisor.

Chairman Toad is the router: START goes to him, every worker returns to him, and
he decides what happens next — a star topology, with the active critter shown by
their panel border.

Every joke in here is load-bearing:
  * the Dead Parrot sketch fires from the web_fetch error branch
  * the Inquisition fires from a conditional edge on real source disagreement
  * the tea break is a genuine node with an edge back to the chair
  * "referred to the Sub-Committee" is the loop-limit guard
  * a dropped connection is the parish telephone, and is NOT blamed on the source

Robustness rules, learned the hard way: llm.* returns None/empty rather than
raising, so one flaky call costs a turn and not the sitting; and every routing
branch has a give-up path, because a search that keeps failing would otherwise
ping-pong the chair to the recursion cap.
"""

from __future__ import annotations

from langgraph.graph import END, START, StateGraph

from . import cast, llm, sketches
from .state import (
    BuzzTurn,
    ChairTurn,
    CouncilState,
    OwlTurn,
    ScoutTurn,
    VoteTurn,
)
from .ui.layout import Display, Overlay

MAX_ROUNDS = 3

# The chair may take at most this many turns before he must refer the matter to
# the Clerk. A healthy sitting uses 8-11; this only bites when something is
# wrong, and it keeps the graph far below LangGraph's recursion limit.
MAX_STEPS = 16

# How many verified claims the chair will settle for. Five reliably buys a
# second search round, which is both better research and a fuller sitting;
# --quick halves it for a cheaper run.
ENOUGH_EVIDENCE = 5

# Tuned so a two-round sitting genuinely runs the urn dry partway through —
# the tea break has to actually fire, not be a theoretical branch.
TEA_COST = {
    "chairman": 4,
    "nigel_search": 14,
    "owlsworth_analyse": 16,
    "buzzwick_verify": 12,
    "inquisition": 18,
    "foxy_minutes": 8,
}


def _situation(state: CouncilState) -> str:
    """A plain-language summary of the sitting so far, for the prompts."""
    sources = state.get("sources") or []
    findings = state.get("findings") or []
    verified = state.get("verified") or []
    dead = state.get("dead_parrots") or []
    plans = state.get("plans") or []
    lines = [
        f"Motion before the council: {state.get('motion', '')}",
        f"Round {state.get('round', 1)} of {MAX_ROUNDS}.",
        f"Tea remaining: {state.get('tea', 100)}%.",
        f"Sources found: {len(sources)}. Deceased sources: {len(dead)}.",
        f"Findings recorded: {len(findings)}. Verified by Buzzwick: {len(verified)}.",
    ]
    if plans:
        lines.append(f"Nigel's most recent cunning plan: {plans[-1]}")
    if findings:
        lines.append("Findings so far:")
        for f in findings[-6:]:
            lines.append(f"  - {f.get('claim', '')}")
    return "\n".join(lines)


def build_graph(display: Display, *, sitting: int = 447, evidence: int = ENOUGH_EVIDENCE):
    counters = {"chair": 0, "flavour": 0}

    def flavour() -> str:
        counters["flavour"] += 1
        return cast.FLAVOUR[counters["flavour"] % len(cast.FLAVOUR)]

    def drain(state: CouncilState, node: str) -> int:
        tea = max(0, state.get("tea", 100) - TEA_COST.get(node, 5))
        display.set_tea(tea)
        return tea

    # --- the chair ---------------------------------------------------------------

    def chairman(state: CouncilState) -> dict:
        display.set_active("chairman")
        display.working("toad", "consulting the agenda")
        n = counters["chair"]
        counters["chair"] += 1

        nudge = (
            "Open the sitting. State the motion in your own contemptuous words and "
            "instruct Nigel to begin."
            if n == 0
            else "Move business along. React to what has just happened."
        )
        turn = llm.structured(
            cast.CHAIRMAN,
            f"{_situation(state)}\n\nThe hall smells of {flavour()}.\n\n{nudge}",
            ChairTurn,
            demo_key=f"chair_{min(n, 4)}",
        )
        remark = turn.remark if turn else sketches.pick(sketches.CHAIR_FALLBACK)
        display.say("toad", remark)
        display.status("toad", "presiding")
        return {
            "tea": drain(state, "chairman"),
            "steps": state.get("steps", 0) + 1,
            "transcript": [{"critter": "Toad", "text": remark}],
        }

    # --- Nigel: the search -------------------------------------------------------

    def nigel_search(state: CouncilState) -> dict:
        display.set_active("nigel_search")
        first = not state.get("sources")
        rnd = state.get("round", 1) + (0 if first else 1)
        display.set_round(rnd)

        display.working("nigel", "hatching a plan")
        turn = llm.structured(
            cast.SCOUT,
            f"{_situation(state)}\n\nSomeone has left {flavour()} on your chair.\n\n"
            "Announce your cunning plan for this round of searching, rate it out of "
            "ten, and give the search queries you will actually run.",
            ScoutTurn,
            demo_key=f"scout_{min(rnd, 3)}",
        )
        if turn:
            plan = turn.plan
            rating = max(1, min(10, turn.cunning_rating))
            queries = [q for q in turn.queries if q.strip()][:3]
        else:
            plan = sketches.pick(sketches.CUNNING_PLAN_FALLBACK)
            rating = 2
            queries = [state.get("motion", "")]

        display.say("nigel", plan)
        display.stats("nigel", f"Cunning Rating: {rating}/10  ({sketches.cunning_verdict(rating)})")

        display.working("nigel", "searching the internet")
        digest, sources, notes = llm.search_and_digest(
            cast.RESEARCHER,
            "Search the web and report, plainly and factually, what you find about "
            f"this question: {state.get('motion', '')}\n\n"
            f"Run searches along these lines: {'; '.join(queries)}\n\n"
            "Then write a factual digest of what the sources actually say. No "
            "persona, no jokes, no preamble in the digest — the council needs it "
            "accurate. Note explicitly where sources disagree.",
            demo_key=f"search_{min(rnd, 2)}",
        )

        known = {s["url"] for s in (state.get("sources") or [])}
        fresh = [s for s in sources if s["url"] not in known]

        display.stats(
            "nigel",
            f"Cunning Rating: {rating}/10    sources found: {len(fresh)}",
        )
        display.status("nigel", "plan executed", state="done")
        # Only complain when something actually went wrong. A max_uses_exceeded
        # note alongside a pile of sources means the model simply ran out of
        # search budget after getting what it needed — not a failure to report.
        if "connection_lost" in notes:
            display.say("nigel", sketches.pick(sketches.API_TROUBLE_SCOUT))
        elif notes and not sources:
            display.say("nigel", "The internet said no, m'lord. I shall try being politer.")

        # A search that turns up nothing new must not send the council round
        # again — otherwise the chair and Nigel ping-pong until the round limit.
        barren = state.get("barren", 0) + (0 if fresh else 1)
        if not fresh and not first:
            display.say("nigel", "Nothing new, m'lord. The internet has run out of cats.")

        return {
            "tea": drain(state, "nigel_search"),
            "round": rnd,
            "barren": barren,
            "plans": [plan],
            "sources": fresh,
            "digests": [digest] if digest else [],
            "transcript": [{"critter": "Nigel", "text": plan}],
        }

    # --- Owlsworth: fetch, assess, find contradictions ---------------------------

    def owlsworth_analyse(state: CouncilState) -> dict:
        display.set_active("owlsworth_analyse")
        analysed = set(state.get("analysed") or [])
        sources = [s for s in (state.get("sources") or []) if s["url"] not in analysed]
        urls = [s["url"] for s in sources][:3]

        display.working("owlsworth", "retrieving the pages")
        before = len(llm.FAILURES)
        fetch_text, dead = llm.fetch_pages(
            urls, demo_key=f"fetch_{min(state.get('round', 1), 2)}"
        )

        # An API failure is the machinery, not the source. Different joke, and
        # the source is not slandered as deceased.
        if urls and not fetch_text and len(llm.FAILURES) > before:
            display.status("owlsworth", "cut off mid-sentence")
            display.say("toad", sketches.pick(sketches.API_TROUBLE), dwell=0.9)

        if dead:
            # This is the web_fetch error handler. It is also the sketch.
            display.status("owlsworth", "pronouncing a source dead")
            display.say("owlsworth", sketches.pick(sketches.DEAD_PARROT), dwell=1.0)
            display.say("nigel", sketches.pick(sketches.DEAD_PARROT_REBUTTAL), dwell=0.9)

        display.working("owlsworth", "assessing the sources")
        digests = "\n\n".join(state.get("digests") or [])
        listing = "\n".join(f"- {s['title']} ({s['url']})" for s in sources[:8])
        turn = llm.structured(
            cast.OWL,
            f"{_situation(state)}\n\nA draught is coming from {flavour()}.\n\n"
            f"SOURCES BEFORE THE COUNCIL:\n{listing or '(none)'}\n\n"
            f"WHAT NIGEL'S SEARCHES REPORTED:\n{digests or '(nothing usable)'}\n\n"
            f"WHAT THE RETRIEVED PAGES SAID:\n{fetch_text or '(nothing retrieved)'}\n\n"
            "Deliver your one-line assessment for the council, then record your "
            "findings. Each finding must be a real, substantive answer drawn from "
            "the material above, attributed to the source it came from, with a "
            "fresh simile rating that source. Record a contradiction only where the "
            "sources genuinely disagree.",
            OwlTurn,
            max_tokens=8000,
            demo_key=f"owl_{min(state.get('round', 1), 3)}",
        )

        if not turn:
            display.say("owlsworth", "I find the evidence, and Nigel, equally impenetrable.")
            return {
                "tea": drain(state, "owlsworth_analyse"),
                "dead_parrots": dead,
                "analysed": [s["url"] for s in sources],
            }

        display.say("owlsworth", turn.quip)
        display.stats(
            "owlsworth",
            f"findings: {len(turn.findings)}    clashes: {len(turn.contradictions)}"
            f"    deceased: {len(dead)}",
        )
        display.status("owlsworth", "assessment filed", state="done")

        return {
            "tea": drain(state, "owlsworth_analyse"),
            "dead_parrots": dead,
            "analysed": [s["url"] for s in sources],
            "findings": [f.model_dump() for f in turn.findings],
            "contradictions": [c.model_dump() for c in turn.contradictions],
            "transcript": [{"critter": "Owlsworth", "text": turn.quip}],
        }

    # --- Buzzwick: paperwork -----------------------------------------------------

    def buzzwick_verify(state: CouncilState) -> dict:
        display.set_active("buzzwick_verify")
        display.working("buzzwick", "locating the correct form")

        findings = state.get("findings") or []
        assessed = set(state.get("assessed") or [])
        pending = [(i, f) for i, f in enumerate(findings) if i not in assessed]
        claims = "\n".join(
            f"{n}. {f.get('claim', '')}" for n, (_, f) in enumerate(pending)
        )

        turn = llm.structured(
            cast.BEE,
            f"{_situation(state)}\n\nSomebody has filed {flavour()} incorrectly.\n\n"
            f"CLAIMS AWAITING VERIFICATION (numbered):\n{claims or '(none)'}\n\n"
            f"SOURCE MATERIAL:\n{chr(10).join(state.get('digests') or []) or '(none)'}\n\n"
            "Deliver your one-line remark to the council, then issue a verdict and a "
            "form number for every numbered claim above. Set claim_index to the "
            "number of the claim you are ruling on. Judge them honestly against the "
            "source material.",
            BuzzTurn,
            max_tokens=8000,
            demo_key=f"buzz_{min(state.get('round', 1), 3)}",
        )

        # Every pending finding is marked assessed regardless of what comes
        # back, so a missing or malformed verdict can never loop the council.
        all_pending = [i for i, _ in pending]

        if not turn:
            display.say("buzzwick", sketches.pick(sketches.FORM_BLOCKS))
            return {
                "tea": drain(state, "buzzwick_verify"),
                "assessed": all_pending,
            }

        display.say("buzzwick", turn.quip)

        # Match verdicts back by position in the numbered list we sent.
        verified = [
            pending[v.claim_index][1].get("claim", "")
            for v in turn.verdicts
            if v.verdict == "verified" and 0 <= v.claim_index < len(pending)
        ]
        blocked = [v for v in turn.verdicts if v.verdict == "blocked"]
        forms = [v.model_dump() for v in turn.verdicts]

        display.stats(
            "buzzwick",
            f"forms filed: {len(forms)}    verified: {len(verified)}"
            f"    blocked: {len(blocked)}",
        )
        if blocked:
            display.say("buzzwick", sketches.pick(sketches.FORM_BLOCKS), dwell=0.9)
        display.status("buzzwick", "in triplicate", state="done")

        return {
            "tea": drain(state, "buzzwick_verify"),
            "forms": forms,
            "verified": verified,
            "assessed": all_pending,
            "transcript": [{"critter": "Buzzwick", "text": turn.quip}],
        }

    # --- the interruptions -------------------------------------------------------

    def inquisition(state: CouncilState) -> dict:
        display.set_active("chairman")
        clashes = state.get("contradictions") or []
        clash = clashes[0] if clashes else {}
        subject = clash.get("subject", "the matter at hand")
        lines = [
            sketches.INQUISITION_ENTRANCE,
            "",
            sketches.pick(sketches.INQUISITION_WEAPONS),
            "",
            f"ON THE SUBJECT OF: {subject}",
            f"  One source maintains: {clash.get('one_says', '?')[:88]}",
            f"  Another insists:     {clash.get('other_says', '?')[:88]}",
            "",
            sketches.pick(sketches.INQUISITION_EXIT),
        ]
        display.slam(Overlay("CARDINAL XIMENEZ", lines, "red", art="ximenez"), 5.0)
        return {
            "tea": drain(state, "inquisition"),
            "contradictions": [],
            "inquisitions": state.get("inquisitions", 0) + 1,
            "transcript": [{"critter": "Ximenez", "text": sketches.INQUISITION_ENTRANCE}],
        }

    def tea_break(state: CouncilState) -> dict:
        lines = [
            sketches.pick(sketches.TEA_BREAK),
            "",
            "ALL COUNCIL BUSINESS IS SUSPENDED.",
            "",
            sketches.pick(sketches.TEA_RETURN),
        ]
        display.slam(Overlay("THE URN IS DRY", lines, "yellow"), 4.5)
        display.set_tea(100)
        return {
            "tea": 100,
            "transcript": [{"critter": "Toad", "text": "Adjourned. Fifteen minutes."}],
        }

    # --- Foxy writes it up, then the division ------------------------------------

    def foxy_minutes(state: CouncilState) -> dict:
        display.set_active("foxy_minutes")
        display.working("foxy", "selecting a typeface")
        display.say("foxy", "Finally. Do step aside, darlings, this needs a professional.")

        display.working("foxy", "drafting the minutes")
        findings = state.get("findings") or []
        verified = set(state.get("verified") or [])
        body = "\n".join(
            f"- [{'VERIFIED' if f.get('claim') in verified else 'unverified'}] "
            f"{f.get('claim', '')}  (source: {f.get('source_url', 'n/a')})"
            for f in findings
        )
        minutes = llm.prose(
            cast.FOX,
            f"{_situation(state)}\n\nYou are writing at a table that wobbles because "
            f"of {flavour()}.\n\n"
            f"THE COUNCIL'S FINDINGS:\n{body or '(the council established nothing)'}\n\n"
            f"Deceased sources this sitting: {len(state.get('dead_parrots') or [])}. "
            f"Forms filed by Buzzwick: {len(state.get('forms') or [])}. "
            f"Inquisitions: {state.get('inquisitions', 0)}. "
            f"Tea remaining: {state.get('tea', 0)}%.\n"
            + (
                f"The council lost contact with the outside world "
                f"{len(llm.FAILURES)} time(s) this sitting, so some avenues went "
                "unexplored. Minute that honestly in NOTED — do not pretend the "
                "research was complete.\n"
                if llm.FAILURES
                else ""
            )
            + "\n"
            "Write the MINUTES OF THE SITTING now, in the exact structure you were "
            "given. RESOLVED must genuinely answer the motion.",
            effort="medium",
            max_tokens=12000,
            demo_key="minutes",
        )
        display.stats("foxy", f"minutes: {len(minutes.split())} words, all of them chosen")
        display.status("foxy", "minutes drafted", state="done")
        display.say("foxy", "Minuted. You may all admire it.")
        return {
            "tea": drain(state, "foxy_minutes"),
            "minutes": minutes,
        }

    def the_vote(state: CouncilState) -> dict:
        display.set_active("foxy_minutes")
        display.working("toad", "calling the division")
        turn = llm.structured(
            cast.TELLER,
            f"{_situation(state)}\n\nThe motion has been minuted. Record the division.",
            VoteTurn,
            demo_key="votes",
        )
        votes = [v.model_dump() for v in turn.votes] if turn else []

        # Buzzwick abstains. Every time. On procedural grounds. This is not
        # left to the model, because the gag has to land every single sitting.
        found_buzz = False
        for v in votes:
            if "buzz" in v.get("critter", "").lower():
                v["vote"] = "abstain"
                v["because"] = "Abstaining pending receipt of a stamped Form 27B/6."
                found_buzz = True
        if not found_buzz:
            votes.append(
                {
                    "critter": "Sgt. Buzzwick",
                    "vote": "abstain",
                    "because": "Abstaining pending receipt of a stamped Form 27B/6.",
                }
            )

        display.say("toad", "The ayes have it. The ayes have it. Now get out of my hall.")
        display.status("toad", "sitting closed", state="done")
        return {"votes": votes}

    # --- routing ------------------------------------------------------------------

    def route_from_chair(state: CouncilState) -> str:
        # Hard ceiling on the length of a sitting. Every routing branch below is
        # meant to terminate on its own, but a bug in any one of them would
        # otherwise burn turns and money until LangGraph's recursion limit threw.
        # Past the cap the chair simply refers the matter to Foxy, so the worst
        # outcome is a short sitting with Minutes rather than a crash.
        if state.get("steps", 0) >= MAX_STEPS:
            return "foxy_minutes"

        if state.get("tea", 100) <= 0:
            return "tea_break"

        if not state.get("sources"):
            # Nothing found at all. Two attempts, then hand it to Foxy to minute
            # the failure — otherwise a search that keeps failing (no results, or
            # the API unreachable) loops the chair and Nigel to the recursion cap.
            if state.get("barren", 0) >= 2:
                return "foxy_minutes"
            return "nigel_search"
        if state.get("contradictions") and state.get("inquisitions", 0) < 1:
            return "inquisition"

        # Anything Nigel has found that Owlsworth has not yet looked at.
        analysed = set(state.get("analysed") or [])
        if any(s["url"] not in analysed for s in (state.get("sources") or [])):
            return "owlsworth_analyse"

        findings = state.get("findings") or []
        assessed = set(state.get("assessed") or [])
        if any(i not in assessed for i in range(len(findings))):
            return "buzzwick_verify"

        verified = state.get("verified") or []
        if (
            len(verified) < evidence
            and state.get("round", 1) < MAX_ROUNDS
            and state.get("barren", 0) == 0
        ):
            return "nigel_search"

        # The loop-limit guard, in the only language Toad respects.
        return "foxy_minutes"

    g = StateGraph(CouncilState)
    g.add_node("chairman", chairman)
    g.add_node("nigel_search", nigel_search)
    g.add_node("owlsworth_analyse", owlsworth_analyse)
    g.add_node("buzzwick_verify", buzzwick_verify)
    g.add_node("inquisition", inquisition)
    g.add_node("tea_break", tea_break)
    g.add_node("foxy_minutes", foxy_minutes)
    g.add_node("the_vote", the_vote)

    g.add_edge(START, "chairman")
    g.add_conditional_edges(
        "chairman",
        route_from_chair,
        {
            "nigel_search": "nigel_search",
            "owlsworth_analyse": "owlsworth_analyse",
            "buzzwick_verify": "buzzwick_verify",
            "inquisition": "inquisition",
            "tea_break": "tea_break",
            "foxy_minutes": "foxy_minutes",
        },
    )
    # Every worker reports back to the chair. That is the whole joke.
    for worker in (
        "nigel_search",
        "owlsworth_analyse",
        "buzzwick_verify",
        "inquisition",
        "tea_break",
    ):
        g.add_edge(worker, "chairman")

    g.add_edge("foxy_minutes", "the_vote")
    g.add_edge("the_vote", END)

    return g.compile()
