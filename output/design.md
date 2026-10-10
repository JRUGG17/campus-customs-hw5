# Dashboard design: "The Desk"

The dashboard is the back office of Campus Customs. It is built to feel like a real desk you sit at: a blotter, paper work orders you can pick up, a till with a glowing display, and five coworkers who each talk differently. The look follows what the agents actually are (their prompts give each one a voice), and it is built so a human can see at a glance what is happening, what needs them, and what it did to the cash.

Screenshots (taken against the live backend with the real model):
[start](dashboard_1_start.png) · [signing a slip](dashboard_2_paying.png) · [after paying](dashboard_3_paid.png) · [ticket 102 after a run](dashboard_4_ticket102_run.png)

## Layout

Three columns on a wide screen, one column on a narrow one.

| Column | Holds | Why it lives there |
|---|---|---|
| **Left** | The cash till, then the ticket board | Money and the queue are the two things you glance at constantly, so they stay put at the left edge. |
| **Center** | The selected ticket and its Start button, the floor, the live feed, the run report, the drafts | This is the story of one ticket, top to bottom: what was asked, who got involved, what they said, what came of it. |
| **Right** | Pay slips | Signing is the one thing only a human can do, so it gets its own place that doesn't move while the feed scrolls. |

The center column reads in the order things happen: pick a ticket, press Start, watch the floor light up, read the conversation, then read the report. Keys 1, 2 and 3 select the tickets, so you can flip between them without the mouse.

## How the agents read differently

Each agent's messages look like the kind of paper that agent would write on, and the same colour and icon follow it everywhere (floor, feed, report). This matches the personality in each prompt, so you can tell who is talking without reading the name.

| Agent | Colour | How it reads | Why |
|---|---|---|---|
| **Boss** | Yale navy with gold | A square memo with a thick gold edge, bold text, and an ORDER label | It is bossy, direct and decisive, so it looks like a memo handed down. |
| **Inventory** | Stockroom teal | A clipboard: dashed border, a clip at the top, monospace text | A precise stockroom clerk who leads with the count. |
| **Accounting** | Ledger green | Ledger paper with ruled lines and a red margin, italic text | The social climber who sucks up to the boss; ledger paper is also where its numbers live. |
| **Facilities** | Safety orange | A work order with hazard tape across the top, condensed capitals | A practical building guy with a faint grumble. |
| **Customer Service** | Warm pink | A rounded, soft speech bubble with a tail | Friendly and warm, and the only agent whose words are meant for a customer. |

Under every message the tools an agent used appear as small coloured chips, with a one-line gist of what came back, so "Inventory looked up `check_stock` and saw qty 0" is readable without opening any JSON. A refusal shows up as a red dashed line, because a refusal is the system doing its job and you should notice it.

## The floor

A map of the five agents with a faint dotted web joining all of them. That web is the full connectivity: anyone can ask anyone. When an agent hands work to another, a coloured arrow is drawn in the sender's colour, thicker and numbered if it happens more than once. The most recent hand-off animates.

Each agent has a state you can see:
- **Working:** its ring pulses.
- **Waiting on someone:** the ring turns dashed and rotates, and the label says who.
- **Done:** a tick appears and the label says "reported back".
- **Not called:** it fades out.

Why: it answers "who is doing something right now?" in one look, and after a run the arrows show who actually talked to whom, which is the same thing the plan in `desk_tickets.html` predicted.

## How tickets resolve

Each ticket is a paper work order taped to the board, with a stamp showing its state: **OPEN**, **ON IT** (pulsing, while the team works), **RESOLVED**, or **NEEDS YOU**.

When a run finishes, the center shows a verdict card with the boss's one-line decision, what money moved or is waiting, and exactly what a person must do. Below it is a card per agent: what they said, the tools they used, how many times they were asked, and how many times they handed work on. Agents who were never called are greyed out and say "sat this one out". During the run the report fills in live, and agents who haven't been asked yet say "not called yet", not "sat out".

A choice worth stating: the dashboard shows the status the boss actually set, which is usually **NEEDS YOU** and not RESOLVED. Anything involving money or a discount is meant to wait for a human, and the boss's prompt says so. Marking a ticket "resolved" the moment the run ends would claim something the shop hasn't done yet. A ticket will show RESOLVED when the boss can close it without a person.

