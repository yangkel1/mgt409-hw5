# AI_prompts.md

Log of the prompts I typed into my vibe coder (Claude Code) while building HW5, with one
section per problem. Spelling and grammar in my prompts have been corrected for
readability, and the intent of each prompt is unchanged. My real Portkey API key never
appears here. It lives only in `.env`, which is excluded from the repo.

**Project:** Campus Customs Multi-Agent Operations. An MCP server, a FastAPI backend with
a five-agent team (Boss, Inventory, Accounting, Facilities, Customer Service) on
`gpt-6-luna` through Portkey, and a React dashboard for watching agents and approving
requests.

---

## Setup: scenario, data, and submission

*(Before the numbered problems: giving the vibe coder the scenario and the required repo
layout.)*

**Prompt 1**

> New AI homework. See the instructions attached. Push my code to a public GitHub
> repository so graders can clone it. I'll submit the repo URL to Canvas and also put it
> in `output/github_url.txt`. Do not push the real `.env` to the GitHub repo. Do include
> both database files under `data/` (the original and the working copy) so graders can
> run the app easily. The expected file layout and additional instructions are attached.
>
> *(attached: the HW5 scenario, data, and shop rules section, plus the expected `hw5/`
> file tree.)*

*What was lacking after the first:* no HW5 code or HW5 `data.zip` existed on disk yet
(the `HW 5` folder was empty), so there was nothing to push. I had to start the work
problem by problem instead.

---

## Problem 1: Vibe coder prompts

**Prompt 1**

> Problem 1: vibe coder prompts. Create `AI_prompts.md` at the start of the assignment
> and keep it updated as you work. This file is the log of what I typed into the vibe
> coder. Put one section for each problem. Each section must include the problem number
> and title, at least one prompt I typed, and one follow-up if needed (with one sentence
> on what was lacking after the first).

*Follow-up:* none needed. The file was created with this structure on the first try.

---

## Problem 2: Study the Campus Customs database

**Prompt 1**

> I downloaded the `data.zip` file and it should be in the Downloads folder. Problem 2:
> study the Campus Customs database. Open `data/campus_customs.db` and look through every
> table and its fields. Copy the original file to `data/campus_customs_new.db`; later
> problems update that working copy. Study the three open tickets so you can see how they
> link to the other tables. Start `output/harness.md`. For each table, list the fields
> and one short line on why that table matters for the agents. You will keep growing this
> harness file in later problems.

*Follow-up:* none needed. The zip had auto-extracted to `Downloads/data-2/`, and the
vibe coder found it, copied it in, and wrote the harness on the first try.

---

## Problem 3: Build the MCP server

**Prompt 1**

> Problem 3: build the MCP server. Write an MCP server in `mcp_server/` using FastMCP. It
> will talk to `data/campus_customs_new.db`. You do not need to connect or run it in this
> problem. Every agent in this homework uses the tools in this MCP server, and I'll add
> more tools later. For now, write 3 tools you know you'll need for the tickets in the
> database. Keep the names clear and never invent data; only use info in the database.
> In `output/harness.md`, list each of the 3 MCP tools. For every tool, include which
> table it reads, which ticket it helps unlock (101, 102, or 103), and one sentence on
> why that tool is the right one for the ticket. Vague lines like "reads inventory" score
> low, so tie each tool to its ticket. Also add a short `mcp_server/README.md` that
> explains what the MCP server is for, which database file it uses, and its 3 tools.

*Follow-up:* none needed. The latest `mcp` package (2.x) renamed FastMCP, so the vibe
coder pinned `mcp<2` to keep FastMCP as the assignment asks.

---

## Problem 4: Add the MCP server to the vibe coder and test each tool

**Prompt 1**

> Problem 4: add the MCP server to the vibe coder and test each tool. Add the MCP server
> to this project so the vibe coder can call the tools. Save the connection JSON in
> `.mcp.json` at the project root (or wherever the vibe coder saves local MCP server
> lists). With the vibe coder connected, test each of the 3 MCP tools. Save the evidence
> in `output/mcp_smoke.json`. For every tool, include the prompt I asked the vibe coder,
> the tool name, and the tool output (which must match the values in
> `data/campus_customs_new.db`).

**Smoke-test prompts** (one per tool, sent to the vibe coder with the MCP server connected)

> Ticket 101 wants 1 Classic Bulldog Tee (CC-TEE-WHITE) in size S. Use the
> campus-customs MCP tools to check stock and tell me the shortfall.

> Ticket 101 is linked to invoice 501. Use the campus-customs MCP tools to check that
> invoice: is it overdue, and is the vendor blocked from shipping?

