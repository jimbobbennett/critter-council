"""Entry point.

    council "your question"      put a motion directly
    council                      let Chairman Toad ask you for one

After each sitting the chair calls for any other business, so one invocation can
run several motions. Blank input adjourns.
"""

from __future__ import annotations

import argparse
import json
import os
import sys
import time
from pathlib import Path

import shutil

from dotenv import load_dotenv
from rich.console import Console
from rich.markdown import Markdown
from rich.live import Live
from rich.panel import Panel
from rich.prompt import Prompt
from rich.text import Text

from . import llm, sketches
from .graph import build_graph
from .ui import minutes as minutes_ui
from .ui.layout import Display

ROOT = Path(__file__).resolve().parent.parent
MIN_WIDTH = 92


def real_terminal_size() -> tuple[int, int] | None:
    """The terminal's own size, via ioctl.

    Rich prefers the COLUMNS/LINES environment variables when they are set, and
    a stale value (an unnoticed resize, a multiplexer, a script that exported it)
    makes every width calculation wrong — lines are computed for one width and
    rendered at another, so they wrap. The ioctl is the authority.
    """
    for stream in (sys.stdout, sys.stderr, sys.stdin):
        try:
            size = os.get_terminal_size(stream.fileno())
        except (OSError, ValueError, AttributeError):
            continue
        if size.columns > 0 and size.lines > 0:
            return size.columns, size.lines
    return None


def make_console() -> Console:
    """A Console pinned to the terminal's actual size."""
    size = real_terminal_size()
    if size is None:
        return Console()
    return Console(width=size[0], height=size[1])


def doctor(console: Console) -> int:
    """Report the environment the council will run in.

    There are no layout invariants to check any more — Rich renders the Minutes
    and the system pager displays them, so neither wrapping nor geometry is this
    project's code. What is worth checking is what those two will be handed.
    """
    ioctl = real_terminal_size()
    console.print()
    console.print("[bold]Terminal[/bold]")
    console.print(
        f"  ioctl (authoritative) : {ioctl[0]} x {ioctl[1]}"
        if ioctl
        else "  ioctl                 : unavailable (not a terminal)"
    )
    console.print(
        f"  COLUMNS / LINES env   : "
        f"{os.environ.get('COLUMNS', 'unset')} / {os.environ.get('LINES', 'unset')}"
    )
    console.print(f"  Rich is using         : {console.width} x {console.size.height}")
    if ioctl and (console.width != ioctl[0] or console.size.height != ioctl[1]):
        console.print("  [red]MISMATCH — a stale COLUMNS would skew rendering[/red]")
    else:
        console.print("  [green]consistent[/green]")

    console.print()
    console.print("[bold]Minutes display[/bold]")
    pager = os.environ.get("PAGER")
    less = shutil.which("less")
    console.print(f"  PAGER env             : {pager or 'unset'}")
    console.print(f"  less on PATH          : {less or 'not found'}")
    if pager:
        console.print(f"  [green]will page with {pager}[/green]")
    elif less:
        console.print("  [green]will page with less -R -F -X[/green]")
    else:
        console.print("  [yellow]no pager found; Minutes will print straight out[/yellow]")

    console.print()
    console.print("[bold]Credentials[/bold]")
    err = llm.preflight()
    console.print("  [green]found[/green]" if err is None
                  else "  [yellow]none — --demo still works[/yellow]")

    console.print()
    console.print("[bold]Sample render[/bold]")
    sample = {
        "motion": "why do onions make you cry?",
        "minutes": "RESOLVED\n\n1. That a volatile sulfur compound irritates the "
                   "cornea — syn-propanethial-S-oxide, released when the cells are "
                   "ruptured.\n\n2. That reflex tears flush it, which is why the "
                   "effect is self-limiting.\n\nNOTED\n\n1. The urn ran dry once.",
        "votes": [{"critter": "Toad", "vote": "aye", "because": "it ends the meeting"}],
        "sources": [{"title": "Example source", "url": "https://example.org/onions"}],
        "dead_parrots": [], "forms": [1] * 6, "tea": 12,
    }
    from .ui import minutes as m

    console.print(Markdown(m.to_markdown(sample, 447)))
    console.print()
    return 0


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    p = argparse.ArgumentParser(
        prog="council",
        description="A shambolic parish committee of woodland animals researches "
        "your question. Built on LangGraph. Omit the question and the Chairman "
        "will ask you for it.",
    )
    p.add_argument(
        "motion",
        nargs="*",
        help="the question to put before the council (omit to be asked in person)",
    )
    p.add_argument(
        "--demo",
        action="store_true",
        help="run a canned sitting: no API calls, no key, perfect timing for filming",
    )
    p.add_argument("--speed", type=float, default=1.0, help="animation speed multiplier")
    p.add_argument("--seed", type=int, default=None, help="seed the sketches for retakes")
    p.add_argument("--model", default=None, help="voice model (default claude-opus-5)")
    p.add_argument(
        "--research-model",
        default=None,
        help="model for the token-heavy search/fetch turns (default claude-sonnet-5)",
    )
    p.add_argument("--sitting", type=int, default=447, help="sitting number, for flavour")
    p.add_argument("--cast", action="store_true", help="introduce the cast and exit")
    p.add_argument(
        "--doctor",
        action="store_true",
        help="report terminal detection and check the layout invariants, then exit",
    )
    p.add_argument(
        "--quick",
        action="store_true",
        help="settle for less evidence: one search round, roughly half the cost",
    )
    p.add_argument(
        "--once",
        action="store_true",
        help="adjourn after one motion instead of calling for other business",
    )
    return p.parse_args(argv)


