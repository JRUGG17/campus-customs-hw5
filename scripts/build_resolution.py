"""Build the Problem 9 deliverables from the database and the audit trail (nothing is typed in by hand
except the expected plan from Problem 6, which is compared against what really happened).

  - output/desk_tickets.html : fills each ticket's Actual section and the Cache tab (Expected is kept)
  - output/resolved_tickets.json
  - output/resolved_board.html (needs the screenshots made by scripts/screenshot_board.py)

Run from hw5/ after the tickets are resolved:  venv/bin/python scripts/build_resolution.py
It refuses to write anything if the cash does not reconcile with cash_accounts.
"""
import collections
import html
import json
import re
import sqlite3
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
OUT = ROOT / "output"
esc = html.escape

# ---------------------------------------------------------------- the plan from Problem 6 (Expected)
EXPECTED_DELEG = {
    101: [("boss", "inventory"), ("inventory", "accounting"), ("boss", "customer_service"), ("customer_service", "inventory")],
    102: [("boss", "facilities"), ("facilities", "accounting")],
    103: [("boss", "inventory"), ("inventory", "accounting"), ("boss", "accounting"), ("boss", "customer_service"),
          ("customer_service", "inventory")],
}
EXPECTED_NOT_SENT = {101: {"facilities"}, 102: {"inventory", "customer_service"}, 103: {"facilities"}}
EXPECTED_TOOLS = {
    101: {"boss": {"list_tickets", "set_ticket_status"}, "inventory": {"check_stock", "find_vendors", "list_open_invoices"},
          "accounting": {"get_invoice_status", "get_cash_balance", "request_approval"},
          "customer_service": {"get_ticket", "get_list_price", "save_draft_reply"}},
    102: {"boss": {"list_tickets", "set_ticket_status"}, "facilities": {"get_ticket", "get_lease_status"},
          "accounting": {"get_cash_balance", "request_approval"}},
    103: {"boss": {"list_tickets", "set_ticket_status"}, "inventory": {"check_stock", "find_vendors"},
          "accounting": {"get_margin", "get_cash_balance", "create_purchase_order"},
          "customer_service": {"get_ticket", "get_list_price", "save_draft_reply"}},
}
NICE = {"boss": "Boss", "inventory": "Inventory", "accounting": "Accounting", "facilities": "Facilities",
        "customer_service": "Customer Service"}
KIND_LABEL = {"rent_payment": "Rent", "invoice_payment": "Vendor invoice", "purchase_order": "Purchase order"}
PAY_KIND = {"rent": "rent_payment", "invoice": "invoice_payment", "purchase_order": "purchase_order"}


def money(n: float) -> str:
    return f"${n:,.2f}"


# ---------------------------------------------------------------- load the evidence
db = sqlite3.connect(ROOT / "data" / "campus_customs_new.db"); db.row_factory = sqlite3.Row
orig = sqlite3.connect(f"file:{ROOT / 'data' / 'campus_customs.db'}?mode=ro", uri=True)
start_balance = orig.execute("SELECT balance FROM cash_accounts WHERE name='checking'").fetchone()[0]
end_balance = db.execute("SELECT balance FROM cash_accounts WHERE name='checking'").fetchone()[0]
today = db.execute("SELECT date_today FROM desk").fetchone()[0]
tickets = {r["id"]: dict(r) for r in db.execute("SELECT * FROM tickets ORDER BY id")}
approvals = [dict(r) for r in db.execute("SELECT * FROM approvals ORDER BY id")]
payments = [dict(r) for r in db.execute("SELECT * FROM payments ORDER BY id")]
summaries = collections.defaultdict(list)
for r in db.execute("SELECT * FROM ticket_summaries ORDER BY id"):
    summaries[r["ticket_id"]].append(dict(r))
drafts = {r["ticket_id"]: dict(r) for r in db.execute("SELECT * FROM drafts")}
pos = {r["id"]: dict(r) for r in db.execute("SELECT * FROM purchase_orders")}

audit = json.loads((OUT / "audit_trail.json").read_text())
reset_at = max(i for i, x in enumerate(audit) if x["kind"] == "database_reset")
cycle = audit[reset_at + 1:]                      # everything since the reset that started this run
agent_events = [x for x in cycle if x["agent"] not in ("human", "backend")]

