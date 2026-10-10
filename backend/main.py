"""FastAPI backend for the Campus Customs dashboard.

Start it from this folder:   uvicorn main:app --reload --port 8000

All shop facts and changes go through the MCP server (the same tools the agents use), so
there is no second tools layer here. The one thing that moves cash is the approve route: agents
only prepare payments, and a human clicking approve is what makes a payment happen.
"""
import asyncio
import json
import sys
import uuid
from contextlib import asynccontextmanager
from datetime import datetime, timezone
from pathlib import Path

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastmcp import Client
from pydantic import BaseModel, Field

HW_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(HW_DIR))                  # so `backend.*` imports work from this folder
sys.path.insert(0, str(HW_DIR / "mcp_server"))   # for db.reset_working_copy

import db  # noqa: E402
from backend import audit  # noqa: E402
from backend.team import Team, mcp_transport  # noqa: E402


def make_team() -> Team:
    """One place to build a team (tests swap this for a fake model)."""
    return Team()


@asynccontextmanager
async def lifespan(app: FastAPI):
    app.state.mcp = Client(mcp_transport())
    app.state.runs = {}          # run_id -> status dict (in memory)
    app.state.active = None      # run_id of the run in progress, if any
    async with app.state.mcp:
        yield


app = FastAPI(title="Campus Customs operations", lifespan=lifespan)
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:5173", "http://127.0.0.1:5173", "http://localhost:3000", "http://127.0.0.1:3000"],
    allow_methods=["*"],
    allow_headers=["*"],
)


async def tool(name: str, **args) -> dict:
    """Call one MCP tool and return its result."""
    try:
        result = await app.state.mcp.call_tool(name, args, raise_on_error=False)
    except Exception as exc:
        raise HTTPException(502, f"MCP server error: {type(exc).__name__}") from exc
    if result.is_error or result.structured_content is None:
        raise HTTPException(502, f"MCP tool {name} failed")
    return result.structured_content


# ------------------------------------------------------------------ tickets

@app.get("/api/tickets")
async def get_tickets():
    """The tickets on the board and whether each is open, resolved, or needs a human."""
    data = await tool("list_tickets", status="all")
    tickets = [{"id": t["id"], "type": t["type"], "requester": t["requester"], "subject": t["subject"],
                "status": t["status"], "open": t["status"] == "open", "created_at": t["created_at"]}
               for t in data["tickets"]]
    active = app.state.active
    return {"today": data["today"], "tickets": tickets,
            "running": app.state.runs[active] if active else None}


@app.get("/api/tickets/{ticket_id}")
async def get_ticket_detail(ticket_id: int):
    """One ticket in full, with any customer drafts (never sent) and the boss's summary."""
    t = await tool("get_ticket", ticket_id=ticket_id)
    if "error" in t:
        raise HTTPException(404, t["error"])
    return t


# ------------------------------------------------------------------ running the team

class RunTask:
    """Runs the agent team on one ticket in the background and records how it went."""

    @staticmethod
    async def go(run_id: str, ticket_id: int, followup: bool = False, human_note: str | None = None,
                 decided_by: str | None = None) -> None:
        info = app.state.runs[run_id]
        try:
            async with make_team() as team:
                outcome, _ = await team.run_board([ticket_id], run_id=run_id, followup=followup,
                                                  human_note=human_note, decided_by=decided_by)
            if outcome is None:
                info.update(status="stopped", error="Stopped by a usage limit. See the events.")
            else:
                info.update(status="finished", outcome=outcome.model_dump())
        except Exception as exc:  # report it; never leave a run stuck as "running"
            info.update(status="error", error=f"{type(exc).__name__}: {exc}"[:300])
            await audit.append({"run_id": run_id, "tickets": [ticket_id], "agent": "backend", "depth": 0,
                                "kind": "run_error", "text": info["error"]})
        finally:
            info["finished_at"] = datetime.now(timezone.utc).isoformat(timespec="seconds")
            app.state.active = None


@app.post("/api/tickets/{ticket_id}/run", status_code=202)
async def run_ticket(ticket_id: int):
    """Start the agent team on one open ticket. Returns at once with a run id; poll the events."""
    if app.state.active:
        raise HTTPException(409, f"Run {app.state.active} is still in progress. Wait for it to finish.")
    t = await tool("get_ticket", ticket_id=ticket_id)
    if "error" in t:
        raise HTTPException(404, t["error"])
    if t["status"] != "open":
        raise HTTPException(409, f"Ticket {ticket_id} is '{t['status']}', not open. Reset the database for a fresh run.")
    run_id = uuid.uuid4().hex[:8]
    app.state.runs[run_id] = {"run_id": run_id, "ticket_id": ticket_id, "status": "running",
                              "started_at": datetime.now(timezone.utc).isoformat(timespec="seconds")}
    app.state.active = run_id
    asyncio.create_task(RunTask.go(run_id, ticket_id))
    return app.state.runs[run_id]


class Closeout(BaseModel):
    note: str | None = Field(default=None, max_length=500, description="The human's decision, in their own words")
    decided_by: str | None = Field(default=None, max_length=40, description="The human's name, required with a note")


