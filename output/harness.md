# Harness: Campus Customs Multi-Agent Operations

This file is the working notes the agent team relies on. It grows with each problem.

- **Original DB (never modified):** `data/campus_customs.db`
- **Working copy (agents and tools write here):** `data/campus_customs_new.db`
- **Reset:** `cp data/campus_customs.db data/campus_customs_new.db`

**Contents:** 1 Tables · 2 Original data · 3 Tickets and links · 4 First 3 tools ·
5 MCP connection · 6 The 5 agents · 7 All 19 MCP tools · 8 Safety · 9 API routes ·
10 Dashboard · 11 Graded full run · 12 How to run it

---

## 1. Database tables

### `desk`: shop clock (1 row)
| Field | Type | Notes |
|---|---|---|
| `date_today` | TEXT | "Today" for the shop: **2026-08-31** |
| `notes` | TEXT | Free-form desk notes (empty) |

**Why it matters:** every agent must use `date_today` (not the real date) to decide what is overdue or coming due.

### `tickets`: the work board (3 rows, all `open`)
| Field | Type | Notes |
|---|---|---|
| `id` | INTEGER PK | 101, 102, 103 |
| `type` | TEXT | `customer_order`, `rent_notice`, `price_override` |
| `requester` | TEXT | Customer, landlord, or student org |
| `subject` | TEXT | Short title |
| `sku`, `size`, `qty` | TEXT/TEXT/INT | Product request (links to `inventory` / `pricing`) |
| `lease_id` | INTEGER FK → `leases.id` | Set on rent tickets |
| `invoice_id` | INTEGER FK → `invoices.id` | Set when an unpaid bill is tied to the ticket |
| `status` | TEXT | `open` → resolved by the team |
| `notes` | TEXT | Original request text |
| `created_at` | TEXT | ISO timestamp |

**Why it matters:** this is the Boss's inbox. It reads each ticket, routes it to the right specialist, and the foreign keys tell agents which other tables to pull.

### `inventory`: stock by SKU and size (10 rows)
| Field | Type | Notes |
|---|---|---|
| `sku` | TEXT | PK part 1 |
| `name` | TEXT | Product name |
| `size` | TEXT | PK part 2 (`S/M/L/XL` or `OS`) |
| `qty` | INTEGER | On-hand units |
| `location` | TEXT | Aisle |

**Why it matters:** Inventory agent checks whether a ticket can be filled now and computes shortfalls (`requested qty − on-hand qty`).

### `pricing`: cost and list price per SKU (4 rows)
| Field | Type | Notes |
|---|---|---|
| `sku` | TEXT PK | |
| `unit_cost` | REAL | What the shop pays the vendor |
| `list_price` | REAL | What the customer normally pays |

**Why it matters:** Accounting uses it to check margins on discount requests and to price restock purchase orders (`shortfall × unit_cost`).

### `vendors`: who can restock (3 rows)
| Field | Type | Notes |
|---|---|---|
| `id` | INTEGER PK | |
| `name` | TEXT | |
| `specialty` | TEXT | What they supply |
| `lead_days` | INTEGER | Shipping lead time (rule: lead times come only from here) |

**Why it matters:** Inventory matches a SKU to a vendor by specialty and gives a realistic restock date (`date_today + lead_days`).

### `leases`: shop space (1 row)
| Field | Type | Notes |
|---|---|---|
| `id` | INTEGER PK | |
| `space_name` | TEXT | |
| `landlord` | TEXT | |
| `monthly_rent` | REAL | |
| `next_due` | TEXT | Next rent due date |
| `notes` | TEXT | |

**Why it matters:** Facilities reads rent amount and due date. After an approved rent payment, `next_due` should move forward one month.

### `cash_accounts`: available cash (1 row)
| Field | Type | Notes |
|---|---|---|
| `name` | TEXT PK | `checking` |
| `balance` | REAL | **$3,400.00** |
| `date` | TEXT | As-of date |

**Why it matters:** the pay tool must refuse any payment larger than this balance (no negative balances). Cash only goes out, so it is a fixed budget that all three tickets share.

