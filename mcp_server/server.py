"""Campus Customs MCP server.

Every agent reaches the shop database through the tools in this file; there is no other
shop tools layer. The tools read and write only data/campus_customs_new.db (the working
copy) and never invent data. "Today" is desk.date_today, never the system clock.

Rules enforced here, in code, whatever an agent's prompt says:
  * No payment happens without a recorded human approval (approvals.decided_by).
  * A payment is refused if cash is short, so the balance never goes below zero.
  * Cash only goes out. Nothing here adds money to an account.
  * A vendor with an open unpaid invoice can't be sent a new purchase order.
  * Nothing is emailed and no vendor is contacted. Customer drafts stay in the drafts table.
"""
import calendar
import re
import sqlite3
import sys
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path
from typing import Literal

from fastmcp import FastMCP

sys.path.insert(0, str(Path(__file__).resolve().parent))
from db import WORKING as DB_PATH, ensure_schema  # noqa: E402

RENT_WINDOW_DAYS = 7  # rent can be prepared for approval this many days before it is due
AGENT_NAMES = {"boss", "inventory", "accounting", "facilities", "customer_service"}

mcp = FastMCP("campus-customs")
_schema_ready = False


@contextmanager
def _db(write: bool = False):
    """Open the working copy. Write blocks run in one transaction: all or nothing."""
    global _schema_ready
    conn = sqlite3.connect(DB_PATH, timeout=10, isolation_level=None)
    conn.row_factory = sqlite3.Row
    try:
        if not _schema_ready:
            ensure_schema(conn)
            _schema_ready = True
        if write:
            conn.execute("BEGIN IMMEDIATE")
        yield conn
        if write:
            conn.execute("COMMIT")
    except BaseException:
        if write and conn.in_transaction:
            conn.execute("ROLLBACK")
        raise
    finally:
        conn.close()


def _today(conn: sqlite3.Connection) -> str:
    """The shop's 'today' is desk.date_today, not the system clock."""
    return conn.execute("SELECT date_today FROM desk").fetchone()["date_today"]


def _now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def _add_month(date: str) -> str:
    year, month, day = (int(x) for x in date.split("-"))
    month += 1
    if month > 12:
        year, month = year + 1, 1
    day = min(day, calendar.monthrange(year, month)[1])
    return f"{year:04d}-{month:02d}-{day:02d}"


def _open_invoices(conn: sqlite3.Connection, vendor_id: int | None = None) -> list[dict]:
    today = _today(conn)
    sql = """SELECT i.id AS invoice_id, i.vendor_id, v.name AS vendor_name, i.amount,
                    i.due_date, i.status, i.description
             FROM invoices i JOIN vendors v ON v.id = i.vendor_id
             WHERE i.status = 'open'"""
    args: tuple = ()
    if vendor_id is not None:
        sql += " AND i.vendor_id = ?"
        args = (vendor_id,)
    rows = [dict(r) for r in conn.execute(sql + " ORDER BY i.due_date", args)]
    for r in rows:
        r["is_overdue"] = r["due_date"] < today
        r["days_overdue"] = max(0, int(
            conn.execute("SELECT julianday(?) - julianday(?)", (today, r["due_date"])).fetchone()[0]))
    return rows


def _cash(conn: sqlite3.Connection, account: str = "checking") -> dict | None:
    row = conn.execute("SELECT name, balance, date FROM cash_accounts WHERE name = ?", (account,)).fetchone()
    if row is None:
        return None
    pending = conn.execute(
        "SELECT COALESCE(SUM(amount), 0) FROM approvals WHERE status IN ('pending', 'approved')"
    ).fetchone()[0]
    return {
        "account": row["name"], "balance": row["balance"], "as_of": row["date"],
        "committed_not_yet_paid": round(pending, 2),
        "available_after_commitments": round(row["balance"] - pending, 2),
    }


# ---------------------------------------------------------------- reads: tickets, stock, vendors