CAST_CARDS = [
    ("nigel", "Nigel, a squirrel", "Scout. Enthusiastic. Has a cunning plan."),
    ("owlsworth", "Prof. Twitchett-Owlsworth", "Assesses sources. Emeritus of nowhere."),
    ("buzzwick", "Sgt. Buzzwick, a bee", "Verification. Ministry of Verified Facts."),
    ("foxy", "Foxtrot Delacroix-Vane", "Clerk. Writes the minutes. Vain."),
    ("toad", "The Rt Hon. Reginald Toad MP", "Chair. Nineteen years. Not once surprised."),
]


def show_cast(console: Console, speed: float) -> None:
    from .ui.frames import FRAMES

    console.print()
    for key, name, role in CAST_CARDS:
        art = "\n".join(FRAMES[key][0])
        console.print(
            Panel(
                Text.assemble((art + "\n\n", "bold"), (role, "italic grey62")),
                title=name,
                title_align="left",
                border_style="grey37",
                width=56,
            )
        )
        time.sleep(0.7 / max(0.2, speed))
    console.print()


def _prompt(console: Console) -> str:
    """Ask for a motion, treating EOF and Ctrl-C as "adjourn".

    Prompt.ask raises EOFError on a closed stdin, which would otherwise dump a
    traceback on any non-interactive run (cron, CI, `< /dev/null`).
    """
    try:
        return Prompt.ask(
            "  [bold green]MOTION[/bold green]", default="", show_default=False
        )
    except (EOFError, KeyboardInterrupt):
        console.print()
        return ""


def ask_briefly(console: Console, question: str) -> str:
    """Compact follow-up prompt.

    The full chamber is ~35 rows; re-rendering it for 'any other business' would
    scroll the Minutes we just printed clean off the screen. So follow-ups get
    three lines.
    """
    console.print()
    console.print(
        Panel(
            Text(f'"{question}"', style="italic bright_white"),
            title="\U0001f438 CHAIRMAN TOAD",
            title_align="left",
            border_style="green",
            padding=(0, 1),
        )
    )
    return _prompt(console)


def ask_for_motion(console: Console, sitting: int, question: str) -> str:
    """Render the assembled chamber, with the chair putting the question to you.

    Deliberately a static frame rather than a Live one: the animation loop and a
    blocking readline fight over the terminal, and a still chamber reads better
    as a cold open anyway. The line is scripted, not generated — there is no
    motion yet, so there is nothing to spend a token on.
    """
    display = Display("awaiting a motion", sitting=sitting, width=console.width - 1)
    for key, line in sketches.WAITING.items():
        display.panels[key].visible = line
        display.panels[key].status = "assembled"
    display.panels["toad"].visible = question
    display.panels["toad"].state = "talking"
    display.panels["toad"].status = "putting the question"

    console.print(display)
    console.print()
    motion = _prompt(console)

    # Wipe the static chamber before the Live one takes over. Live runs on the
    # alternate screen, so anything left on the normal screen reappears when it
    # tears down — and a leftover chamber above the result looks like the
    # display failed to close.
    if motion.strip():
        console.clear()
    return motion