### `payments`: payment ledger (0 rows)
| Field | Type | Notes |
|---|---|---|
| `id` | INTEGER PK | |
| `kind` | TEXT | e.g. `invoice`, `rent` |
| `ref_id` | INTEGER | ID of the invoice or lease being paid |
| `amount` | REAL | |
| `account` | TEXT | Cash account debited |
| `paid_at` | TEXT | Date paid |
| `approved_by` | TEXT | The human approver (required for every payment) |

**Why it matters:** audit trail for every outgoing dollar. A row is written only after human approval, together with the balance decrease and the invoice or lease update.

### `invoices`: vendor bills (1 row)
| Field | Type | Notes |
|---|---|---|
| `id` | INTEGER PK | |
| `vendor_id` | INTEGER FK → `vendors.id` | |
| `amount` | REAL | |
| `due_date` | TEXT | |
| `status` | TEXT | `open` / `paid` |
| `description` | TEXT | |

**Why it matters:** an open invoice blocks that vendor from shipping. Accounting must flag overdue ones (`due_date < date_today`) and queue them for approval.

---

## 2. Original data snapshot (date_today = 2026-08-31, before any run)

| Item | Value |
|---|---|
| Cash (checking) | $3,400.00 |
| Invoice 501 | Bulldog Print Co, $840.00, due 2026-08-28, **open, 3 days overdue**: "Rush reprint CC-TEE-WHITE S" |
| Lease 1 | Chapel Street shop, Elm City Properties, $2,400.00, due **2026-09-02** (in 2 days) |
| CC-TEE-WHITE | S **0**, M 5, L 3, XL 2 · cost $8 / list $28 |
| CC-HOOD-NAVY | S 4, **M 8**, L 14, XL 6 · cost $22 / list $58 |
| CC-HAT-BLUE / CC-MUG-CREST | OS 40 / OS **0** |
| Vendors | 1 Bulldog Print Co (apparel reprint, 5 days) · 2 Elm City Gifts (mugs/small goods, 3 days) · 3 QuickShip CT (courier, 1 day) |

---

## 3. The three open tickets and how they link

### Ticket 101: `customer_order` (Tauhid Zaman, Bulldog tee, CC-TEE-WHITE size S × 1)
- **Links:** `inventory` (CC-TEE-WHITE, S) → `invoices` 501 (via `invoice_id`) → `vendors` 1 (via `invoice.vendor_id`).
- **What the data shows:** size S has **0** on hand. A rush reprint for this exact item is already billed on invoice 501, but that invoice is **open and overdue**, so Bulldog Print Co won't ship.
- **Agents:** Inventory (shortfall 1, vendor 1, 5-day lead) → Accounting (queue $840 invoice payment for human approval) → Customer Service (draft a delay/ETA message for the customer).

### Ticket 102: `rent_notice` (Elm City Properties, rent due)
- **Links:** `leases` 1 (via `lease_id`) → `cash_accounts`.
- **What the data shows:** $2,400 due 2026-09-02. Cash is $3,400, so rent is affordable on its own.
- **Agents:** Facilities (confirm lease, amount, due date) → Accounting (queue $2,400 rent payment for human approval; on approval, update `cash_accounts`, `payments`, and move `leases.next_due` to 2026-10-02).

### Ticket 103: `price_override` (Yale AI Club, 20 × CC-HOOD-NAVY M, wants a bulk discount)
- **Links:** `inventory` (CC-HOOD-NAVY, M) → `pricing` (CC-HOOD-NAVY) → `vendors` (apparel → Bulldog Print Co).
- **What the data shows:** only **8** size M on hand, so the shortfall is **12**. Margin at list price is $36/unit (62%), so there's room for a discount but it must stay above the $22 cost. Restock would come from Bulldog Print Co, which is **blocked by open invoice 501**, and a 12-unit PO costs 12 × $22 = **$264**.
- **Agents:** Inventory (shortfall + vendor + lead time) → Accounting (margin check on the proposed discount, PO cost) → Boss (final call on the discount) → Customer Service (draft a quote for the club).

