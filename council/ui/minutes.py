"""The reveal, in two forms.

`scroll_lines` produces pre-wrapped, styled lines for the scrollable in-chamber
panel — scrolling needs an accurate line count, so this owns its own wrapping.
`render` prints the same content to the normal screen afterwards, where Rich can
wrap it, so the Minutes survive in the scrollback once the chamber is gone.
"""

from __future__ import annotations

import textwrap

from rich import box
from rich.console import Console, Group
from rich.panel import Panel
from rich.table import Table
from rich.text import Text

VOTE_STYLE = {"aye": "green", "nay": "red", "abstain": "yellow"}
HEADINGS = ("RESOLVED", "NOTED", "ANY OTHER BUSINESS")


def scroll_lines(state: dict, width: int) -> list[tuple[str, str]]:
    """Everything worth reading, as (text, style) pairs, wrapped to `width`."""
    w = max(30, width - 10)
    out: list[tuple[str, str]] = []

    def add(text: str = "", style: str = "white", indent: str = "") -> None:
        if not text:
            out.append(("", style))
            return
        for line in textwrap.wrap(
            text, w, initial_indent=indent, subsequent_indent=indent
        ) or [""]:
            out.append((line, style))

    add(f'MOTION: "{state.get("motion", "")}"', "italic grey62")
    add()

    minutes = (state.get("minutes") or "").strip()
    if minutes:
        for raw in minutes.splitlines():
            stripped = raw.strip()
            if not stripped:
                add()
            elif stripped in HEADINGS:
                add()
                add(stripped, "bold bright_white")
                add("─" * min(w, len(stripped) + 24), "grey30")
            else:
                add(stripped, "white", indent="  " if stripped[0].isdigit() else "")
    else:
        add("The council failed to produce minutes. Toad blames Nigel.", "italic red")

    votes = state.get("votes") or []
    if votes:
        add()
        add("THE DIVISION", "bold bright_white")
        add("─" * min(w, 36), "grey30")
        for v in votes:
            choice = v.get("vote", "abstain")
            style = VOTE_STYLE.get(choice, "white")
            add(
                f"{v.get('critter', '?'):<18} {choice.upper():<8} {v.get('because', '')}",
                style,
            )
        ayes = sum(1 for v in votes if v.get("vote") == "aye")
        nays = sum(1 for v in votes if v.get("vote") == "nay")
        abst = sum(1 for v in votes if v.get("vote") == "abstain")
        add()
        verdict = "THE MOTION IS CARRIED." if ayes > nays else "THE MOTION FALLS."
        add(f"Ayes {ayes}   Noes {nays}   Abstentions {abst}      {verdict}",
            "bold bright_white")

    sources = state.get("sources") or []
    if sources:
        add()
        add("SCHEDULE A — SOURCES CONSULTED", "bold bright_white")
        add("─" * min(w, 36), "grey30")
        for s in sources:
            add(s.get("title", "") or s.get("url", ""), "white")
            add(s.get("url", ""), "blue", indent="   ")

    dead = state.get("dead_parrots") or []
    if dead:
        add()
        add("SCHEDULE B — DECEASED SOURCES", "bold bright_white")
        add("─" * min(w, 36), "grey30")
        for url in dead:
            add(url, "red")

    from .. import llm

    add()
    add(
        f"Sources {len(sources)}   Deceased {len(dead)}   "
        f"Forms {len(state.get('forms') or [])}   Tea {state.get('tea', 0)}%",
        "grey54",
    )
    if llm.LEDGER.calls:
        add(llm.LEDGER.summary(), "grey42")
    return out


def _section(minutes: str, name: str) -> list[str]:
    """Pull one heading's body out of the Minutes text."""
    lines = [line.rstrip() for line in minutes.splitlines()]
    try:
        start = next(i for i, l in enumerate(lines) if l.strip() == name) + 1
    except StopIteration:
        return []
    body: list[str] = []
    for line in lines[start:]:
        if line.strip() in HEADINGS:
            break
        body.append(line)
    while body and not body[0].strip():
        body.pop(0)
    while body and not body[-1].strip():
        body.pop()
    return body