> Ticket 102 is a rent notice for lease 1. Use the campus-customs MCP tools to check the
> rent, when it is due, and whether checking can cover it.

*Follow-up:* none needed. Every tool returned values that matched the database. One
side effect: the vibe coder also tried to add its own entry to this log during the first
test, but that write failed, so this file was not changed.

---

## Problem 5: Build the agent team and grow the MCP tools

**Prompt 1**

> Problem 5: build the agent team and grow the MCP tools. Build the agentic team for
> Campus Customs using PydanticAI: Boss, Inventory, Accounting, Facilities, and Customer
> Service. Include prompts, models, and an agent loop so they can delegate work to each
> other with full connectivity. Put the agent prompts in `backend/prompts/`, one file per
> agent. Put data types in `backend/models.py` and the agent files under `backend/` (the
> layout can vary as long as the 5 roles are clear). Use my `PORTKEY_API_KEY` and only
> `gpt-6-luna` for every agent. Write each prompt in my own words with the shop rules that
> agent needs. More detailed prompts that cover all aspects of an agent's work and scope
> score higher than a short generic prompt. Add any tools the agents need to the MCP
> server so they can work on the open tickets. Shop facts come from the MCP server over
> `data/campus_customs_new.db`; do not invent a second shop tools layer that bypasses
> MCP. Wire the agents so they append to `output/audit_trail.json` as they run: for each
> agent loop step, record enough to audit later. Append to this file; do not wipe it each
> run. In `output/harness.md`, list each agent and each MCP tool (including ones added in
> this problem), along with each table the tool uses. Also add a short safety section:
> the guardrails a real business would want when agents touch real customers and real
> money, plus limits that keep token use in check. Update `mcp_server/README.md` so the
> tool list matches what we have now.

*What was lacking after the first:* the first live test failed. Portkey's `gpt-6-luna`
deployment rejects function tools on the Chat Completions endpoint while reasoning is
on, so the agents were switched to the Responses API (same model). PydanticAI 2.x also
needs `mcp` 2.x, which drops the old built-in FastMCP, so the server moved to the
standalone `fastmcp` package. After both fixes, ticket 102 ran end to end.

---

## Problem 6: Plan the three tickets

**Prompt 1**

> Problem 6: plan the three tickets. Before wiring the backend, write down what I expect
> the team to do on each open ticket. Build `output/desk_tickets.html`, a page I can
> double-click, with one tab per ticket (101, 102, 103). Also add empty Cash and
> Reflection tabs for later problems (blank or with a short "coming later" note for now).
> On each ticket tab, fill in an Expected section only, and leave room for an Actual
> section to fill in after running the agents. For each ticket's Expected section, write
> in my own words: who the Boss should call first and why, all the agent delegations I
> expect (not "Boss calls everyone"), and which MCP tools I expect that run to use. Plans
> that send every specialist on every ticket score low. I'll compare this plan to what
> actually happens when the agents resolve the 3 tickets.

*Follow-up:* none needed. (I typed `desl_tickets.html`; the vibe coder used
`desk_tickets.html` to match the expected file layout.)

---

## Problem 7: Backend routes

**Prompt 1**

> Problem 7: backend routes. The React frontend dashboard (next problem) needs a backend
> it can call. In `backend/main.py`, use FastAPI and add routes that: return the three
> tickets and whether each is open or resolved; take a ticket id and run the agent team
> on that ticket; return recent agent events (what each agent said and which tools it
> used) so the board can refresh; approve a payment or purchase after a human clicks
> approve (agents only prepare the payment; this route is what actually changes cash);
> return the current checking balance from `cash_accounts`; and reset the database to the
> original values for a fresh run. From the `backend/` folder, start the server with
> `uvicorn main:app --reload --port 8000`, which turns on the backend at
> `http://localhost:8000` so the dashboard can call those routes. In `output/harness.md`,
> list each route in one list (URL and what it does).

*What was lacking after the first:* port 8000 was already taken by my HW4 backend, which
was still running, so the routes were tested on port 8001. A re-run of ticket 102 also
came back in 9 seconds with token counts identical to an earlier run (Portkey was
replaying cached responses), so the agents now ask Portkey for a fresh response on every
call.

---

## Problem 8: Agent dashboard

**Prompt 1**

