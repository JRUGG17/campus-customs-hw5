"""Exercise every MCP tool and the money rules on a scratch copy of the database.

Never touches data/campus_customs_new.db: it builds its own copy in a temp folder.
Run from hw5/:  venv/bin/python scripts/check_tools.py
"""
import asyncio
import os
import sqlite3
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
scratch = Path(tempfile.mkdtemp()) / "scratch.db"
os.environ["CAMPUS_DB"] = str(scratch)
sys.path.insert(0, str(ROOT / "mcp_server"))

import db  # noqa: E402
import server as m  # noqa: E402

from fastmcp import Client  # noqa: E402

db.reset_working_copy()
original_hash = os.popen(f'shasum "{db.ORIGINAL}"').read().split()[0]


async def call(client, name, **args):
    r = await client.call_tool(name, args, raise_on_error=False)
    return r.structured_content


def q(sql, *a):
    c = sqlite3.connect(scratch)
    try:
        return c.execute(sql, a).fetchall()
    finally:
        c.close()


def check(label, cond):
    print(("PASS  " if cond else "FAIL  ") + label)
    if not cond:
        check.failed += 1
check.failed = 0


async def main():
    async with Client(m.mcp) as c:
        names = {t.name for t in await c.list_tools()}
        print(f"{len(names)} tools:", sorted(names))

        t = await call(c, "list_tickets")
        check("list_tickets: 3 open tickets, today 2026-08-31", len(t["tickets"]) == 3 and t["today"] == "2026-08-31")
        check("get_ticket 101 links invoice 501", (await call(c, "get_ticket", ticket_id=101))["invoice_id"] == 501)
        check("check_stock hoodie M = 8", (await call(c, "check_stock", sku="CC-HOOD-NAVY", size="M"))["qty"] == 8)
        v = await call(c, "find_vendors", keyword="apparel")
        check("find_vendors: apparel vendor is on hold (invoice 501)",
              v["vendors"][0]["id"] == 1 and v["vendors"][0]["on_hold"] and v["vendors"][0]["lead_days"] == 5)
        check("find_vendors: mugs vendor is not on hold",
              not (await call(c, "find_vendors", keyword="mugs"))["vendors"][0]["on_hold"])
        oi = await call(c, "list_open_invoices")
        check("list_open_invoices: 501 is 3 days overdue", oi["open_invoices"][0]["days_overdue"] == 3)
        check("get_list_price hoodie = 58", (await call(c, "get_list_price", sku="CC-HOOD-NAVY"))["list_price"] == 58)
        mg = await call(c, "get_margin", sku="CC-HOOD-NAVY")
        check("get_margin at list = $36 / 62.1%", mg["margin_dollars"] == 36 and mg["margin_percent"] == 62.1)
        check("get_margin at 40 = $18", (await call(c, "get_margin", sku="CC-HOOD-NAVY", price=40))["margin_dollars"] == 18)

        # --- vendor hold blocks a purchase order
        po = await call(c, "create_purchase_order", vendor_id=1, sku="CC-HOOD-NAVY", size="M", qty=12)
        check("create_purchase_order refused while vendor 1 is on hold", po["ok"] is False and "on hold" in po["error"])

        # --- payment needs a human
        a1 = await call(c, "request_approval", kind="invoice_payment", ref_id=501, ticket_id=101)
        check("request_approval invoice 501 = $840 pending", a1["ok"] and a1["amount"] == 840 and a1["status"] == "pending")
        dup = await call(c, "request_approval", kind="invoice_payment", ref_id=501)
        check("duplicate request returns the same approval", dup["approval_id"] == a1["approval_id"])
        p = await call(c, "pay_approved_request", approval_id=a1["approval_id"])
        check("pay refused before any human approval", p["ok"] is False and "human" in p["error"])
        bad = await call(c, "approve_request", approval_id=a1["approval_id"], approved_by="accounting")
        check("an agent name can't approve", bad["ok"] is False)
        check("still no money moved", q("select balance from cash_accounts")[0][0] == 3400 and q("select count(*) from payments")[0][0] == 0)
        ok = await call(c, "approve_request", approval_id=a1["approval_id"], approved_by="Jamie Ruggiero")
        check("human approves", ok["ok"])
        paid = await call(c, "pay_approved_request", approval_id=a1["approval_id"])
        check("pay invoice 501: balance 3400 -> 2560", paid["ok"] and paid["balance_after"] == 2560)
        check("invoice 501 now paid", q("select status from invoices where id=501")[0][0] == "paid")
        check("payments row records the human", q("select kind, ref_id, amount, approved_by from payments")[0] == ("invoice", 501, 840.0, "Jamie Ruggiero"))
        again = await call(c, "pay_approved_request", approval_id=a1["approval_id"])
        check("can't pay the same approval twice", again["ok"] is False)

        # --- vendor hold lifted, but cash gets tight
        check("vendor 1 off hold after paying 501", not (await call(c, "find_vendors", keyword="apparel"))["vendors"][0]["on_hold"])
        rent = await call(c, "request_approval", kind="rent_payment", ref_id=1, ticket_id=102)
        await call(c, "approve_request", approval_id=rent["approval_id"], approved_by="Jamie Ruggiero")
        r = await call(c, "pay_approved_request", approval_id=rent["approval_id"])
        check("pay rent: balance 2560 -> 160, next_due moves to 2026-10-02",
              r["ok"] and r["balance_after"] == 160 and q("select next_due from leases")[0][0] == "2026-10-02")
        again_rent = await call(c, "request_approval", kind="rent_payment", ref_id=1, ticket_id=102)
        check("rent already paid: a second rent slip is refused (next rent is 32 days away)",
              again_rent["ok"] is False and "isn't due yet" in again_rent["error"])
        po = await call(c, "create_purchase_order", vendor_id=1, sku="CC-HOOD-NAVY", size="M", qty=12, ticket_id=103)
        check("purchase order for 12 hoodies = $264", po["ok"] and po["total"] == 264)
        dup = await call(c, "create_purchase_order", vendor_id=1, sku="CC-HOOD-NAVY", size="M", qty=12, ticket_id=103)
        check("asking for the same purchase order again returns it, no duplicate",
              dup["ok"] and dup.get("duplicate") and dup["purchase_order_id"] == po["purchase_order_id"] and q("select count(*) from purchase_orders")[0][0] == 1)
        pa = await call(c, "request_approval", kind="purchase_order", ref_id=po["purchase_order_id"], ticket_id=103)
        check("request shows cash is short", pa["ok"] and pa["enough_cash_after_other_commitments"] is False)
        await call(c, "approve_request", approval_id=pa["approval_id"], approved_by="Jamie Ruggiero")
        pr = await call(c, "pay_approved_request", approval_id=pa["approval_id"])
        check("pay refused: not enough cash ($264 > $160)", pr["ok"] is False and "not enough cash" in pr["error"])
        check("balance still 160, never negative", q("select balance from cash_accounts")[0][0] == 160)
        check("PO still 'prepared'", q("select status from purchase_orders")[0][0] == "prepared")

        # --- drafts and ticket status
        bad = await call(c, "save_draft_reply", ticket_id=101, body="Hi Tauhid, the vendor is on hold over an unpaid invoice.")
        check("a draft that tells the customer internal matters is refused", bad["ok"] is False and "vendor" in bad["error"])
        check("nothing was saved by the refused draft", q("select count(*) from drafts")[0][0] == 0)
        d = await call(c, "save_draft_reply", ticket_id=101, body="Hi Tauhid, the tee in S is out of stock. We'll update you.")
        check("draft saved and NOT sent", d["ok"] and d["sent"] is False)
        d2 = await call(c, "save_draft_reply", ticket_id=101, body="Hi Tauhid, the tee in S is $28 and out of stock. We're arranging more.")
        check("saving again replaces the draft: still one draft per ticket",
              d2["ok"] and d2["replaced_earlier_draft"] and len((await call(c, "get_ticket", ticket_id=101))["drafts"]) == 1)
        s = await call(c, "set_ticket_status", ticket_id=102, status="resolved", summary="Rent paid with approval.")
        check("set_ticket_status resolves 102", s["ok"] and q("select status from tickets where id=102")[0][0] == "resolved")
        log = await call(c, "list_approvals")
        check("spending log: 3 approvals, 2 payments", len(log["approvals"]) == 3 and len(log["payments_made"]) == 2)
        # a human can decline an approved request that couldn't be paid
        rej_ok = await call(c, "reject_request", approval_id=pa["approval_id"], rejected_by="Jamie Ruggiero")
        check("human declines the approved-but-refused purchase order", rej_ok["ok"] and q("select status from approvals where id=?", pa["approval_id"])[0][0] == "rejected")
        check("declining a purchase order cancels it", q("select status from purchase_orders")[0][0] == "cancelled")
        redo = await call(c, "create_purchase_order", vendor_id=1, sku="CC-HOOD-NAVY", size="M", qty=12, ticket_id=103)
        check("a cancelled order can be prepared again", redo["ok"] and not redo.get("duplicate") and redo["purchase_order_id"] != po["purchase_order_id"])
        check("an agent name can't decline", (await call(c, "reject_request", approval_id=1, rejected_by="boss"))["ok"] is False)
        check("can't decline something already paid", (await call(c, "reject_request", approval_id=a1["approval_id"], rejected_by="Jamie Ruggiero"))["ok"] is False)
        rej = await call(c, "request_approval", kind="invoice_payment", ref_id=999)
        check("unknown invoice is an error, not a guess", rej["ok"] is False)

asyncio.run(main())
after = os.popen(f'shasum "{db.ORIGINAL}"').read().split()[0]
check("original data/campus_customs.db unchanged", original_hash == after)
print("\nALL PASSED" if not check.failed else f"\n{check.failed} FAILED")
sys.exit(1 if check.failed else 0)
