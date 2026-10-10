"""Fill the Reflection tab of output/desk_tickets.html.

The numbers come from the audit trail and the database (same sources as the Actual and Cache tabs),
so every figure in the reflection can be traced. The prose is written here.

Run from hw5/ after build_resolution.py:  venv/bin/python scripts/build_reflection.py
"""
import collections
import json
import re
import sqlite3
import sys
from datetime import datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
OUT = ROOT / "output"

# ---------------------------------------------------------------- numbers from the evidence
audit = json.loads((OUT / "audit_trail.json").read_text())
reset_at = max(i for i, x in enumerate(audit) if x["kind"] == "database_reset")
cycle = [x for x in audit[reset_at + 1:] if x["agent"] not in ("human", "backend")]
db = sqlite3.connect(ROOT / "data" / "campus_customs_new.db")
orig = sqlite3.connect(f"file:{ROOT / 'data' / 'campus_customs.db'}?mode=ro", uri=True)
start_bal = orig.execute("SELECT balance FROM cash_accounts").fetchone()[0]
end_bal = db.execute("SELECT balance FROM cash_accounts").fetchone()[0]
resolved = json.loads((OUT / "resolved_tickets.json").read_text())
assert resolved["ending_checking_balance"] == end_bal

M = {}
for tid in (101, 102, 103):
    xs = [x for x in cycle if x["tickets"] == [tid]]
    runs = list(dict.fromkeys(x["run_id"] for x in xs))
    req = tok = secs = 0
    for r in runs:
        ys = [y for y in xs if y["run_id"] == r]
        u = [y["usage"] for y in ys if y.get("usage")][-1]
        req += u["requests"]
        tok += u["input_tokens"] + u["output_tokens"]
        st = next(y for y in ys if y["kind"] == "run_start")
        en = next((y for y in ys if y["kind"] == "run_end"), None)
        if en:
            secs += (datetime.fromisoformat(en["timestamp"]) - datetime.fromisoformat(st["timestamp"])).total_seconds()
    mcp = sum(1 for y in xs for c in (y.get("tool_calls") or []) if c["tool"] not in ("delegate", "final_result"))
    M[tid] = {"runs": len(runs), "requests": req, "tokens": tok, "secs": round(secs), "mcp": mcp,
              "deleg": sum(1 for y in xs if y["kind"] == "delegation"),
              "refused_deleg": sum(1 for y in xs if y["kind"] == "delegation_refused"),
              "pairs": {(y["agent"], y["tool_calls"][0]["args"]["to"]) for y in xs if y["kind"] == "delegation"}}
tot_req = sum(m["requests"] for m in M.values())
tot_tok = sum(m["tokens"] for m in M.values())
tot_mcp = sum(m["mcp"] for m in M.values())
tot_deleg = sum(m["deleg"] for m in M.values())

# the plan from Problem 6, to count how many of its calls came true
EXPECTED = {101: {("boss", "inventory"), ("inventory", "accounting"), ("boss", "customer_service"), ("customer_service", "inventory")},
            102: {("boss", "facilities"), ("facilities", "accounting")},
            103: {("boss", "inventory"), ("inventory", "accounting"), ("boss", "accounting"), ("boss", "customer_service"),
                  ("customer_service", "inventory")}}
hit = {t: len(EXPECTED[t] & M[t]["pairs"]) for t in EXPECTED}
extra = {t: len(M[t]["pairs"] - EXPECTED[t]) for t in EXPECTED}
exp_n = {t: len(EXPECTED[t]) for t in EXPECTED}
if M[102]["mcp"] != 18 or M[101]["requests"] != 45 or tot_req != 98:
    print("NOTE: the numbers differ from the ones this prose was checked against:", {t: (M[t]['requests'], M[t]['mcp']) for t in M})