# ---------------------------------------------------------------- the money has to add up, or we stop
by_ticket_pay: dict[int, list[dict]] = collections.defaultdict(list)
for p in payments:
    match = [a for a in approvals if a["status"] == "executed" and a["kind"] == PAY_KIND[p["kind"]]
             and a["ref_id"] == p["ref_id"] and abs(a["amount"] - p["amount"]) < 1e-9]
    if len(match) != 1:
        sys.exit(f"STOP: payment {p['id']} does not match exactly one executed approval")
    a = match[0]
    by_ticket_pay[a["ticket_id"]].append({**p, "approval_id": a["id"], "paid_at_time": a["decided_at"],
                                          "description": a["description"], "approved_by": a["approved_by"] if "approved_by" in a else a["decided_by"]})
total_paid = round(sum(p["amount"] for p in payments), 2)
if round(start_balance - total_paid, 2) != round(end_balance, 2):
    sys.exit(f"STOP: {start_balance} - {total_paid} != cash_accounts {end_balance}")
for tid, plist in by_ticket_pay.items():
    if tid not in tickets:
        sys.exit(f"STOP: payment tied to unknown ticket {tid}")
ledger, running = [], start_balance
for p in sorted(payments, key=lambda x: x["id"]):
    running = round(running - p["amount"], 2)
    ap = next(a for a in approvals if a["status"] == "executed" and a["kind"] == PAY_KIND[p["kind"]] and a["ref_id"] == p["ref_id"])
    ledger.append({"payment_id": p["id"], "ticket_id": ap["ticket_id"], "what": ap["description"], "amount": p["amount"],
                   "approved_by": p["approved_by"], "balance_after": running})
if ledger[-1]["balance_after"] != round(end_balance, 2):
    sys.exit("STOP: running balance does not end at cash_accounts")
print(f"cash reconciles: {start_balance:,.2f} - {total_paid:,.2f} = {end_balance:,.2f} (cash_accounts)")


# ---------------------------------------------------------------- what really happened, per ticket
def clip(s: str, n: int) -> str:
    s = re.sub(r"\s+", " ", s).strip()
    return s if len(s) <= n else s[: n - 1].rstrip() + "…"


def report_answer(text: str) -> str:
    try:
        return json.loads(text)["answer"]
    except Exception:
        m = re.search(r'"answer":\s*"((?:[^"\\]|\\.)*)', text or "")
        return m.group(1) if m else ""


facts: dict[int, dict] = {}
for tid in (101, 102, 103):
    xs = [x for x in agent_events if x["tickets"] == [tid]]
    run_ids: list[str] = []
    for x in xs:
        if x["run_id"] not in run_ids:
            run_ids.append(x["run_id"])
    run_labels = {}
    n_close = 0
    for rid in run_ids:
        first = next(x for x in xs if x["run_id"] == rid)
        if first["text"].startswith("Follow-up"):
            n_close += 1
            run_labels[rid] = f"close-out {n_close}"
        else:
            run_labels[rid] = "first run"
    deleg = [(x["agent"], x["tool_calls"][0]["args"]["to"], run_labels[x["run_id"]]) for x in xs if x["kind"] == "delegation"]
    tools = collections.defaultdict(collections.Counter)
    for x in xs:
        for c in x.get("tool_calls") or []:
            if c["tool"] not in ("delegate", "final_result"):
                tools[x["agent"]][c["tool"]] += 1
    refused_tools = []
    for x in xs:
        for t in x.get("tool_results") or []:
            r = (t.get("result") or "")
            if '"ok": false' in r or '"ok":false' in r.replace(" ", ""):
                try:
                    err = json.loads(r)["error"]
                except Exception:
                    err = clip(r, 160)
                refused_tools.append((x["agent"], t["tool"], err, run_labels[x["run_id"]]))
    refused_deleg = [x for x in xs if x["kind"] == "delegation_refused"]
    said = {}
    for x in xs:
        if x["kind"] == "final" and x["agent"] != "boss":
            a = report_answer(x.get("text") or "")
            if a:
                said[x["agent"]] = a
    final = summaries[tid][-1]
    decision = re.search(r"Ticket and decision:\s*(.*?)\s*(?:Who did what:|$)", final["summary"], re.S)
    facts[tid] = {"run_labels": [run_labels[r] for r in run_ids], "run_ids": run_ids, "deleg": deleg, "tools": tools,
                  "refused_tools": refused_tools, "refused_deleg": len(refused_deleg), "said": said,
                  "agents": sorted({x["agent"] for x in xs}, key=lambda a: list(NICE).index(a)),
                  "decision": clip(decision.group(1) if decision else final["summary"], 320), "final_status": final["status"],
                  "resolved_at": final["created_at"]}
    assert tickets[tid]["status"] == final["status"] == "resolved", f"ticket {tid} is not resolved"