### Cross-ticket constraint: shared cash
Invoice 501 ($840) + rent ($2,400) = $3,240, leaving **$160**, which isn't enough for the $264 hoodie PO. The tickets compete for the same cash, and paying invoice 501 is the prerequisite for any Bulldog Print Co shipment (tickets 101 and 103). The Boss has to sequence these, and the pay tool must refuse anything that would overdraw the balance.

---

## 4. First three MCP tools (Problem 3)

Section 7 has the full, current tool list.

All tools read `data/campus_customs_new.db`, use `desk.date_today` as "today", and return
`found: false` instead of guessing when a row is missing.

| # | Tool | Tables read | Unlocks ticket | Why it's the right tool for the ticket |
|---|---|---|---|---|
| 1 | `check_stock(sku, size, qty_needed)` | `inventory`, `pricing` | **101** (CC-TEE-WHITE S × 1) and **103** (CC-HOOD-NAVY M × 20) | Both tickets ask for a specific SKU, size, and quantity, so the agents need one call that returns on-hand qty, the shortfall, and unit cost / list price. It shows tee S is 0 (short 1) and hoodie M is 8 (short 12, $22 cost vs $58 list for the discount margin). |
| 2 | `get_invoice_status(invoice_id)` | `invoices`, `vendors`, `desk` | **101** (via `invoice_id` 501), which also gates **103**'s restock | Ticket 101 links straight to invoice 501, and the tool shows it is $840, 3 days overdue, and owed to Bulldog Print Co, so that vendor is blocked from shipping the tee (and any hoodie restock) until a human approves payment. |
| 3 | `get_lease_and_cash(lease_id)` | `leases`, `cash_accounts`, `desk` | **102** (via `lease_id` 1) | The rent notice is only actionable once you know the amount, the due date relative to the shop's today, and whether cash covers it. This one call shows $2,400 due in 2 days against $3,400 in checking ($1,000 left after rent). |

---

## 5. MCP connection and smoke test

- **Config:** `.mcp.json` at the `hw5/` root registers the `campus-customs` stdio server
  (`.venv/bin/python mcp_server/server.py`). The paths are relative, so launch the vibe
  coder from `hw5/`.
- **Evidence:** `output/mcp_smoke.json`. It has two runs: the original Problem 4 run (checked against the original DB) and a re-run after the graded full run on the current FastMCP 4 server (checked against the finished working DB). Calls to tools outside the allowed three were denied. The vibe coder (Claude Code) called each tool
  once with a ticket-specific prompt, and every output was cross-checked against a direct
  SQL query on `data/campus_customs_new.db` (all match).

| Tool | Ticket | Key values returned |
|---|---|---|
| `check_stock` | 101 | CC-TEE-WHITE S: qty 0, shortfall 1, $8 cost / $28 list |
| `get_invoice_status` | 101 (→103) | Invoice 501: $840, due 2026-08-28, 3 days overdue, Bulldog Print Co blocked |
| `get_lease_and_cash` | 102 | Lease 1: $2,400 due 2026-09-02 (2 days), checking $3,400, $1,000 left after rent |

---

## 6. Agent team (`backend/agents.py`, prompts in `backend/prompts/`)

All five agents are PydanticAI agents on **`gpt-6-luna` through Portkey** (Responses API).
`MODEL_NAME` is defined once in `backend/agents.py` and no other model appears in the
code. The provider reports the deployment as `gpt-6-luna-global` in responses. Shop facts
come only from the MCP server. The one local tool is `delegate(to_agent, task)`, which
gives **full connectivity**: any agent can hand a brief to any other agent and get its
report back.

