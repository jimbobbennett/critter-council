"""The live council chamber.

Rich's Live redraws on a background thread, so nodes simply mutate this object
and the screen keeps up. A second small daemon thread ("the pacer") drives the
typewriter effect and the blink animation, which means `say()` can block until a
line has finished typing — that is what gives the sitting its rhythm.
"""

from __future__ import annotations


import threading
import time
from dataclasses import dataclass

from rich import box
from rich.console import Group, RenderableType
from rich.panel import Panel
from rich.table import Table
from rich.text import Text

from .. import sketches
from .frames import FRAMES, GAVEL

BUBBLE_LINES = 4  # speech bubbles are a fixed height so the grid never jitters
GRID_ROW_HEIGHT = 3 + (BUBBLE_LINES + 2) + 1 + 2  # art + bubble + stats + border
CHARS_PER_SEC = 48.0


@dataclass
class CritterPanel:
    key: str
    name: str
    icon: str
    colour: str
    art: str
    state: str = "idle"  # idle | working | talking | done
    status: str = "waiting"
    pending: str = ""
    visible: str = ""
    stats: str = ""
    _acc: float = 0.0


@dataclass
class Overlay:
    title: str
    lines: list[str]
    colour: str
    art: str | None = None


@dataclass
class ScrollBox:
    """A scrollable panel that takes over the chamber — used for the Minutes.

    Lines arrive pre-wrapped as (text, style) pairs because scrolling needs an
    accurate line count, which means owning the wrapping rather than letting
    Rich do it.
    """

    title: str
    lines: list[tuple[str, str]]
    height: int = 20
    offset: int = 0
    subtitle: str = ""

    def clamp(self) -> None:
        self.offset = max(0, min(self.offset, max(0, len(self.lines) - self.height)))

    def by(self, delta: int) -> None:
        self.offset += delta
        self.clamp()

    def to(self, where: str) -> None:
        self.offset = 0 if where == "top" else len(self.lines)
        self.clamp()

    @property
    def at_end(self) -> bool:
        return self.offset >= len(self.lines) - self.height


