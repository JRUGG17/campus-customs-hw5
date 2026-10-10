# AI Prompt Log

## Problem 1 — Vibe Coder Prompts

### Prompt 1

```
Homework five today. We're working in there.
```

```
It looks like we're building an agent in agentic team uh, like campus customs multi-agent operations um, it's open tickets land on a board customer orders rent unpaid bills discounts shop has to handle a lot so whatever the shop needs to handle uh, we're gonna build three pieces that talk to one another an MPC server a fast API backend that has a multi-agent team and then a React dashboard. So humans can watch the agents at work and approve requests. The agent team is going to have full connectivity so any agent can delegate tasks to any other agent and this assignment we're going to be building these agents that follow. We're going to have a boss that reads each ticket, decides who should work on it, and makes final calls, an inventory that checks stock by SKU and size, spots shortfalls, figures out which vendors can restock, a accounting um, that's going to watch cash, invoices, they're going to check margins, um, prepare payments or purchase orders for final human approval, and facilities are going to handle the shop space side so looking at leases rent etc and then customer service drafts messages for customers so you got all those agents can you read those back to me
```

### Follow-up prompt 1

The first prompt described the system and the five agents but gave no data, rules, or model, and I wanted to go one problem at a time.

```
Yeah, I meant MCP. Server. And I think this is like a fresh start. But yeah,
```

```
Uh, don't do anything yet. I'm going to upload some data and then we have to go through problem by problem like before. So hang on.
```

### Follow-up prompt 2

The agent description left out the database handling, the date, and the payment safety rules.

```
our tools are gonna update the database as tickets get resolved. make copy of db file called data/campus_customs_new.db and point uh, MCP server and backend at that working copy. keep campus_customs.db untouched so we can reset when want to restart resolving the tickets

the field desk.date_today is "today" for the shop. use this date to determine what is overdue
vendor lead times come from the vendors table
Uh, vendor is not going to ship a new product while they still have an open unpaid invoice. Also, human approval is required for any payments. Keep in mind, points are going to be deducted if this is not done. If a payment is made, make sure to update the relevant table. Uh, if there's not enough cash, the pay tool must refuse. We don't want any negative balances. Cash only goes out for this homework. We didn't model revenue, so no money comes in. Before a full run to resolve the tickets, make sure to reset the database to the original values. Do not email customers or call real vendors, please. Drafts stay on the board. We're going to use our port key 8 API key for AI calls for this assignment. Use only GPT-6 Luna. So we're going to have to I guess change my ENV from five point six Luna to six Luna. We're going to work on one problem at a time. All good. Question mark.
```

### Follow-up prompt 3

The model name was ambiguous against the saved `gpt-5.6 luna` setting, so I had to confirm which one was meant.

```
we want to use gpt-6 luna from now on
```

### Follow-up prompt 4

I needed to know where the old model name actually came from, since I assumed it was in my env file.

```
Where was it using five point six Luna before? Like where was the thing telling it to do that?
```

```
like how have we known what model to use where did I originally set that up is that not in the env file
```

### Prompt 2 (Problem 1 kickoff)

The earlier replies didn't yet ask for the prompt log itself.

```
Problem one: vibe coder prompts

create AI_prompts.md that will keep a log of what i type same as always

one section for each problem and for each section include problem number and title, at least one prompt i typed, and one followup prompt if needed ( in one sentence of what was lacking after the first.)
```

## Problem 2 — Study the Campus Customs Database

### Prompt 1

```
Problem two, study the campus customs database.
open data/campus_customs.db And then look through every table and its fields. We're going to copy that original file to data/campus_customs_new.db and later problems will update that working copy uh, we want to study the three open tickets so we can see how they link to other tables so if you could help me understand that that'd be helpful then we're going to start output/harness.md And for each table, we're going to want to list the fields in one short line on why that table matters for the agents. And we'll keep growing that harness file as we go. Any questions?
```