| Agent | Prompt | Job | Output type | MCP tools it can call |
|---|---|---|---|---|
| **Boss** | `boss.md` | Reads each ticket, routes it, sets cash priority, makes the discount call, sets the final status | `TicketResolution` | `get_desk_today`, `list_open_tickets`, `get_ticket`, `get_ticket_board`, `get_cash_position`, `list_payment_requests`, `post_board_note`, `update_ticket_status` |
| **Inventory** | `inventory.md` | Stock by SKU and size, shortfalls, which vendor restocks, arrival date, vendor blocks | `AgentReport` | `get_desk_today`, `get_ticket`, `get_ticket_board`, `check_stock`, `list_vendors`, `get_invoice_status`, `post_board_note` |
| **Accounting** | `accounting.md` | Cash and invoices, margin checks, **queues** payments and POs for human approval | `AgentReport` | `get_desk_today`, `get_ticket`, `get_ticket_board`, `check_stock`, `list_vendors`, `get_invoice_status`, `list_open_invoices`, `get_lease_and_cash`, `get_cash_position`, `quote_margin`, `list_payment_requests`, `request_payment`, `create_purchase_order`, `post_board_note` |
| **Facilities** | `facilities.md` | Lease, rent, due dates, landlord draft; asks Accounting to queue rent | `AgentReport` | `get_desk_today`, `get_ticket`, `get_ticket_board`, `get_lease_and_cash`, `get_cash_position`, `post_board_note` |
| **Customer Service** | `customer_service.md` | Drafts customer messages from tool facts only; never sends | `AgentReport` | `get_desk_today`, `get_ticket`, `get_ticket_board`, `check_stock`, `quote_margin`, `list_vendors`, `post_board_note` |

**Loop:** `run_ticket(id)` starts the Boss, which uses `agent.iter()` and calls tools and
`delegate` until it returns a `TicketResolution`. Each delegate runs the target agent's own
loop with the same deps and the same usage counter, and returns its `AgentReport` as JSON.
`--all` works open tickets oldest first, one at a time, so later tickets see earlier
tickets' pending requests in the cash math.

**How a run ends:** the Boss's `TicketResolution.final_status` can only be `resolved` (the
team's part is done; payments may still wait in the approval tray) or `escalated` (a human
must decide). If the Boss forgets to record it, `run_ticket` records it through the MCP
`update_ticket_status` tool (`final_status_recorded` event). If a ticket is escalated, a
person posts a decision (`POST /api/tickets/{id}/human-decision`), which writes a `decision`
note authored `human:<name>` and reopens the ticket. The Boss prompt treats that note as
binding on the next run (this is what resolved 103).

**Data types (`backend/models.py`):** `AgentName`, `TicketStatus`, `AgentReport`,
`TicketResolution`, `AuditEvent`, `TicketRunResult`, `PaymentDecision`.

**Audit trail (`output/audit_trail.json`):** one JSON array, appended (load, append,
atomic replace) and never wiped. A file that can't be parsed is renamed aside, not
deleted. Each event records `ts`, `run_id`, `ticket_id`, `agent`, `depth`, `chain`
(e.g. `boss -> accounting`), `step`, and `event`, plus details:
- `run_start` / `run_end`: model, limits, final ok/error, and total tokens, requests, and tool calls
- `agent_start`: the brief and the agent's allowed tools
- `model_response`: text, tool calls with arguments, reasoning size, model name, and token usage
- `model_request`: tool results (truncated at 2,000 chars) and retry prompts
- `delegation` / `delegation_refused`: target, brief, count, or refusal reason
- `identity_stamped`: a model tried to sign as someone else and was corrected
- `agent_end` / `agent_error`, and `human_decision` for approve and reject actions

---

## 7. All MCP tools and the tables they use (19 tools)

