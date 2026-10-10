"""The Campus Customs agent team: five PydanticAI agents with full connectivity.

Every agent can delegate to every other agent. All shop facts and all changes go through the
MCP server (mcp_server/mcp_server.py); there is no other tools layer here. Each agent only sees
the MCP tools on its own allowlist, and the human-only tools (approve_request, reject_request)
are on nobody's list.
"""
import json
import sys
import uuid
from dataclasses import replace
from pathlib import Path

from fastmcp import Client
from fastmcp.client.transports import StdioTransport
from pydantic_ai import Agent, RunContext
from pydantic_ai.exceptions import UsageLimitExceeded
from pydantic_ai.mcp import MCPToolset
from pydantic_ai.messages import (RetryPromptPart, TextPart, ToolCallPart, ToolReturnPart, UserPromptPart)
from pydantic_ai.settings import ModelSettings
from pydantic_ai.usage import RunUsage

from . import audit
from .llm import MODEL_NAME, make_model
from .models import (AGENT_NAMES, MAX_DEPTH, MAX_OUTPUT_TOKENS, MAX_PAIR_REPEATS, AgentName,
                     AgentReport, BoardOutcome, RunState, TeamDeps, usage_limits)

HW_DIR = Path(__file__).resolve().parent.parent
PROMPTS = Path(__file__).resolve().parent / "prompts"
MCP_SERVER = HW_DIR / "mcp_server" / "mcp_server.py"

# Which MCP tools each agent may call. approve_request and reject_request are human-only.
TOOLS_BY_AGENT: dict[str, set[str]] = {
    "boss": {"list_tickets", "get_ticket", "get_cash_balance", "list_approvals", "set_ticket_status"},
    "inventory": {"get_ticket", "check_stock", "find_vendors", "list_open_invoices"},
    "accounting": {"get_ticket", "get_cash_balance", "list_open_invoices", "get_invoice_status", "get_margin",
                   "create_purchase_order", "request_approval", "list_approvals", "pay_approved_request"},
    "facilities": {"get_ticket", "get_lease_status"},
    "customer_service": {"get_ticket", "check_stock", "get_list_price", "save_draft_reply"},
}


def mcp_transport() -> StdioTransport:
    """How to start the MCP server. Inherits CAMPUS_DB, so tests can point it at a scratch copy."""
    import os
    return StdioTransport(command=sys.executable, args=[str(MCP_SERVER)], env=dict(os.environ))


