"""The set pieces. Fixed text, because a sketch that lands every time beats a
sketch the model might paraphrase into mush.

Everything is chosen through a seeded Random so `--seed` gives identical retakes.
"""

from __future__ import annotations

import random

_rng = random.Random()


def seed(n: int) -> None:
    _rng.seed(n)


def pick(options: list[str]) -> str:
    return _rng.choice(options)


# --- the dead parrot: fires on a genuine web_fetch failure ----------------------

DEAD_PARROT = [
    "This source is no more. It has ceased to be. It has expired and gone to meet "
    "its maker. This is a late source. It is a stiff. Bereft of life, it rests in peace.",
    "It's not pinin'! It's passed on! This citation is no more! It has ceased to be! "
    "It's expired and gone to meet its maker! THIS IS AN EX-SOURCE.",
    "Nigel, this URL is definitively deceased. It has shuffled off this mortal coil, "
    "run down the curtain, and joined the bleedin' choir invisible.",
]

DEAD_PARROT_REBUTTAL = [
    "It's probably just stunned, m'lord.",
    "No no, it's resting. Remarkable server, the Apache. Beautiful plumage.",
    "I think it's pining for the fjords.",
]


# --- the inquisition: fires when sources contradict each other -----------------

INQUISITION_ENTRANCE = "NOBODY EXPECTS THE CONTRADICTORY SOURCE!"

INQUISITION_WEAPONS = [
    "Our three chief weapons are citation, cross-reference, and a fanatical "
    "devotion to the footnote!",
    "Our chief weapons are surprise, ruthless peer review, and an almost fanatical "
    "devotion to the bibliography!",
]

INQUISITION_EXIT = [
    "Fetch... THE COMFY CHAIR. And a second opinion.",
    "You will confess by teatime, or face the SOFT CUSHIONS of methodological doubt.",
]


# --- the tea urn: fires when state['tea'] hits zero ----------------------------

TEA_BREAK = [
    "The urn is dry. I'm afraid all council business is suspended until it is refilled. "
    "That is not a preference. That is the constitution.",
    "Tea has run out. Under Standing Order 4, no motion may be progressed by a "
    "dehydrated committee. Adjourned. Fifteen minutes.",
    "No tea. No council. I don't make the rules, Nigel — I merely enforce them with "
    "tremendous enthusiasm.",
]

TEA_RETURN = [
    "Right. Tea replenished. Biscuit situation: dire but survivable. Where were we.",
    "The urn lives. Back to work, you shower.",
]


# --- Buzzwick blocks on paperwork ----------------------------------------------

FORM_BLOCKS = [
    "I'm afraid I can't verify that until Form 27B/6 is stamped. In triplicate. "
    "By me. I'll get to it.",
    "That claim has been logged but not stamped, and an unstamped claim is, "
    "procedurally speaking, a rumour.",
    "I've drawn up a timetable for the verification. The first four hours are for "
    "drawing up the timetable.",
]


# --- fallbacks, if the model returns something unusable -----------------------

CUNNING_PLAN_FALLBACK = [
    "I have a cunning plan, m'lord: we type the question into the internet.",
    "I have a plan so cunning you could pin a tail on it and call it a weasel: "
    "we look it up.",
    "A cunning plan, m'lord. We ask someone who knows.",
]

CHAIR_FALLBACK = [
    "Order. ORDER. Get on with it.",
    "I have presided over parish drainage disputes with more intellectual content "
    "than this. Proceed.",
]


def cunning_verdict(rating: int) -> str:
    """Toad's assessment of a Cunning Rating."""
    if rating <= 2:
        return "a plan so cunning you could pin a tail on it and call it a weasel"
    if rating <= 5:
        return "cunning as a fox who has recently been made redundant"
    if rating <= 8:
        return "cunning as a fox who's just been made Professor of Cunning at Oxford"
    return "suspiciously cunning. I don't trust it and neither should you"


# --- convening: Toad asks for the motion himself ------------------------------

TOAD_ASKS = [
    "The council is convened, at considerable inconvenience to us all. "
    "What is the motion?",
    "Nineteen years I have chaired this council. Not once has it been worth it. "
    "What is the motion?",
    "We are assembled. The urn is full. State your business and try to make it "
    "interesting.",
    "Order. The floor is yours, briefly. What would you have this council "
    "research?",
]

TOAD_AOB = [
    "Any other business? Speak now, or I am going home.",
    "Is there further business, or may I finally leave this hall?",
    "The council remains, regrettably, in session. Another motion?",
]

TOAD_ADJOURNS = [
    "No further business. This council is adjourned. Nigel, put the chairs away.",
    "Then we are done. Adjourned. I shall be at the pub, and I am not to be "
    "followed.",
    "Nothing? Splendid. Adjourned, with the thanks of a grateful parish. Out.",
]

# What each critter says while waiting for a motion to be put to them.
WAITING = {
    "nigel": "I'm ready, m'lord. I have brought a pencil.",
    "owlsworth": "I shall require at least four sources, and a biscuit.",
    "buzzwick": "The forms are pre-stamped. I have been here since six.",
    "foxy": "Wake me when there is something worth writing, darlings.",
}


# --- the machinery fails: distinct from a dead source, and honest about it ----
# A transient API error is not the same thing as an unreachable page, so it gets
# its own joke rather than being blamed on the source.

API_TROUBLE = [
    "The parish telephone has gone down again. I blame the Post Office, and "
    "Nigel, in that order.",
    "The line has dropped. Nineteen years I have asked for a second telephone. "
    "Nineteen years.",
    "We have lost contact with the outside world. Proceed on what we have, "
    "which is regrettably little.",
]

API_TROUBLE_SCOUT = [
    "The internet has hung up on me, m'lord. I don't think it was personal.",
    "I dialled and it went dead. Shall I try shouting instead?",
]
