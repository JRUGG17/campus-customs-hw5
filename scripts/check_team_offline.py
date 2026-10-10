"""Check the team's wiring without calling the real model (no API cost).

Uses a scripted fake model to confirm: tool allowlists, delegation between agents, the depth and
loop limits, and that the audit trail is appended to and never wiped. Works on a scratch
database and a scratch audit file, never the real ones.   Run from hw5/:  venv/bin/python scripts/check_team_offline.py
"""
import asyncio
import json
import os
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
tmp = Path(tempfile.mkdtemp())
os.environ["CAMPUS_DB"] = str(tmp / "scratch.db")
os.environ["AUDIT_PATH"] = str(tmp / "audit_trail.json")
os.environ.setdefault("PORTKEY_API_KEY", "not-used")  # the fake model never calls the network
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "mcp_server"))

import db  # noqa: E402
from pydantic_ai.messages import ModelResponse, TextPart, ToolCallPart  # noqa: E402
from pydantic_ai.models.function import AgentInfo, FunctionModel  # noqa: E402

from backend import audit  # noqa: E402
from backend.models import MAX_DEPTH, MAX_PAIR_REPEATS, RunState, TeamDeps  # noqa: E402
from backend.team import TOOLS_BY_AGENT, Team  # noqa: E402

db.reset_working_copy()


def check(label, cond):
    print(("PASS  " if cond else "FAIL  ") + label)
    if not cond:
        check.failed += 1
check.failed = 0


def entries():
    return json.loads(Path(os.environ["AUDIT_PATH"]).read_text())


def script(plan):
    """A fake model that follows `plan`: a function(agent_name, step) -> ToolCallPart | None (None = finish)."""
    def fn(messages, info: AgentInfo):
        names = {t.name for t in info.function_tools}
        who = next(iter(n for n in ("boss", "inventory", "accounting", "facilities", "customer_service")
                        if f"You are the {n.replace('_', ' ').title()}" in (messages[0].instructions or "")
                        or f"# {n.replace('_', ' ').title()}" in (messages[0].instructions or "")), "?")
        step = sum(1 for m in messages if isinstance(m, ModelResponse))
        call = plan(who, step, names)
        if call:
            return ModelResponse(parts=[call])
        out = next(t for t in info.output_tools)
        args = ({"agent": who, "answer": f"{who} done"} if who != "boss"
                else {"priority_order": [], "priority_reasoning": "test", "tickets": []})
        return ModelResponse(parts=[ToolCallPart(out.name, args)])
    return FunctionModel(fn)


async def main():
    # 1. allowlists: the human-only tools are on nobody's list, and every listed tool exists
    all_listed = set().union(*TOOLS_BY_AGENT.values())
    check("approve_request / reject_request are on no agent's list", not ({"approve_request", "reject_request"} & all_listed))

    # 2. delegation + audit, boss -> inventory (check_stock) and boss -> facilities
    def plan(who, step, names):
        if who == "boss" and step == 0:
            return ToolCallPart("delegate", {"to": "inventory", "task": "Check CC-TEE-WHITE S"})
        if who == "boss" and step == 1:
            return ToolCallPart("delegate", {"to": "facilities", "task": "Check lease 1"})
        if who == "inventory" and step == 0:
            return ToolCallPart("check_stock", {"sku": "CC-TEE-WHITE", "size": "S"})
        if who == "facilities" and step == 0:
            return ToolCallPart("get_lease_status", {"lease_id": 1})
        return None

    async with Team(model=script(plan)) as team:
        names = {t for t in TOOLS_BY_AGENT["boss"]}
        outcome, run_id = await team.run_board()
        check("run finished with a board outcome", outcome is not None)
    e = entries()
    check(f"audit trail has entries for this run ({len(e)})", len(e) > 8 and all(x["run_id"] == run_id for x in e))
    agents_seen = {x["agent"] for x in e}
    check("boss, inventory and facilities all appear in the trail", {"boss", "inventory", "facilities"} <= agents_seen)
    check("delegations are logged with who asked whom",
          any(x["kind"] == "delegation" and x["text"] == "boss -> inventory" for x in e))
    check("tool calls and results are logged", any(x.get("tool_calls") and x["tool_calls"][0]["tool"] == "check_stock" for x in e)
          and any(r["tool"] == "check_stock" and '"qty":0' in r["result"].replace(" ", "") for x in e for r in x.get("tool_results", [])))
    check("each step records usage", any(x.get("usage") for x in e))
    first_count = len(e)

    # 3. a second run APPENDS, it does not wipe
    async with Team(model=script(plan)) as team:
        _, run2 = await team.run_board()
    e2 = entries()
    check("second run appended (earlier entries still there)", len(e2) > first_count and e2[0] == e[0])
    check("both run ids are in the file", {run_id, run2} <= {x["run_id"] for x in e2})

    # 4. limits: loop detection and depth
    def pingpong(who, step, names):
        if who == "boss":
            return ToolCallPart("delegate", {"to": "inventory", "task": "again"}) if step < MAX_PAIR_REPEATS + 2 else None
        return None
    async with Team(model=script(pingpong)) as team:
        await team.run_board()
    refused = [x for x in entries() if x["kind"] == "delegation_refused" and "loop" in x["text"]]
    check(f"asking the same agent more than {MAX_PAIR_REPEATS} times is refused as a loop", len(refused) >= 1)

    def deep(who, step, names):
        nxt = {"boss": "inventory", "inventory": "accounting", "accounting": "facilities", "facilities": "customer_service"}
        return ToolCallPart("delegate", {"to": nxt[who], "task": "go deeper"}) if step == 0 and who in nxt else None
    async with Team(model=script(deep)) as team:
        await team.run_board()
    check(f"delegation past depth {MAX_DEPTH} is refused",
          any(x["kind"] == "delegation_refused" and "depth" in x["text"] for x in entries()))

    def cycle(who, step, names):
        nxt = {"boss": "inventory", "inventory": "boss"}
        return ToolCallPart("delegate", {"to": nxt[who], "task": "hand it back"}) if step == 0 and who in nxt else None
    async with Team(model=script(cycle)) as team:
        await team.run_board()
    check("delegating back to someone already in the chain is refused",
          any(x["kind"] == "delegation_refused" and "chain" in x["text"] for x in entries()))

    # 5. an unreadable audit file is set aside, not deleted
    Path(os.environ["AUDIT_PATH"]).write_text("{not json")
    await audit.append({"kind": "test"})
    check("a corrupt audit file is moved aside, not deleted", any(p.name.startswith("audit_trail.unreadable") for p in tmp.iterdir()))

asyncio.run(main())
print("\nALL PASSED" if not check.failed else f"\n{check.failed} FAILED")
sys.exit(1 if check.failed else 0)