A ticket that has been worked can't be started again until you press **Start a fresh day**, which resets the database to the original values. The audit trail is kept, and the feed simply starts from the new day.

## How cash shows up

The balance is a till display: amber digits on a dark screen, like a shop's cash register. It never goes up in this homework, only down, and the page says so.

- **The number rolls,** like a till counting, when the balance changes.
- **A red "−$840" chip floats up** from the screen when a payment goes out, and the screen flashes briefly.
- **A bar under it** splits the money three ways: free (green), earmarked for slips that are waiting for a signature (gold stripes), and already paid out (red). Earmarking shows up before anything is paid, so you see that cash is spoken for while it is still in the account.

Why: the interesting thing about cash in this shop is the squeeze. Three tickets want money, and after rent and one invoice only a little is left. The bar makes that squeeze visible before anyone signs anything.

## How a human approves

A pay slip is a small paper slip with a perforated top. It shows the kind of payment, the ticket it came from, the amount in large type, and "Prepared by accounting. Not paid yet."

- **You sign with your name** at the top of the column, in a handwritten-style field. The Approve button stays disabled until you type one, because the backend requires a human's name.
- **Approve & pay** is the only thing on the page that moves cash. The button says the amount.
- **Decline** puts a DECLINED stamp on it and moves nothing.
- **If the payment is refused** (not enough cash, vendor still on hold), the slip stays and shows a red "Refused" with the reason, and the button becomes "Try the payment again".
- **Paid slips** get a rotated PAID stamp and "Signed by <name>", and stay on the page as a receipt.

Why: it makes the rule physical. Agents prepare a slip; only a person's signature turns it into money.

## Creative choices that make it feel special

1. **A desk, not a dashboard.** Work orders with tape and punched holes, perforated pay slips, a blotter background. It is a place that feels like a shop.
2. **Agents with voices.** The paper each one writes on matches its personality, so the conversation reads like a room of different people.
3. **The till.** The glowing display, the rolling number and the floating "−$840" give a payment weight. You feel the money leave.
4. **The floor with the dotted web.** Full connectivity is visible: you see everyone who could be asked, and the ones who were.
5. **"Sat this one out."** Greyed-out cards show the specialists a ticket didn't need. Good routing is part of the story.
6. **Draft replies stamped DRAFT · NOT SENT.** Customer messages stay on the board, and a stamp says so.
7. **Honest empty states.** "The floor is quiet." and "Nothing waiting." are written in the shop's voice.
8. **Keys 1, 2 and 3** switch tickets. **Start a fresh day** resets the whole desk.
9. **Reduced motion:** if the system asks for less movement, the animations switch off.

## How a ticket finishes (added after using it for real)

Using the first version showed that tickets were left waiting with nothing to close them, so the dashboard now finishes the loop:

- **Run the whole board** runs every open ticket in priority order (rent, the customer order, then the discount request), one after another.
- **Signing or declining the last slip on a ticket hands it back to the boss automatically.** The boss re-checks and resolves it, or prepares what the payment unblocked. Paying an invoice also re-checks tickets that were stuck behind a vendor.
- **The decision box.** When a ticket is waiting on a human and has no slip, a box says "Waiting on you" and lets you state your decision in your own words (for example "No discount, the list price stands"). The boss acts on it and records it.
- **The chat is quiet by default.** Orders, reports and refusals show; each agent's lookups fold into one line, with a "show every lookup" checkbox. The chat box scrolls by itself without moving the page.
- **Your own actions appear in the story:** each approval, decline, payment and refusal is a line in the feed.

## How it talks to the backend

The page runs at http://localhost:5173 and calls the FastAPI routes at http://localhost:8000 directly. The backend allows that origin through CORS. While a run is going the page refreshes about every second, otherwise every few seconds. A run starts in the background, and the page follows its events as they arrive.

Everything uses the same routes from Problem 7: tickets, run, events, approvals, cash and reset. The page adds no data of its own.

## Easy to change

The look lives in one stylesheet (`frontend/src/styles.css`), the agent colours, labels and icons in `frontend/src/agents.tsx`, and how each event is turned into a message in `frontend/src/lib.ts`. Changing a colour, a label or a voice is a small edit in one of those.