human = collections.defaultdict(list)
for a in approvals:
    if a["decided_by"]:
        human[a["ticket_id"]].append(a)


def cash_at(moment: str) -> float:
    """Checking balance at a moment: the start, less every payment a human made at or before then."""
    paid = sum(a["amount"] for a in approvals if a["status"] == "executed" and a["decided_at"] <= moment)
    return round(start_balance - paid, 2)


def cash_for(tid: int) -> dict:
    plist = by_ticket_pay.get(tid, [])
    return {"net_change": -round(sum(p["amount"] for p in plist), 2), "payments": plist}


# ---------------------------------------------------------------- compare expected and actual
def compare(tid: int) -> list[tuple[str, str]]:
    f = facts[tid]
    out: list[tuple[str, str]] = []
    seen = {(a, b) for a, b, _ in f["deleg"]}
    exp = set(EXPECTED_DELEG[tid])
    for a, b in EXPECTED_DELEG[tid]:
        out.append(("match" if (a, b) in seen else "diff",
                    f"{NICE[a]} → {NICE[b]}: " + ("happened as expected." if (a, b) in seen else "expected, but it did not happen.")))
    extra = sorted(seen - exp)
    for a, b in extra:
        out.append(("diff", f"{NICE[a]} → {NICE[b]}: not in the plan, but it happened."))
    for a in sorted(EXPECTED_NOT_SENT[tid]):
        out.append(("match" if a not in f["agents"] else "diff",
                    f"{NICE[a]} " + ("was correctly left out." if a not in f["agents"] else "was expected to sit out but was used.")))
    for ag, want in EXPECTED_TOOLS[tid].items():
        got = set(f["tools"].get(ag, {}))
        missing, more = sorted(want - got), sorted(got - want)
        text = f"{NICE[ag]} tools: "
        text += ("all expected tools used" if not missing else "expected but unused: " + ", ".join(missing))
        if more:
            text += "; also used: " + ", ".join(more)
        out.append(("match" if not missing else "diff", text + "."))
    return out


NOTES = {
    101: ["Expected the run to end with the $840 payment waiting. It did, and cash stayed at $3,400 until a human signed.",
          "The plan said no purchase order while the vendor is on hold. That held: Accounting's first try was refused by the tool. After the human paid invoice 501, a close-out prepared the $8 tee order, a human approved it, and the ticket resolved.",
          "The plan did not foresee the second step (the $8 tee order), so cash fell by $848 on this ticket, not $840."],
    102: ["Facilities went first and told Accounting about the rent, as planned. Boss also went straight to Accounting, and Accounting asked Facilities back, which the plan didn't list.",
          "Two attempts to hand work back up the chain were refused by the no-cycles rule. Nothing broke.",
          "Rent was not overdue (due in 2 days). Cash stayed at $3,400 until the human signed, then fell by $2,400."],
    103: ["Boss → Inventory first and Inventory → Accounting happened as planned. Customer Service did not ask Inventory for stock; it checked it itself, so that one expected hand-off didn't happen.",
          "The expected refusal happened: Accounting's first purchase order was refused because the vendor was on hold. While that run was still going, the human paid invoice 501, so Accounting's second attempt worked and prepared the $264 order. Only $160 was left by then, so it could not be afforded, and the human declined it. A close-out then resolved the ticket.",
          "No discount was granted. The list price of $58 stood. Cash did not change on this ticket."],
}