## Problem 3 — Build the MCP Server

### Prompt 1

```
Problem three, build the MCP server.

So we're going to write an MCP server in mcp_server/ using FastMCP which will talk to data/campus_customs_new.db
And we don't need to connect or run it in this problem. Uh, every agent in this homework is going to use tools in this MCP server so we're going to add more tools later but for now we're going to write three tools we know we'll need for tickets in the database keep the names clear we're not going to invent any data only use information in the database please

in output/harness.md list each of our three MCP tools. For each tool, include which table it reads, which ticket it helps unlock, one hundred one, one hundred two, or one hundred three, and one sentence on why the tool is right for that ticket. Uh, just heads up, vague lines like reads inventory are going to score low, so we're going to want to tie the tool to a ticket.

also add short mcp_server/README.md file that will explain what the MCP server is for, which database it uses, and the three tools it has. Any questions?
```

## Problem 4 — Add the MCP Server to the Vibe Coder and Test Each Tool

### Prompt 1

```
Problem four. Add the MCP server to VibeCoder and test each tool. So in our VibeCoder, you ,we're gonna add the MCP server to the project, to the VibeCoder can call the tools.  save the connection JSON text in .mcp.json at the project root or I guess however you save local MCP server lists. with the vibe driller connected, we're going to test each of our three MCP tools. Save the evidence in output/mcp_smoke.json please And for every tool we're going to include the prompt I asked the vibe coder for the tool name and the tool output (must match values in data/campus_customs.db)

all good?
```

### Follow-up prompt 1

I had no tool calls to show yet, because the server was not loaded in the session until I restarted, and the evidence needed prompts I typed myself.

```
1. check stock: Using the campus-customs MCP tool, how many size M Basic Hoodies (CC-HOOD-NAVY) are in stock? I need it for ticket 103.
2. get invoice status: Using the campus-customs MCP tool, look up invoice 501. Who is it owed to, and is it overdue? I need it for ticket 101.
3. get lease status: Using the campus-customs MCP tool, check lease 1. How much is the rent, and how many days until it's due? I need it for ticket 102.

how r these?
```

## Problem 5 — Build the Agent Team and Grow the MCP Tools

### Prompt 1

```
Problem five, build the agent team and grow the MCP tools. So for this one, we're going to build the agentic team for campus customs using Pydantic AI. So remember our five agents, we have the boss, the inventory, accounting, facilities, and customer service. We're going to want to include prompts, models, and agent loops so they can delegate work to each other with full connectivity. Let's put those agent prompts in backend/prompts/ - one file per agent pls! put data types in backend/models.py and agent files under backend/ ( our layout can vary as long as the five roles are clear) Uh, we're going to use our port_key_API key and only GPT-6 Luna for every agent, please. I'm going to need to write each prompt in my own words with a shop rules that the agent needs. More detailed prompts that cover all aspects of an agent's work and scope are going to score higher than a short generic prompt. So I guess I'll get a little more specific here.

Um, so we're going to add any tools the agents need to the MCP server so they can work on the open tickets. Shop facts come from the MCP server over data/campus_customs_new.db Uh, be sure we're not inventing a second shop tools layer that bypasses the MCP. Uh, we're going to wire the agents so they append to output/audit_trail.json as they run. Uh, for each agent, loop step we're going to record enough to audit later. Append to this file, make sure not to wipe it each run. Do not wipe it each run. Please. In output/harness.md, We're going to list each agent and each MCP tool including the ones we add in this problem along with which table the tool uses let's also add a short safety section uh, so guardrail it's a real business would want when agents touch real customers and real money uh, plus we're going to want limits that keep our token use in check. Then update mcp_server/README.md So the tool list matches what we have now

all good?
```

### Follow-up prompt 1

The kickoff prompt asked for one prompt per agent but didn't give the boss's rules, so I gave the boss prompt in my own words.