mug = db.execute("SELECT qty, location FROM inventory WHERE sku='CC-MUG-CREST'").fetchone()
mug_price = db.execute("SELECT unit_cost, list_price FROM pricing WHERE sku='CC-MUG-CREST'").fetchone()
hat = db.execute("SELECT qty FROM inventory WHERE sku='CC-HAT-BLUE'").fetchone()[0]
hat_price = db.execute("SELECT unit_cost, list_price FROM pricing WHERE sku='CC-HAT-BLUE'").fetchone()
apparel = db.execute("SELECT name, lead_days FROM vendors WHERE specialty LIKE '%apparel%'").fetchone()
mug_vendor = db.execute("SELECT id, name, lead_days FROM vendors WHERE specialty LIKE '%mugs%'").fetchone()
next_rent = db.execute("SELECT next_due, monthly_rent FROM leases").fetchone()
assert mug[0] == 0 and not db.execute("SELECT 1 FROM invoices WHERE vendor_id=? AND status='open'", (mug_vendor[0],)).fetchone()
mug_order = 24 * mug_price[0]
hat_margin = 18 - hat_price[0]


def g(tab, label):
    return f'<a class="goto" href="#{tab}" data-goto="{tab}">{label}</a>'


T101, T102, T103, CACHE = g("t101", "Ticket 101 tab"), g("t102", "Ticket 102 tab"), g("t103", "Ticket 103 tab"), g("cache", "Cache tab")
m1, m2, m3 = M[101], M[102], M[103]

