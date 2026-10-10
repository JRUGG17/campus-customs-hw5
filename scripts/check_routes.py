"""Check every backend route without calling the real model (no API cost).

Runs the FastAPI app in-process on a scratch database and scratch audit file, with a fake model
standing in for the agents. Run from hw5/:  venv/bin/python scripts/check_routes.py
"""
import os
import sys
import tempfile
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
tmp = Path(tempfile.mkdtemp())
os.environ["CAMPUS_DB"] = str(tmp / "scratch.db")
os.environ["AUDIT_PATH"] = str(tmp / "audit_trail.json")
os.environ.setdefault("PORTKEY_API_KEY", "not-used")
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "mcp_server"))

import db  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402
from pydantic_ai.messages import ModelResponse, ToolCallPart  # noqa: E402
from pydantic_ai.models.function import FunctionModel  # noqa: E402

from backend import main  # noqa: E402
from backend.team import Team  # noqa: E402

db.reset_working_copy()
original_hash = os.popen(f'shasum "{db.ORIGINAL}"').read().split()[0]


def check(label, cond):
    print(("PASS  " if cond else "FAIL  ") + label)
    if not cond:
        check.failed += 1
check.failed = 0


def fake_model():
    """Boss asks Accounting to prepare the rent payment; Accounting does it. No network."""
    def fn(messages, info):
        text = messages[0].instructions or ""
        who = "boss" if "# Boss" in text else "accounting" if "# Accounting" in text else "other"
        step = sum(1 for m in messages if isinstance(m, ModelResponse))
        first = str(messages[0].parts[0].content) if messages[0].parts else ""
        if who == "boss" and first.startswith("Follow-up"):
            tid = int(first.split("ticket ")[1].split(".")[0])
            if step == 0:
                return ModelResponse(parts=[ToolCallPart("set_ticket_status", {"ticket_id": tid, "status": "resolved", "summary": "Settled by a human."})])
            return ModelResponse(parts=[ToolCallPart(info.output_tools[0].name, {
                "priority_order": [tid], "priority_reasoning": "closing out",
                "tickets": [{"ticket_id": tid, "status": "resolved", "decision": "Closed", "who_did_what": [], "money": "settled", "needs_human": "nothing"}]})])
        if who == "boss" and step == 0:
            return ModelResponse(parts=[ToolCallPart("delegate", {"to": "accounting", "task": "Prepare rent for lease 1, ticket 102"})])
        if who == "boss" and step == 1:
            return ModelResponse(parts=[ToolCallPart("set_ticket_status", {"ticket_id": 102, "status": "needs_human", "summary": "Rent payment waiting for a human."})])
        if who == "accounting" and step == 0:
            return ModelResponse(parts=[ToolCallPart("request_approval", {"kind": "rent_payment", "ref_id": 1, "ticket_id": 102})])
        out = info.output_tools[0]
        args = ({"agent": "accounting", "answer": "Prepared."} if who != "boss" else
                {"priority_order": [102], "priority_reasoning": "rent first",
                 "tickets": [{"ticket_id": 102, "status": "needs_human", "decision": "Rent prepared", "who_did_what": ["Accounting"],
                              "money": "$2,400 waiting", "needs_human": "Approve rent"}]})
        return ModelResponse(parts=[ToolCallPart(out.name, args)])
    return FunctionModel(fn)


main.make_team = lambda: Team(model=fake_model())