```
Okay, here's my prompt for boss. Um, we want them to set the priority across the tickets um, so ideally doing the rent first then we pay overdue invoices and then fund restocks and discounts uh, we're going to want to delegate everything all the tasks so the audit trail shows uh, who did what uh, check the results before closing the ticket uh, we want to escalate to a human for anything involving real money any big discounts or any tasks that get stuck or pinged back and forth uh, so the boss's job is also to write the final summary for each ticket and I guess have a pretty pretty bossy direct and decisive tone never make stuff up either thanks. How's that?
```

### Follow-up prompt 2

The boss prompt was done, but Inventory's rules weren't defined yet, so I gave the Inventory agent's job in my own words.

```
Okay, so for the inventory agent, uh, let's do this. So first it's got to know the stock. So it like checks it by the size and the SKU. And then report what they have. Um, I guess it can spot when they're short on things. So compare the stock to what like a ticket says they need and then will let us know how many short they are. Um, maybe it finds the vendor too. So it picks out vendors that can then restock those items. Um, and then there's the thing about like vendors being on hold. So it is recognizing when it is on hold. Um, should report back to the boss, not make anything up. And I'm going to take a pause there for a sec.
```

### Follow-up prompt 3

The Inventory prompt didn't make clear who places orders and pays vendors, so I said Inventory reports and hands off to Accounting, which does the paying and preparing.

```
Um, and they will... Uh, I guess... Go to accounting... To pay the vendors and stuff. but it'll make reports like what we have on hand, what's needed, where we're short, what the vendors are, if there's any blocks. And then it passes off to accounting you know, what needs to be done, and then accounting can prepare that stuff, but we'll do that next.
```

### Follow-up prompt 4

The Inventory prompt covered the job but gave the agent no personality or tone, so I picked one.

```
For tone, we'll go with uh, let's see. Um, So I get pretty precise stockroom clerk. Um, who's pretty matter of fact. And doesn't have time for nonsense
```

### Follow-up prompt 5

The Inventory prompt was done, but Accounting's job wasn't defined yet, so I gave the Accounting agent's rules in my own words.

```
Okay, for the counting, we'll say, no, the accounting, not counting. Uh, here's what we'll say. Uh, I guess they watch the cash, uh, so they know the balance, what's, what's left after each payment. We said they were tracking invoices earlier. Um, it's like inventory, we'll let them know stuff. And we gotta figure out what's owed to vendors and then like what's overdue and if any vendors are on hold because of it. Uh, he's paying attention to margins. So like the cost of stocking versus the price, or cost of buying versus the price. Is that cost of goods sold, COGS? Um, just keeps track of inventory, maybe. Prepares the payments and purchases for human approval. Um, how they interact with other people, I guess, like they would uh, get the rent from facilities. Yeah, you should probably keep a spending log so they know uh, what's pending. Maybe maybe not.
```

### Follow-up prompt 6

The Accounting prompt covered the job but gave the agent no personality or tone, so I picked one.

```
tone will say uh, like social climber who like sucks up to the boss but Uh, it's pretty transparent and you can't really read a room. But still relatively competent at the job.
```

### Follow-up prompt 7

The Accounting prompt was done, but Facilities' job, its heads-up timing and its tone weren't decided yet, so I gave the Facilities agent's rules in my own words.

```
Let's think about facilities. So I guess it should let accounting know when rent is due. Maybe like it's five days before. Do we CC the boss on that email? Uh, should I keep track of other costs like utilities or repairs if they come up? I'm not sure they will. I don't know. Uh, I guess the big one is the rent. Yeah. Personality. Yeah. Like a grumpy grumpy guy. Uh, doesn't like how much rent is. Thinks the rent is too damn high. But that's life.
```

### Follow-up prompt 8

The grumpy tone in the Facilities prompt was too strong, so I asked for it to be lighter, twice.

```
Maybe you can even tone down the grumpy thing.
```

```
Or even lighter than that.
```

### Follow-up prompt 9