def render_digest(console: Console, state: dict, sitting: int) -> None:
    """The short record printed after the scrollable panel is dismissed.

    Deliberately not a box: the full Minutes run past 60 rows, and a panel taller
    than the terminal scrolls its own top border off screen, which reads as
    broken output. A rule plus plain text overflows gracefully instead — and the
    detail is one keypress away in the panel the reader just closed.
    """
    console.print()
    console.rule(
        f"[bold bright_white]\U0001f4dc  MINUTES OF THE {_ordinal(sitting)} SITTING",
        style="grey37",
        align="left",
    )
    console.print()
    console.print(f'  [italic grey62]MOTION:[/italic grey62] "{state.get("motion", "")}"')
    console.print()

    resolved = _section(state.get("minutes") or "", "RESOLVED")
    if resolved:
        console.print("  [bold bright_white]RESOLVED[/bold bright_white]")
        # Wrap here rather than letting Rich do it, so continuation lines keep a
        # hanging indent and numbered resolutions stay readable as a list.
        width = max(40, console.width - 6)
        for line in resolved:
            body = line.strip()
            if not body:
                console.print()
                continue
            numbered = body[0].isdigit()
            for out in textwrap.wrap(
                body,
                width,
                initial_indent="  ",
                subsequent_indent="     " if numbered else "  ",
            ):
                console.print(Text(out, style="white"))
    else:
        console.print(
            "  [italic red]The council established nothing. Toad blames Nigel.[/italic red]"
        )

    votes = state.get("votes") or []
    ayes = sum(1 for v in votes if v.get("vote") == "aye")
    nays = sum(1 for v in votes if v.get("vote") == "nay")
    abst = sum(1 for v in votes if v.get("vote") == "abstain")
    sources = state.get("sources") or []
    dead = state.get("dead_parrots") or []

    console.print()
    if votes:
        outcome = "Carried" if ayes > nays else "Fallen"
        console.print(
            f"  [grey54]{outcome} {ayes}–{nays}"
            f"{f' ({abst} abstention{"s" if abst != 1 else ""})' if abst else ''}"
            f"  ·  {len(sources)} sources  ·  {len(dead)} deceased"
            f"  ·  {len(state.get('forms') or [])} forms[/grey54]"
        )

    from .. import llm

    if llm.LEDGER.calls:
        console.print(f"  [grey42]{llm.LEDGER.summary()}[/grey42]")
    console.print(
        "  [grey30]NOTED, ANY OTHER BUSINESS, the division and the full source "
        "list were in the panel.[/grey30]"
    )
    console.print()


def render(console: Console, state: dict, sitting: int) -> None:
    body: list = []

    minutes = (state.get("minutes") or "").strip()
    if minutes:
        text = Text()
        for line in minutes.splitlines():
            stripped = line.strip()
            if stripped in ("RESOLVED", "NOTED", "ANY OTHER BUSINESS"):
                text.append("\n" + stripped + "\n", style="bold bright_white underline")
            else:
                text.append(line + "\n", style="white")
        body.append(text)
    else:
        body.append(
            Text(
                "The council failed to produce minutes. Chairman Toad blames Nigel.",
                style="italic red",
            )
        )

    votes = state.get("votes") or []
    if votes:
        table = Table(
            box=box.SIMPLE_HEAD, show_edge=False, padding=(0, 2), title_justify="left"
        )
        table.add_column("THE DIVISION", style="grey62", no_wrap=True)
        table.add_column("", no_wrap=True)
        table.add_column("", style="italic grey58")
        for v in votes:
            # No emoji in this table: terminals disagree with Rich about the
            # cell width of several of these animals, which shifts the columns.
            name = v.get("critter", "?")
            choice = v.get("vote", "abstain")
            table.add_row(
                name,
                Text(choice.upper(), style=f"bold {VOTE_STYLE.get(choice, 'white')}"),
                v.get("because", ""),
            )
        ayes = sum(1 for v in votes if v.get("vote") == "aye")
        nays = sum(1 for v in votes if v.get("vote") == "nay")
        abst = sum(1 for v in votes if v.get("vote") == "abstain")
        body.append(table)
        body.append(
            Text.assemble(
                ("  Ayes ", "grey62"), (str(ayes), "bold green"),
                ("   Noes ", "grey62"), (str(nays), "bold red"),
                ("   Abstentions ", "grey62"), (str(abst), "bold yellow"),
                ("     THE MOTION IS CARRIED.", "bold bright_white")
                if ayes > nays
                else ("     THE MOTION FALLS.", "bold bright_white"),
            )
        )

    # The paper trail — genuinely useful, and the joke is that it's exhaustive.
    sources = state.get("sources") or []
    if sources:
        refs = Table(box=box.SIMPLE_HEAD, show_edge=False, padding=(0, 2))
        refs.add_column("SCHEDULE A — SOURCES CONSULTED", style="grey62", overflow="fold")
        for s in sources[:8]:
            title = (s.get("title") or "").strip()[:70]
            url = s.get("url", "")
            refs.add_row(Text.assemble((title + "\n", "white"), ("  " + url, "blue underline")))
        body.append(refs)

    dead = state.get("dead_parrots") or []
    forms = state.get("forms") or []
    footer = Text()
    footer.append("  Sources consulted ", style="grey50")
    footer.append(str(len(sources)), style="bold white")
    footer.append("    Deceased sources ", style="grey50")
    footer.append(str(len(dead)), style="bold red")
    footer.append("    Forms filed ", style="grey50")
    footer.append(str(len(forms)), style="bold yellow")
    footer.append("    Tea remaining ", style="grey50")
    footer.append(f"{state.get('tea', 0)}%", style="bold green")
    body.append(footer)

    from .. import llm

    if llm.LEDGER.calls:
        body.append(Text("  " + llm.LEDGER.summary(), style="grey42"))

    console.print()
    console.print(
        Panel(
            Group(*body),
            title=f"\U0001f4dc  MINUTES OF THE {_ordinal(sitting)} SITTING",
            title_align="left",
            subtitle="Clerk: F. Delacroix-Vane  ·  Chair: R. Toad MP",
            subtitle_align="right",
            border_style="bright_white",
            box=box.DOUBLE,
            padding=(1, 2),
        )
    )
    console.print()


def _ordinal(n: int) -> str:
    if 10 <= n % 100 <= 20:
        suffix = "th"
    else:
        suffix = {1: "st", 2: "nd", 3: "rd"}.get(n % 10, "th")
    return f"{n}{suffix}"