page_html = f'''<section class="tab" id="reflection">
  <h2>Reflection</h2>
  <p class="sub">Written the way we'd say it. Every answer points at something we actually ran: the three ticket tabs and the Cache tab are the evidence.</p>

  <div class="strip">
    <div><b>3</b><span>tickets, all resolved</span></div>
    <div><b>{tot_req}</b><span>model calls</span></div>
    <div><b>{tot_tok:,}</b><span>tokens used</span></div>
    <div><b>{tot_mcp}</b><span>MCP tool calls</span></div>
    <div><b>${start_bal:,.0f} → ${end_bal:,.0f}</b><span>checking, start to end ({CACHE})</span></div>
  </div>

  <div class="card refl bottom">
    <b>Bottom line.</b> The team got every ticket to the right ending and never moved money without a human. The tools did most of the protecting: the vendor hold, the cash check, the no-discount rule and the draft filter all live in the tools, not in anybody's good behavior. Where it fell short is cost and honesty at the edges: it took {tot_req} model calls to do work a single agent could mostly do in a fraction of that, and the boss once reported a fact (the tee is "in transit") that nothing in our system can know.
  </div>

  <!-- ============================================================ 1 -->
  <h3>1. How would we grade the agents on each ticket, and why?</h3>

  <div class="card refl">
    <div class="verdict-line"><b>Ticket 102, rent:</b> <span class="pill ok">right answer</span> <span class="pill warn">far too much machinery</span></div>
    <p><b>What went right.</b> Facilities checked the notice against lease 1 and got it exactly right: Elm City Properties, $2,400, due 2026-09-02, two days out so <i>not</i> overdue. Accounting prepared one slip for $2,400. Nothing moved until the human signed, and then cash went from $3,400 to $1,000 (first line of the payment table on the {CACHE}). The boss closed it as resolved once the rent was paid.</p>
    <p><b>What went wrong.</b> This ticket needs two real lookups, the lease and the cash balance, and then one slip. The team used <b>{m2["mcp"]} MCP tool calls, {m2["requests"]} model calls and {m2["tokens"]:,} tokens across {m2["runs"]} runs</b> and {m2["deleg"]} delegations. Accounting asked for the same rent slip twice (the second answer was "Already requested; no duplicate created", which is the tool catching it), and the no-cycles rule had to refuse {m2["refused_deleg"]} attempts by agents to hand the work back up the chain. Facilities existed here to call one tool.</p>
    <p><b>Why we grade it that way.</b> Outcome is perfect; the process is the weak part. A person would call this "correct but wasteful". See the {T102}.</p>
  </div>

  <div class="card refl">
    <div class="verdict-line"><b>Ticket 101, Tauhid's tee:</b> <span class="pill ok">best demo of the guardrails</span> <span class="pill warn">heaviest bill</span> <span class="pill bad">overclaimed at the end</span></div>
    <p><b>What went right.</b> This is the ticket the whole design was for. The tee had 0 in stock and the only apparel vendor, Bulldog Print Co, was on hold for overdue invoice 501. Accounting tried to order anyway and <b>the tool refused</b> ("Bulldog Print Co is on hold: invoice(s) [501] are open and unpaid"). The team then did the sensible order of operations: prepare the $840 payment first, wait for a human, and only after the hold lifted prepare the one-tee order ($8, our unit cost). Customer Service's final draft tells Tauhid the tee is out of stock, gives the $28 list price and says we have no date, and it says nothing about vendors or invoices. The {CACHE} shows both payments: −$840 and −$8.</p>
    <p><b>What went wrong.</b> It was the most expensive ticket: <b>{m1["requests"]} model calls, {m1["tokens"]:,} tokens, {m1["mcp"]} MCP calls, {m1["runs"]} runs, {m1["deleg"]} delegations</b>. Part of that is unavoidable (it really is a two-step ticket: pay, then order). But the boss's closing summary says the tee "remains in transit". We never contacted the vendor and have no shipment tool, so the truth is only "ordered". The ticket also got marked resolved while our own inventory still says 0 tees, because nothing records stock arriving (more on that in section 5).</p>
    <p><b>Why we grade it that way.</b> The hard behavior (refuse, pay first, then order) was right. The cost and the "in transit" line are the deductions. See the {T101}.</p>
  </div>

  <div class="card refl">
    <div class="verdict-line"><b>Ticket 103, the AI Club's hoodies:</b> <span class="pill ok">right call on policy</span> <span class="pill warn">thin help for the customer</span></div>
    <p><b>What went right.</b> Nobody offered or approved a discount, which is the rule. Accounting worked out the real numbers: the hoodie costs $22 and lists at $58, so $36 a unit, 62%. Inventory found 8 on hand, 12 short. The first order attempt was refused because of the vendor hold, again as planned. The $264 restock was prepared once the hold lifted, and the human declined it with only $160 left ({CACHE}: this ticket's cash change is $0.00). The boss resolved it as "list price stands, discount not approved, restock declined".</p>
    <p><b>What went wrong.</b> Customer Service never asked Inventory for stock (it checked itself), and the draft it wrote to the club says the list price stands but <b>never mentions that we have 8 hoodies they could buy right now</b>. That's the most useful thing we could have told them. Also, the $264 slip only existed because the human happened to pay invoice 501 <i>while this run was still going</i>, so Accounting's second attempt worked. A different click order would have produced no slip. Cost: {m3["requests"]} model calls and {m3["tokens"]:,} tokens.</p>
    <p><b>Why we grade it that way.</b> Policy and money were handled well; service to the customer was the miss. See the {T103}.</p>
  </div>

  <!-- ============================================================ 2 -->
  <h3>2. For each ticket, how did actual compare to expected?</h3>
  <div class="card refl">
    <table class="money">
      <thead><tr><th>Ticket</th><th>Delegations we expected</th><th>Extra ones that happened</th><th>Who we said would sit out</th><th>Ending we expected</th><th>Ending we got</th></tr></thead>
      <tbody>
        <tr><td>101</td><td>{hit[101]} of {exp_n[101]} happened</td><td>{extra[101]}</td><td>Facilities: right</td><td>Waiting on the $840 payment, no purchase order</td><td>Resolved. −$840, and also a −$8 tee order after the hold lifted</td></tr>
        <tr><td>102</td><td>{hit[102]} of {exp_n[102]} happened</td><td>{extra[102]}</td><td>Inventory and Customer Service: right</td><td>Waiting on the $2,400 payment</td><td>Resolved. −$2,400</td></tr>
        <tr><td>103</td><td>{hit[103]} of {exp_n[103]} happened</td><td>{extra[103]}</td><td>Facilities: right</td><td>Waiting on a human: no discount, order refused</td><td>Resolved. $0. The human declined the $264 order</td></tr>
      </tbody>
    </table>
    <p style="margin-top:12px"><b>The routing prediction was good.</b> We got {sum(hit.values())} of {sum(exp_n.values())} expected delegations and all 4 of our "this agent sits out" calls. The one miss was Customer Service asking Inventory on ticket 103. Our plan said Facilities would stay out of 101 and 103 and Inventory and Customer Service out of 102, and that is what happened, so the "do not send everyone everywhere" idea held.</p>
    <p><b>What we got wrong was the ending, not the routing.</b> We expected each ticket to stop at "waiting on a human". In reality they went one step further, because after the human signs, somebody has to re-check. That is why we added the boss close-out step, and it changed the picture on ticket 101 (a second money step we hadn't planned) and ticket 103 (the order only appeared once the invoice was paid). The {CACHE} is the honest record: the plan said $840 for 101, the real number is $848.</p>
    <p><b>The agents also did more talking than we pictured.</b> We expected a boss who calls specialists. We got agents calling each other and the boss repeatedly: {tot_deleg} delegations over three tickets, and {M[102]["refused_deleg"]} refused hand-backs on ticket 102 alone. The plan was about who gets sent; it said nothing about how often.</p>
  </div>

  <!-- ============================================================ 3 -->
  <h3>3. What would have been simpler as one agent with tools?</h3>
  <div class="card refl">
    <table class="money">
      <thead><tr><th>Ticket</th><th>What the team did</th><th>What one agent with the same tools would do</th><th>Simpler as one agent?</th></tr></thead>
      <tbody>
        <tr><td>102 rent</td><td>{m2["mcp"]} MCP calls, {m2["requests"]} model calls, 3 agents, {m2["deleg"]} delegations</td><td><code>get_ticket</code> → <code>get_lease_status</code> → <code>get_cash_balance</code> → <code>request_approval</code>. Four calls, one run.</td><td><b>Yes, clearly.</b> This is the weakest case for a team.</td></tr>
        <tr><td>103 hoodies</td><td>{m3["mcp"]} MCP calls, {m3["requests"]} model calls, 4 agents, {m3["deleg"]} delegations</td><td><code>check_stock</code>, <code>get_margin</code>, <code>get_list_price</code>, <code>find_vendors</code>, then <code>save_draft_reply</code>. One agent holds the whole picture, which also means it would have remembered to tell the club about the 8 in stock.</td><td><b>Mostly yes.</b> It is reads plus one draft.</td></tr>
        <tr><td>101 tee</td><td>{m1["mcp"]} MCP calls, {m1["requests"]} model calls, 4 agents, {m1["deleg"]} delegations, {m1["runs"]} runs</td><td><code>check_stock</code>, <code>find_vendors</code>, <code>get_invoice_status</code>, <code>request_approval</code> for the invoice, a draft; later <code>create_purchase_order</code> and <code>request_approval</code> again.</td><td><b>Mostly, but this is where a team earns something</b> (below).</td></tr>
      </tbody>
    </table>
    <p style="margin-top:12px"><b>Why.</b> All three tickets are the same shape: read a few rows from the 9 tables, do small arithmetic ($36 margin, $160 left), and prepare at most one slip. Nothing in them needed two minds. The team's cost is mostly agents passing the same facts to each other. 103's Inventory told Accounting about the shortfall and the hold, and then Accounting asked Inventory for it again.</p>
    <p><b>What the team did buy us.</b> We'd keep three things even if we collapsed the rest:</p>
    <ul class="steps">
      <li><b>Only Accounting holds money tools.</b> <code>create_purchase_order</code>, <code>request_approval</code> and <code>pay_approved_request</code> are on one agent's list. Nobody who writes to customers can touch cash.</li>
      <li><b>Customer Service never sees cost.</b> It has <code>get_list_price</code> and not <code>get_margin</code>, so a draft cannot quote the shop's $22 hoodie cost to the AI Club. (The word filter in <code>save_draft_reply</code> is the second wall.)</li>
      <li><b>The audit trail reads as people.</b> "Facilities verified the lease, Accounting prepared the slip" is easier to check than one agent's long list of tool calls.</li>
    </ul>
    <p><b>What we would actually build next time:</b> two agents, not five. One <i>operator</i> holding every read tool plus <code>save_draft_reply</code> and <code>set_ticket_status</code>, and one <i>Accounting</i> holding the money tools behind the human gate. That keeps what the team protects and drops most of the hand-offs. The {T102} is the proof: four calls would have done what eighteen did.</p>
  </div>

  <!-- ============================================================ 4 -->
  <h3>4. Three new problems Campus Customs might face that this team could solve with the tools we built</h3>

  <div class="card refl">
    <p><b>A. "The Crest Mug is out." ({mug_vendor[1]} restock.)</b> Right now <code>CC-MUG-CREST</code> shows <b>{mug[0]}</b> in stock at {mug[1]}. A customer asks for six. Inventory runs <code>check_stock</code> and <code>find_vendors</code> and finds <b>{mug_vendor[1]}</b> (mugs and small goods, {mug_vendor[2]}-day lead). Unlike Bulldog Print Co on ticket 101, this vendor has <i>no open invoice</i>, so it is not on hold. Accounting runs <code>create_purchase_order</code> for 24 mugs at ${mug_price[0]:.2f} each (${mug_order:,.2f}), then <code>request_approval</code>, and a human signs. It fits the ${end_bal:,.0f} we ended with on the {CACHE}, with ${end_bal - mug_order:,.2f} left. This is ticket 101 without the hold, so the same tools solve it, faster.</p>
  </div>
  <div class="card refl">
    <p><b>B. "October rent is coming."</b> Paying rent on ticket 102 moved lease 1's next due date to <b>{next_rent[0]}</b>. Seven days before that, Facilities' <code>get_lease_status</code> shows it coming up and Accounting's <code>request_approval</code> becomes allowed (it refuses earlier, which is the rule we added after a second rent slip appeared). The team would do the whole workflow: detect it, prepare the ${next_rent[1]:,.0f} slip, and flag how much cash we have. It <i>can't fix the shortfall</i> (we'd have ${end_bal:,.0f}; see problem 1 in the next section), but it will say so plainly instead of letting a human find out when the payment is refused.</p>
  </div>
  <div class="card refl">
    <p><b>C. "A club wants 30 Yale Caps at $18."</b> <code>CC-HAT-BLUE</code> has {hat} on hand, so there is enough stock and no restock. Customer Service quotes the ${hat_price[1]:.0f} list price with <code>get_list_price</code>. Accounting runs <code>get_margin</code> at $18: cost ${hat_price[0]:.0f}, so <b>${hat_margin:.0f} a cap, {hat_margin / 18 * 100:.1f}%</b>. The boss does not approve it, per our rule that humans decide discounts. It puts the numbers in front of the human, who can answer in the decision box. This is ticket 103's discount path with the stock problem removed. The team would be good at it.</p>
  </div>

  <!-- ============================================================ 5 -->
  <h3>5. Three new problems this team could not solve, and the tools it would need</h3>

  <div class="card refl">
    <p><b>1. Money coming in.</b> Everything we modeled only goes out. The <code>payments</code> table has no deposits, and <code>cash_accounts</code> has one number that only ever falls. When the AI Club pays $58 a hoodie for the 8 we could sell them (up to $464), or Tauhid pays $28 for his tee, nothing records it. The {CACHE} ends at <b>${end_bal:,.0f}</b> and <b>{next_rent[0]}'s rent is ${next_rent[1]:,.0f}</b>. With no way to book income the team can see the shortfall, but it can never close it.</p>
    <p><b>Tools it would need:</b> <code>record_customer_payment(ticket_id, amount, method)</code> writing to a new <code>receipts</code> table and raising <code>cash_accounts.balance</code>; <code>refund_customer(receipt_id)</code>; <code>list_receivables()</code> for orders placed but unpaid; and <code>forecast_cash(days)</code> so Accounting can warn about October before it is a crisis. Accounting would own them, and deposits and refunds should still need a human to confirm.</p>
  </div>
  <div class="card refl">
    <p><b>2. The order arrives, and the customer needs to hear about it.</b> On ticket 101 the tee order is marked <i>ordered</i>, but our inventory still says 0 tees, forever. Nothing tracks the {apparel[1]}-day lead time we know Bulldog Print Co has, nothing marks stock received, and the team can't tell Tauhid it's here. The boss even wrote "in transit" with nothing behind it. Ticket 101 is "resolved" while the customer still has no tee.</p>
    <p><b>Tools it would need:</b> <code>receive_purchase_order(po_id, qty)</code> to add to <code>inventory.qty</code> and close the order; <code>get_order_status(po_id)</code> that reports an expected arrival date from <code>vendors.lead_days</code>; <code>reserve_stock(ticket_id, sku, size, qty)</code> so the arriving tee is held for Tauhid; and <code>send_customer_message(draft_id)</code>, which sends a saved draft only after a human approves it. (Today there is deliberately no way to send anything.) QuickShip CT, the 1-day local courier in the <code>vendors</code> table, is unused because we have no <code>schedule_delivery</code> tool.</p>
  </div>
  <div class="card refl">
    <p><b>3. "The heat is out at the Chapel Street shop."</b> Facilities was designed to handle HVAC, repairs and utilities. We found the database holds only the <code>leases</code> table (landlord, $2,400 rent, due date, empty notes). So Facilities can say "we have no record" and nothing else. It cannot log the problem, find a contractor, or pay one. And <code>invoices</code> only links to <code>vendors</code>, so a repair bill has nowhere to live.</p>
    <p><b>Tools it would need:</b> new tables for <code>maintenance_requests</code>, <code>contractors</code> and <code>utility_bills</code>; <code>log_maintenance_request(space, issue, urgency)</code>; <code>list_contractors(trade)</code>; <code>schedule_repair(request_id, contractor_id)</code> with a spending cap above which a human must approve; and contractor rows added to <code>vendors</code> so Accounting can pay them through the same <code>request_approval</code> gate. Facilities would own the first three; Accounting the payment.</p>
  </div>
</section>'''