class Display:
    def __init__(self, motion: str, sitting: int = 447, speed: float = 1.0):
        self.motion = motion
        self.sitting = sitting
        self.speed = max(0.2, speed)
        self.tea = 100
        self.round = 1
        self.max_rounds = 3
        self.active: str = "chairman"
        self.overlay: Overlay | None = None
        self.scroll: ScrollBox | None = None
        self.toaster_line = sketches.TOASTER[0]
        self._toaster_at = time.monotonic()

        self.panels: dict[str, CritterPanel] = {
            "nigel": CritterPanel("nigel", "NIGEL (Scout)", "\U0001f43f", "yellow", "nigel"),
            "owlsworth": CritterPanel(
                "owlsworth", "PROF. OWLSWORTH", "\U0001f989", "cyan", "owlsworth"
            ),
            "buzzwick": CritterPanel(
                "buzzwick", "SGT. BUZZWICK", "\U0001f41d", "bright_yellow", "buzzwick"
            ),
            "foxy": CritterPanel("foxy", "FOXY (Clerk)", "\U0001f98a", "magenta", "foxy"),
            "toad": CritterPanel(
                "toad", "CHAIRMAN TOAD, presiding", "\U0001f438", "green", "toad"
            ),
        }

        self._lock = threading.RLock()
        self._stop = threading.Event()
        self._pacer = threading.Thread(target=self._pace, daemon=True)

    # --- lifecycle ---------------------------------------------------------------

    def start(self) -> None:
        self._pacer.start()

    def stop(self) -> None:
        self._stop.set()

    # --- pacing ------------------------------------------------------------------

    def _pace(self) -> None:
        tick = 1.0 / 40.0
        while not self._stop.is_set():
            time.sleep(tick)
            now = time.monotonic()
            with self._lock:
                for p in self.panels.values():
                    if not p.pending:
                        continue
                    p._acc += CHARS_PER_SEC * self.speed * tick
                    take = int(p._acc)
                    if take:
                        p._acc -= take
                        p.visible += p.pending[:take]
                        p.pending = p.pending[take:]
                if now - self._toaster_at > 9.0 / self.speed:
                    self._toaster_at = now
                    self.toaster_line = sketches.pick(sketches.TOASTER)

    def beat(self, seconds: float) -> None:
        time.sleep(max(0.0, seconds) / self.speed)

    # --- mutation from nodes -----------------------------------------------------

    def say(self, key: str, text: str, *, dwell: float = 0.8) -> None:
        """Type a line into a critter's bubble, blocking until it has landed."""
        text = " ".join((text or "").split())
        if not text:
            return
        p = self.panels[key]
        with self._lock:
            p.pending = text
            p.visible = ""
            p._acc = 0.0
            p.state = "talking"
        while True:
            with self._lock:
                if not p.pending:
                    break
            time.sleep(0.02)
        self.beat(dwell)
        with self._lock:
            if p.state == "talking":
                p.state = "idle"

    def working(self, key: str, status: str) -> None:
        with self._lock:
            p = self.panels[key]
            p.state = "working"
            p.status = status

    def status(self, key: str, status: str, *, state: str | None = None) -> None:
        with self._lock:
            p = self.panels[key]
            p.status = status
            if state:
                p.state = state

    def stats(self, key: str, stats: str) -> None:
        with self._lock:
            self.panels[key].stats = stats

    def set_active(self, node: str) -> None:
        with self._lock:
            self.active = node

    def set_tea(self, value: int) -> None:
        with self._lock:
            self.tea = max(0, min(100, value))

    def set_round(self, value: int) -> None:
        with self._lock:
            self.round = value

    def slam(self, overlay: Overlay, seconds: float) -> None:
        with self._lock:
            self.overlay = overlay
        self.beat(seconds)
        with self._lock:
            self.overlay = None

    def show_scroll(self, box: ScrollBox) -> None:
        with self._lock:
            self.scroll = box

    def scroll_by(self, delta: int) -> None:
        with self._lock:
            if self.scroll:
                self.scroll.by(delta)

    def scroll_to(self, where: str) -> None:
        with self._lock:
            if self.scroll:
                self.scroll.to(where)

    def close_scroll(self) -> None:
        with self._lock:
            self.scroll = None

    # --- rendering ---------------------------------------------------------------

    def _frame_index(self, p: CritterPanel) -> int:
        t = time.monotonic()
        if p.state == "talking":
            return 2 if int(t * 7) % 2 else 0
        if p.state == "working":
            return 1 if int(t * 3) % 2 else 0
        return 1 if (t % 3.2) < 0.13 else 0

    def _leds(self, p: CritterPanel) -> str:
        if p.state == "working":
            i = int(time.monotonic() * 4) % 3
            return " ".join("●" if j == i else "○" for j in range(3))
        if p.state == "talking":
            return "● ● ●"
        if p.state == "done":
            return "✓ ✓ ✓"
        return "○ ○ ○"

    def _bubble(self, p: CritterPanel) -> Panel:
        # Fixed height, but let Rich do the wrapping — pre-wrapping at a
        # hard-coded column count double-wraps on narrower terminals.
        return Panel(
            Text(p.visible or "", overflow="fold"),
            box=box.ROUNDED,
            border_style="grey37",
            padding=(0, 1),
            height=BUBBLE_LINES + 2,
        )

    def _critter(self, p: CritterPanel) -> Panel:
        art = FRAMES[p.art][self._frame_index(p)]
        head = Table.grid(padding=(0, 1))
        head.add_column(width=11, no_wrap=True)
        head.add_column(ratio=1)
        head.add_row(
            Text("\n".join(art), style=f"bold {p.colour}"),
            Text(f"{self._leds(p)}\n{p.status}", style="italic grey62"),
        )
        border = p.colour if p.state in ("working", "talking") else "grey30"
        return Panel(
            Group(head, self._bubble(p), Text(p.stats or " ", style="dim")),
            title=f"{p.icon} {p.name}",
            title_align="left",
            border_style=border,
            box=box.ROUNDED,
            padding=(0, 1),
        )

    def _header(self) -> Panel:
        filled = round(self.tea / 10)
        bar = "▓" * filled + "░" * (10 - filled)
        tea_style = "green" if self.tea > 40 else ("yellow" if self.tea > 0 else "red")
        top = Table.grid(expand=True)
        top.add_column(ratio=1)
        top.add_column(justify="right", no_wrap=True)
        top.add_row(
            Text("THE RIGHT HONOURABLE COUNCIL OF CRITTERS", style="bold white"),
            Text.assemble(
                ("\U0001fad6 TEA ", "bold"),
                (bar, tea_style),
                (f" {self.tea:>3}%", tea_style),
            ),
        )
        # Live cost meter, straight off the API usage figures. Good for a demo:
        # you can watch the sitting spend real money.
        from .. import llm

        led = llm.LEDGER
        top.add_row(
            Text(f"Sitting #{self.sitting}", style="grey62"),
            Text.assemble(
                (f"round {self.round}/{self.max_rounds}   ", "grey62"),
                (f"{led.searches} searches  ", "grey50"),
                (f"~${led.cost:.2f}", "bold grey74"),
            ),
        )
        motion = Text.assemble(
            ("MOTION: ", "bold grey62"), (f'"{self.motion}"', "italic bright_white")
        )
        return Panel(
            Group(top, motion), box=box.DOUBLE, border_style="white", padding=(0, 1)
        )

    def _grid(self) -> RenderableType:
        if self.overlay:
            ov = self.overlay
            body: list[RenderableType] = []
            if ov.art:
                art = FRAMES[ov.art][2]
                body.append(Text("\n".join(art) + "\n", style=f"bold {ov.colour}"))
            for line in ov.lines:
                body.append(Text(line, style="bold bright_white"))
            # Height matches the 2x2 grid it replaces, so the rest of the
            # chamber doesn't jump when the overlay slams in and out.
            return Panel(
                Group(*body),
                title=f"⚠  {ov.title}",
                title_align="center",
                border_style=ov.colour,
                box=box.DOUBLE,
                padding=(1, 2),
                height=GRID_ROW_HEIGHT * 2,
            )
        g = Table.grid(expand=True)
        g.add_column(ratio=1)
        g.add_column(ratio=1)
        g.add_row(self._critter(self.panels["nigel"]), self._critter(self.panels["owlsworth"]))
        g.add_row(self._critter(self.panels["buzzwick"]), self._critter(self.panels["foxy"]))
        return g

    def _chair(self) -> Panel:
        p = self.panels["toad"]
        art = FRAMES["toad"][self._frame_index(p)]
        row = Table.grid(padding=(0, 2))
        row.add_column(width=11, no_wrap=True)
        row.add_column(ratio=1)
        row.add_column(width=9, no_wrap=True)
        spoken = " ".join(p.visible.split())
        row.add_row(
            Text("\n".join(art), style="bold green"),
            Text(f'"{spoken}"' if spoken else "", style="italic bright_white",
                 overflow="fold"),
            Text("\n".join(GAVEL), style="yellow" if p.state == "talking" else "grey30"),
        )
        return Panel(
            row,
            title=f"{p.icon} {p.name}",
            title_align="left",
            border_style="green" if p.state in ("working", "talking") else "grey30",
            box=box.ROUNDED,
            padding=(0, 1),
        )

    def _footer(self) -> RenderableType:
        # Just the toaster, across the full width. It gets the whole line to
        # itself, which is the only recognition it will ever receive.
        #
        # Unicode has no toaster emoji, so the bread sits in a slot instead:
        # [🍞] reads as a two-slot toaster at a glance. The brackets are
        # single-width ASCII, so nothing shifts.
        return Text.assemble(
            ("  [", "grey30"),
            ("\U0001f35e", ""),
            ("]  ", "grey30"),
            (f'"{self.toaster_line}"', "italic grey42"),
            overflow="ellipsis",
            no_wrap=True,
        )

    def _scrollbox(self) -> RenderableType:
        sb = self.scroll
        assert sb is not None
        sb.clamp()
        window = sb.lines[sb.offset : sb.offset + sb.height]

        # A proportional thumb down the right edge, so it reads as scrollable at
        # a glance rather than only when you try the keys.
        total = max(1, len(sb.lines))
        thumb_len = max(1, round(sb.height * sb.height / total))
        thumb_at = round(sb.offset * sb.height / total)

        body = Table.grid(expand=True)
        body.add_column(ratio=1, overflow="crop")
        body.add_column(width=1, no_wrap=True)
        for i in range(sb.height):
            text, style = window[i] if i < len(window) else ("", "")
            in_thumb = thumb_at <= i < thumb_at + thumb_len
            bar = "█" if in_thumb else "│"
            body.add_row(
                Text(text, style=style),
                Text(bar, style="grey54" if in_thumb else "grey27"),
            )

        first = sb.offset + 1 if sb.lines else 0
        last = min(sb.offset + sb.height, len(sb.lines))
        nav = "↑↓ / jk scroll   space page   g / G ends   q or Enter to close"
        if len(sb.lines) <= sb.height:
            nav = "q or Enter to close"
        return Panel(
            body,
            title=f"\U0001f4dc  {sb.title}",
            title_align="left",
            subtitle=f"{first}–{last} of {len(sb.lines)}   ·   {nav}",
            subtitle_align="right",
            border_style="bright_white",
            box=box.DOUBLE,
            padding=(0, 2),
        )

    def __rich__(self) -> RenderableType:
        with self._lock:
            if self.scroll:
                return Group(self._header(), self._scrollbox())
            return Group(self._header(), self._grid(), self._chair(), self._footer())
