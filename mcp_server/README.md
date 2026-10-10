# Campus Customs MCP server

The MCP server is the one place where every agent (Boss, Inventory, Accounting, Facilities, Customer Service) gets its facts about the shop and makes its changes. Agents call its tools instead of touching the database, so no agent invents data and the rules below are enforced in code.

**Database:** `data/campus_customs_new.db`, the working copy of `data/campus_customs.db`. The original is only ever opened read-only, by the reset. Set `CAMPUS_DB` to point somewhere else. The shop's "today" is `desk.date_today`.

**Reset:** `venv/bin/python -m backend.cli reset` (or `python mcp_server/db.py`) restores the working copy from the original and adds the extra tables (`purchase_orders`, `approvals`, `drafts`, `ticket_summaries`). Do this before every full run.

## Tools (18)

Read:
- `list_tickets(status)`: tickets on the board (status `open` by default, or `all`), plus the shop's date. Table: tickets.
- `get_ticket(ticket_id)`: one ticket with its drafts and the boss's summary. Tables: tickets, drafts, ticket_summaries.
- `check_stock(sku, size)`: units on hand and shelf location. Table: inventory.
- `find_vendors(keyword)`: vendors, lead times, and whether each is on hold. Tables: vendors, invoices.
- `get_list_price(sku)`: the selling price only. Table: pricing.
- `get_invoice_status(invoice_id)`: vendor, amount, due date, open or overdue. Tables: invoices, vendors.
- `list_open_invoices(vendor_id)`: all unpaid invoices with overdue flags. Tables: invoices, vendors.
- `get_lease_status(lease_id)`: rent and days until due. Table: leases.
- `get_margin(sku, price)`: cost, price and margin, at list or at a given price. Table: pricing.
- `get_cash_balance(account)`: balance and money already committed. Tables: cash_accounts, approvals.
- `list_approvals(status)`: the spending log and payments made. Tables: approvals, payments.

Write:
- `create_purchase_order(...)`: prepares an order for approval; refused if the vendor is on hold. Table: purchase_orders.
- `request_approval(kind, ref_id)`: asks a human to approve an invoice payment, rent payment or purchase order. Table: approvals.
- `pay_approved_request(approval_id)`: pays a request a human approved; updates cash, payments, and the paid invoice, lease or order. Refuses without approval or without cash.
- `save_draft_reply(ticket_id, body)`: saves a customer reply as a draft. Never sent. Table: drafts.
- `set_ticket_status(ticket_id, status, summary)`: closes a ticket as `resolved` or `needs_human`. Tables: tickets, ticket_summaries.

Human only (the backend gives these to no agent):
- `approve_request(approval_id, approved_by)` and `reject_request(approval_id, rejected_by)`. An agent's name is refused.

## Rules the server enforces
- Nothing is paid without a recorded human approval.
- A payment is refused if cash is short, so the balance never goes below zero. Cash only goes out.
- A vendor with an open unpaid invoice can't be sent a purchase order.
- Amounts come from the database, not from the caller.
- Nothing is emailed and no vendor is contacted.

**Run it:** `venv/bin/python mcp_server/mcp_server.py` from the `hw5/` folder. The project's `.mcp.json` (repo root) points the vibe coder at it, and `backend/team.py` starts it for the agents.
