# Campus Customs MCP Server

**What it's for:** this is the single tool layer for the Campus Customs agent team. The
agents (Boss, Inventory, Accounting, Facilities, Customer Service) never touch SQLite
directly. Every shop fact they see and every change they make goes through these MCP
tools, which return only what's stored in the database. If a row doesn't exist, the tool
says so rather than inventing data.

**Database:** `data/campus_customs_new.db`, the working copy. The original
`data/campus_customs.db` is never touched. To reset, run
`cp data/campus_customs.db data/campus_customs_new.db` from `hw5/`. On startup the server
creates three empty board tables if they're missing (`board_notes`, `payment_requests`,
`purchase_orders`), so a fresh copy of the original works without any extra step.

**Built with:** [FastMCP](https://gofastmcp.com) 4.x (`from fastmcp import FastMCP`). It
runs over stdio.

```bash
# from hw5/
.venv/bin/python mcp_server/server.py
```

## Tools (19)

### Read (any agent, scoped per role in `backend/agents.py`)
| Tool | Tables read | Returns |
|---|---|---|
| `get_desk_today()` | `desk` | The shop's "today" (`date_today`) |
| `list_tickets()` | `tickets` | Every ticket with `is_resolved` (used by the dashboard) |
| `list_open_tickets()` | `tickets` | All tickets not yet `resolved` |
| `get_ticket(ticket_id)` | `tickets`, `leases`, `invoices`, `vendors` | One ticket plus its linked lease or invoice |
| `check_stock(sku, size, qty_needed)` | `inventory`, `pricing` | On-hand qty, location, cost/list price, shortfall, `can_fill_now` |
| `list_vendors()` | `vendors`, `invoices`, `desk` | Specialty, lead days, open invoices, `blocked`, arrival if ordered today |
| `get_invoice_status(invoice_id)` | `invoices`, `vendors`, `desk` | Amount, due date, `days_overdue`, `vendor_blocked` |
| `list_open_invoices()` | `invoices`, `vendors`, `desk` | Every unpaid invoice with days overdue |
| `get_lease_and_cash(lease_id)` | `leases`, `cash_accounts`, `desk` | Rent, next due, `days_until_due`, whether cash covers it |
| `get_cash_position()` | `cash_accounts`, `payment_requests`, `payments` | Balance, pending total, `available_after_pending` |
| `quote_margin(sku, qty, discount_pct)` | `pricing` | Discounted price, margin per unit and %, totals, `below_cost` |
| `list_payment_requests(status)` | `payment_requests` | Requests by status (pending, paid, rejected) |
| `get_ticket_board(ticket_id)` | `tickets`, `board_notes`, `payment_requests`, `purchase_orders` | Everything posted for a ticket |

### Board (agents write; no money moves)
| Tool | Tables | What it does |
|---|---|---|
| `post_board_note(ticket_id, kind, content, author)` | writes `board_notes` | Posts a finding, customer/vendor/landlord draft, or decision. Drafts are never sent. |
| `request_payment(ticket_id, kind, ref_id, reason, requested_by)` | reads `invoices`/`leases`, `cash_accounts`; writes `payment_requests` | Queues an invoice or rent payment as **pending**. The amount comes from the DB. Duplicates are refused. |
| `create_purchase_order(ticket_id, vendor_id, sku, size, qty, requested_by)` | reads `vendors`, `inventory`, `pricing`, `invoices`, `desk`; writes `purchase_orders`, `payment_requests` | Drafts a restock PO (qty × unit_cost) and queues its payment as **pending** |
| `update_ticket_status(ticket_id, status, resolution_note, updated_by)` | writes `tickets`, `board_notes` | Sets the status and records why (Boss only; the backend also uses it to reopen an escalated ticket with a human decision) |

### Human only (never given to an agent; called by the backend when a person clicks approve or reject)
| Tool | Tables | What it does |
|---|---|---|
| `approve_payment(request_id, approved_by)` | reads `payment_requests`, `cash_accounts`, `invoices`, `purchase_orders`, `vendors`, `desk`; writes `cash_accounts`, `payments`, `invoices` / `leases` / `purchase_orders`, `payment_requests` | Pays in one transaction. **Refuses** if cash is short (no negative balances), if a PO's vendor has an open invoice, or if `approved_by` is an agent name. |
| `reject_payment(request_id, rejected_by, reason)` | writes `payment_requests`, `purchase_orders` | Rejects a pending request. No money moves. |