| Tool | Group | Tables read | Tables written | Ticket(s) it serves |
|---|---|---|---|---|
| `get_desk_today` | read | `desk` | none | all (overdue math) |
| `list_tickets` | read | `tickets` | none | dashboard (all tickets, open + resolved; backend only) |
| `list_open_tickets` | read | `tickets` | none | all (board) |
| `get_ticket` | read | `tickets`, `leases`, `invoices`, `vendors` | none | all |
| `check_stock` | read | `inventory`, `pricing` | none | 101 (tee S = 0), 103 (hoodie M = 8, short 12) |
| `list_vendors` | read | `vendors`, `invoices`, `desk` | none | 101, 103 (Bulldog Print Co blocked, 5-day lead) |
| `get_invoice_status` | read | `invoices`, `vendors`, `desk` | none | 101 (invoice 501, 3 days overdue) |
| `list_open_invoices` | read | `invoices`, `vendors`, `desk` | none | 101, 103 (all bills competing for cash) |
| `get_lease_and_cash` | read | `leases`, `cash_accounts`, `desk` | none | 102 ($2,400 due 2026-09-02) |
| `get_cash_position` | read | `cash_accounts`, `payment_requests`, `payments` | none | all (shared $3,400 budget) |
| `quote_margin` | read | `pricing` | none | 103 (discount vs $22 cost / $58 list) |
| `list_payment_requests` | read | `payment_requests` | none | all |
| `get_ticket_board` | read | `tickets`, `board_notes`, `payment_requests`, `purchase_orders` | none | all (avoid duplicate work) |
| `post_board_note` | board | `tickets` | `board_notes` | all (findings, customer/landlord drafts; also the human decision on 103, via the backend) |
| `request_payment` | board | `tickets`, `invoices`, `vendors`, `leases`, `cash_accounts`, `payment_requests` | `payment_requests` | 101 (invoice 501), 102 (rent) |
| `create_purchase_order` | board | `tickets`, `vendors`, `inventory`, `pricing`, `invoices`, `cash_accounts`, `desk` | `purchase_orders`, `payment_requests` | 103 (restock 12 hoodies M) |
| `update_ticket_status` | board | `tickets` | `tickets`, `board_notes` | all (Boss only; the backend uses it to reopen an escalated ticket with a human decision) |
| `approve_payment` | **human only** | `payment_requests`, `cash_accounts`, `invoices`, `purchase_orders`, `vendors`, `leases`, `desk` | `cash_accounts`, `payments`, `invoices`, `leases`, `purchase_orders`, `payment_requests` | 101, 102, 103 once a person approves |
| `reject_payment` | **human only** | `payment_requests` | `payment_requests`, `purchase_orders` | any pending request |

**Board tables the server adds to the working copy** (created if missing, so a reset
needs no migration):
- `board_notes` (id, ticket_id, author, kind, content, created_at): findings, drafts, and decisions
- `payment_requests` (id, ticket_id, kind, ref_id, payee, amount, account, reason, status, requested_by, decided_by, decided_at, decision_note, payment_id, created_at): the human approval queue
- `purchase_orders` (id, ticket_id, vendor_id, sku, size, qty, unit_cost, total, status, expected_arrival, requested_by, created_at): restock orders

---

## 8. Safety

### Guardrails for real customers and real money
- **A human approves every payment, enforced in code.** Agents can only queue requests.
  `approve_payment` / `reject_payment` are filtered out of every agent's toolset, blocked
  again in the tool-call hook, and only reachable through the backend's human-decision
  path. They refuse an `approved_by` that is an agent name.
- **Agents can't set amounts.** `request_payment` looks the amount up from the invoice or
  lease, and PO totals are qty × `pricing.unit_cost`. A model can't type in a number.
- **No negative balances.** `approve_payment` checks the balance inside the same
  transaction that debits it and refuses with the shortfall. `get_cash_position` shows
  `available_after_pending` so agents see the whole queue, not just their ticket.
- **Vendor rule enforced in code.** A PO can't be paid while its vendor has an open
  invoice.
- **All-or-nothing payments.** The balance debit, the `payments` row (with
  `approved_by`), and the invoice/lease/PO update are written together or not at all.
- **No duplicates.** Duplicate pending payment requests and POs are refused.
- **Drafts only.** Customer, vendor, and landlord messages are `board_notes`. Nothing is
  emailed or sent, and no tool can contact anyone outside.
- **Escalation goes to a person, not around the rules.** When the shop rules block a ticket
  (103: $264 restock vs $160 checking), the Boss escalates instead of forcing it. Only a
  human decision (author `human:<name>`, posted by the backend, never by an agent) reopens
  the ticket, and the Boss must still carry it out within the rules.
- **Least privilege.** Each agent sees only the tools its role needs (e.g. only
  Accounting can queue money, and only the Boss can change ticket status).
- **Trusted identity.** The MCP hook overwrites `author` / `requested_by` / `updated_by`
  with the real calling agent, so one agent can't sign as another.
- **No invented facts.** Every prompt requires each fact to come from a tool result.
  Tools return `found: false` instead of guessing.
- **Full audit trail.** Every step, tool call, delegation, refusal, and human decision is
  appended to `output/audit_trail.json` and never overwritten.