class Team:
    """Builds the five agents around one MCP connection. Use as an async context manager."""

    def __init__(self, model=None, log: bool = True):
        self.model = model or make_model()
        self.log = log
        self.toolset = MCPToolset(Client(mcp_transport()))
        self.agents: dict[str, Agent] = {name: self._build(name) for name in AGENT_NAMES}

    async def __aenter__(self):
        await self.toolset.__aenter__()
        return self

    async def __aexit__(self, *exc):
        return await self.toolset.__aexit__(*exc)

    # ------------------------------------------------------------ building
    def _build(self, name: str) -> Agent:
        allowed = TOOLS_BY_AGENT[name]
        agent = Agent(
            self.model,
            name=name,
            deps_type=TeamDeps,
            output_type=BoardOutcome if name == "boss" else AgentReport,
            instructions=(PROMPTS / f"{name}.md").read_text(),
            toolsets=[self.toolset.filtered(lambda ctx, tool_def, allowed=allowed: tool_def.name in allowed)],
            model_settings=ModelSettings(max_tokens=MAX_OUTPUT_TOKENS),
            retries=2,
        )

        @agent.tool
        async def delegate(ctx: RunContext[TeamDeps], to: AgentName, task: str) -> str:
            """Hand a task to another agent and get their report back. Any agent can ask any other.

            Say which ticket it is for, what you need, and what to report back. The task is
            logged. Only delegate for something you can't get with your own tools. Limits: delegation
            depth is capped, you can't ask anyone who is already in the chain of requests that got
            you here (report back to them instead), and asking the same agent over and over is
            treated as a loop. If you are refused, stop and say so in your report.
            """
            return await self._delegate(ctx, to, task)

        return agent

    # ------------------------------------------------------------ delegation
    async def _delegate(self, ctx: RunContext[TeamDeps], to: str, task: str) -> str:
        deps = ctx.deps
        me = deps.agent_name

        async def refuse(reason: str) -> str:
            await self._record(deps, kind="delegation_refused", text=f"{me} -> {to}: {reason}",
                               tool_calls=[{"tool": "delegate", "args": {"to": to, "task": audit.short(task)}}])
            return f"Refused: {reason}"

        if to == me:
            return await refuse("you can't delegate to yourself.")
        if to in deps.chain:
            return await refuse(f"{to} is already in this chain of requests ({' -> '.join(deps.chain)}). Answer "
                                "by returning your report to whoever asked you, don't hand the work back.")
        if deps.depth >= MAX_DEPTH:
            return await refuse(f"delegation depth limit ({MAX_DEPTH}) reached. Do it with your own tools, "
                                "or report back that it needs the boss or a human.")
        deps.state.pair_counts[(me, to)] += 1
        if deps.state.pair_counts[(me, to)] > MAX_PAIR_REPEATS:
            return await refuse(f"you have already asked {to} {MAX_PAIR_REPEATS} times. This looks like a loop. "
                                "Stop, and report that it is stuck and needs a human.")
        deps.state.delegations += 1
        await self._record(deps, kind="delegation", text=f"{me} -> {to}",
                           tool_calls=[{"tool": "delegate", "args": {"to": to, "task": audit.short(task, 1500)}}])
        child = replace(deps, agent_name=to, depth=deps.depth + 1, parent=me, chain=deps.chain + (to,))
        try:
            report = await self._run(to, f"Request from {me}:\n{task}", child, ctx.usage)
        except UsageLimitExceeded:
            raise  # the token/request budget is shared; blow the whole run, don't hide it
        except Exception as exc:  # a failed specialist shouldn't crash the board
            await self._record(child, kind="agent_error", text=f"{type(exc).__name__}: {exc}")
            return f"{to} failed and returned nothing: {type(exc).__name__}"
        report.agent = to  # the code knows who answered; don't trust the model's label
        return report.model_dump_json()

    # ------------------------------------------------------------ the loop, with audit
    async def _run(self, name: str, prompt: str, deps: TeamDeps, usage: RunUsage):
        agent = self.agents[name]
        step = 0
        async with agent.iter(prompt, deps=deps, usage=usage, usage_limits=usage_limits()) as run:
            async for node in run:
                step += 1
                await self._record_node(node, run, deps, step)
        return run.result.output

    async def _record_node(self, node, run, deps: TeamDeps, step: int) -> None:
        u = run.usage
        snap = {"requests": u.requests, "input_tokens": u.input_tokens, "output_tokens": u.output_tokens,
                "tool_calls": u.tool_calls}
        if Agent.is_user_prompt_node(node):
            prompt = node.user_prompt if isinstance(node.user_prompt, str) else "(non-text prompt)"
            await self._record(deps, kind="prompt", step=step, text=audit.short(prompt, 1500), usage=snap)
        elif Agent.is_model_request_node(node):
            results = []
            for p in node.request.parts:
                if isinstance(p, ToolReturnPart):
                    results.append({"tool": p.tool_name, "result": audit.short(p.content)})
                elif isinstance(p, RetryPromptPart):
                    results.append({"tool": p.tool_name or "output", "retry": audit.short(p.content)})
            if results:
                await self._record(deps, kind="tool_results", step=step, tool_results=results, usage=snap)
        elif Agent.is_call_tools_node(node):
            text = " ".join(p.content for p in node.model_response.parts if isinstance(p, TextPart)).strip()
            calls = [{"tool": p.tool_name, "args": p.args_as_dict()}
                     for p in node.model_response.parts if isinstance(p, ToolCallPart)]
            await self._record(deps, kind="model_response", step=step, text=audit.short(text) if text else None,
                               tool_calls=calls, usage=snap)
        elif Agent.is_end_node(node):
            await self._record(deps, kind="final", step=step, text=audit.short(node.data.output.model_dump(), 3000), usage=snap)

    async def _record(self, deps: TeamDeps, **fields) -> None:
        if not self.log:
            return
        entry = {"run_id": deps.state.run_id, "tickets": deps.state.ticket_ids, "agent": deps.agent_name, "depth": deps.depth,
                 "parent": deps.parent, "model": MODEL_NAME}
        entry.update({k: v for k, v in fields.items() if v is not None})
        await audit.append(entry)

    # ------------------------------------------------------------ entry point
    async def run_board(self, ticket_ids: list[int] | None = None, run_id: str | None = None,
                        followup: bool = False, human_note: str | None = None,
                        decided_by: str | None = None) -> tuple[BoardOutcome | None, str]:
        """One boss run over the open tickets. Returns (outcome, run_id)."""
        state = RunState(run_id=run_id or uuid.uuid4().hex[:8], ticket_ids=list(ticket_ids or []))
        deps = TeamDeps(state=state, agent_name="boss", chain=("boss",))
        scope = ("Work only these ticket ids: " + ", ".join(map(str, ticket_ids)) + "."
                 if ticket_ids else "Work every open ticket.")
        prompt = ("Read the open tickets on the board with list_tickets. " + scope +
                  " Set the priority across them, delegate the work, check the results, and close out each "
                  "ticket with set_ticket_status. Then give the board outcome.")
        if followup:
            prompt = (f"Follow-up on ticket {', '.join(map(str, ticket_ids or []))}. A human has acted since your last "
                      "run on it: they may have approved and paid slips, or declined them. Check what happened with "
                      "get_ticket and list_approvals, and the cash with get_cash_balance. Then: if every payment or "
                      "purchase for this ticket is settled (paid, or declined by a human) and nothing else is waiting on "
                      "a person, close it with set_ticket_status 'resolved' and a summary of how it ended, including what "
                      "the human decided. A ticket is resolved once everything the shop can do has been done: the money for it is "
                      "paid or declined by a human, any order with a vendor is placed, and the customer's draft reply is on "
                      "the board. Stock that is still on its way does not keep a ticket open, and neither does a question "
                      "nobody needs to answer, such as whether to cancel an order the customer never asked to cancel. "
                      "A ticket that asks for a discount is settled once its restock question is settled (the human has paid or "
                      "declined the order) and no human granted a discount: the list price stands, and that is the answer. "
                      "Resolve it with that. A human's own words, if given below, override this. "
                      "If there is work the agents can do now that they couldn't before (for example a "
                      "vendor that was on hold can now be ordered from), delegate it and prepare it for approval, and "
                      "leave the ticket as needs_human with what is left. Discounts are still only a human's decision, "
                      "and none was approved. Then give the board outcome.")
            if human_note:
                prompt += (f" The human, {decided_by}, told you their decision in these words: \"{human_note}\". "
                           "That is the human's decision. Act on it, and if it settles what was waiting on a person, "
                           "close the ticket and record the decision in your summary.")
        await self._record(deps, kind="run_start", text=prompt, usage=None)
        try:
            outcome = await self._run("boss", prompt, deps, RunUsage())
        except UsageLimitExceeded as exc:
            await self._record(deps, kind="run_stopped", text=f"Usage limit hit: {exc}. Needs a human.")
            return None, state.run_id
        await self._record(deps, kind="run_end", text=audit.short(outcome.model_dump(), 3000))
        return outcome, state.run_id


# ---------------------------------------------------------------- human steps, also through the MCP
async def human_call(tool: str, **args) -> dict:
    """Call one MCP tool as the human-side operator (approve, reject, or run a paid-for request)."""
    async with Client(mcp_transport()) as client:
        result = await client.call_tool(tool, args, raise_on_error=False)
        return result.structured_content
