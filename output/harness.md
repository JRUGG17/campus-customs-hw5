# Harness: Campus Customs multi-agent operations

The whole system on one page: the database tables, the MCP tools, the five agents, the API routes, the dashboard, the safety rules, and what the final run did.

**Parts:** an MCP server (`mcp_server/`) that every agent uses to read and change the shop's data, a FastAPI backend (`backend/`) that hosts the five-agent team, and a React dashboard (`frontend/`) where a human watches the agents and approves payments. Agents only prepare payments. A human clicks approve.

**Databases:** `data/campus_customs.db` is the original and is never written. The agents work on the copy `data/campus_customs_new.db`, which "Start a fresh day" resets from the original.

## 1. Database tables

Nine tables in the original, plus four the agents need that exist only in the working copy (below). The shop's "today" is `desk.date_today` = **2026-08-31**.

### desk (1 row)
**Why it matters:** the only source of "today", so every agent judges overdue and due-soon dates from it, not the system clock.
- `date_today`: the shop's current date.
- `notes`: free text (empty).

### inventory (10 rows, key = sku + size)
**Why it matters:** Inventory agent's stock check; a ticket's sku and size must match a row here.
- `sku`: product code, joins to `pricing.sku` and `tickets.sku`.
- `name`: product name for messages.
- `size`: S/M/L/XL, or OS (one size) for hats and mugs.
- `qty`: units on hand; 0 means out of stock.
- `location`: aisle, for the pick.

### pricing (4 rows, key = sku)
**Why it matters:** Accounting's margin check and the Boss's discount decisions.
- `sku`: product code.
- `unit_cost`: what the shop pays per unit (restock cost).
- `list_price`: normal selling price. The margin is list_price minus unit_cost.

### vendors (3 rows)
**Why it matters:** Inventory picks who can restock and how fast.
- `id`: joins to `invoices.vendor_id`.
- `name`: vendor name.
- `specialty`: what they supply (apparel reprint, mugs and small goods, local courier).
- `lead_days`: days to deliver (5, 3, 1).

### leases (1 row)
**Why it matters:** Facilities tracks rent for the shop space.
- `id`: joins to `tickets.lease_id`.
- `space_name`: the space (Chapel Street shop).
- `landlord`: who gets paid.
- `monthly_rent`: amount due each month.
- `next_due`: next rent due date, compared against `desk.date_today`.
- `notes`: free text (empty).

### cash_accounts (1 row)
**Why it matters:** the limit on all spending; the pay tool must refuse any payment above `balance`.
- `name`: account (checking).
- `balance`: cash on hand. Cash only goes out, and it can never go negative.
- `date`: date of this balance.

### invoices (1 row)
**Why it matters:** an open invoice blocks that vendor from shipping and is a bill Accounting must pay.
- `id`: invoice number, joins to `tickets.invoice_id` and `payments.ref_id`.
- `vendor_id`: which vendor is owed.
- `amount`: amount owed.
- `due_date`: compared with today to see if it's overdue.
- `status`: `open` or paid.
- `description`: what it was for.

### payments (0 rows)
**Why it matters:** the ledger of approved payments, empty at the start. Every payment must be human-approved, then written here.
- `id`: payment number.
- `kind`: what was paid (invoice, rent, purchase order).
- `ref_id`: the invoice or lease paid, depending on `kind`.
- `amount`: dollars paid.
- `account`: which cash account paid.
- `paid_at`: when it was paid.
- `approved_by`: the human who approved it. Required.

