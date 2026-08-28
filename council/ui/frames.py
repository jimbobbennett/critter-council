"""ASCII portraits. Three frames per critter: resting, blinking, talking.

Deliberately pure ASCII inside the art blocks — emoji are double-width in most
terminals and shear the panel alignment. Emoji live in panel titles only, where
Rich measures them properly.
"""

from __future__ import annotations

# Each frame is exactly 3 lines. The pacer cycles them.

NIGEL = [
    [r"  (\__/)  ", r"  ( o.o )  ", r"   c( )>   "],
    [r"  (\__/)  ", r"  ( -.- )  ", r"   c( )>   "],
    [r"  (\__/)  ", r"  ( o.O )  ", r"   c( )/   "],
]

OWLSWORTH = [
    [r"   ,___,   ", r"  ( O,O )  ", r"   /)_)    "],
    [r"   ,___,   ", r"  ( -,- )  ", r"   /)_)    "],
    [r"   ,___,   ", r"  ( O,o )  ", r"   /)_)>   "],
]

BUZZWICK = [
    [r"   \ | /   ", r"  ( o.o )  ", r"  (#####)  "],
    [r"   \ | /   ", r"  ( -.- )  ", r"  (#####)  "],
    [r"   \\|//   ", r"  ( o.O )  ", r"  (#####)  "],
]

FOXY = [
    [r"  /\ _ /\  ", r" (  ^.^  ) ", r"   > ^ <   "],
    [r"  /\ _ /\  ", r" (  -.-  ) ", r"   > ^ <   "],
    [r"  /\ _ /\  ", r" (  ^.o  ) ", r"   > w <   "],
]

TOAD = [
    [r"   @..@    ", r"  (----)   ", r" ( >__< )  "],
    [r"   @--@    ", r"  (----)   ", r" ( >__< )  "],
    [r"   @..@    ", r"  (-oo-)   ", r" ( >__< )  "],
]

XIMENEZ = [
    [r"    _+_    ", r"  ( O.O )  ", r"   /|_|\   "],
    [r"    _+_    ", r"  ( o.o )  ", r"   /|_|\   "],
    [r"    _+_    ", r"  ( O.O )  ", r"  </|_|\>  "],
]

GAVEL = [
    r"   __/\ ",
    r"  /___/ ",
    r" ___|__ ",
]

FRAMES = {
    "nigel": NIGEL,
    "owlsworth": OWLSWORTH,
    "buzzwick": BUZZWICK,
    "foxy": FOXY,
    "toad": TOAD,
    "ximenez": XIMENEZ,
}