> If HW5 needs the port, then stop the server; finishing HW5 is the main priority.
> Problem 8: agent dashboard. Build the frontend dashboard in `frontend/` with React +
> Vite + TypeScript. The page should call the routes built in Problem 7. At minimum, the
> board should: list all 3 tickets; let me pick one ticket and start the agent team on it;
> show each agent and what it's saying or doing while the ticket runs; mark a ticket
> resolved when the run finishes; show a short summary of what each agent did on that
> ticket; let a human approve a payment or purchase when asked; and show the checking
> balance (it should drop after an approved payment). Make the dashboard look good. Be
> creative with the layout and feel; this is a real desk people would want to sit at, so
> put thought into how it looks. Tell the frontend to talk to the backend at
> `http://localhost:8000`. On the backend, allow the Vite page origin (usually
> `http://localhost:5173`) so the browser can call those routes. `npm run dev` runs the
> React desk in the browser so I can pick tickets and watch agents. Write
> `output/design.md` with what I chose for the dashboard look (layout, how agents read
> differently, how resolved tickets and cash show up) and why, including the creative
> choices that make it feel special and something people would actually enjoy using.

*What was lacking after the first:* the Boss ended runs as `waiting_on_approval`, so no
ticket ever showed as resolved when its run finished. The Boss now ends a run as
`resolved` (approvals stay in the tray) or `escalated`. Screenshot checks also caught a
race that appended events twice (feed out of order) and a stale pre-reset run showing on
a fresh ticket; both were fixed. Ports 8000 and 5173 were held by my old HW4 servers,
which were stopped.

---

## Problem 9: Resolve the tickets

**Prompt 1**

> Problem 9: resolve the tickets. Before testing the agents on a full run over the 3
> tickets, reset the working database `data/campus_customs_new.db` again so I start clean.
> Note the starting checking balance. Then run all 3 tickets on the board (101, 102, 103)
> until each is resolved. Open `output/desk_tickets.html` from Problem 6. On each ticket
> tab, fill in the Actual section from this run: which agents worked, what they delegated,
> and which tools they used. Keep the Expected section so I can compare the two. In the
> Cash tab of the same page, itemize the money: the starting checking balance (after the
> reset), how cash changed when each ticket resolved and why (which payment or purchase,
> and the dollar amount), and the ending checking balance, which must match
> `cash_accounts` in the working database. Wrong cash math loses points even if the board
> shows every ticket resolved. Also save `output/resolved_tickets.json` (for each ticket:
> id, final status, short outcome, what each agent contributed, and any human approvals)
> and `output/resolved_board.html` (a page I can double-click with a screenshot of my
> React board for each resolved ticket). Append real runs to `output/audit_trail.json`.
> Finish `output/harness.md` so it covers tables, MCP tools, the 5 agents, API routes, the
> dashboard, and safety rules.

**Follow-up** (the vibe coder asked how human approvals should happen in the graded run)

> Approve as Kelly Yang.

*What was lacking after the first:* ticket 103 came back `escalated`, not resolved,
because the 12-hoodie restock ($264) cost more than the $160 left after the first two
payments, and the team had no way to take a human's business decision (only payment
approvals). A human-decision route and dashboard box were added. Kelly Yang chose the
partial offer for the 8 on hand, the decision was posted to the board, and the Boss
carried it out and resolved 103. Final checking: $3,400 → $160.

---

## Problem 10: Reflection

**Prompt 1**

> Problem 10: reflection. Open `output/desk_tickets.html` and fill in the Reflection tab.
> Answer in my own voice, detailed and thorough, with a thoughtful Yale SOM student vibe.
> How would I evaluate the agents' performance on each ticket, and why? For each ticket,
> how did the actual run compare to the expected plan I wrote earlier? What would have
> been simpler as one agent with tools, and why? Describe 3 new problems Campus Customs
> might face that this agent team could solve with the tools I built. Describe 3 new
> problems it could not solve with those tools, and explain the tools and agents I would
> need to solve them. Tie every answer to this app and the 3 tickets I ran. Use the ticket
> tabs and the Cash tab on the same page as evidence. Generic AI essays without Campus
> Customs details will score low.

*Follow-up:* none needed. (I typed `desl_tickets.html`; the reflection went into
`desk_tickets.html`, the same page as the ticket and Cash tabs.)

---

## Submission: public GitHub repo and final checks

**Prompt 1** (from the start of the assignment)

> Push my code to a public GitHub repository so graders can clone it. I'll submit the repo
> URL to Canvas and also put it in `output/github_url.txt`. Do not push the real `.env` to
> the GitHub repo. Do include both database files under `data/` (the original and the
> working copy) so graders can run the app easily.

**Follow-up**

> What's your confidence level of completing this assignment, and what issues still need
> resolving? … Yes, fix the items.

*What was lacking after the first:* the root `README.md` was missing,
`output/mcp_smoke.json` predated the move to FastMCP 4, and nothing had been tested from a
clean clone. The vibe coder wrote the README, re-ran the smoke test through `.mcp.json`
(all outputs match the DB), confirmed the real key isn't in any committed file, pushed the
public repo, and installed and ran it from a fresh clone.