### tickets (3 rows)
**Why it matters:** the work queue; the Boss reads each one and routes it.
- `id`: ticket number.
- `type`: `customer_order`, `rent_notice`, or `price_override`.
- `requester`: who asked.
- `subject`: short title.
- `sku`, `size`, `qty`: the item and amount involved (blank when it doesn't apply).
- `lease_id`: link to `leases.id`.
- `invoice_id`: link to `invoices.id`.
- `status`: all three are `open`.
- `notes`: the request in plain words.
- `created_at`: when the ticket arrived.

### How the three open tickets link to other tables

| Ticket | Links | What the data shows |
|---|---|---|
| **101** customer order: tee, size S, qty 1 (Tauhid Zaman) | `sku`+`size` → inventory; `invoice_id` 501 → invoices → vendor 1 | CC-TEE-WHITE S has **0** in stock. Vendor 1 (Bulldog Print Co, 5-day lead) is the apparel reprinter, but invoice 501 ($840, due 2026-08-28) is **open and 3 days overdue**, so they won't ship until it's paid. |
| **102** rent notice (Elm City Properties) | `lease_id` 1 → leases | $2,400 due 2026-09-02, which is 2 days from today, so it is not yet overdue. |
| **103** price override: 20 hoodies, M, bulk discount (Yale AI Club) | `sku`+`size` → inventory; `sku` → pricing | Only **8** M hoodies in stock, so the shortfall is 12. Cost $22, list $58 (margin $36, 62%). The discount has to leave a margin. Vendor 1 would restock, but is blocked by 501. |

**Things that connect across tickets**
- **Vendor 1 blocks two tickets.** Both 101 and 103 need apparel, and both wait on paying invoice 501.
- **They compete for one pot of cash.** Checking has $3,400. Invoice 501 ($840) plus rent ($2,400) is $3,240, leaving $160. A 12-hoodie restock at $22 is $264, so after both payments there isn't enough cash for it, and the pay tool would refuse.
- **Every payment needs a human.** The `payments` table is empty and `approved_by` is required.

**Gaps in the data**
- No purchase-order table. We need somewhere to hold POs (and draft customer messages, and approval requests) while they wait for a human.
- No link from a ticket to a vendor. Inventory has to match on `vendors.specialty`.
- `payments.ref_id` points to different tables depending on `kind`.

### Tables added to the working copy only
Created by `mcp_server/db.py` after each reset. The original database never has them.

| Table | Why it exists |
|---|---|
| `approvals` | The slips: every payment or purchase order an agent prepared, with its amount (read from the database, not typed by the agent), status (`pending`, `approved`, `rejected`, `executed`) and the human who decided. |
| `purchase_orders` | Orders Accounting prepared for a vendor (`prepared`, `ordered`, or `cancelled` when a human declines). |
| `drafts` | Customer replies. One per ticket, never sent. |
| `ticket_summaries` | The boss's final summary each time it closes out or escalates a ticket. |

## 2. MCP tools (18) and the tables they use

`mcp_server/server.py` (FastMCP). Shop facts and every change go through these tools. There is no second tools layer. "Today" always comes from `desk.date_today`. Each tool was also called through the vibe coder's MCP connection and checked against the database (`output/mcp_smoke.json`).

| Tool | Table(s) | What it does, and which agent uses it |
|---|---|---|
| `list_tickets` | tickets, desk | Boss reads the board (`open` by default, or `all`). |
| `get_ticket` | tickets, drafts, ticket_summaries, desk | Every agent reads its ticket, its draft and the boss's summaries. |
| `check_stock` | inventory | Inventory and Customer Service: units on hand and shelf location for a SKU and size (ticket 101's tee, 103's hoodies). |
| `find_vendors` | vendors, invoices, desk | Inventory: who can restock, their lead time, and whether each is on hold for an unpaid invoice. |
| `get_list_price` | pricing | Customer Service: the price to quote (it never sees cost). |
| `get_invoice_status` | invoices, vendors, desk | Accounting: who is owed, how much, whether it is overdue (ticket 101's invoice 501). |
| `list_open_invoices` | invoices, vendors, desk | Inventory and Accounting: everything unpaid and how overdue. |
| `get_lease_status` | leases, desk | Facilities: rent and days until due (ticket 102). |
| `get_margin` | pricing | Accounting: margin at list price or at a requested price (ticket 103). |
| `get_cash_balance` | cash_accounts, approvals | Boss and Accounting: the balance, and money already earmarked for slips. |
| `list_approvals` | approvals, payments | Boss and Accounting: the spending log. |
| `create_purchase_order` | purchase_orders, vendors, invoices, inventory, pricing | Accounting prepares an order. Refused if the vendor is on hold. Asking again for the same order returns it, with no duplicate. |
| `request_approval` | approvals, invoices, leases, purchase_orders | Accounting puts a payment or order in front of a human. The amount comes from the database. Rent is only prepared within 7 days of its due date. |
| `pay_approved_request` | approvals, cash_accounts, payments, invoices, leases, purchase_orders | Makes a payment a human approved: lowers cash, adds a payments row, marks the invoice paid, moves the rent's next due date a month, or marks the order placed. Refuses otherwise. |
| `save_draft_reply` | drafts, tickets | Customer Service saves the draft. Never sent. One per ticket (saving again replaces it). Refused if it mentions the shop's internal matters. |
| `set_ticket_status` | tickets, ticket_summaries | Boss closes a ticket as `resolved` or `needs_human` with its summary. |
| `approve_request` | approvals | **Human only.** No agent has it. An agent's name is refused. |
| `reject_request` | approvals, purchase_orders | **Human only.** Declines a request that is pending or approved-but-unpaid; a declined order is cancelled. |

## 3. The five agents

All five run on one model, `gpt-6 luna`, through Portkey (`backend/llm.py`). Prompts are in `backend/prompts/`, one file each. The agents and the delegation loop are in `backend/team.py`, and the data types in `backend/models.py`. Each agent only sees the MCP tools on its own list, and every agent has a `delegate(to, task)` tool, so any agent can hand work to any other.

| Agent | Prompt | Its job and personality | MCP tools it may call |
|---|---|---|---|
| **Boss** | `boss.md` | Reads tickets, sets priority (rent, then overdue invoices, then restocks), delegates everything, checks results, closes tickets. Bossy, direct, decisive. | `list_tickets`, `get_ticket`, `get_cash_balance`, `list_approvals`, `set_ticket_status` |
| **Inventory** | `inventory.md` | Checks stock by SKU and size, spots shortfalls, finds vendors, notices a hold, hands Accounting what needs doing. A precise stockroom clerk. | `get_ticket`, `check_stock`, `find_vendors`, `list_open_invoices` |
| **Accounting** | `accounting.md` | Watches cash, invoices and margins; prepares payments and purchase orders for human approval; never pays. A social climber who sucks up to the boss. | `get_ticket`, `get_cash_balance`, `list_open_invoices`, `get_invoice_status`, `get_margin`, `create_purchase_order`, `request_approval`, `list_approvals`, `pay_approved_request` |
| **Facilities** | `facilities.md` | Rent and the lease; heads-up to Accounting about rent. A plain building guy with a faint grumble. | `get_ticket`, `get_lease_status` |
| **Customer Service** | `customer_service.md` | Drafts replies, never sends them; no promises, no discounts, list prices only, nothing about the shop's inside business. Friendly and warm, a little weary. | `get_ticket`, `check_stock`, `get_list_price`, `save_draft_reply` |

**Boss close-out.** After a human approves or declines slips, the boss re-checks the ticket: it resolves it once everything the shop can do is done, or prepares what the payment unblocked (for example the order from a vendor that is no longer on hold). A human can also give a decision in words, which the boss acts on and records.

## 4. API routes

`backend/main.py` (FastAPI). Start it from `backend/`: `uvicorn main:app --reload --port 8000`. It allows the dashboard's origin, `http://localhost:5173`. Everything goes through the MCP tools.

| Route | What it does |
|---|---|
| `GET /api/tickets` | The tickets and whether each is open, resolved or needs a human; says if a run is in progress. |
| `GET /api/tickets/{id}` | One ticket with its draft (never sent) and the boss's summaries. |
| `POST /api/tickets/{id}/run` | Starts the agent team on one open ticket; returns a run id at once. |
| `POST /api/tickets/{id}/closeout` | The boss re-checks a ticket after a human acted; optional `note` and `decided_by` carry the human's decision. |
| `GET /api/runs/{run_id}` | Whether a run is going, finished or stopped, with the boss's outcome (rebuilt from the audit trail after a restart). |
| `GET /api/events` | Recent audit events: what each agent said and which tools it used. Filter by `run_id`, `ticket_id`, `agent`; `after` for new events; `since_reset=true` for the current day. |
| `GET /api/approvals` | The slips and the payments made. |
| `POST /api/approvals/{id}/approve` | **A human approves, and this pays it.** The only route that moves cash. Refused if cash is short or the vendor is on hold. |
| `POST /api/approvals/{id}/reject` | A human declines a slip. Nothing is paid. |
| `GET /api/cash` | The current checking balance from `cash_accounts`, plus money earmarked. |
| `POST /api/reset` | Restores the working copy to the original values; the audit trail is kept and a reset marker is written. |

## 5. The dashboard

`frontend/` (React, Vite, TypeScript). `npm run dev` serves it at `http://localhost:5173`. It calls the routes above at `http://localhost:8000`. The look, layout and the reasons for each choice are in `output/design.md`.

- **The board:** the three tickets as work orders, with **Run the whole board** (rent first, then the customer order, then the discount request) or a Start button per ticket.
- **The floor and the chat:** the five agents, who handed work to whom, and what each said and did, live while a ticket runs. Each agent reads differently (memo, clipboard, ledger, work order, speech bubble). Lookups are folded away unless you ask for them.
- **The report:** the boss's decision and a card per agent: what it said, the tools it used, who asked it.
- **Pay slips:** the one place a human approves or declines. The till shows checking drop after an approved payment.
- **Close-outs happen by themselves** after the last slip on a ticket is decided; paying an invoice also re-checks tickets that were waiting on a vendor.

## 6. Safety rules

What a real business would want when agents touch real customers and real money. They are enforced in the tools, not only asked for in prompts.

1. **A human approves every payment.** `pay_approved_request` refuses without a recorded human approval. `approve_request` and `reject_request` are on no agent's list, and an agent's name is refused as an approver.
2. **No overdrafts.** A payment is refused if cash is short, so the balance never goes below zero. Cash only goes out.
3. **Amounts come from the database,** not from the agent. A request for the same thing isn't duplicated, an approval can't be paid twice, and a duplicate purchase order is not made.
4. **Vendor hold is enforced.** No order goes to a vendor with an open unpaid invoice, checked again when paying.
5. **Rent is only prepared when it is due soon** (within 7 days), so a month already paid can't be paid twice.
6. **No contact with the outside world.** There is no email or phone tool. Customer replies are drafts on the board.
7. **Customers aren't told the shop's business.** A draft that mentions vendors, invoices, holds, cash, rent or approvals is refused.
8. **No discounts.** The boss and Customer Service never approve or offer one. A human decides; the margin tool only reports numbers.
9. **Least privilege.** Each agent sees only its own tools. Customer Service gets the list price, not the cost.
10. **No made-up facts.** Tools return an error for an id that isn't there. Dates come from `desk.date_today`.
11. **Everything is traceable.** The audit trail records every agent step, every delegation and refusal, and each human approval, decline and payment. It is append-only. An unreadable file is moved aside, never deleted.
12. **Escalation.** Stuck work, any money, and any discount go to a human.

## 7. Limits that keep token use in check

Set in `backend/models.py`:
- **Run budget, whole team together:** 100 model calls, 150 tool calls, 400,000 tokens. Going over stops the run and leaves a note in the audit trail.
- **Delegation depth:** at most 3 levels.
- **No cycles:** an agent can't ask anyone already in its chain of requests.
- **Loop breaker:** the same agent asking the same agent a 4th time is refused.
- **Output size:** 2,500 tokens per model response, with short structured reports between agents.
- **Shared budget:** delegated work counts against the same totals as the boss's.

A single ticket's first run costs about 20 model calls and 40,000 input tokens.

## 8. The final run (Problem 9)

Reset to the original values, then each ticket run on the real shop in priority order (102, 101, 103), with a human (`rjr`) signing or declining each slip.

| | |
|---|---|
| Starting checking balance | **3,400.00** |
| Rent, ticket 102 | −2,400.00 |
| Invoice 501, ticket 101 | −840.00 |
| Tee order, ticket 101 | −8.00 |
| Hoodie order, ticket 103 ($264) | declined by the human, no money moved |
| Ending checking balance | **152.00** (matches `cash_accounts`) |

- **101** resolved: the tee was ordered after the vendor's invoice was paid; the customer's draft stays on the board.
- **102** resolved: rent paid once, two days before it was due.
- **103** resolved: no discount, the list price stands; the $264 restock could not be afforded and was declined.

Evidence, all in `output/`: `desk_tickets.html` (plan against what happened, the cash itemization, and the written reflection), `resolved_tickets.json`, `resolved_board.html` (screenshots of the board), `audit_trail.json` (2,095 entries from 47 agent runs, the final run being the part after the last `database_reset`; the early ones show attempts made before the fixes), `mcp_smoke.json`, and `design.md`.

## 9. How it was checked

- `scripts/check_tools.py`: every MCP tool and money rule on a scratch database (42 checks, all passing).
- `scripts/check_team_offline.py`: delegation, limits and the audit trail, with a fake model so it costs nothing (13 checks, all passing).
- `scripts/check_routes.py`: every API route in-process, including close-out, human decisions and the audit entries (48 checks, all passing).
- A real browser (headless Chromium) drove the dashboard against the real model on a scratch copy: one click on **Run the whole board**, then signing and declining. All three tickets ended resolved with $152 left, and the refused payment and the human decisions were recorded.
- `scripts/build_resolution.py` refuses to write the results unless start balance minus payments equals `cash_accounts`.
