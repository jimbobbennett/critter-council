"""Entry point.

    council "your question"      put a motion directly
    council                      let Chairman Toad ask you for one

After each sitting the chair calls for any other business, so one invocation can
run several motions. Blank input adjourns.
"""

from __future__ import annotations

import argparse
import json
import sys
import time
from pathlib import Path

from dotenv import load_dotenv
from rich.console import Console
from rich.live import Live
from rich.panel import Panel
from rich.prompt import Prompt
from rich.text import Text

from . import llm, sketches
from .graph import build_graph
from .ui import minutes as minutes_ui
from .ui.layout import Display, ScrollBox

ROOT = Path(__file__).resolve().parent.parent
MIN_WIDTH = 92


def read_key() -> str:
    """Read one keypress, including arrow-key escape sequences.

    Raw mode via termios, because the Minutes panel has to scroll while the Live
    display is still driving the screen — there is no line to read.

    Returns "" on EOF or a terminal error. Callers must treat that as "stop
    reading": on a closed or exhausted stdin, read() returns immediately and
    forever, so ignoring it spins a busy loop.
    """
    import termios
    import tty

    try:
        fd = sys.stdin.fileno()
        old = termios.tcgetattr(fd)
    except (termios.error, ValueError, OSError):
        return ""
    try:
        tty.setraw(fd)
        ch = sys.stdin.read(1)
        if not ch:
            return ""
        if ch == "\x1b":  # escape: could be an arrow key
            ch += sys.stdin.read(2)
    except (OSError, ValueError):
        return ""
    finally:
        termios.tcsetattr(fd, termios.TCSADRAIN, old)
    return ch


def drain_stdin() -> None:
    """Throw away anything already typed but not yet read.

    The terminal buffers keystrokes during the sitting, and the panel's key loop
    would consume them the instant it opens: a stray space is a page-down (so the
    Minutes appear to start partway in), a stray Enter closes the panel before it
    is seen, and whatever is left leaks to the shell on exit.
    """
    try:
        import termios

        termios.tcflush(sys.stdin.fileno(), termios.TCIFLUSH)
    except Exception:
        pass


def browse_minutes(display: Display, console: Console, final: dict) -> None:
    """Show the Minutes as a scrollable panel inside the chamber.

    Non-interactive stdin (a pipe, CI) gets one static frame and moves on, so
    this never blocks a scripted run.
    """
    # header is 5 rows, the panel adds 2 borders, and one row is left spare so
    # writing the last cell can't scroll the terminal. Floor is low enough that a
    # very short window shrinks the panel rather than overflowing it.
    height = max(4, console.size.height - 8)
    box = ScrollBox(
        title="MINUTES OF THE SITTING",
        lines=minutes_ui.scroll_lines(final, console.width),
        height=height,
    )
    display.show_scroll(box)

    if not sys.stdin.isatty():
        display.beat(2.0)
        display.close_scroll()
        return

    # Start from a clean input buffer, and start at the top of the document.
    drain_stdin()
    display.scroll_to("top")

    # Note: the panel is deliberately left up on exit rather than closed here.
    # Live tears down immediately after this returns, so closing it first would
    # flash the chamber back for a frame on the way out.
    page = max(1, height - 2)
    while True:
        key = read_key()
        # "" is EOF or a terminal error — never keep looping on it.
        if key == "" or key in ("q", "Q", "\r", "\n", "\x03", "\x1b"):
            break
        elif key in ("j", "\x1b[B"):
            display.scroll_by(1)
        elif key in ("k", "\x1b[A"):
            display.scroll_by(-1)
        elif key in (" ", "\x1b[6~", "f"):
            display.scroll_by(page)
        elif key in ("b", "\x1b[5~"):
            display.scroll_by(-page)
        elif key == "g":
            display.scroll_to("top")
        elif key == "G":
            display.scroll_to("end")

    # Don't let unread keypresses spill onto the shell prompt after teardown.
    drain_stdin()


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
    display = Display("awaiting a motion", sitting=sitting)
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
    display = Display(motion, sitting=sitting, speed=args.speed)
    display.start()
    graph = build_graph(display, sitting=sitting, evidence=2 if args.quick else 5)

    initial = {
        "motion": motion,
        "tea": 100,
        "round": 1,
        "inquisitions": 0,
        "barren": 0,
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
                final = graph.invoke(initial, config={"recursion_limit": 60})
            except KeyboardInterrupt:
                raise
            except Exception as exc:  # noqa: BLE001 — last line of defence
                blew_up = exc
            if final:
                display.beat(1.0)
                # Foxy's actual output, in the chamber, before anything can
                # scroll it away. Blocks until dismissed.
                browse_minutes(display, console, final)
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
    console = Console()

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
            # Interactively, the reader has just scrolled the full Minutes in the
            # panel, so the scrollback copy is a short record. Non-interactively
            # the panel only flashed, so print everything — it is all they get.
            if not final:
                pass  # sitting collapsed; run_sitting has already explained
            elif sys.stdin.isatty():
                minutes_ui.render_digest(console, final, sitting)
            else:
                minutes_ui.render(console, final, sitting)
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