@mcp.tool
def list_tickets(status: str = "open") -> dict:
    """List tickets on the board with the given status (default 'open'), plus the shop's date.

    Use status 'all' for every ticket. Statuses: open, resolved, needs_human. Reads the
    tickets table. Each ticket has its type, requester, the SKU/size/quantity it involves,
    and the lease or invoice it links to.
    """
    with _db() as conn:
        if status in ("all", ""):
            rows = conn.execute("SELECT * FROM tickets ORDER BY id").fetchall()
        else:
            rows = conn.execute("SELECT * FROM tickets WHERE status = ? ORDER BY id", (status,)).fetchall()
        return {"today": _today(conn), "tickets": [dict(r) for r in rows]}


@mcp.tool
def get_ticket(ticket_id: int) -> dict:
    """Look up one ticket by id, including draft replies and the boss's summary, if any."""
    with _db() as conn:
        row = conn.execute("SELECT * FROM tickets WHERE id = ?", (ticket_id,)).fetchone()
        if row is None:
            return {"error": f"No ticket with id {ticket_id}"}
        drafts = [dict(d) for d in conn.execute(
            "SELECT id, audience, body, created_by FROM drafts WHERE ticket_id = ?", (ticket_id,))]
        summaries = [dict(x) for x in conn.execute(
            "SELECT status, summary, created_at FROM ticket_summaries WHERE ticket_id = ? ORDER BY id", (ticket_id,))]
        return {**dict(row), "today": _today(conn), "drafts": drafts, "summaries": summaries}


@mcp.tool
def check_stock(sku: str, size: str) -> dict:
    """Look up units on hand for one SKU and size, and where it is shelved.

    Returns qty and location from the inventory table. If the sku/size pair is not
    in inventory, returns an error instead of guessing.
    """
    with _db() as conn:
        row = conn.execute(
            "SELECT sku, name, size, qty, location FROM inventory WHERE sku = ? AND size = ?",
            (sku, size),
        ).fetchone()
    if row is None:
        return {"error": f"No inventory row for sku={sku!r}, size={size!r}"}
    return dict(row)


@mcp.tool
def find_vendors(keyword: str = "") -> dict:
    """List vendors that could restock, with lead time and whether each is on hold.

    keyword filters vendors by name or specialty (for example 'apparel' or 'mugs'); leave it
    empty for all vendors. A vendor is on hold when it has an open unpaid invoice, and it
    will not ship anything new until that invoice is paid. Reads vendors and invoices.
    """
    with _db() as conn:
        like = f"%{keyword.strip()}%"
        vendors = conn.execute(
            "SELECT id, name, specialty, lead_days FROM vendors WHERE name LIKE ? OR specialty LIKE ? ORDER BY id",
            (like, like)).fetchall()
        result = []
        for v in vendors:
            open_inv = _open_invoices(conn, v["id"])
            result.append({**dict(v), "on_hold": bool(open_inv), "open_invoices": open_inv})
        return {"today": _today(conn), "vendors": result}


@mcp.tool
def get_list_price(sku: str) -> dict:
    """The selling (list) price of one SKU. Customer Service uses this; it does not include cost."""
    with _db() as conn:
        row = conn.execute("SELECT sku, list_price FROM pricing WHERE sku = ?", (sku,)).fetchone()
    return dict(row) if row else {"error": f"No pricing row for sku={sku!r}"}


# ---------------------------------------------------------------- reads: money

@mcp.tool
def get_invoice_status(invoice_id: int) -> dict:
    """Look up one vendor invoice: who is owed, how much, and whether it is overdue.

    Joins invoices to vendors, and compares due_date with desk.date_today. An invoice
    with status 'open' means that vendor will not ship new product yet.
    """
    with _db() as conn:
        today = _today(conn)
        row = conn.execute(
            """SELECT i.id AS invoice_id, i.vendor_id, v.name AS vendor_name,
                      v.specialty, v.lead_days, i.amount, i.due_date, i.status, i.description
               FROM invoices i JOIN vendors v ON v.id = i.vendor_id
               WHERE i.id = ?""",
            (invoice_id,),
        ).fetchone()
    if row is None:
        return {"error": f"No invoice with id {invoice_id}"}
    result = dict(row)
    result["today"] = today
    result["is_open"] = result["status"] == "open"
    result["is_overdue"] = result["is_open"] and result["due_date"] < today
    return result


