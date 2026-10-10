"""Build output/resolved_board.html from output/resolved_tickets.json and the screenshots in output/screens/.

Run from hw5/ after build_resolution.py and screenshot_board.py:  venv/bin/python scripts/build_board_page.py
"""
import html
import json
from pathlib import Path

OUT = Path(__file__).resolve().parent.parent / "output"
d = json.loads((OUT / "resolved_tickets.json").read_text())
esc = html.escape
money = lambda n: f"${n:,.2f}"

sections = []
for t in d["tickets"]:
    shot = OUT / "screens" / f"ticket_{t['id']}.png"
    if not shot.exists():
        raise SystemExit(f"missing screenshot {shot}")
    change = f"−{money(abs(t['cash_change']))}" if t["cash_change"] else "$0.00 (no money moved)"
    humans = "".join(
        f"<li>{esc(h['decided_by'])} {esc(h['decision'])}: {esc(h['what'])} ({money(h['amount'])})</li>" for h in t["human_approvals"])
    sections.append(f"""
  <section class="ticket" id="t{t['id']}">
    <header>
      <div><span class="no">№ {t['id']}</span><h2>{esc(t['subject'])}</h2></div>
      <span class="stamp">{esc(t['final_status']).upper()}</span>
    </header>
    <p class="outcome">{esc(t['outcome'])}</p>
    <dl>
      <dt>Agents who worked</dt><dd>{esc(", ".join(t['agents_who_worked']))}</dd>
      <dt>Left out</dt><dd>{esc(", ".join(t['agents_left_out']) or "no one")}</dd>
      <dt>Human approvals</dt><dd><ul>{humans}</ul></dd>
      <dt>Cash change</dt><dd><b>{change}</b></dd>
    </dl>
    <a href="screens/ticket_{t['id']}.png" target="_blank" title="Open full size">
      <img src="screens/ticket_{t['id']}.png" alt="The React board showing ticket {t['id']} resolved">
    </a>
  </section>""")

page = f"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="utf-8">
<title>Campus Customs: the three resolved tickets</title>
<meta name="viewport" content="width=device-width, initial-scale=1">
<style>
  :root {{ --navy:#00356b; --gold:#f2c14e; --ink:#1d2430; --muted:#68707e; --line:#ddd4bd; --green:#2f7d4f; }}
  * {{ box-sizing: border-box; }}
  body {{ margin:0; font:15px/1.5 -apple-system,'Segoe UI',system-ui,sans-serif; color:var(--ink); background:#ece5d3; }}
  .top {{ background:var(--navy); color:#fff; padding:22px 32px; border-bottom:3px solid var(--gold); }}
  .top h1 {{ margin:0; font:700 24px Georgia,serif; }}
  .top p {{ margin:6px 0 0; color:#c6d3e6; }}
  .sum {{ display:flex; gap:28px; flex-wrap:wrap; margin-top:14px; }}
  .sum div b {{ display:block; font:700 22px ui-monospace,Menlo,monospace; color:var(--gold); }}
  .sum div span {{ font-size:12px; letter-spacing:.08em; text-transform:uppercase; color:#aebfd6; }}
  nav {{ display:flex; gap:10px; padding:12px 32px 0; }}
  nav a {{ color:var(--navy); font-weight:700; text-decoration:none; padding:6px 14px; border:1.5px solid var(--navy); border-radius:999px; background:#fffdf6; }}
  main {{ max-width:1100px; margin:0 auto; padding:22px 32px 60px; }}
  .ticket {{ background:#fffdf6; border:1px solid var(--line); border-radius:14px; padding:20px 24px; margin-bottom:28px; box-shadow:0 6px 14px -8px rgba(40,30,10,.45); }}
  .ticket header {{ display:flex; justify-content:space-between; align-items:flex-start; gap:12px; }}
  .no {{ font:700 13px ui-monospace,Menlo,monospace; color:var(--navy); }}
  h2 {{ margin:2px 0 0; font:700 26px Georgia,serif; }}
  .stamp {{ border:2px solid var(--green); color:var(--green); border-radius:4px; padding:3px 12px; font-weight:800; letter-spacing:.14em; transform:rotate(-4deg); }}
  .outcome {{ font:700 17px/1.4 Georgia,serif; margin:12px 0; }}
  dl {{ display:grid; grid-template-columns:170px 1fr; gap:6px 14px; margin:0 0 16px; font-size:14px; }}
  dt {{ color:var(--muted); font-weight:700; font-size:12px; text-transform:uppercase; letter-spacing:.08em; padding-top:2px; }}
  dd {{ margin:0; }} dd ul {{ margin:0; padding-left:18px; }}
  img {{ width:100%; border:1px solid var(--line); border-radius:10px; display:block; }}
  .foot {{ color:var(--muted); font-size:13px; }}
</style>
</head>
<body>
<div class="top">
  <h1>Campus Customs: the three resolved tickets</h1>
  <p>The React board, once each ticket was resolved. Shop date {esc(d['shop_date'])}.</p>
  <div class="sum">
    <div><b>{money(d['starting_checking_balance'])}</b><span>Starting checking balance</span></div>
    <div><b>−{money(sum(l['amount'] for l in d['payment_ledger']))}</b><span>Paid out, all human-approved</span></div>
    <div><b>{money(d['ending_checking_balance'])}</b><span>Ending checking balance (matches cash_accounts)</span></div>
  </div>
</div>
<nav>{"".join(f'<a href="#t{t["id"]}">Ticket {t["id"]}</a>' for t in d["tickets"])}</nav>
<main>
{"".join(sections)}
  <p class="foot">Click a screenshot to open it full size. The comparison with the plan and the cash itemization are in desk_tickets.html; the details for each ticket are in resolved_tickets.json.</p>
</main>
</body>
</html>
"""
(OUT / "resolved_board.html").write_text(page)
print("wrote output/resolved_board.html")