- **Separate working copy.** Agents write only to `campus_customs_new.db`. The original
  stays untouched for resets.
- **Secrets.** `PORTKEY_API_KEY` lives only in `.env` (git-ignored); `.env.example` has a
  placeholder.
- **What a real business would add next:** approval limits by amount (two people above a
  threshold), sign-in for approvers, rate limits per customer, PII redaction in logs,
  and a review of drafts before anything is sent.

### Limits that keep token use in check
| Limit | Value | Where |
|---|---|---|
| Model | `gpt-6-luna` only | `MODEL_NAME` |
| Max output per model response | 4,000 tokens | `ModelSettings(max_tokens)` |
| Requests per ticket (all agents combined) | 40 | `UsageLimits.request_limit` |
| Tool calls per ticket | 80 | `UsageLimits.tool_calls_limit` |
| Total tokens per ticket | 250,000 | `UsageLimits.total_tokens_limit` |
| Delegation depth | 2 (boss → specialist → specialist) | `MAX_DEPTH` |
| Delegations per ticket | 8 | `MAX_DELEGATIONS_PER_TICKET` |
| No cycles | can't delegate to yourself or anyone already waiting in the chain | `delegate()` |
| Narrow toolsets | 6–14 tools per agent instead of 19, so less schema text per request | `AGENT_TOOLS` |
| Truncated tool results in the audit log | 2,000 characters | `audit.MAX_FIELD_CHARS` |
| Prompt rules | check the board first, don't repeat identical tool calls, keep notes short | `backend/prompts/*.md` |

One agent's usage counter is shared down the delegation chain, so these limits cap the
whole ticket, not each agent. Test run on ticket 102: 16 requests, 21 tool calls, about
42k tokens, 2 delegations.

---

## 9. Backend routes (`backend/main.py`, FastAPI)

Start from `backend/` with `uvicorn main:app --reload --port 8000`, which serves
`http://localhost:8000`. Every route reads or writes the shop through the MCP server.
Interactive docs are at `http://localhost:8000/docs`.

- `GET /api/health`: backend is up; shows the model (`gpt-6-luna`) and the working DB file.
- `GET /api/tickets`: **all tickets with open/resolved state** (`state`, raw `status`, and `agent_run_in_progress`).
- `GET /api/tickets/{id}`: one ticket, its linked lease or invoice, and its board (notes, drafts, payment requests, POs).
- `POST /api/tickets/{id}/run`: **runs the agent team on that ticket** (Boss first). Returns `202` with a `run_id` right away; add `?wait=true` to block until it finishes. Returns `409` if that ticket is already running.
- `POST /api/tickets/{id}/human-decision` (body `{"decided_by": "...", "decision": "..."}`): a person answers an **escalated** ticket. Posts the decision to the board through MCP and reopens the ticket so the team can run again. Returns `409` unless the ticket is escalated. No money moves.
- `GET /api/runs` / `GET /api/runs/{run_id}`: run status (`running` / `done` / `failed`) and the result (`TicketResolution` + token usage).
- `GET /api/events?since_id=&ticket_id=&run_id=&limit=&verbose=`: **recent agent events** from `output/audit_trail.json`. Each event gives the agent, `said` (its text, brief, delegation, or final decision), `tools` (MCP tools it called), and raw `detail`. `since_id` lets the board poll for new events only.
- `GET /api/payments?status=pending|paid|rejected`: payment requests and POs the agents prepared.
- `POST /api/payments/{request_id}/approve` (body `{"approved_by": "<human name>"}`): **a human approves a payment or purchase order. This is the only route that changes cash.** It calls the human-only MCP `approve_payment`, which lowers `cash_accounts`, writes `payments` (with `approved_by`), and marks the invoice paid, moves the lease due date, or orders the PO. Returns `409` with the reason if refused (not enough cash, vendor still blocked, already paid, or an agent name as approver).
- `POST /api/payments/{request_id}/reject` (body `{"rejected_by": "...", "reason": "..."}`): a human rejects a request. No money moves.
- `GET /api/cash`: **current checking balance from `cash_accounts`**, plus the pending total, available after pending, and payments made.
- `POST /api/reset`: **resets the database**: copies `data/campus_customs.db` over `data/campus_customs_new.db`, clears the run list, and appends a `db_reset` event (the audit trail itself is kept). Returns `409` while an agent run is in progress.

