"""The reveal, in two forms.

`scroll_lines` produces pre-wrapped, styled lines for the scrollable in-chamber
panel — scrolling needs an accurate line count, so this owns its own wrapping.
`render` prints the same content to the normal screen afterwards, where Rich can
wrap it, so the Minutes survive in the scrollback once the chamber is gone.
"""

from __future__ import annotations

import textwrap

from rich import box
from rich.cells import cell_len
from rich.console import Console, Group
from rich.panel import Panel
from rich.table import Table
from rich.text import Text

VOTE_STYLE = {"aye": "green", "nay": "red", "abstain": "yellow"}
HEADINGS = ("RESOLVED", "NOTED", "ANY OTHER BUSINESS")


def scroll_lines(state: dict, width: int) -> list[tuple[str, str]]:
    """Everything worth reading, as (text, style) pairs, wrapped to `width`.

    The panel renders one screen row per item in this list, so the wrapping here
    must match the panel's real text column: 2 border + 4 padding + 1 scrollbar,
    with a character of slack.
    """
    w = max(24, width - 8)
    out: list[tuple[str, str]] = []

    def add(
        text: str = "", style: str = "white", indent: str = "", hang: str | None = None
    ) -> None:
        """`hang` is the continuation indent — without it, wrapped lines sit
        underneath the list number instead of the text, which reads as broken."""
        if not text:
            out.append(("", style))
            return
        for line in textwrap.wrap(
            text, w, initial_indent=indent, subsequent_indent=hang if hang is not None else indent
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
                numbered = stripped[0].isdigit()
                add(
                    stripped,
                    "white",
                    indent="  " if numbered else "",
                    hang="     " if numbered else "  ",
                )
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
                hang=" " * 28,
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
            add(s.get("title", "") or s.get("url", ""), "white", hang="   ")
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


def _paragraphs(lines: list[str]) -> list[str]:
    """Group a section's raw lines into one paragraph per item.

    The model sometimes hard-wraps its own output, so consecutive non-blank
    lines are rejoined and blank lines separate items.
    """
    out: list[str] = []
    buf: list[str] = []
    for line in lines:
        if line.strip():
            buf.append(line.strip())
        elif buf:
            out.append(" ".join(buf))
            buf = []
    if buf:
        out.append(" ".join(buf))
    return out


def _numbered_grid(items: list[str], body_width: int) -> Table:
    """Resolutions as a two-column grid.

    The hanging indent is structural rather than a string of spaces, and Rich
    does the wrapping — which matters because Rich measures display *cells*
    while textwrap counts *characters*. One emoji is one cell wider than its
    character count, one CJK glyph is two, so hand-computed wrap widths overflow
    the terminal by a character and it wraps, which is what made this list look
    offset and pushed its opening off the top of the screen.
    """
    # Not expand=True, and the margin is a column rather than Padding: an
    # expanded renderable pads every line with spaces out to the full width, and
    # a row of exactly `width` cells is what makes a terminal wrap by one.
    t = Table.grid(padding=(0, 1))
    t.add_column(width=1, no_wrap=True)          # left margin
    t.add_column(width=2, no_wrap=True)          # "1."
    t.add_column(width=body_width, overflow="fold")
    for item in items:
        head, _, rest = item.partition(" ")
        if head[:1].isdigit():
            t.add_row("", Text(head, style="white"), Text(rest, style="white"))
        else:
            t.add_row("", "", Text(item, style="white"))
        t.add_row("", "", "")
    return t


def render_digest(console: Console, state: dict, sitting: int) -> None:
    """The short record printed after the scrollable panel is dismissed.

    Two hard rules, both learned from bugs:

    * Not a box, and never taller than the window. A terminal always scrolls to
      the bottom of what it is given, so anything taller loses its top and the
      reader lands midway down the findings. Items are added only while they
      measurably fit.
    * Rich does all wrapping and all measuring. No character arithmetic.
    """
    inner = max(30, console.width - 2)          # two spare columns, always
    body_width = max(20, inner - 8)             # margin + number + grid padding
    opts = console.options.update(width=inner)

    def rows_of(renderable) -> int:
        return len(console.render_lines(renderable, opts, pad=False))

    motion = Text.assemble(
        ("MOTION: ", "italic grey62"), (f'"{state.get("motion", "")}"', "italic grey74")
    )

    votes = state.get("votes") or []
    ayes = sum(1 for v in votes if v.get("vote") == "aye")
    nays = sum(1 for v in votes if v.get("vote") == "nay")
    abst = sum(1 for v in votes if v.get("vote") == "abstain")
    sources = state.get("sources") or []
    dead = state.get("dead_parrots") or []

    from .. import llm

    tail: list[Text] = []
    if votes:
        outcome = "Carried" if ayes > nays else "Fallen"
        extra = f" ({abst} abstention{'s' if abst != 1 else ''})" if abst else ""
        tail.append(
            Text(
                f"{outcome} {ayes}-{nays}{extra}  ·  {len(sources)} sources"
                f"  ·  {len(dead)} deceased  ·  {len(state.get('forms') or [])} forms",
                style="grey54",
            )
        )
    if llm.LEDGER.calls:
        tail.append(Text(llm.LEDGER.summary(), style="grey42"))

    items = _paragraphs(_section(state.get("minutes") or "", "RESOLVED"))

    # Everything printed that is not a resolution: a blank, the heading, a blank,
    # the motion, a blank, "RESOLVED", the truncation note, and a trailing blank.
    # That is 8, plus however many rows the tallies take.
    chrome = 8 + sum(rows_of(t) for t in tail)
    budget = console.size.height - chrome
    if budget < 3:
        # Too short for findings and tallies both. The findings are the point.
        tail = []
        budget = max(0, console.size.height - 8)

    # Add resolutions only while they measurably fit. Measuring beats arithmetic:
    # it accounts for cell widths, styles and the grid's own padding.
    shown: list[str] = []
    for item in items:
        trial = _numbered_grid(shown + [item], body_width)
        if rows_of(trial) > budget:
            break
        shown.append(item)
    dropped = len(items) - len(shown)

    # Hand-rolled rather than console.rule(): rule fills the full width exactly,
    # and a row of precisely `width` cells is what a terminal wraps by one. This
    # always leaves a spare column.
    title = f"MINUTES OF THE {_ordinal(sitting)} SITTING "
    bar = "─" * max(0, (console.width - 1) - cell_len(title))
    console.print()
    console.print(
        Text(title, style="bold bright_white") + Text(bar, style="grey37")
    )
    console.print()
    console.print(Text("  ") + motion)
    console.print()
    if shown:
        console.print(Text("  RESOLVED", style="bold bright_white"))
        console.print(_numbered_grid(shown, body_width))
    else:
        console.print(
            Text("  The council established nothing. Toad blames Nigel.", "italic red")
        )
    if dropped:
        console.print(
            Text(
                f"  … {dropped} further resolution(s) — the full Minutes were in "
                "the panel.",
                style="grey30",
            )
        )
    for t in tail:
        console.print(Text("  ") + t)
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
