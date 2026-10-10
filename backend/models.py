"""Data types for the agent team: what agents report back, run state, and the limits."""
from collections import Counter
from dataclasses import dataclass, field
from typing import Literal

from pydantic import BaseModel, Field
from pydantic_ai.usage import UsageLimits

AgentName = Literal["boss", "inventory", "accounting", "facilities", "customer_service"]
AGENT_NAMES: tuple[str, ...] = ("boss", "inventory", "accounting", "facilities", "customer_service")

# ---------- limits that keep token use in check ----------
MAX_DEPTH = 3             # boss -> specialist -> specialist -> specialist; nobody delegates past this
MAX_PAIR_REPEATS = 3      # the same agent asking the same agent a 4th time is treated as a loop
MAX_OUTPUT_TOKENS = 2500  # per model response
REQUEST_LIMIT = 100       # model calls in one board run, whole team together
TOOL_CALLS_LIMIT = 150   # tool calls in one board run, whole team together
TOTAL_TOKENS_LIMIT = 400_000


def usage_limits() -> UsageLimits:
    return UsageLimits(request_limit=REQUEST_LIMIT, tool_calls_limit=TOOL_CALLS_LIMIT,
                       total_tokens_limit=TOTAL_TOKENS_LIMIT)


# ---------- what agents hand back ----------
class AgentReport(BaseModel):
    """What a specialist reports to whoever asked."""
    agent: AgentName
    answer: str = Field(description="Short, factual report in plain words, in the agent's own voice.")
    facts: list[str] = Field(default_factory=list, description="Key numbers, ids and dates the answer relies on.")
    blockers: list[str] = Field(default_factory=list, description="Anything stopping the work, such as a vendor hold or a refusal.")
    needs_human: list[str] = Field(default_factory=list, description="Anything a person must approve or decide.")


class TicketOutcome(BaseModel):
    """The boss's final summary for one ticket."""
    ticket_id: int
    status: Literal["resolved", "needs_human"]
    decision: str = Field(description="One line: the decision on this ticket.")
    who_did_what: list[str]
    money: str = Field(description="What was spent, what is waiting for human approval, what was refused.")
    needs_human: str = Field(description="Exactly what a person must decide or approve, or 'nothing'.")


class BoardOutcome(BaseModel):
    """The boss's result for the whole board."""
    priority_order: list[int] = Field(description="Ticket ids in the order the boss decided to work them.")
    priority_reasoning: str
    tickets: list[TicketOutcome]


# ---------- run state ----------
@dataclass
class RunState:
    """Shared by every agent in one board run."""
    run_id: str
    ticket_ids: list[int] = field(default_factory=list)
    pair_counts: Counter = field(default_factory=Counter)  # (caller, callee) -> times asked
    delegations: int = 0


@dataclass
class TeamDeps:
    """Per-agent context handed to the delegate tool."""
    state: RunState
    agent_name: str
    depth: int = 0
    parent: str | None = None
    chain: tuple[str, ...] = ()  # who asked whom to get here, boss first; nobody in it may be asked again