@mcp.tool
def list_open_invoices(vendor_id: int | None = None) -> dict:
    """All open (unpaid) vendor invoices, or just one vendor's, with overdue flags.

    Reads invoices and vendors, compared with desk.date_today.
    """
    with _db() as conn:
        return {"today": _today(conn), "open_invoices": _open_invoices(conn, vendor_id)}


@mcp.tool
def get_lease_status(lease_id: int) -> dict:
    """Look up one lease: landlord, monthly rent, and how soon the rent is due.

    Compares next_due with desk.date_today and reports days until due (negative
    means overdue).
    """
    with _db() as conn:
        today = _today(conn)
        row = conn.execute(
            """SELECT id AS lease_id, space_name, landlord, monthly_rent, next_due, notes,
                      CAST(julianday(next_due) - julianday(?) AS INTEGER) AS days_until_due
               FROM leases WHERE id = ?""",
            (today, lease_id),
        ).fetchone()
    if row is None:
        return {"error": f"No lease with id {lease_id}"}
    result = dict(row)
    result["today"] = today
    result["is_overdue"] = result["days_until_due"] < 0
    return result


@mcp.tool
def get_margin(sku: str, price: float | None = None) -> dict:
    """Unit cost, list price and margin for one SKU, optionally at a different price.

    Reads pricing. With no price, the margin is at list price. Pass price to see what a
    requested price would leave (this reports numbers only; it does not approve anything).
    """
    with _db() as conn:
        row = conn.execute("SELECT sku, unit_cost, list_price FROM pricing WHERE sku = ?", (sku,)).fetchone()
    if row is None:
        return {"error": f"No pricing row for sku={sku!r}"}
    used = row["list_price"] if price is None else price
    if used <= 0:
        return {"error": "price must be above zero"}
    return {
        "sku": sku, "unit_cost": row["unit_cost"], "list_price": row["list_price"],
        "price_used": used, "margin_dollars": round(used - row["unit_cost"], 2),
        "margin_percent": round((used - row["unit_cost"]) / used * 100, 1),
    }


@mcp.tool
def get_cash_balance(account: str = "checking") -> dict:
    """Cash balance, plus money already committed to pending or approved requests.

    Reads cash_accounts and approvals. available_after_commitments is the balance minus
    everything waiting to be paid. Cash only goes out; it can't go below zero.
    """
    with _db() as conn:
        cash = _cash(conn, account)
        return cash if cash else {"error": f"No cash account named {account!r}"}


@mcp.tool
def list_approvals(status: str = "") -> dict:
    """The spending log: payment and purchase-order requests, optionally filtered by status.

    Statuses: pending (waiting for a human), approved (human said yes, not paid yet),
    rejected, executed (paid). Reads approvals and payments.
    """
    with _db() as conn:
        if status:
            rows = conn.execute("SELECT * FROM approvals WHERE status = ? ORDER BY id", (status,))
        else:
            rows = conn.execute("SELECT * FROM approvals ORDER BY id")
        payments = [dict(p) for p in conn.execute("SELECT * FROM payments ORDER BY id")]
        return {"approvals": [dict(r) for r in rows], "payments_made": payments}


# ---------------------------------------------------------------- writes: Accounting