**Verified via the API (ticket 102):** run → `waiting_on_approval` with rent request #1 →
approve as "Kelly Yang" → checking $3,400 → **$1,000**, `payments` row written, lease
`next_due` 2026-09-02 → 2026-10-02 → a second approve returned `409` → reset → $3,400,
all tickets open, no requests.

---

## 10. Frontend dashboard (`frontend/`, React + Vite + TypeScript)

- Start from `frontend/` with `npm install` (first time), then `npm run dev`, and open
  `http://localhost:5173`. It calls the backend at `http://localhost:8000`
  (`VITE_API_BASE`). The backend's CORS settings allow `http://localhost:5173`.
- Routes used: `GET /api/health`, `GET /api/tickets`, `GET /api/tickets/{id}`,
  `POST /api/tickets/{id}/run`, `GET /api/runs`, `GET /api/runs/{id}`,
  `GET /api/events?since_id=` (polled every 1.2 s during a run), `GET /api/payments?status=pending`,
  `POST /api/payments/{id}/approve`, `POST /api/payments/{id}/reject`, `POST /api/tickets/{id}/human-decision`,
  `GET /api/cash`, and `POST /api/reset`.
- Escalated tickets show a decision box (signed with the approval tray's name) that posts the
  decision and sends the ticket back to the team. `?ticket=101` opens a specific ticket.
- Run outcome rule: the Boss now ends every run as `resolved` (the team's part is done;
  approvals may still be pending in the tray) or `escalated`. `TicketResolution.final_status`
  only allows those two, and `run_ticket` records it through MCP if the Boss forgot.
- Design rationale: `output/design.md`.


---

## 11. Graded full run (Problem 9)

Reset with `POST /api/reset`, then tickets ran in order through `POST /api/tickets/{id}/run`.
All runs used gpt-6-luna. Events are appended to `output/audit_trail.json` after the last
`db_reset` marker.

| Ticket | Agents worked | Delegations | Outcome | Human step | Checking |
|---|---|---|---|---|---|
| start | | | DB reset to original | | **$3,400.00** |
| 101 | Boss, Inventory, Accounting, Customer Service | boss→inventory, boss→accounting, boss→customer_service | resolved: invoice 501 queued (request #1), customer draft #3 | Kelly Yang approved #1 ($840) | $2,560.00 |
| 102 | Boss, Facilities, Accounting | boss→facilities, boss→accounting | resolved: rent queued (request #2), landlord draft #5 | Kelly Yang approved #2 ($2,400) | $160.00 |
| 103 pass 1 | Boss, Inventory (×2), Accounting, Customer Service | boss→inventory, boss→accounting, accounting→inventory, boss→customer_service | escalated: 8 on hand / 12 short, restock $264 > $160, no PO; offer draft #11 | Kelly Yang decision (note #13): partial offer, defer restock | $160.00 |
| 103 pass 2 | Boss | none | resolved: carried out the decision | none | **$160.00** |

`cash_accounts.checking` = **160.0** = 3,400 − 840 − 2,400. `SUM(payments.amount)` = 3,240.
Tokens: 56,679 + 43,409 + 73,570 + 14,333 = **187,991**. Evidence:
`output/desk_tickets.html` (Actual, Cash, and Reflection tabs), `output/resolved_tickets.json`,
and `output/resolved_board.html` (dashboard screenshots).

---

## 12. How to run it

```bash
# one-time setup (from hw5/)
python3 -m venv .venv && .venv/bin/pip install -r requirements.txt
cp .env.example .env            # add PORTKEY_API_KEY
cd frontend && npm install && cd ..

# fresh start (or use the dashboard's "Reset desk" button / POST /api/reset)
cp data/campus_customs.db data/campus_customs_new.db

# backend (starts the MCP server as a subprocess) at http://localhost:8000
cd backend && ../.venv/bin/uvicorn main:app --reload --port 8000

# dashboard at http://localhost:5173 (second terminal)
cd frontend && npm run dev
```
