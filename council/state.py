"""Council state and the structured shapes the critters speak in.

Every model in here is sent to the API as a JSON schema, so two rules apply:
no numeric/length constraints (the API rejects them), and every field is
required with no default (strict schemas list all properties as required).
Validation of ranges happens in Python instead.
"""

from __future__ import annotations

import operator
from typing import Annotated, Literal, TypedDict

from pydantic import BaseModel, ConfigDict


class Strict(BaseModel):
    """Base for anything used as an output schema — emits additionalProperties: false."""

    model_config = ConfigDict(extra="forbid")


# --- things the critters produce -------------------------------------------------


class Source(Strict):
    url: str
    title: str
    snippet: str


class Finding(Strict):
    claim: str
    source_url: str
    # Owlsworth's Blackadder-grade assessment of the source.
    simile: str


class Clash(Strict):
    subject: str
    one_says: str
    other_says: str


class Verdict(Strict):
    # Index into the numbered list of claims Buzzwick was handed. Verdicts are
    # matched back by index, never by string equality — the model restates
    # claims in its own words and exact-match would silently drop verdicts.
    claim_index: int
    claim: str
    verdict: Literal["verified", "dubious", "blocked"]
    form_number: str
    remark: str


class Vote(Strict):
    critter: str
    vote: Literal["aye", "nay", "abstain"]
    because: str


# --- one turn of speech per critter ---------------------------------------------


class ScoutTurn(Strict):
    plan: str
    cunning_rating: int
    queries: list[str]


class OwlTurn(Strict):
    quip: str
    findings: list[Finding]
    contradictions: list[Clash]


class BuzzTurn(Strict):
    quip: str
    verdicts: list[Verdict]


class ChairTurn(Strict):
    remark: str


class VoteTurn(Strict):
    votes: list[Vote]


# --- the graph state -------------------------------------------------------------


class Utterance(TypedDict):
    critter: str
    text: str


class CouncilState(TypedDict, total=False):
    """Append-only lists carry operator.add; anything that gets cleared or
    replaced is a plain key (last write wins, nodes return the full value)."""

    motion: str

    plans: Annotated[list[str], operator.add]
    sources: Annotated[list[dict], operator.add]
    digests: Annotated[list[str], operator.add]
    dead_parrots: Annotated[list[str], operator.add]
    findings: Annotated[list[dict], operator.add]
    forms: Annotated[list[dict], operator.add]
    transcript: Annotated[list[Utterance], operator.add]

    # source URLs Owlsworth has already assessed, so a fresh search sends him
    # back to work instead of the router skipping him
    analysed: Annotated[list[str], operator.add]

    # INDICES into `findings` that Buzzwick has ruled on. Indices, not claim
    # text: `findings` is append-only so an index is a stable identity, whereas
    # two findings can carry identical claim text — and when they did, the
    # membership test found the text already assessed while the length test said
    # otherwise, so the chair and Buzzwick looped until the recursion limit.
    assessed: Annotated[list[int], operator.add]
    verified: Annotated[list[str], operator.add]

    # cleared by the inquisition, so it cannot be append-only
    contradictions: list[dict]

    minutes: str
    votes: list[dict]
    tea: int
    round: int
    inquisitions: int
    # searches that returned nothing new; stops the chair/Nigel ping-pong
    barren: int
    # turns the chair has taken; capped so a sitting cannot grow without bound
    steps: int