@mcp.tool
def create_purchase_order(vendor_id: int, sku: str, size: str, qty: int,
                          ticket_id: int | None = None, created_by: str = "accounting") -> dict:
    """Prepare a purchase order for human approval. Nothing is ordered or paid yet.

    If an order for the same vendor, item and ticket is already prepared or placed, that one is returned
    and no second order is made. Uses pricing.unit_cost for the cost. Refuses if the vendor has an open unpaid invoice
    (the vendor won't ship), if the SKU/size isn't one the shop sells, or if qty is not
    positive. Writes purchase_orders with status 'prepared'.
    """
    if qty <= 0:
        return {"ok": False, "error": "qty must be above zero"}
    with _db(write=True) as conn:
        vendor = conn.execute("SELECT id, name FROM vendors WHERE id = ?", (vendor_id,)).fetchone()
        if vendor is None:
            return {"ok": False, "error": f"No vendor with id {vendor_id}"}
        held = _open_invoices(conn, vendor_id)
        if held:
            return {"ok": False, "error": f"{vendor['name']} is on hold: invoice(s) "
                    f"{[i['invoice_id'] for i in held]} are open and unpaid, so they won't ship. "
                    "Pay those first.", "open_invoices": held}
        if conn.execute("SELECT 1 FROM inventory WHERE sku = ? AND size = ?", (sku, size)).fetchone() is None:
            return {"ok": False, "error": f"No inventory row for sku={sku!r}, size={size!r}"}
        same = conn.execute(
            "SELECT id, qty, total, status FROM purchase_orders WHERE vendor_id = ? AND sku = ? AND size = ? "
            "AND status IN ('prepared', 'ordered') AND COALESCE(ticket_id, -1) = COALESCE(?, -1)",
            (vendor_id, sku, size, ticket_id)).fetchone()
        if same:
            return {"ok": True, "duplicate": True, "purchase_order_id": same["id"], "vendor": vendor["name"], "sku": sku,
                    "size": size, "qty": same["qty"], "total": same["total"], "status": same["status"],
                    "note": f"Purchase order {same['id']} already covers this ({same['status']}). No second order was made."}
        price = conn.execute("SELECT unit_cost FROM pricing WHERE sku = ?", (sku,)).fetchone()
        if price is None:
            return {"ok": False, "error": f"No pricing row for sku={sku!r}"}
        total = round(price["unit_cost"] * qty, 2)
        cur = conn.execute(
            """INSERT INTO purchase_orders (vendor_id, sku, size, qty, unit_cost, total, status,
                                            ticket_id, created_by, created_at)
               VALUES (?, ?, ?, ?, ?, ?, 'prepared', ?, ?, ?)""",
            (vendor_id, sku, size, qty, price["unit_cost"], total, ticket_id, created_by, _now()))
        return {"ok": True, "purchase_order_id": cur.lastrowid, "vendor": vendor["name"], "sku": sku,
                "size": size, "qty": qty, "unit_cost": price["unit_cost"], "total": total,
                "status": "prepared", "note": "Not ordered. Request approval to put it in front of a human."}