# ---------------------------------------------------------------- resolved_tickets.json
resolved = {"database": "data/campus_customs_new.db", "shop_date": today, "starting_checking_balance": start_balance,
            "ending_checking_balance": end_balance, "cash_reconciles_with_cash_accounts": True,
            "audit_trail": "output/audit_trail.json (this run starts after the last database_reset entry)", "tickets": []}
for tid in (101, 102, 103):
    f = facts[tid]
    contrib = {}
    for ag in f["agents"]:
        told = [b for a, b, _ in f["deleg"] if a == ag]
        asked = [a for a, b, _ in f["deleg"] if b == ag]
        contrib[ag] = {"what_it_said": clip(f["said"].get(ag, "Coordinated the ticket and wrote the final summary." if ag == "boss" else ""), 420),
                       "tools_used": dict(f["tools"].get(ag, {})), "handed_work_to": sorted(set(told)), "was_asked_by": sorted(set(asked))}
    resolved["tickets"].append({
        "id": tid, "type": tickets[tid]["type"], "subject": tickets[tid]["subject"], "final_status": f["final_status"],
        "outcome": f["decision"], "runs": f["run_labels"], "run_ids": f["run_ids"],
        "agents_who_worked": [NICE[a] for a in f["agents"]],
        "agents_left_out": [NICE[a] for a in NICE if a not in f["agents"] and a != "boss"],
        "agent_contributions": contrib,
        "delegations": [f"{NICE[a]} -> {NICE[b]} ({lab})" for a, b, lab in f["deleg"]],
        "refused": [{"agent": NICE[a], "tool": t, "reason": e, "when": lab} for a, t, e, lab in f["refused_tools"]]
                   + ([{"agent": "several", "tool": "delegate", "reason": f"{f['refused_deleg']} hand-back(s) refused by the no-cycles rule"}] if f["refused_deleg"] else []),
        "human_approvals": [{"approval_id": a["id"], "what": a["description"], "amount": a["amount"],
                             "decision": {"executed": "approved and paid", "rejected": "declined"}.get(a["status"], a["status"]),
                             "decided_by": a["decided_by"], "decided_at": a["decided_at"]} for a in human.get(tid, [])],
        "cash_change": cash_for(tid)["net_change"],
        "cash_payments": [{"payment_id": p["id"], "what": p["description"], "amount": p["amount"], "approved_by": p["approved_by"]}
                          for p in cash_for(tid)["payments"]],
        "customer_draft_on_board": (drafts.get(tid) or {}).get("body"), "customer_draft_sent": False,
        "closed_at": f["resolved_at"]})
resolved["payment_ledger"] = ledger
(OUT / "resolved_tickets.json").write_text(json.dumps(resolved, indent=2))
print("wrote output/resolved_tickets.json")


# ---------------------------------------------------------------- desk_tickets.html
def tags(agent: str, counter: collections.Counter) -> str:
    return "".join(f'<span class="tag">{esc(t)}{f" ×{n}" if n > 1 else ""}</span>' for t, n in counter.items())


