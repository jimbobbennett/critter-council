"""The deliverable: Foxy's Minutes, as Markdown.

This file used to hand-roll text wrapping, a scrollable panel, a scrollbar and
terminal width arithmetic. Every one of those was a bug, repeatedly: textwrap
counts characters where terminals count cells, a fixed-width Rich column pads
rows with trailing spaces, and a row of exactly the terminal width wraps by one.

So none of it happens here any more. Markdown is the format, Rich owns the
rendering, the system pager owns the scrolling, and the terminal owns the
wrapping. All three already do those jobs correctly.
"""

from __future__ import annotations

import os
import re
import shutil
import sys
from pathlib import Path

from rich.console import Console
from rich.markdown import Markdown

# Foxy writes these as bare upper-case headings; they become Markdown sections.
HEADINGS = {
    "RESOLVED": "Resolved",
    "NOTED": "Noted",
    "ANY OTHER BUSINESS": "Any Other Business",
}

VOTE_MARK = {"aye": "Aye", "nay": "No", "abstain": "Abstain"}


def _ordinal(n: int) -> str:
    suffix = (
        "th" if 10 <= n % 100 <= 20 else {1: "st", 2: "nd", 3: "rd"}.get(n % 10, "th")
    )
    return f"{n}{suffix}"


def to_markdown(state: dict, sitting: int) -> str:
    """The whole sitting as one Markdown document."""
    out: list[str] = [f"# Minutes of the {_ordinal(sitting)} Sitting", ""]
    out.append(f'**Motion:** *"{state.get("motion", "")}"*')

    minutes = (state.get("minutes") or "").strip()
    if minutes:
        for raw in minutes.splitlines():
            line = raw.strip()
            if line in HEADINGS:
                out += ["", f"## {HEADINGS[line]}", ""]
            else:
                out.append(line)
    else:
        out += ["", "*The council failed to produce minutes. Toad blames Nigel.*"]

    votes = state.get("votes") or []
    if votes:
        out += ["", "## The Division", "", "| Member | Vote | Reason |", "|---|---|---|"]
        for v in votes:
            reason = (v.get("because") or "").replace("|", r"\|")
            out.append(
                f"| {v.get('critter', '?')} "
                f"| {VOTE_MARK.get(v.get('vote', ''), v.get('vote', ''))} "
                f"| {reason} |"
            )
        ayes = sum(1 for v in votes if v.get("vote") == "aye")
        nays = sum(1 for v in votes if v.get("vote") == "nay")
        abst = sum(1 for v in votes if v.get("vote") == "abstain")
        verdict = "**The motion is carried.**" if ayes > nays else "**The motion falls.**"
        out += ["", f"Ayes {ayes}, Noes {nays}, Abstentions {abst}. {verdict}"]

    sources = state.get("sources") or []
    if sources:
        out += ["", "## Schedule A - Sources Consulted", ""]
        for s in sources:
            title = (s.get("title") or s.get("url") or "").strip().replace("]", r"\]")
            out.append(f"- [{title}]({s.get('url', '')})")

    dead = state.get("dead_parrots") or []
    if dead:
        out += ["", "## Schedule B - Deceased Sources", ""]
        out += [f"- {url}" for url in dead]

    from .. import llm

    out += ["", "---", ""]
    out.append(
        f"Sources consulted {len(sources)} · deceased {len(dead)} · "
        f"forms filed {len(state.get('forms') or [])} · "
        f"tea remaining {state.get('tea', 0)}%"
    )
    if llm.LEDGER.calls:
        out += ["", f"*{llm.LEDGER.summary()}*"]

    # Foxy's own blank lines land next to the ones added around headings, so
    # collapse any run of them. Markdown ignores the difference; the saved file
    # reads better without it.
    return re.sub(r"\n{3,}", "\n\n", "\n".join(out)).strip() + "\n"


def write_file(markdown: str, sitting: int, directory: str = "minutes") -> Path | None:
    """Save the Minutes as a file. Returns the path, or None if it could not."""
    try:
        folder = Path(directory)
        folder.mkdir(parents=True, exist_ok=True)
        path = folder / f"sitting-{sitting}.md"
        path.write_text(markdown, encoding="utf-8")
        return path
    except OSError:
        return None


def show(console: Console, markdown: str, path: Path | None) -> None:
    """Render the Minutes and hand them to the system pager.

    The pager provides scrolling, searching and resize handling for free, which
    is why this project no longer has a scrollbox. Non-interactive output skips
    the pager and prints straight through.
    """
    doc = Markdown(markdown)

    if not sys.stdout.isatty():
        console.print(doc)
        _print_path(console, path)
        return

    # -R passes styles through, -F exits at once if it all fits on one screen,
    # -X leaves the text on screen afterwards instead of clearing it.
    if not os.environ.get("PAGER") and shutil.which("less"):
        os.environ["PAGER"] = "less -R -F -X"

    try:
        with console.pager(styles=True):
            console.print(doc)
    except Exception:
        # No pager, or it refused to run. Printing is always valid.
        console.print(doc)
    _print_path(console, path)


def _print_path(console: Console, path: Path | None) -> None:
    if path is not None:
        console.print(f"  [grey54]Minutes written to[/grey54] [bold]{path}[/bold]")
        console.print()