@mcp.tool
def request_approval(kind: Literal["invoice_payment", "rent_payment", "purchase_order"], ref_id: int,
                     ticket_id: int | None = None, requested_by: str = "accounting") -> dict:
    """Put a payment or purchase order in front of a human for approval. Does not pay anything.

    kind is 'invoice_payment' (ref_id = invoice id), 'rent_payment' (ref_id = lease id; only within 7 days of the due date) or
    'purchase_order' (ref_id = purchase order id). The amount is read from the database, not
    supplied by the caller. Reads invoices, leases or purchase_orders; writes approvals.
    """
    with _db(write=True) as conn:
        if kind == "invoice_payment":
            row = conn.execute("SELECT amount, status, description FROM invoices WHERE id = ?", (ref_id,)).fetchone()
            if row is None:
                return {"ok": False, "error": f"No invoice with id {ref_id}"}
            if row["status"] != "open":
                return {"ok": False, "error": f"Invoice {ref_id} is {row['status']}, not open"}
            amount, desc = row["amount"], f"Pay invoice {ref_id}: {row['description']}"
        elif kind == "rent_payment":
            row = conn.execute(
                "SELECT monthly_rent, landlord, next_due, CAST(julianday(next_due) - julianday(?) AS INTEGER) AS days "
                "FROM leases WHERE id = ?", (_today(conn), ref_id)).fetchone()
            if row is None:
                return {"ok": False, "error": f"No lease with id {ref_id}"}
            if row["days"] > RENT_WINDOW_DAYS:
                return {"ok": False, "error": f"Rent isn't due yet: the next rent for lease {ref_id} is due {row['next_due']}, "
                        f"{row['days']} days away. Rent is only prepared within {RENT_WINDOW_DAYS} days of the due date. "
                        "Nothing to pay."}
            amount, desc = row["monthly_rent"], f"Pay rent to {row['landlord']}, due {row['next_due']}"
        else:
            row = conn.execute("SELECT total, status, qty, sku, size FROM purchase_orders WHERE id = ?", (ref_id,)).fetchone()
            if row is None:
                return {"ok": False, "error": f"No purchase order with id {ref_id}"}
            if row["status"] != "prepared":
                return {"ok": False, "error": f"Purchase order {ref_id} is {row['status']}, not prepared"}
            amount, desc = row["total"], f"Purchase order {ref_id}: {row['qty']} x {row['sku']} {row['size']}"
        existing = conn.execute(
            "SELECT id, status FROM approvals WHERE kind = ? AND ref_id = ? AND status IN ('pending', 'approved')",
            (kind, ref_id)).fetchone()
        if existing:
            return {"ok": True, "approval_id": existing["id"], "status": existing["status"],
                    "note": "Already requested; no duplicate created."}
        cur = conn.execute(
            """INSERT INTO approvals (kind, ref_id, amount, description, ticket_id, requested_by, status, created_at)
               VALUES (?, ?, ?, ?, ?, ?, 'pending', ?)""",
            (kind, ref_id, amount, desc, ticket_id, requested_by, _now()))
        cash = _cash(conn)
        return {"ok": True, "approval_id": cur.lastrowid, "status": "pending", "amount": amount,
                "description": desc, "cash": cash,
                "enough_cash_after_other_commitments": cash["available_after_commitments"] >= 0,
                "note": "Waiting for a human. Nothing is paid until a human approves and the payment runs."}