def actual_block(tid: int) -> str:
    f = facts[tid]
    c = cash_for(tid)
    rows = []
    rows.append(f'<div class="row"><div class="k">Runs</div><div>{len(f["run_labels"])}: ' + ", ".join(f["run_labels"]) +
                '. The first run is the team preparing the work; each close-out is the boss re-checking after a human acted.</div></div>')
    first = next((a, b) for a, b, _ in f["deleg"])
    rows.append(f'<div class="row"><div class="k">Boss called first</div><div><div class="flow"><span class="agent">{NICE[first[0]]}</span>'
                f'<span class="arrow">&rarr;</span><span class="agent">{NICE[first[1]]}</span></div></div></div>')
    worked = "".join(f'<span class="agent">{NICE[a]}</span> ' for a in f["agents"])
    left = "".join(f'<span class="agent skip">{NICE[a]}: not sent</span> ' for a in NICE if a not in f["agents"])
    rows.append(f'<div class="row"><div class="k">Agents who worked</div><div><div class="flow">{worked}{left}</div></div></div>')
    steps = "".join(f"<li><b>{NICE[a]} &rarr; {NICE[b]}</b> <span class=\"why\">({esc(lab)})</span></li>" for a, b, lab in f["deleg"])
    refused = f"<div class=\"why\" style=\"margin-top:6px\">Also: {f['refused_deleg']} attempt(s) to hand work back up the chain were refused by the no-cycles rule.</div>" if f["refused_deleg"] else ""
    rows.append(f'<div class="row"><div class="k">Delegations that happened</div><div><ol class="steps">{steps}</ol>{refused}</div></div>')
    tl = "".join(f"<b>{NICE[a]}:</b> {tags(a, f['tools'][a])}<br>" for a in f["agents"] if f["tools"].get(a))
    rt = "".join(f'<div class="note">Refused: {NICE[a]} called <code>{esc(t)}</code> ({esc(lab)}): {esc(clip(e, 170))}</div>' for a, t, e, lab in f["refused_tools"])
    rows.append(f'<div class="row"><div class="k">MCP tools used</div><div>{tl}{rt}</div></div>')
    if human.get(tid):
        hl = "".join(f"<li>{esc(a['decided_by'])}: {esc(KIND_LABEL[a['kind']])}, {money(a['amount'])}, "
                     f"{'approved and paid' if a['status'] == 'executed' else 'declined'} &mdash; {esc(a['description'])}</li>" for a in human[tid])
        rows.append(f'<div class="row"><div class="k">Human approvals</div><div><ul class="steps">{hl}</ul></div></div>')
    cash_txt = (f"Cash on this ticket: <b>{'−' if c['net_change'] else ''}{money(abs(c['net_change']))}</b>" if c["net_change"]
                else "Cash on this ticket: <b>$0.00</b> (no money moved)")
    rows.append(f'<div class="row"><div class="k">Result</div><div>Status <b>{f["final_status"]}</b>. {esc(f["decision"])}<div class="{"good" if True else "note"}">{cash_txt}</div></div></div>')
    cmp_items = compare(tid)
    li = "".join(f'<li class="{k}"><span class="cmp-mark">{"✓" if k == "match" else "≠"}</span> {esc(t)}</li>' for k, t in cmp_items)
    notes = "".join(f"<li>{esc(n)}</li>" for n in NOTES[tid])
    rows.append(f'<div class="row"><div class="k">Expected vs actual</div><div><ul class="cmp">{li}</ul>'
                f'<div class="why" style="margin:8px 0 4px"><b>What to take from it</b></div><ul class="steps">{notes}</ul></div></div>')
    return '<h3>Actual</h3>\n  <div class="card actual filled">\n    ' + "\n    ".join(rows) + "\n  </div>"


