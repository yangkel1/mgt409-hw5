# Campus Customs Multi-Agent Operations (MGT 409 HW5)

An agent team runs the Campus Customs shop desk. It has three parts that talk to each other:

- **MCP server** (`mcp_server/server.py`, FastMCP): the only tool layer. It has 19 tools
  over the shop's SQLite database, and payments need a human approver.
- **FastAPI backend** (`backend/`): five PydanticAI agents (Boss, Inventory, Accounting,
  Facilities, Customer Service) on **`gpt-6-luna` via Portkey**, with full delegation
  between agents and an append-only audit trail.
- **React dashboard** (`frontend/`, Vite + TypeScript): pick a ticket, watch the agents
  work, approve payments, and see the checking balance drop.

The design, tools, routes, safety rules, and results are documented in
[`output/harness.md`](output/harness.md).

## Requirements

- Python 3.11+ and Node 20+
- A Portkey API key with access to `gpt-6-luna`

## 1. Setup (one time)

```bash
cd hw5
python3 -m venv .venv
.venv/bin/pip install -r requirements.txt

cp .env.example .env        # then set PORTKEY_API_KEY=... in .env (never commit .env)

cd frontend && npm install && cd ..
```

## 2. Copy the original DB to the working copy (clean run)

`data/campus_customs.db` is the original shop database and is never modified.
Everything reads and writes the working copy `data/campus_customs_new.db`. Copy the
original over it whenever you want a clean run:

```bash
cp data/campus_customs.db data/campus_customs_new.db
```

> The repo ships `campus_customs_new.db` in its **finished** state from the graded run
> (all 3 tickets resolved, checking $160). Copy the original over it before a new run.

## 3. Start the MCP server

The backend starts the MCP server for you as a stdio subprocess, so for the app you can
skip ahead to step 4. To run it on its own:

```bash
.venv/bin/python mcp_server/server.py
```

To give a vibe coder (Claude Code) the tools, open this folder in it. `.mcp.json`
registers the `campus-customs` server (approve it once when prompted).

## 4. Start the FastAPI backend

```bash
cd backend
../.venv/bin/uvicorn main:app --reload --port 8000
```

The backend runs at http://localhost:8000 (interactive docs at `/docs`). Agents can also
be run from the command line in `hw5/` with `.venv/bin/python -m backend.agents --ticket 101`.

## 5. Start the React board

In a second terminal:

```bash
cd frontend
npm run dev
```

Open http://localhost:5173. The board calls the backend at `http://localhost:8000`, and
the backend allows that origin through CORS.

## 6. Reset the DB before a full three-ticket run

Before resolving all three tickets, reset to the original values, using any one of:

- the **Reset desk** button on the board,
- `curl -X POST http://localhost:8000/api/reset`, or
- `cp data/campus_customs.db data/campus_customs_new.db` (with the backend stopped).

Then send tickets **101 → 102 → 103** to the team in order, approve the payments the
agents queue in the approval tray (sign with your name), and answer an escalated ticket
in its decision box if the team asks you to.

## Layout

```
hw5/
├── AI_prompts.md           prompts typed into the vibe coder, one section per problem
├── requirements.txt  .env.example  .gitignore  .mcp.json  README.md
├── data/                   campus_customs.db (original) · campus_customs_new.db (working copy)
├── mcp_server/             server.py · README.md
├── backend/                main.py (FastAPI) · agents.py · audit.py · models.py · prompts/*.md
├── frontend/               React + Vite + TypeScript dashboard
└── output/                 harness.md · mcp_smoke.json · desk_tickets.html · design.md
                            resolved_tickets.json · resolved_board.html · audit_trail.json · github_url.txt
```

## Shop rules the code enforces

- "Today" is `desk.date_today` (2026-08-31).
- Every payment needs human approval. Agents can only queue them; amounts come from the DB.
- No negative balances: the pay tool refuses.
- A vendor with an open invoice won't ship.
- Customer, vendor, and landlord messages are drafts on the board and are never sent.
- Only `gpt-6-luna` is used, for every agent.