@mcp.tool
def pay_approved_request(approval_id: int) -> dict:
    """Make a payment that a human has already approved. Refuses otherwise.

    Refuses when: the request isn't approved by a human, it was already paid, the cash
    isn't there (the balance never goes below zero), or a purchase order's vendor is on
    hold. On success it lowers cash_accounts, adds a payments row, and updates the paid
    thing: invoice -> 'paid', rent -> next_due moves one month, purchase order -> 'ordered'.
    """
    with _db(write=True) as conn:
        a = conn.execute("SELECT * FROM approvals WHERE id = ?", (approval_id,)).fetchone()
        if a is None:
            return {"ok": False, "error": f"No approval with id {approval_id}"}
        if a["status"] == "executed":
            return {"ok": False, "error": f"Approval {approval_id} was already paid"}
        if a["status"] != "approved" or not a["decided_by"]:
            return {"ok": False, "error": f"Approval {approval_id} is '{a['status']}'. A human must approve "
                    "it before it can be paid. No payment was made."}
        cash = conn.execute("SELECT balance FROM cash_accounts WHERE name = 'checking'").fetchone()
        if a["amount"] > cash["balance"] + 1e-9:
            return {"ok": False, "error": f"Refused: not enough cash. Balance is {cash['balance']:.2f}, "
                    f"payment is {a['amount']:.2f}. The balance can't go below zero. No payment was made."}
        today = _today(conn)
        if a["kind"] == "invoice_payment":
            inv = conn.execute("SELECT status FROM invoices WHERE id = ?", (a["ref_id"],)).fetchone()
            if inv is None or inv["status"] != "open":
                return {"ok": False, "error": f"Invoice {a['ref_id']} is not open; nothing to pay"}
            conn.execute("UPDATE invoices SET status = 'paid' WHERE id = ?", (a["ref_id"],))
            kind = "invoice"
        elif a["kind"] == "rent_payment":
            lease = conn.execute("SELECT next_due FROM leases WHERE id = ?", (a["ref_id"],)).fetchone()
            conn.execute("UPDATE leases SET next_due = ? WHERE id = ?", (_add_month(lease["next_due"]), a["ref_id"]))
            kind = "rent"
        else:
            po = conn.execute("SELECT vendor_id, status FROM purchase_orders WHERE id = ?", (a["ref_id"],)).fetchone()
            if po is None or po["status"] != "prepared":
                return {"ok": False, "error": f"Purchase order {a['ref_id']} is not ready to order"}
            held = _open_invoices(conn, po["vendor_id"])
            if held:
                return {"ok": False, "error": "Vendor is on hold: invoice(s) "
                        f"{[i['invoice_id'] for i in held]} are still open. No payment was made."}
            conn.execute("UPDATE purchase_orders SET status = 'ordered' WHERE id = ?", (a["ref_id"],))
            kind = "purchase_order"
        conn.execute("UPDATE cash_accounts SET balance = balance - ? WHERE name = 'checking'", (a["amount"],))
        conn.execute(
            "INSERT INTO payments (kind, ref_id, amount, account, paid_at, approved_by) VALUES (?, ?, ?, 'checking', ?, ?)",
            (kind, a["ref_id"], a["amount"], today, a["decided_by"]))
        conn.execute("UPDATE approvals SET status = 'executed', executed_at = ? WHERE id = ?", (today, approval_id))
        return {"ok": True, "approval_id": approval_id, "paid": a["amount"], "kind": kind,
                "approved_by": a["decided_by"], "balance_after": round(cash["balance"] - a["amount"], 2)}


# ---------------------------------------------------------------- writes: Customer Service, Boss

# Words that mean a customer is being told the shop's own business. A draft with any of them is refused.
_INTERNAL = re.compile(
    r"\b(vendors?|suppliers?|invoices?|unpaid|overdue|on hold|cash|rent|landlord|margins?|"
    r"purchase orders?|approvals?|approved|human|accounting|bulldog print|elm city)\b", re.IGNORECASE)


@mcp.tool
def save_draft_reply(ticket_id: int, body: str, created_by: str = "customer_service") -> dict:
    """Save the draft reply to a customer on the board. It is NOT sent; nothing is emailed.

    There is one live draft per ticket: saving again replaces the earlier one. A draft that
    mentions the shop's internal matters (vendors, invoices, holds, cash, rent, approvals) is
    refused, because a customer shouldn't be told those. Writes drafts.
    """
    if not body.strip():
        return {"ok": False, "error": "Draft is empty"}
    leaked = sorted({m.group(0).lower() for m in _INTERNAL.finditer(body)})
    if leaked:
        return {"ok": False, "error": f"Draft refused: it mentions internal matters a customer shouldn't hear about "
                f"({', '.join(leaked)}). Rewrite it without them. Say only what the customer needs: the item, "
                "its price, whether it is in stock, and that we will update them. Nothing was saved."}
    with _db(write=True) as conn:
        t = conn.execute("SELECT requester FROM tickets WHERE id = ?", (ticket_id,)).fetchone()
        if t is None:
            return {"ok": False, "error": f"No ticket with id {ticket_id}"}
        old = conn.execute("SELECT id FROM drafts WHERE ticket_id = ? AND created_by = ?", (ticket_id, created_by)).fetchone()
        if old:
            conn.execute("UPDATE drafts SET body = ?, created_at = ? WHERE id = ?", (body.strip(), _now(), old["id"]))
            draft_id, replaced = old["id"], True
        else:
            cur = conn.execute(
                "INSERT INTO drafts (ticket_id, audience, body, created_by, created_at) VALUES (?, ?, ?, ?, ?)",
                (ticket_id, t["requester"], body.strip(), created_by, _now()))
            draft_id, replaced = cur.lastrowid, False
        return {"ok": True, "draft_id": draft_id, "ticket_id": ticket_id, "audience": t["requester"],
                "replaced_earlier_draft": replaced, "sent": False, "note": "Saved on the board as a draft. Not sent."}


