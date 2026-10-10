# Campus Customs: a multi-agent operations desk

A Yale merch shop (Campus Customs) has three open tickets on its board: a customer who needs a size S tee, rent due in two days, and a student club asking for a bulk hoodie discount. A team of five AI agents works them. Humans watch the agents and approve every payment.

Three pieces talk to each other:

| Piece | Folder | What it is |
|---|---|---|
| **MCP server** | `mcp_server/` | FastMCP server. The 18 tools every agent uses to read and change the shop's database. |
| **Backend** | `backend/` | FastAPI app hosting the five-agent team (PydanticAI): Boss, Inventory, Accounting, Facilities, Customer Service. |
| **Dashboard** | `frontend/` | React + Vite + TypeScript board. Pick a ticket, watch the agents, approve payments. |

**The one rule that matters:** agents only *prepare* payments. Nothing is paid until a human clicks approve, and the pay tool refuses if cash is short, so checking never goes below $0.

## What's in this repo

```
data/campus_customs.db       the ORIGINAL database (never written by the app)
data/campus_customs_new.db   the WORKING copy the tools update (committed in its final state, after the full run)
backend/                     FastAPI + the five agents (backend/prompts/ = one prompt file per agent)
mcp_server/                  the MCP server and the database reset
frontend/                    the React board
scripts/                     tests and the scripts that built the evidence
output/                      the evidence: desk_tickets.html, resolved_board.html, resolved_tickets.json,
                             audit_trail.json, harness.md, design.md, github_url.txt
AI_prompts.md                the log of the prompts used to build this
```

Start with `output/harness.md`: it lists the tables, MCP tools, agents, API routes, dashboard and safety rules.

## Setup (once)

You need Python 3.11+ (built on 3.14) and Node 22+ (built on 24).

```bash
python3 -m venv venv
source venv/bin/activate
pip install -r requirements.txt
cd frontend && npm install && cd ..
```

**API key (only needed to run the agents).** The agents call `gpt-6 luna` through Portkey. Copy the template and put your key in it. The real `.env` is never committed.

```bash
cp .env.example .env      # then edit .env and set PORTKEY_API_KEY
```

Without a key, the MCP server, the API routes and the dashboard all still work. Only "run the agents" needs it.

## 1. Copy the original database to the working copy (for a clean run)

The app only ever writes to `data/campus_customs_new.db`. The original, `data/campus_customs.db`, is the reset source. The working copy in this repo is in its **final state** (all three tickets resolved, checking at $152), so the evidence matches. For a clean run, reset it to the original values:

```bash
python -m backend.cli reset          # recommended: copies the original over the working copy
```

That command restores the working copy and adds the extra tables the agents need (`approvals`, `purchase_orders`, `drafts`, `ticket_summaries`). You can also press **Start a fresh day** in the dashboard or `POST /api/reset`; they do the same thing and also write a "fresh day" marker into the audit trail, which the dashboard uses to show only today's activity.

A plain file copy also works as a fallback (the tables are created on first use), but it does not write the marker, so the dashboard may still show old runs in the chat:

```bash
cp data/campus_customs.db data/campus_customs_new.db
```

## 2. Start the MCP server

```bash
python mcp_server/mcp_server.py
```

It talks over stdio and reads/writes `data/campus_customs_new.db` only. The backend starts its own copy for the agents, so you don't need to leave this running for the dashboard. Run it by hand to test it, or to connect it to an MCP client such as Claude Code (see `mcp.json.example`). To check every tool and money rule without an API key:

```bash
python scripts/check_tools.py
```

## 3. Start the FastAPI backend

```bash
cd backend
uvicorn main:app --reload --port 8000
```

It serves the routes at http://localhost:8000 (listed in `output/harness.md`) and allows the dashboard's origin, http://localhost:5173.

## 4. Start the React board

In a second terminal:

```bash
cd frontend
npm run dev
```

Open http://localhost:5173. The board calls the backend at http://localhost:8000.

## 5. Reset the database before a full three-ticket run

Do this right before every full run, so you start from $3,400 and three open tickets:

```bash
python -m backend.cli reset
```

(or the **Start a fresh day** button). Then:

1. Click **Run the whole board**. The team works rent (102) first, then the customer order (101), then the discount request (103).
2. Type your name in the **Signing as** box. A human's name is required to approve.
3. Sign the **$2,400 rent** slip. Ticket 102 resolves by itself.
4. Sign the **$840 invoice** slip. The boss re-checks the other tickets, and the $8 tee order and the $264 hoodie order appear.
5. Sign the **$8 tee order**. Ticket 101 resolves.
6. Try to approve the **$264 hoodie order**. The pay tool refuses it (not enough cash). Press **Decline**, and ticket 103 resolves with no discount.

You end with all three tickets resolved and **checking at $152** ($3,400 − $2,400 − $840 − $8).

## Checks you can run

```bash
python scripts/check_tools.py          # every MCP tool and money rule
python scripts/check_team_offline.py   # delegation, limits and the audit trail (fake model, no key)
python scripts/check_routes.py         # every API route (fake model, no key)
```

These use scratch copies of the database and never touch `data/`.

## The evidence

Open these in a browser (double-click in Finder):

- `output/desk_tickets.html`: for each ticket, what we expected against what happened, the cash itemization, and the written reflection.
- `output/resolved_board.html`: screenshots of the React board with each ticket resolved.

And these as text: `output/resolved_tickets.json`, `output/audit_trail.json` (every agent step, append-only), `output/harness.md`, `output/design.md`.