@app.post("/api/tickets/{ticket_id}/closeout", status_code=202)
async def closeout_ticket(ticket_id: int, body: Closeout | None = None):
    """After a human has approved, paid or declined slips, have the boss re-check the ticket and close it.

    The boss resolves the ticket if everything is settled, or prepares any work the payment unblocked
    (for example an order from a vendor that is no longer on hold). Only for tickets waiting on a human,
    and only once no slip for the ticket is still waiting for a signature. A human can pass their decision
    in words (`note`, with their name in `decided_by`), such as "No discount. List price stands." The boss
    acts on it and the note is recorded in the audit trail.
    """
    note = (body.note or "").strip() if body else ""
    by = (body.decided_by or "").strip() if body else ""
    if note and len(by) < 2:
        raise HTTPException(400, "Type your name to go with your decision.")
    if note and by.lower().replace(" ", "_") in ("boss", "inventory", "accounting", "facilities", "customer_service"):
        raise HTTPException(400, "A decision has to come from a human, not an agent.")
    if app.state.active:
        raise HTTPException(409, f"Run {app.state.active} is still in progress. Wait for it to finish.")
    t = await tool("get_ticket", ticket_id=ticket_id)
    if "error" in t:
        raise HTTPException(404, t["error"])
    if t["status"] != "needs_human":
        raise HTTPException(409, f"Ticket {ticket_id} is '{t['status']}'. Only a ticket waiting on a human can be closed out.")
    waiting = [a for a in (await tool("list_approvals"))["approvals"]
               if a["ticket_id"] == ticket_id and a["status"] in ("pending", "approved")]
    if waiting:
        raise HTTPException(409, f"{len(waiting)} slip(s) for ticket {ticket_id} are still waiting for a human decision.")
    run_id = uuid.uuid4().hex[:8]
    app.state.runs[run_id] = {"run_id": run_id, "ticket_id": ticket_id, "status": "running", "followup": True,
                              "started_at": datetime.now(timezone.utc).isoformat(timespec="seconds")}
    app.state.active = run_id
    asyncio.create_task(RunTask.go(run_id, ticket_id, followup=True, human_note=note or None, decided_by=by or None))
    return app.state.runs[run_id]


def run_from_audit(run_id: str) -> dict | None:
    """Rebuild a finished run's status and outcome from the audit trail (it is never wiped)."""
    path = audit.AUDIT_PATH
    if not path.exists():
        return None
    try:
        entries = [e for e in json.loads(path.read_text()) if e.get("run_id") == run_id]
    except ValueError:
        return None
    start = next((e for e in entries if e.get("kind") == "run_start"), None)
    if start is None:
        return None
    info: dict = {"run_id": run_id, "ticket_id": (start.get("tickets") or [None])[0], "status": "running",
                  "started_at": start["timestamp"], "followup": str(start.get("text", "")).startswith("Follow-up")}
    end = next((e for e in entries if e.get("kind") == "run_end"), None)
    if end:
        info.update(status="finished", finished_at=end["timestamp"])
        try:
            info["outcome"] = json.loads(end["text"])
        except ValueError:
            pass
    for e in entries:
        if e.get("kind") in ("run_error", "run_stopped"):
            info.update(status="error" if e["kind"] == "run_error" else "stopped", error=e.get("text"))
    return info


@app.get("/api/runs/{run_id}")
async def get_run(run_id: str):
    """Is a run still going, and what was its outcome?"""
    info = app.state.runs.get(run_id)
    if info is None:
        info = run_from_audit(run_id)   # the server restarted since: rebuild it from the audit trail
    if info is None:
        raise HTTPException(404, f"No run {run_id}")
    return info


# ------------------------------------------------------------------ events (the audit trail)

def headline(e: dict) -> str:
    """A one-line description of an audit entry, for the dashboard feed."""
    kind = e.get("kind")
    if kind == "model_response":
        calls = e.get("tool_calls") or []
        if calls:
            return "calls " + ", ".join(
                f"delegate({c['args'].get('to')})" if c["tool"] == "delegate" else c["tool"] for c in calls)
        return e.get("text") or "replied"
    if kind == "tool_results":
        return "got results from " + ", ".join(r["tool"] for r in e.get("tool_results", []))
    if kind in ("delegation", "delegation_refused", "run_error", "run_stopped", "database_reset",
                "human_approved", "human_declined", "payment_made", "payment_refused"):
        return e.get("text", kind)
    if kind == "prompt":
        return "was asked: " + (e.get("text") or "")[:160]
    if kind == "final":
        return "gave a final report"
    return kind or "event"