@mcp.tool
def set_ticket_status(ticket_id: int, status: Literal["resolved", "needs_human"], summary: str) -> dict:
    """Close out a ticket with the boss's final summary.

    'resolved' means nothing more is needed. 'needs_human' means a person must approve,
    decide, or untangle something. Writes tickets.status and ticket_summaries.
    """
    if not summary.strip():
        return {"ok": False, "error": "A summary is required"}
    with _db(write=True) as conn:
        if conn.execute("SELECT 1 FROM tickets WHERE id = ?", (ticket_id,)).fetchone() is None:
            return {"ok": False, "error": f"No ticket with id {ticket_id}"}
        conn.execute("UPDATE tickets SET status = ? WHERE id = ?", (status, ticket_id))
        conn.execute("INSERT INTO ticket_summaries (ticket_id, status, summary, created_at) VALUES (?, ?, ?, ?)",
                     (ticket_id, status, summary.strip(), _now()))
        return {"ok": True, "ticket_id": ticket_id, "status": status}


# ---------------------------------------------------------------- human-only (never given to an agent)

@mcp.tool
def approve_request(approval_id: int, approved_by: str) -> dict:
    """HUMAN ONLY. Record a human's approval of a pending request. Does not pay it.

    The backend never offers this tool to any agent. approved_by must be a person's name;
    the names of the agents are refused.
    """
    name = approved_by.strip()
    if len(name) < 2 or name.lower().replace(" ", "_") in AGENT_NAMES:
        return {"ok": False, "error": "approved_by must be a human's name, not an agent"}
    with _db(write=True) as conn:
        a = conn.execute("SELECT status FROM approvals WHERE id = ?", (approval_id,)).fetchone()
        if a is None:
            return {"ok": False, "error": f"No approval with id {approval_id}"}
        if a["status"] != "pending":
            return {"ok": False, "error": f"Approval {approval_id} is '{a['status']}', not pending"}
        conn.execute("UPDATE approvals SET status = 'approved', decided_by = ?, decided_at = ? WHERE id = ?",
                     (name, _now(), approval_id))
        return {"ok": True, "approval_id": approval_id, "status": "approved", "approved_by": name}


@mcp.tool
def reject_request(approval_id: int, rejected_by: str) -> dict:
    """HUMAN ONLY. Record a human's rejection of a request that is pending, or approved but not yet paid."""
    name = rejected_by.strip()
    if len(name) < 2 or name.lower().replace(" ", "_") in AGENT_NAMES:
        return {"ok": False, "error": "rejected_by must be a human's name, not an agent"}
    with _db(write=True) as conn:
        a = conn.execute("SELECT status FROM approvals WHERE id = ?", (approval_id,)).fetchone()
        if a is None or a["status"] not in ("pending", "approved"):
            return {"ok": False, "error": f"Approval {approval_id} can't be rejected: it is not waiting on a decision"}
        conn.execute("UPDATE approvals SET status = 'rejected', decided_by = ?, decided_at = ? WHERE id = ?",
                     (name, _now(), approval_id))
        row = conn.execute("SELECT kind, ref_id FROM approvals WHERE id = ?", (approval_id,)).fetchone()
        if row["kind"] == "purchase_order":
            conn.execute("UPDATE purchase_orders SET status = 'cancelled' WHERE id = ? AND status = 'prepared'", (row["ref_id"],))
        return {"ok": True, "approval_id": approval_id, "status": "rejected", "rejected_by": name}


if __name__ == "__main__":
    mcp.run()