with TestClient(main.app) as c:
    # tickets
    r = c.get("/api/tickets").json()
    check("GET /api/tickets: three tickets, all open", [t["id"] for t in r["tickets"]] == [101, 102, 103] and all(t["open"] for t in r["tickets"]))
    check("GET /api/tickets/102: detail with drafts list", c.get("/api/tickets/102").json()["drafts"] == [])
    check("GET /api/tickets/999: 404", c.get("/api/tickets/999").status_code == 404)

    # cash
    check("GET /api/cash: checking is 3400", c.get("/api/cash").json()["balance"] == 3400)

    # run
    check("run unknown ticket: 404", c.post("/api/tickets/999/run").status_code == 404)
    r = c.post("/api/tickets/102/run")
    check("POST /api/tickets/102/run: 202 with a run id", r.status_code == 202 and r.json()["status"] == "running")
    run_id = r.json()["run_id"]
    check("a second run while one is going: 409", c.post("/api/tickets/101/run").status_code == 409 or c.get(f"/api/runs/{run_id}").json()["status"] != "running")
    for _ in range(100):
        info = c.get(f"/api/runs/{run_id}").json()
        if info["status"] != "running":
            break
        time.sleep(0.2)
    check("GET /api/runs/{id}: finished with an outcome", info["status"] == "finished" and info["outcome"]["tickets"][0]["ticket_id"] == 102)
    main.app.state.runs.clear()   # pretend the server restarted
    again = c.get(f"/api/runs/{run_id}").json()
    check("after a restart, the run and its outcome are rebuilt from the audit trail",
          again["status"] == "finished" and again["ticket_id"] == 102 and again["outcome"]["tickets"][0]["ticket_id"] == 102)
    check("ticket 102 is no longer open", [t for t in c.get("/api/tickets").json()["tickets"] if t["id"] == 102][0]["status"] == "needs_human")
    check("re-running a ticket that isn't open: 409", c.post("/api/tickets/102/run").status_code == 409)

    # events
    ev = c.get("/api/events").json()
    check("GET /api/events: has events with headlines and ticket ids", ev["total"] > 5 and all("headline" in e for e in ev["events"]) and 102 in ev["events"][0]["tickets"])
    check("events show the delegation and the tool used",
          any(e["kind"] == "delegation" and e["headline"] == "boss -> accounting" for e in ev["events"])
          and any("request_approval" in e["headline"] for e in ev["events"]))
    nxt = ev["next_after"]
    check("refresh with after=next_after returns nothing new", c.get(f"/api/events?after={nxt}").json()["events"] == [])
    check("filter by run_id and agent works", all(e["agent"] == "accounting" for e in c.get(f"/api/events?run_id={run_id}&agent=accounting").json()["events"]))
    check("filter by ticket_id works", c.get("/api/events?ticket_id=101").json()["events"] == [])

    # approvals: agents only prepared it, no money has moved
    ap = c.get("/api/approvals").json()["approvals"]
    check("GET /api/approvals: rent prepared and pending", len(ap) == 1 and ap[0]["status"] == "pending" and ap[0]["amount"] == 2400)
    check("cash unchanged before a human approves", c.get("/api/cash").json()["balance"] == 3400)
    check("approve with an agent's name: 400", c.post(f"/api/approvals/{ap[0]['id']}/approve", json={"approved_by": "accounting"}).status_code == 400)
    check("approve with no name: 422", c.post(f"/api/approvals/{ap[0]['id']}/approve", json={}).status_code == 422)
    check("cash still unchanged", c.get("/api/cash").json()["balance"] == 3400)
    r = c.post(f"/api/approvals/{ap[0]['id']}/approve", json={"approved_by": "Jamie Ruggiero"})
    check("POST approve: pays rent, balance 3400 -> 1000", r.status_code == 200 and r.json()["balance_after"] == 1000)
    check("GET /api/cash now 1000", c.get("/api/cash").json()["balance"] == 1000)
    check("approving again: 409 already paid", c.post(f"/api/approvals/{ap[0]['id']}/approve", json={"approved_by": "Jamie Ruggiero"}).status_code == 409)

    # a payment the cash can't cover is refused, and stays approved-but-unpaid
    import asyncio
    from fastmcp import Client
    async def prepare_big():
        async with Client(main.mcp_transport()) as cl:
            await cl.call_tool("request_approval", {"kind": "invoice_payment", "ref_id": 501})
            await cl.call_tool("approve_request", {"approval_id": 2, "approved_by": "Jamie Ruggiero"})
            await cl.call_tool("pay_approved_request", {"approval_id": 2})
            po = (await cl.call_tool("create_purchase_order", {"vendor_id": 1, "sku": "CC-HOOD-NAVY", "size": "M", "qty": 40})).structured_content
            return (await cl.call_tool("request_approval", {"kind": "purchase_order", "ref_id": po["purchase_order_id"]})).structured_content
    big = asyncio.run(prepare_big())
    r = c.post(f"/api/approvals/{big['approval_id']}/approve", json={"approved_by": "Jamie Ruggiero"})
    check("approve a payment the cash can't cover: 409 refused", r.status_code == 409 and "not enough cash" in r.json()["detail"]["error"])
    kinds = [(e["kind"], e.get("human")) for e in c.get("/api/events?limit=500").json()["events"] if e["agent"] == "human"]
    check("the audit trail records the human's approval, the payment, and the refused payment",
          ("human_approved", "Jamie Ruggiero") in kinds and ("payment_made", "Jamie Ruggiero") in kinds and ("payment_refused", "Jamie Ruggiero") in kinds)
    check("balance never negative", c.get("/api/cash").json()["balance"] == 160)
    check("refused one is 'approved' but unpaid", [a for a in c.get("/api/approvals").json()["approvals"] if a["id"] == big["approval_id"]][0]["status"] == "approved")

    # reject
    async def prepare_rent_again():
        async with Client(main.mcp_transport()) as cl:
            po = (await cl.call_tool("create_purchase_order", {"vendor_id": 1, "sku": "CC-TEE-WHITE", "size": "S", "qty": 1})).structured_content
            return (await cl.call_tool("request_approval", {"kind": "purchase_order", "ref_id": po["purchase_order_id"]})).structured_content
    again = asyncio.run(prepare_rent_again())
    cash_before = c.get("/api/cash").json()["balance"]
    r = c.post(f"/api/approvals/{again['approval_id']}/reject", json={"rejected_by": "Jamie Ruggiero"})
    check("POST reject: rejected, no money moves", r.status_code == 200 and c.get("/api/cash").json()["balance"] == cash_before)
    check("the audit trail records the decline", ("human_declined", "Jamie Ruggiero") in [(e["kind"], e.get("human")) for e in c.get("/api/events?limit=500").json()["events"] if e["agent"] == "human"])
    check("approving a rejected request: 409", c.post(f"/api/approvals/{again['approval_id']}/approve", json={"approved_by": "Jamie Ruggiero"}).status_code == 409)
    # a human can decline a slip that was approved but refused for lack of cash
    r = c.post(f"/api/approvals/{big['approval_id']}/reject", json={"rejected_by": "Jamie Ruggiero"})
    check("decline an approved-but-refused slip: 200", r.status_code == 200 and r.json()["status"] == "rejected")

    # close-out: the boss re-checks a ticket after the human acted
    check("close-out on an open ticket: 409", c.post("/api/tickets/103/closeout").status_code == 409)
    async def make_waiting():
        async with Client(main.mcp_transport()) as cl:
            await cl.call_tool("set_ticket_status", {"ticket_id": 101, "status": "needs_human", "summary": "waiting"})
            po = (await cl.call_tool("create_purchase_order", {"vendor_id": 1, "sku": "CC-TEE-WHITE", "size": "S", "qty": 1, "ticket_id": 101})).structured_content
            return (await cl.call_tool("request_approval", {"kind": "purchase_order", "ref_id": po["purchase_order_id"], "ticket_id": 101})).structured_content
    waiting = asyncio.run(make_waiting())
    check("close-out with a slip still waiting: 409", c.post("/api/tickets/101/closeout").status_code == 409)
    c.post(f"/api/approvals/{waiting['approval_id']}/reject", json={"rejected_by": "Jamie Ruggiero"})
    r = c.post("/api/tickets/101/closeout")
    check("close-out once every slip is decided: 202", r.status_code == 202)
    rid = r.json()["run_id"]
    for _ in range(100):
        info = c.get(f"/api/runs/{rid}").json()
        if info["status"] != "running":
            break
        time.sleep(0.2)
    check("close-out run finishes and the boss resolves the ticket",
          info["status"] == "finished" and [t for t in c.get("/api/tickets").json()["tickets"] if t["id"] == 101][0]["status"] == "resolved")
    async def waiting_again():
        async with Client(main.mcp_transport()) as cl:
            await cl.call_tool("set_ticket_status", {"ticket_id": 101, "status": "needs_human", "summary": "waiting again"})
    asyncio.run(waiting_again())
    check("a decision note without a name: 400", c.post("/api/tickets/101/closeout", json={"note": "No discount."}).status_code == 400)
    check("a decision note from an agent: 400", c.post("/api/tickets/101/closeout", json={"note": "No discount.", "decided_by": "boss"}).status_code == 400)
    r = c.post("/api/tickets/101/closeout", json={"note": "No discount. List price stands.", "decided_by": "Jamie Ruggiero"})
    check("close-out with the human's decision: 202", r.status_code == 202)
    rid2 = r.json()["run_id"]
    for _ in range(100):
        if c.get(f"/api/runs/{rid2}").json()["status"] != "running":
            break
        time.sleep(0.2)
    start = [e for e in c.get(f"/api/events?run_id={rid2}").json()["events"] if e["kind"] == "run_start"][0]
    check("the human's words and name are recorded in the audit trail",
          "No discount. List price stands." in start["text"] and "Jamie Ruggiero" in start["text"])
    check("the close-out run is in the audit trail",
          any(e["kind"] == "run_start" and e["text"].startswith("Follow-up") for e in c.get(f"/api/events?run_id={rid}").json()["events"]))

    # reset
    before = c.get("/api/events").json()["total"]
    r = c.post("/api/reset")
    check("POST /api/reset: ok", r.status_code == 200 and r.json()["ok"])
    check("after reset cash is 3400 and all tickets open again", c.get("/api/cash").json()["balance"] == 3400 and all(t["open"] for t in c.get("/api/tickets").json()["tickets"]))
    check("after reset no approvals or payments", c.get("/api/approvals").json() == {"approvals": [], "payments_made": []})
    check("reset keeps the audit trail (and adds a reset marker)", c.get("/api/events").json()["total"] == before + 1)
    check("since_reset shows nothing from before the reset", c.get("/api/events?since_reset=true").json()["events"] == [])
    check("without since_reset the old events are still there", len(c.get("/api/events?limit=500").json()["events"]) > 10)
    check("original database untouched", os.popen(f'shasum "{db.ORIGINAL}"').read().split()[0] == original_hash)

print("\nALL PASSED" if not check.failed else f"\n{check.failed} FAILED")
sys.exit(1 if check.failed else 0)