The first three agents were done, but Customer Service's job, who it talks to and its tone weren't defined yet, so I gave the Customer Service agent's rules in my own words.

```
Alright, customer service. Uh, let's have it handle the customer-facing tickets. Write draft replies, but don't send emails. Only keep it as drafts. Uh, I can guess talk to inventory. Figure out what's in stock. Quantity. Vendor. Lead time. Uh, counting, we talk to the them, only for uh, maybe it wouldn't, I don't know. shouldn't promise things to customers. No discounts, that has to be the human decision we said. So we need to use a list prices, not discount prices. No making stuff up. Uh, we'll do a kind of friendly warm tone uh, but maybe there's an undercurrent of like I'm tired of dealing with upset customers all day. It's not my fault. Blame the inventory guy. I don't know.
```

## Problem 6 — Plan the Three Tickets

### Prompt 1

```
Okay, problem six. Before we wire The backend, Uh, let's write down what we expect the team to do on each open ticket. So we're going to want to build output/desk_tickets.html uh, which is a page we can double click with one tab per ticket. Like 101, 102, 103 Uh, also, let's add empty cache and reflection tabs for later problems. Like leave them blank or maybe like a short coming later note for now. Um, and on each ticket tab, fill an expected section only so we're going to leave room for an actual section. We're going to fill after we've run the agents

Okay, so for each ticket's expected section, uh, we're going to write an our own words, who the boss should call first and why. All the agent delegations we expect, not boss calls everyone. Which MCP tools you expect that run to use. Uh, plans that send every specialist on every ticket score low, so we're going to compare this plan to what actually happens when our agents resolve the three tickets. Um, so a little distinction in which which specialist gets sent the tickets not just sent to everyone I guess huh.
```

### Follow-up prompt 1

My first plan only had the boss calling specialists, and the assignment asks for all the delegations we expect, so I asked whether specialists talk to each other.

```
Yeah, well, the specialists ever talk to each other?
```

### Follow-up prompt 2

The plan now had specialist-to-specialist handoffs, but I still had to confirm the flow for each ticket in my own words before it went into the page.

```
Okay, let's fill out that expected thing then. Um, so yeah, I guess at a high level for uh, um, like the ticket 101, like the boss will call inventory, then accounting, Or like inventory will get in touch with accounting. will boss get in touch with customer service who's then going to ask inventory for stock and lead time and for 102 the boss will get in touch with facilities or is it vice versa and facilities will get in touch with accounting to tell them rent's coming up for 103 I guess the boss will talk to inventory inventory goes to accounting boss will talk to accounting oh yeah
```

## Problem 7 — Backend Routes

### Prompt 1

```
Problem seven. Backend routes. Uh, so the React front-end dashboard, the next problem, is going to need a backend it can call. So in backend/main.py uh, use fast API and add routes that do the following. Please. Uh, return the three tickets and whether each is open or resolved. Take a ticket ID and run the agent team on that ticket. Return recent agent events like what each agent said, what tools they use, so that board can refresh. Uh, approve a payment or purchase after a human clicks approve, so agents only prepare the pay uh, this route is actually what changes cash. Uh, return the current checking balance from cash_accounts and then reset the database to the original values when you want to try a fresh run. Um, from the backend/ folder, start the server with uvicorn main:app --reload --port 8000

in output/harness.md uh, list each route in one line like what URL what it does
```

## Problem 8 — Agent Dashboard

### Prompt 1