def run_sitting(
    console: Console, motion: str, args: argparse.Namespace, sitting: int
) -> dict:
    llm.LEDGER.reset()
    display = Display(motion, sitting=sitting, speed=args.speed, width=console.width - 1)
    display.start()
    graph = build_graph(display, sitting=sitting, evidence=2 if args.quick else 5)

    initial = {
        "motion": motion,
        "tea": 100,
        "round": 1,
        "inquisitions": 0,
        "barren": 0,
        "steps": 0,
        "contradictions": [],
    }
    final: dict = {}
    blew_up: BaseException | None = None
    try:
        with Live(
            display,
            console=console,
            refresh_per_second=12,
            screen=True,
            transient=True,
        ):
            display.beat(1.2)
            try:
                # Lowered from 60 deliberately. The router's MAX_STEPS ceiling
                # bounds a sitting at ~33 nodes even when a branch misbehaves,
                # so this is a genuine backstop rather than a ceiling the graph
                # is expected to approach. If it ever throws, that is a routing
                # bug to fix, not a number to raise.
                final = graph.invoke(initial, config={"recursion_limit": 45})
            except KeyboardInterrupt:
                raise
            except Exception as exc:  # noqa: BLE001 — last line of defence
                blew_up = exc
            if final:
                display.beat(1.2)
    finally:
        display.stop()

    if blew_up is not None:
        # A traceback into the user's terminal is never the right answer here.
        # Show what broke, keep the session alive for another motion.
        console.print()
        console.print(
            Panel(
                Text.assemble(
                    ("The sitting collapsed. Chairman Toad has left the hall.\n\n",
                     "italic green"),
                    (f"{type(blew_up).__name__}: {blew_up}", "red"),
                    ("\n\nAnything already spent is on the ledger below. Put the "
                     "motion again to retry.", "grey54"),
                ),
                title="Sitting abandoned",
                border_style="red",
                padding=(1, 2),
            )
        )
        if llm.LEDGER.calls:
            console.print(f"  [grey42]{llm.LEDGER.summary()}[/grey42]\n")
    return final


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    load_dotenv(ROOT / ".env")
    console = make_console()

    if args.doctor:
        return doctor(console)

    if args.model:
        llm.MODEL = args.model
    if args.research_model:
        llm.RESEARCH_MODEL = args.research_model
    if args.seed is not None:
        sketches.seed(args.seed)

    if args.cast:
        show_cast(console, args.speed)
        return 0

    motion = " ".join(args.motion).strip()

    if args.demo:
        fixtures_path = ROOT / "demo_fixtures.json"
        if not fixtures_path.exists():
            console.print(f"[red]Missing {fixtures_path}[/red]")
            return 1
        llm.enable_demo(json.loads(fixtures_path.read_text()))
        # Demo content is canned and keyed to one question, so the chair does
        # not ask here — a typed motion answered with canned findings about cats
        # would be actively misleading on video.
        motion = motion or llm.demo_motion()

    err = llm.preflight()
    if err:
        console.print(Panel(err, title="Cannot convene", border_style="red"))
        return 1

    if console.width < MIN_WIDTH:
        console.print(
            f"[yellow]Terminal is {console.width} columns; the chamber wants "
            f"{MIN_WIDTH}+. Widen the window for the full layout.[/yellow]\n"
        )
        time.sleep(2)

    sitting = args.sitting
    sittings_held = 0

    try:
        while True:
            if not motion:
                if sittings_held == 0:
                    motion = ask_for_motion(
                        console, sitting, sketches.pick(sketches.TOAD_ASKS)
                    ).strip()
                else:
                    motion = ask_briefly(
                        console, sketches.pick(sketches.TOAD_AOB)
                    ).strip()
                if not motion:
                    console.print(
                        f"\n  [italic green]{sketches.pick(sketches.TOAD_ADJOURNS)}"
                        "[/italic green]\n"
                    )
                    break

            final = run_sitting(console, motion, args, sitting)
            # Markdown, rendered by Rich, displayed by the pager, saved to a
            # file. None of those three is this project's code, which is the
            # point: each of them already handles its job correctly.
            if final:
                markdown = minutes_ui.to_markdown(final, sitting)
                path = minutes_ui.write_file(markdown, sitting)
                minutes_ui.show(console, markdown, path)
            sittings_held += 1
            sitting += 1
            motion = ""

            # No point calling for other business with nobody in the hall.
            if args.once or llm.DEMO or not sys.stdin.isatty():
                break
    except KeyboardInterrupt:
        console.print("\n  [grey62]The chair adjourned the sitting early.[/grey62]\n")
        return 130

    if sittings_held > 1:
        console.print(
            f"  [grey42]{sittings_held} sittings held this session · "
            f"~${llm.LEDGER.session_cost:.2f} total[/grey42]\n"
        )
    return 0


if __name__ == "__main__":
    sys.exit(main())