CSS = """
  .strip { display: flex; flex-wrap: wrap; gap: 12px; margin: 0 0 16px; }
  .strip div { flex: 1 1 150px; background: #fff; border: 1px solid var(--line); border-radius: 12px; padding: 10px 14px; }
  .strip b { display: block; font: 700 22px ui-monospace, Menlo, monospace; color: var(--blue); }
  .strip span { font-size: 12px; color: var(--muted); }
  .card.refl { border-left: 5px solid var(--blue); margin-bottom: 16px; }
  .card.refl p { margin: 8px 0; }
  .card.refl.bottom { background: #f3f7fc; }
  .verdict-line { display: flex; flex-wrap: wrap; gap: 8px; align-items: center; font-size: 16px; }
  .pill { font-size: 12px; font-weight: 700; padding: 2px 10px; border-radius: 999px; }
  .pill.ok { background: #e5f4ea; color: #1f6b3a; }
  .pill.warn { background: #fff4dc; color: #8a5a00; }
  .pill.bad { background: #fde6e3; color: #8a2a22; }
  a.goto { color: var(--blue); font-weight: 700; text-decoration: underline dotted; cursor: pointer; }
  #reflection h3 { margin-top: 26px; font-size: 13px; letter-spacing: .06em; }
  #reflection table.money td, #reflection table.money th { font-size: 13.5px; }
"""

path = OUT / "desk_tickets.html"
page = path.read_text()
pat = re.compile(r'<section class="tab" id="reflection">.*?</section>', re.S)
if not pat.search(page):
    sys.exit("could not find the Reflection tab")
page = pat.sub(lambda _: page_html, page, count=1)
if ".card.refl" not in page:
    page = page.replace("</style>", CSS + "</style>", 1)
if "data-goto" not in page.split("<script>")[-1]:
    page = page.replace("  tabs.forEach(b => b.addEventListener('click', () => show(b.dataset.tab)));",
                        "  tabs.forEach(b => b.addEventListener('click', () => show(b.dataset.tab)));\n"
                        "  document.addEventListener('click', e => {\n"
                        "    const a = e.target.closest('[data-goto]');\n"
                        "    if (a) { e.preventDefault(); show(a.dataset.goto); window.scrollTo(0, 0); }\n"
                        "  });")
path.write_text(page)
print("wrote the Reflection tab:", {t: (M[t]["requests"], M[t]["tokens"], M[t]["mcp"]) for t in M}, "| hits", hit, "extras", extra)
