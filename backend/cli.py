"""Command line for the Campus Customs team.   Run from hw5/:  venv/bin/python -m backend.cli <command>

  reset                 restore data/campus_customs_new.db from the original, add the extra tables
  run [ticket ids...]   run the boss over the open tickets (reset first for a clean run!)
  approvals             show requests waiting for a human, and the payments made
  approve ID --by NAME  a human approves a request (an agent name is refused)
  reject ID --by NAME   a human rejects a request
  pay ID                make an approved payment (refuses without approval or without cash)
"""
import argparse
import asyncio
import json
import sys

from . import audit
from .team import HW_DIR, Team, human_call

sys.path.insert(0, str(HW_DIR / "mcp_server"))
import db  # noqa: E402


def show(obj) -> None:
    print(json.dumps(obj, indent=2, default=str))


async def main() -> None:
    p = argparse.ArgumentParser(prog="backend.cli", description=__doc__, formatter_class=argparse.RawTextHelpFormatter)
    sub = p.add_subparsers(dest="cmd", required=True)
    sub.add_parser("reset")
    run = sub.add_parser("run")
    run.add_argument("tickets", nargs="*", type=int)
    sub.add_parser("approvals")
    for name in ("approve", "reject"):
        s = sub.add_parser(name)
        s.add_argument("id", type=int)
        s.add_argument("--by", required=True, help="the human's name")
    pay = sub.add_parser("pay")
    pay.add_argument("id", type=int)
    a = p.parse_args()

    if a.cmd == "reset":
        print(f"Reset {db.reset_working_copy()} from the original {db.ORIGINAL}")
        # Same marker the dashboard's reset writes, so the board shows only what happens after it.
        await audit.append({"run_id": "-", "tickets": [], "agent": "backend", "depth": 0, "kind": "database_reset",
                            "text": "Database reset to the original values. Starting a fresh day."})
    elif a.cmd == "run":
        async with Team() as team:
            outcome, run_id = await team.run_board(a.tickets or None)
        print(f"run_id {run_id}")
        show(outcome.model_dump() if outcome else "Stopped by a usage limit. See the audit trail.")
    elif a.cmd == "approvals":
        show(await human_call("list_approvals"))
    elif a.cmd == "approve":
        show(await human_call("approve_request", approval_id=a.id, approved_by=a.by))
    elif a.cmd == "reject":
        show(await human_call("reject_request", approval_id=a.id, rejected_by=a.by))
    elif a.cmd == "pay":
        show(await human_call("pay_approved_request", approval_id=a.id))


if __name__ == "__main__":
    asyncio.run(main())