```
Problem eight, agent dashboard. Build the front end dashboard in frontend/ with React, Vite, and TypeScript. Uh, the page should call the routes we built in problem seven at minimum the board should: List all three tickets. Let you pick one ticket and start the agent team on it. Show each agent and what they are saying. Or doing while the ticket runs. More ticket resolved when the run finishes. Show a short summary of what each agent did on that ticket. Let a human prove a pay or purchase when asked. Show the checking balance. It should drop after an approved pay. Please make the dashboard look good. Um, let's make a creative where you can always edit it as we go, but try and make it creative at the start. Uh, let's put some thought into it. Uh, so we're going to tell the front end of the talk to the back end at http: //localhost:8000 then on the back end a lot of the Vite page origin usually localhost colon 5173. So the browser is allowed to call those routes. And then we start the board with npm run dev

Uh, so let's open the React desk in the browser so we can pick tickets and watch agents. Uh, write output/design.md with what we chose for the dashboard look, like the layouts, how the agents read differently, how it resolved tickets and cash show up, and why. And let's also include those creative choices that make it feel special and something uh, we humans would actually enjoy using. How's that?
```

### Follow-up prompt 1

After the first run, the last ticket's restock never showed up as a slip to sign, so I asked about it, and the Accounting agent was changed to prepare the order for real even when cash is short.

```
so like i cant pay the last thing?
```

## Problem 9 — Resolve the Tickets

### Prompt 1

```
Problem nine, resolve the tickets. Before testing the agents on a full run over the three tickets, reset the working database data/campus_customs_new.db Again, so you start clean, note the starting checking balance, then run all three on the board, one on one, one on two, one on three, until each is resolved. Open output/desk_tickets.html from problem six. On each ticket tab, fill the actual section from this run. Which agents worked, what they delegated, and which tools they used. Keep your expected sections so you can compare the two. Then on the cache tab of the same output/desk_tickets.html itemize the money. So we're going to want the starting checking balance after the reset, and then for each ticket, how cash changed when that ticket resolved, and why, like which pay slash purchase, dollar amount, then ending checking balance. It must match cash underscore accounts in the working database. Uh, so wrong math is going to lose a point, even if the board shows every ticket resolved.

also save : output/resolved_tickets.json- for each ticket. ID, final status, short outcome, what each agent contributed, any human approvals,
and
output/resolved_board.html- The page you can double click with a screenshot of your React board for each resolved ticket, 101, 102, and 103. And then we're going to append real runs to output/audit_trail.json. and then finish output/harness.md So it covers tables, MCP tools, five agents, API routes, the dashboard, and safety rules, please. Can we do all of that?
```

### Follow-up prompt 1

The first run left tickets waiting on me with nothing to close them, and the chat view had several problems I only saw once I used it, so I asked about each one.

```
why 8? and why does it keep jumping to the chat and why is the chat so hard to follow and why are we tellling company things to the customer in the emails like the vendor block and why are there 3 emails at the bottom
```

### Follow-up prompt 2

The close-out step was confusing: I did not know why I had to ask the boss to close tickets, and a second rent slip for next month appeared.

```
why do i have to close out with boss. and why does another rent for the next month pop up in 102
```

### Follow-up prompt 3

After the fixes, ticket 103 still could not be resolved, because nothing was waiting for me to act on and the boss kept it open.

```
cant resplve all 3
```

### Follow-up prompt 4

Resolving tickets still took too many manual steps and I was not sure the flow matched what the assignment wanted.

```
can you fix it to make it work like it is supposed to?
```

### Follow-up prompt 5

I wanted to check that the failed attempts were in the audit trail, and found my own approvals were not being recorded there.

```
are all of the failed attempts in the audit log?
```

## Problem 10 — Reflection

### Prompt 1

```
problem 10: reflection
open output/desk_ticket.html and fill the reflection tab that I answered in our own vibe, but be detailed and thorough. So how would you evaluate the performance of the agents on each ticket? Why? For each ticket, how did the actual compare to expected? What would have been simpler as one agent with tools? And why? Describe three new problems campus customs might face that this agent team could solve with tools you built. Describe three new problems campus customs might face that this agent team could not solve and explain the tools the agents would need to solve them. So we got a tie every answer to this app and the three tickets we ran. Use ticket tabs and cache tab on the same page as our evidence. Generic AI essays without campus custom details will score low.
```