@app.get("/api/events")
async def get_events(limit: int = 100, after: int | None = None, run_id: str | None = None,
                     ticket_id: int | None = None, agent: str | None = None, since_reset: bool = False):
    """Recent agent events: what each agent said, which tools it used, and who delegated to whom.

    Without `after`, returns the latest `limit` events. To refresh, pass back `next_after` from
    the last response as `after` and you get only what is new. With `since_reset=true`, only events
    after the last database reset are returned (the trail itself is never cleared).
    """
    path = audit.AUDIT_PATH
    entries: list = []
    if path.exists() and path.stat().st_size > 0:
        try:
            entries = json.loads(path.read_text())
        except ValueError:
            entries = []
    seq = [{"seq": i, "headline": headline(e), **e} for i, e in enumerate(entries)]
    if since_reset:
        marks = [e["seq"] for e in seq if e.get("kind") == "database_reset"]
        if marks:
            seq = [e for e in seq if e["seq"] > marks[-1]]
    picked = [e for e in seq
              if (run_id is None or e.get("run_id") == run_id)
              and (ticket_id is None or ticket_id in e.get("tickets", []))
              and (agent is None or e.get("agent") == agent)]
    limit = max(1, min(limit, 500))
    picked = [e for e in picked if e["seq"] >= after][:limit] if after is not None else picked[-limit:]
    return {"total": len(entries), "next_after": len(entries), "events": picked}


# ------------------------------------------------------------------ approvals (the only route that moves cash)

class Approve(BaseModel):
    approved_by: str = Field(min_length=2, description="The human's name")


class Reject(BaseModel):
    rejected_by: str = Field(min_length=2, description="The human's name")


@app.get("/api/approvals")
async def get_approvals(status: str = ""):
    """Payments and purchase orders the agents prepared, waiting for (or past) a human decision."""
    return await tool("list_approvals", status=status)


async def log_human(kind: str, a: dict, who: str, text: str, **extra) -> None:
    """Record a human's action in the audit trail, so it survives a database reset."""
    await audit.append({"run_id": "-", "tickets": [a["ticket_id"]] if a.get("ticket_id") else [], "agent": "human", "depth": 0,
                        "kind": kind, "text": text, "human": who, "approval_id": a["id"], "approval_kind": a["kind"],
                        "amount": a["amount"], **extra})


async def find_approval(approval_id: int) -> dict:
    for a in (await tool("list_approvals"))["approvals"]:
        if a["id"] == approval_id:
            return a
    raise HTTPException(404, f"No approval with id {approval_id}")


@app.post("/api/approvals/{approval_id}/approve")
async def approve(approval_id: int, body: Approve):
    """A human approves a prepared payment or purchase order. This is what actually pays it.

    Records the human's approval, then makes the payment, which lowers checking and updates the
    invoice, rent or order. If the payment is refused (not enough cash, vendor still on hold),
    nothing is paid, the approval stays recorded, and you get the reason.
    """
    a = await find_approval(approval_id)
    if a["status"] == "executed":
        raise HTTPException(409, f"Approval {approval_id} was already paid")
    if a["status"] == "rejected":
        raise HTTPException(409, f"Approval {approval_id} was rejected")
    if a["status"] == "pending":
        decided = await tool("approve_request", approval_id=approval_id, approved_by=body.approved_by)
        if not decided["ok"]:
            raise HTTPException(400, decided["error"])
        await log_human("human_approved", a, body.approved_by,
                        f"{body.approved_by} approved: {a['description']} ({a['amount']:.2f})")
    paid = await tool("pay_approved_request", approval_id=approval_id)
    if not paid["ok"]:
        await log_human("payment_refused", a, body.approved_by, paid["error"], paid=False)
        raise HTTPException(409, {"error": paid["error"], "approval_status": "approved", "paid": False})
    await log_human("payment_made", a, paid["approved_by"],
                    f"Paid {a['amount']:.2f}: {a['description']}. Checking is now {paid['balance_after']:.2f}.",
                    paid=True, balance_after=paid["balance_after"])
    return {"approval_id": approval_id, "approved_by": paid["approved_by"], "paid": paid["paid"],
            "kind": paid["kind"], "balance_after": paid["balance_after"]}


@app.post("/api/approvals/{approval_id}/reject")
async def reject(approval_id: int, body: Reject):
    """A human declines a prepared payment or purchase order (pending, or approved but refused). Nothing is paid."""
    a = await find_approval(approval_id)
    result = await tool("reject_request", approval_id=approval_id, rejected_by=body.rejected_by)
    if not result["ok"]:
        raise HTTPException(400, result["error"])
    await log_human("human_declined", a, body.rejected_by, f"{body.rejected_by} declined: {a['description']} ({a['amount']:.2f})")
    return result


# ------------------------------------------------------------------ cash and reset

@app.get("/api/cash")
async def get_cash():
    """The current checking balance from cash_accounts, plus money already committed."""
    return await tool("get_cash_balance", account="checking")


@app.post("/api/reset")
async def reset():
    """Restore data/campus_customs_new.db to the original values for a fresh run.

    The original database is only read. The audit trail is NOT cleared: it is append-only.
    """
    if app.state.active:
        raise HTTPException(409, f"Run {app.state.active} is still in progress. Wait for it to finish.")
    path = db.reset_working_copy()
    app.state.runs.clear()
    await audit.append({"run_id": "-", "tickets": [], "agent": "backend", "depth": 0, "kind": "database_reset",
                        "text": "Database reset to the original values. Starting a fresh day."})
    return {"ok": True, "reset": str(path.name), "from": str(db.ORIGINAL.name),
            "note": "The audit trail was kept; only the database was reset."}