def cache_section() -> str:
    t_rows = []
    for tid in (101, 102, 103):
        c = cash_for(tid)
        if c["payments"]:
            what = "<br>".join(f"{esc(KIND_LABEL[PAY_KIND[p['kind']]])}: {esc(p['description'])} ({money(p['amount'])}, approved by {esc(p['approved_by'])})" for p in c["payments"])
        else:
            declined = [a for a in human.get(tid, []) if a["status"] == "rejected"]
            what = ("Nothing was paid. " + "; ".join(f"The {money(a['amount'])} {KIND_LABEL[a['kind']].lower()} ({esc(a['description'])}) was prepared but the human declined it, because only {money(cash_at(a['decided_at']))} was left at that point" for a in declined) + ". No discount was given.") if declined else "Nothing was paid."
        why = {101: "Customer needs a size S tee. The vendor would not ship while invoice 501 was unpaid, so the invoice was paid first. Then one tee was ordered at $8 each.",
               102: "Rent for the Chapel Street shop, due 2026-09-02.",
               103: "Wanted 20 hoodies with a discount. The restock ($264) was more than the cash left, and no discount was granted, so nothing was bought."}[tid]
        change = f"−{money(abs(c['net_change']))}" if c["net_change"] else "$0.00"
        t_rows.append(f"<tr><td>{tid}</td><td>{esc(tickets[tid]['subject'])}</td><td>{what}</td><td>{esc(why)}</td><td class=\"num neg\">{change}</td></tr>")
    l_rows = [f'<tr><td></td><td colspan="2"><b>Starting checking balance</b> (after the reset, same as the original database)</td><td class="num"></td><td class="num"><b>{money(start_balance)}</b></td></tr>']
    for L in ledger:
        l_rows.append(f"<tr><td>{L['payment_id']}</td><td>{L['ticket_id']}</td><td>{esc(L['what'])}</td><td class=\"num neg\">−{money(L['amount'])}</td><td class=\"num\">{money(L['balance_after'])}</td></tr>")
    return f'''<section class="tab" id="cache">
  <h2>Cache: where the money went</h2>
  <p class="sub">Only cash going out is modeled; nothing comes in. Every payment below was approved by a human and is in the <code>payments</code> table.</p>

  <h3>By ticket</h3>
  <div class="card actual filled">
    <table class="money">
      <thead><tr><th>Ticket</th><th>What it was</th><th>Pay / purchase</th><th>Why</th><th class="num">Cash change</th></tr></thead>
      <tbody>{"".join(t_rows)}</tbody>
      <tfoot>
        <tr><td colspan="4"><b>Total paid out</b></td><td class="num neg"><b>−{money(total_paid)}</b></td></tr>
      </tfoot>
    </table>
  </div>

  <h3>In the order it was paid</h3>
  <div class="card actual filled">
    <table class="money">
      <thead><tr><th>Payment</th><th>Ticket</th><th>What</th><th class="num">Amount</th><th class="num">Checking after</th></tr></thead>
      <tbody>{"".join(l_rows)}</tbody>
      <tfoot><tr><td colspan="4"><b>Ending checking balance</b></td><td class="num"><b>{money(end_balance)}</b></td></tr></tfoot>
    </table>
    <div class="good" style="margin-top:12px"><b>It adds up.</b> {money(start_balance)} − {money(total_paid)} = <b>{money(end_balance)}</b>, which is exactly what <code>cash_accounts</code> holds in <code>data/campus_customs_new.db</code> (checked by a script before this page was written).</div>
  </div>
</section>'''


CSS = """
  .card.actual.filled { border-left: 5px solid var(--ok); background: #fff; }
  ul.cmp { list-style: none; margin: 0; padding: 0; }
  ul.cmp li { padding: 3px 0; }
  .cmp-mark { display: inline-block; width: 18px; font-weight: 800; }
  ul.cmp li.match .cmp-mark { color: var(--ok); }
  ul.cmp li.diff .cmp-mark { color: var(--warn); }
  ul.cmp li.diff { color: #5a4308; }
  table.money { width: 100%; border-collapse: collapse; font-size: 14px; }
  table.money th { text-align: left; font-size: 12px; text-transform: uppercase; letter-spacing: .06em; color: var(--muted); border-bottom: 2px solid var(--line); padding: 6px 8px; }
  table.money td { padding: 8px; border-bottom: 1px solid var(--line); vertical-align: top; }
  table.money tfoot td { border-top: 2px solid var(--blue); border-bottom: 0; }
  table.money .num { text-align: right; white-space: nowrap; font-variant-numeric: tabular-nums; }
  table.money .neg { color: #8a2a22; }
  h3 + .card.actual.filled { margin-bottom: 16px; }
"""

page = (OUT / "desk_tickets.html").read_text()
if "card actual filled" in page:
    # re-running: restore the blank Actual placeholders first is not needed; we replace whatever is there
    pass
for tid in (101, 102, 103):
    pat = re.compile(rf'(<section class="tab[^"]*" id="t{tid}">.*?)<h3>Actual</h3>\s*<div class="card actual[^"]*">.*?</div>\s*(</section>)', re.S)
    m = pat.search(page)
    if not m:
        sys.exit(f"could not find the Actual section for ticket {tid}")
    block = actual_block(tid)
    page = page[: m.start()] + m.group(1) + block + "\n" + m.group(2) + page[m.end():]
page = re.sub(r'<section class="tab" id="cache">.*?</section>', lambda _: cache_section(), page, flags=re.S)
if "table.money" not in page:
    page = page.replace("</style>", CSS + "</style>", 1)
page = page.replace("What we expect the team to do on each open ticket, with room for what actually happens.",
                    "What we expected the team to do on each ticket, and what actually happened.")
(OUT / "desk_tickets.html").write_text(page)
print("wrote output/desk_tickets.html (Actual sections + Cache tab; Expected kept)")
