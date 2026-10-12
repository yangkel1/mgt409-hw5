"""Campus Customs MCP server.

The single tool layer for the Campus Customs agent team. Every tool reads or
writes data/campus_customs_new.db (the working copy) and returns only what is
stored there. If a row is missing, the tool says so instead of guessing.

Tool groups
  read      : any agent may call
  board     : agents record findings, drafts, payment requests, and POs
  human-only: approve_payment / reject_payment. The backend never exposes these
              to an agent; they run only when a person clicks approve or reject.

Money rules enforced here (not just in prompts):
  - Payment amounts are always looked up from the database, never passed in.
  - No money moves without approve_payment, which needs a human approved_by.
  - approve_payment refuses if the balance would go negative.
  - A purchase order can't be paid while the vendor has an open invoice.

Run (stdio):  python mcp_server/server.py
"""

import os
import sqlite3
from calendar import monthrange
from datetime import date, datetime
from pathlib import Path

from fastmcp import FastMCP

# CAMPUS_CUSTOMS_DB overrides the path (used only for scratch-copy testing).
DB_PATH = Path(
    os.getenv("CAMPUS_CUSTOMS_DB")
    or Path(__file__).resolve().parents[1] / "data" / "campus_customs_new.db"
)

AGENT_NAMES = {"boss", "inventory", "accounting", "facilities", "customer_service"}
NOTE_KINDS = {"finding", "customer_draft", "vendor_draft", "landlord_draft", "decision"}
TICKET_STATUSES = {"open", "in_progress", "waiting_on_approval", "escalated", "resolved"}

mcp = FastMCP("campus-customs")


# ---------------------------------------------------------------- helpers

def _connect() -> sqlite3.Connection:
    """Open the working DB. Board tables are (re)created if missing on every
    connection, so a reset to the original file never leaves them absent."""
    if not DB_PATH.exists():
        raise FileNotFoundError(f"Working database not found at {DB_PATH}")
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    conn.executescript(_BOARD_SCHEMA)
    return conn


# Board tables the agents write to. Created on demand, so a fresh copy of the
# original database works without a migration step.
_BOARD_SCHEMA = """
            CREATE TABLE IF NOT EXISTS board_notes (
                id INTEGER PRIMARY KEY,
                ticket_id INTEGER NOT NULL,
                author TEXT NOT NULL,
                kind TEXT NOT NULL,
                content TEXT NOT NULL,
                created_at TEXT NOT NULL,
                FOREIGN KEY (ticket_id) REFERENCES tickets(id)
            );
            CREATE TABLE IF NOT EXISTS purchase_orders (
                id INTEGER PRIMARY KEY,
                ticket_id INTEGER,
                vendor_id INTEGER NOT NULL,
                sku TEXT NOT NULL,
                size TEXT NOT NULL,
                qty INTEGER NOT NULL,
                unit_cost REAL NOT NULL,
                total REAL NOT NULL,
                status TEXT NOT NULL,
                expected_arrival TEXT,
                requested_by TEXT NOT NULL,
                created_at TEXT NOT NULL,
                FOREIGN KEY (vendor_id) REFERENCES vendors(id)
            );
            CREATE TABLE IF NOT EXISTS payment_requests (
                id INTEGER PRIMARY KEY,
                ticket_id INTEGER,
                kind TEXT NOT NULL,
                ref_id INTEGER NOT NULL,
                payee TEXT NOT NULL,
                amount REAL NOT NULL,
                account TEXT NOT NULL,
                reason TEXT,
                status TEXT NOT NULL,
                requested_by TEXT NOT NULL,
                decided_by TEXT,
                decided_at TEXT,
                decision_note TEXT,
                payment_id INTEGER,
                created_at TEXT NOT NULL
            );
"""


def _now() -> str:
    return datetime.now().isoformat(timespec="seconds")


def _today(conn: sqlite3.Connection) -> str:
    """The shop's 'today' comes from desk.date_today, never the system clock."""
    return conn.execute("SELECT date_today FROM desk LIMIT 1").fetchone()["date_today"]


def _days_between(start: str, end: str) -> int:
    return (date.fromisoformat(end) - date.fromisoformat(start)).days


def _add_days(day: str, n: int) -> str:
    return date.fromordinal(date.fromisoformat(day).toordinal() + n).isoformat()


def _add_month(day: str) -> str:
    d = date.fromisoformat(day)
    y, m = (d.year + 1, 1) if d.month == 12 else (d.year, d.month + 1)
    return date(y, m, min(d.day, monthrange(y, m)[1])).isoformat()


def _ticket_exists(conn: sqlite3.Connection, ticket_id: int) -> bool:
    return conn.execute("SELECT 1 FROM tickets WHERE id = ?", (ticket_id,)).fetchone() is not None


def _open_invoices_for_vendor(conn: sqlite3.Connection, vendor_id: int) -> list[dict]:
    return [
        dict(r)
        for r in conn.execute(
            "SELECT id, amount, due_date FROM invoices WHERE vendor_id = ? AND status = 'open'",
            (vendor_id,),
        )
    ]


def _pending_total(conn: sqlite3.Connection, account: str) -> float:
    row = conn.execute(
        "SELECT COALESCE(SUM(amount), 0) FROM payment_requests WHERE account = ? AND status = 'pending'",
        (account,),
    ).fetchone()
    return round(row[0], 2)


def _refuse(reason: str, **extra) -> dict:
    return {"ok": False, "refused": True, "reason": reason, **extra}


# ---------------------------------------------------------------- read tools

@mcp.tool
def get_desk_today() -> dict:
    """Return the shop's 'today' (desk.date_today) and desk notes.

    Reads `desk`. Use this date, never the real calendar, to decide what is
    overdue or coming due.
    """
    with _connect() as conn:
        row = conn.execute("SELECT date_today, notes FROM desk LIMIT 1").fetchone()
    return dict(row)


@mcp.tool
def list_open_tickets() -> dict:
    """List every ticket that is not resolved, oldest first.

    Reads `tickets`. Returns id, type, requester, subject, sku/size/qty,
    lease_id, invoice_id, status, notes, and created_at.
    """
    with _connect() as conn:
        rows = [
            dict(r)
            for r in conn.execute(
                "SELECT * FROM tickets WHERE status != 'resolved' ORDER BY created_at"
            )
        ]
    return {"count": len(rows), "tickets": rows}


@mcp.tool
def list_tickets() -> dict:
    """List every ticket on the board (open and resolved) with its status.

    Reads `tickets`. Each row adds `is_resolved` so a dashboard can show open
    vs resolved at a glance.
    """
    with _connect() as conn:
        rows = [dict(r) for r in conn.execute("SELECT * FROM tickets ORDER BY id")]
    for r in rows:
        r["is_resolved"] = r["status"] == "resolved"
    return {"count": len(rows), "tickets": rows}


@mcp.tool
def get_ticket(ticket_id: int) -> dict:
    """Return one ticket plus the lease and invoice rows it links to.

    Reads `tickets`, and follows `lease_id` into `leases` and `invoice_id` into
    `invoices` and `vendors`. Use it first on any ticket to see which other
    tables matter.
    """
    with _connect() as conn:
        t = conn.execute("SELECT * FROM tickets WHERE id = ?", (ticket_id,)).fetchone()
        if t is None:
            return {"found": False, "ticket_id": ticket_id, "message": "No ticket with this id."}
        result = {"found": True, "ticket": dict(t), "date_today": _today(conn)}
        if t["lease_id"] is not None:
            lease = conn.execute("SELECT * FROM leases WHERE id = ?", (t["lease_id"],)).fetchone()
            result["linked_lease"] = dict(lease) if lease else None
        if t["invoice_id"] is not None:
            inv = conn.execute(
                """SELECT i.*, v.name AS vendor_name FROM invoices i
                   JOIN vendors v ON v.id = i.vendor_id WHERE i.id = ?""",
                (t["invoice_id"],),
            ).fetchone()
            result["linked_invoice"] = dict(inv) if inv else None
    return result


@mcp.tool
def check_stock(sku: str, size: str, qty_needed: int = 0) -> dict:
    """Look up on-hand stock and pricing for one SKU and size.

    Reads `inventory` and `pricing`. If qty_needed is given, also reports the
    shortfall (qty_needed minus on-hand, never below 0). Use this for customer
    orders and bulk requests to see if the shop can fill them right now.
    """
    with _connect() as conn:
        item = conn.execute(
            "SELECT sku, name, size, qty, location FROM inventory WHERE sku = ? AND size = ?",
            (sku, size),
        ).fetchone()
        if item is None:
            sizes = [
                r["size"]
                for r in conn.execute("SELECT size FROM inventory WHERE sku = ?", (sku,))
            ]
            return {
                "found": False,
                "sku": sku,
                "size": size,
                "message": "No inventory row for this SKU and size.",
                "sizes_on_file_for_sku": sizes,
            }
        price = conn.execute(
            "SELECT unit_cost, list_price FROM pricing WHERE sku = ?", (sku,)
        ).fetchone()

    result = {"found": True, **dict(item)}
    result["unit_cost"] = price["unit_cost"] if price else None
    result["list_price"] = price["list_price"] if price else None
    if qty_needed:
        result["qty_needed"] = qty_needed
        result["shortfall"] = max(qty_needed - item["qty"], 0)
        result["can_fill_now"] = item["qty"] >= qty_needed
    return result


@mcp.tool
def list_vendors() -> dict:
    """List vendors with specialty, lead time, and whether they can ship now.

    Reads `vendors`, `invoices`, and `desk`. A vendor with any open invoice is
    `blocked` (it won't ship new product). `arrival_if_ordered_today` is
    desk.date_today + lead_days; lead times come only from this table.
    """
    with _connect() as conn:
        today = _today(conn)
        vendors = []
        for v in conn.execute("SELECT id, name, specialty, lead_days FROM vendors ORDER BY id"):
            open_inv = _open_invoices_for_vendor(conn, v["id"])
            vendors.append(
                {
                    **dict(v),
                    "open_invoices": open_inv,
                    "blocked": bool(open_inv),
                    "arrival_if_ordered_today": _add_days(today, v["lead_days"]),
                }
            )
    return {"date_today": today, "vendors": vendors}


@mcp.tool
def get_invoice_status(invoice_id: int) -> dict:
    """Look up one vendor invoice, its vendor, and whether it is overdue.

    Reads `invoices`, `vendors`, and `desk`. Overdue means status is 'open'
    and due_date is before desk.date_today. A vendor will not ship new product
    while it has an open invoice, so `vendor_blocked` tells you if restocking
    from this vendor is on hold.
    """
    with _connect() as conn:
        today = _today(conn)
        row = conn.execute(
            """
            SELECT i.id, i.vendor_id, i.amount, i.due_date, i.status, i.description,
                   v.name AS vendor_name, v.specialty AS vendor_specialty,
                   v.lead_days AS vendor_lead_days
            FROM invoices i JOIN vendors v ON v.id = i.vendor_id
            WHERE i.id = ?
            """,
            (invoice_id,),
        ).fetchone()
        if row is None:
            return {"found": False, "invoice_id": invoice_id, "message": "No invoice with this id."}
        open_count = len(_open_invoices_for_vendor(conn, row["vendor_id"]))

    result = {"found": True, "date_today": today, **dict(row)}
    is_open = row["status"] == "open"
    result["days_overdue"] = (
        max(_days_between(row["due_date"], today), 0) if is_open else 0
    )
    result["overdue"] = is_open and result["days_overdue"] > 0
    result["vendor_open_invoices"] = open_count
    result["vendor_blocked"] = open_count > 0
    return result


@mcp.tool
def list_open_invoices() -> dict:
    """List every unpaid vendor invoice with days overdue.

    Reads `invoices`, `vendors`, and `desk`. Use it to see all bills competing
    for cash, not just the one linked to the current ticket.
    """
    with _connect() as conn:
        today = _today(conn)
        rows = []
        for r in conn.execute(
            """SELECT i.id, i.vendor_id, v.name AS vendor_name, i.amount, i.due_date,
                      i.description FROM invoices i JOIN vendors v ON v.id = i.vendor_id
               WHERE i.status = 'open' ORDER BY i.due_date"""
        ):
            d = dict(r)
            d["days_overdue"] = max(_days_between(r["due_date"], today), 0)
            rows.append(d)
    return {"date_today": today, "count": len(rows), "invoices": rows}


@mcp.tool
def get_lease_and_cash(lease_id: int) -> dict:
    """Look up one lease's rent and due date next to the shop's cash balance.

    Reads `leases`, `cash_accounts`, and `desk`. Reports days until rent is
    due (negative means overdue) and whether each cash account can cover the
    rent without going negative. Read-only: it does not pay anything.
    """
    with _connect() as conn:
        today = _today(conn)
        lease = conn.execute(
            "SELECT id, space_name, landlord, monthly_rent, next_due, notes FROM leases WHERE id = ?",
            (lease_id,),
        ).fetchone()
        if lease is None:
            return {"found": False, "lease_id": lease_id, "message": "No lease with this id."}
        accounts = [
            dict(r) for r in conn.execute("SELECT name, balance, date FROM cash_accounts")
        ]

    rent = lease["monthly_rent"]
    for acct in accounts:
        acct["can_cover_rent"] = acct["balance"] >= rent
        acct["balance_after_rent"] = round(acct["balance"] - rent, 2)
    return {
        "found": True,
        "date_today": today,
        **dict(lease),
        "days_until_due": _days_between(today, lease["next_due"]),
        "cash_accounts": accounts,
    }


@mcp.tool
def get_cash_position() -> dict:
    """Return each cash account's balance, pending requests, and what's left.

    Reads `cash_accounts`, `payment_requests`, and `payments`. `available_after_pending`
    is the balance minus every pending payment request on that account. Cash
    only goes out in this shop (no revenue), so treat this as a fixed budget.
    """
    with _connect() as conn:
        accounts = []
        for a in conn.execute("SELECT name, balance, date FROM cash_accounts"):
            pending = _pending_total(conn, a["name"])
            accounts.append(
                {
                    **dict(a),
                    "pending_requests_total": pending,
                    "available_after_pending": round(a["balance"] - pending, 2),
                }
            )
        paid = conn.execute("SELECT COUNT(*), COALESCE(SUM(amount),0) FROM payments").fetchone()
    return {"accounts": accounts, "payments_made": {"count": paid[0], "total": round(paid[1], 2)}}


@mcp.tool
def quote_margin(sku: str, qty: int, discount_pct: float = 0.0) -> dict:
    """Price a quantity of one SKU at a discount and show the margin.

    Reads `pricing`. discount_pct is 0-100 off list price. Returns unit price
    after discount, margin per unit, margin %, and order totals, and flags
    `below_cost` if the discounted price would lose money.
    """
    if qty <= 0 or not 0 <= discount_pct < 100:
        return _refuse("qty must be > 0 and discount_pct must be between 0 and 100.")
    with _connect() as conn:
        p = conn.execute("SELECT unit_cost, list_price FROM pricing WHERE sku = ?", (sku,)).fetchone()
    if p is None:
        return {"found": False, "sku": sku, "message": "No pricing row for this SKU."}
    price = round(p["list_price"] * (1 - discount_pct / 100), 2)
    margin = round(price - p["unit_cost"], 2)
    return {
        "found": True,
        "sku": sku,
        "qty": qty,
        "unit_cost": p["unit_cost"],
        "list_price": p["list_price"],
        "discount_pct": discount_pct,
        "unit_price_after_discount": price,
        "margin_per_unit": margin,
        "margin_pct": round(margin / price * 100, 1) if price else None,
        "order_revenue": round(price * qty, 2),
        "order_cost": round(p["unit_cost"] * qty, 2),
        "order_margin": round(margin * qty, 2),
        "below_cost": margin < 0,
        "list_margin_pct": round((p["list_price"] - p["unit_cost"]) / p["list_price"] * 100, 1),
    }


@mcp.tool
def list_payment_requests(status: str = "") -> dict:
    """List payment requests waiting for, or past, human approval.

    Reads `payment_requests`. Filter with status = pending, paid, rejected
    (empty string returns all).
    """
    with _connect() as conn:
        if status:
            rows = conn.execute(
                "SELECT * FROM payment_requests WHERE status = ? ORDER BY id", (status,)
            )
        else:
            rows = conn.execute("SELECT * FROM payment_requests ORDER BY id")
        rows = [dict(r) for r in rows]
    return {"count": len(rows), "requests": rows}


@mcp.tool
def get_ticket_board(ticket_id: int) -> dict:
    """Return everything the team has posted for one ticket.

    Reads `tickets`, `board_notes`, `payment_requests`, and `purchase_orders`.
    Check it before acting so you don't duplicate a note, request, or PO that
    another agent already made.
    """
    with _connect() as conn:
        t = conn.execute("SELECT id, status, subject FROM tickets WHERE id = ?", (ticket_id,)).fetchone()
        if t is None:
            return {"found": False, "ticket_id": ticket_id, "message": "No ticket with this id."}
        q = lambda sql: [dict(r) for r in conn.execute(sql, (ticket_id,))]
        return {
            "found": True,
            "ticket": dict(t),
            "notes": q("SELECT * FROM board_notes WHERE ticket_id = ? ORDER BY id"),
            "payment_requests": q("SELECT * FROM payment_requests WHERE ticket_id = ? ORDER BY id"),
            "purchase_orders": q("SELECT * FROM purchase_orders WHERE ticket_id = ? ORDER BY id"),
        }


# ---------------------------------------------------------------- board tools (agents)

@mcp.tool
def post_board_note(ticket_id: int, kind: str, content: str, author: str) -> dict:
    """Post a finding, draft, or decision to a ticket's board.

    Writes `board_notes`. kind is one of: finding, customer_draft, vendor_draft,
    landlord_draft, decision. Drafts stay on the board; nothing is emailed or
    sent to a real customer, vendor, or landlord.
    """
    if kind not in NOTE_KINDS:
        return _refuse(f"kind must be one of {sorted(NOTE_KINDS)}.")
    if not content.strip():
        return _refuse("content is empty.")
    with _connect() as conn:
        if not _ticket_exists(conn, ticket_id):
            return _refuse(f"No ticket {ticket_id}.")
        cur = conn.execute(
            "INSERT INTO board_notes (ticket_id, author, kind, content, created_at) VALUES (?,?,?,?,?)",
            (ticket_id, author, kind, content.strip(), _now()),
        )
    return {"ok": True, "note_id": cur.lastrowid, "ticket_id": ticket_id, "kind": kind, "author": author}


@mcp.tool
def request_payment(
    ticket_id: int, kind: str, ref_id: int, reason: str, requested_by: str, account: str = "checking"
) -> dict:
    """Queue an invoice or rent payment for HUMAN approval. Moves no money.

    Reads `invoices`/`vendors` (kind='invoice', ref_id = invoice id) or `leases`
    (kind='rent', ref_id = lease id), plus `cash_accounts`; writes
    `payment_requests` with status 'pending'. The amount is taken from the
    database (invoice amount or monthly rent), never from the caller. Refuses
    duplicates and already-paid invoices.
    """
    if kind not in {"invoice", "rent"}:
        return _refuse("kind must be 'invoice' or 'rent'. Use create_purchase_order for restocks.")
    with _connect() as conn:
        if not _ticket_exists(conn, ticket_id):
            return _refuse(f"No ticket {ticket_id}.")
        acct = conn.execute("SELECT balance FROM cash_accounts WHERE name = ?", (account,)).fetchone()
        if acct is None:
            return _refuse(f"No cash account named {account!r}.")
        if kind == "invoice":
            inv = conn.execute(
                """SELECT i.amount, i.status, v.name FROM invoices i
                   JOIN vendors v ON v.id = i.vendor_id WHERE i.id = ?""",
                (ref_id,),
            ).fetchone()
            if inv is None:
                return _refuse(f"No invoice {ref_id}.")
            if inv["status"] != "open":
                return _refuse(f"Invoice {ref_id} is already {inv['status']}.")
            amount, payee = inv["amount"], inv["name"]
        else:
            lease = conn.execute(
                "SELECT monthly_rent, landlord FROM leases WHERE id = ?", (ref_id,)
            ).fetchone()
            if lease is None:
                return _refuse(f"No lease {ref_id}.")
            amount, payee = lease["monthly_rent"], lease["landlord"]
        dup = conn.execute(
            "SELECT id FROM payment_requests WHERE kind = ? AND ref_id = ? AND status = 'pending'",
            (kind, ref_id),
        ).fetchone()
        if dup:
            return _refuse(f"A pending request already exists for this {kind}.", existing_request_id=dup["id"])
        pending_before = _pending_total(conn, account)
        cur = conn.execute(
            """INSERT INTO payment_requests (ticket_id, kind, ref_id, payee, amount, account, reason,
               status, requested_by, created_at) VALUES (?,?,?,?,?,?,?,'pending',?,?)""",
            (ticket_id, kind, ref_id, payee, amount, account, reason, requested_by, _now()),
        )
    available = round(acct["balance"] - pending_before - amount, 2)
    return {
        "ok": True,
        "request_id": cur.lastrowid,
        "status": "pending",
        "kind": kind,
        "ref_id": ref_id,
        "payee": payee,
        "amount": amount,
        "account": account,
        "balance_now": acct["balance"],
        "available_after_all_pending": available,
        "warning": "Pending requests exceed the balance; a human must choose which to pay." if available < 0 else None,
        "note": "Waiting for human approval. No money has moved.",
    }


@mcp.tool
def create_purchase_order(
    ticket_id: int, vendor_id: int, sku: str, size: str, qty: int, requested_by: str, account: str = "checking"
) -> dict:
    """Draft a restock purchase order and queue its payment for HUMAN approval.

    Reads `vendors`, `inventory`, `pricing`, `invoices`, and `desk`; writes
    `purchase_orders` (status 'pending_approval') and a `payment_requests` row
    (kind 'purchase_order'). Cost is qty x pricing.unit_cost. If the vendor
    has an open invoice, the PO is still drafted, but it can't be approved
    until that invoice is paid.
    """
    if qty <= 0:
        return _refuse("qty must be positive.")
    with _connect() as conn:
        today = _today(conn)
        if not _ticket_exists(conn, ticket_id):
            return _refuse(f"No ticket {ticket_id}.")
        v = conn.execute("SELECT id, name, lead_days FROM vendors WHERE id = ?", (vendor_id,)).fetchone()
        if v is None:
            return _refuse(f"No vendor {vendor_id}.")
        if conn.execute("SELECT 1 FROM inventory WHERE sku = ? AND size = ?", (sku, size)).fetchone() is None:
            return _refuse(f"No inventory row for {sku} size {size}.")
        p = conn.execute("SELECT unit_cost FROM pricing WHERE sku = ?", (sku,)).fetchone()
        if p is None:
            return _refuse(f"No pricing row for {sku}.")
        if conn.execute("SELECT name FROM cash_accounts WHERE name = ?", (account,)).fetchone() is None:
            return _refuse(f"No cash account named {account!r}.")
        dup = conn.execute(
            """SELECT id FROM purchase_orders WHERE vendor_id = ? AND sku = ? AND size = ?
               AND status = 'pending_approval'""",
            (vendor_id, sku, size),
        ).fetchone()
        if dup:
            return _refuse("A pending PO for this vendor, SKU, and size already exists.", existing_po_id=dup["id"])
        total = round(qty * p["unit_cost"], 2)
        po = conn.execute(
            """INSERT INTO purchase_orders (ticket_id, vendor_id, sku, size, qty, unit_cost, total,
               status, requested_by, created_at) VALUES (?,?,?,?,?,?,?,'pending_approval',?,?)""",
            (ticket_id, vendor_id, sku, size, qty, p["unit_cost"], total, requested_by, _now()),
        )
        req = conn.execute(
            """INSERT INTO payment_requests (ticket_id, kind, ref_id, payee, amount, account, reason,
               status, requested_by, created_at) VALUES (?,'purchase_order',?,?,?,?,?,'pending',?,?)""",
            (ticket_id, po.lastrowid, v["name"], total, account,
             f"Restock {qty} x {sku} {size}", requested_by, _now()),
        )
        open_inv = _open_invoices_for_vendor(conn, vendor_id)
    return {
        "ok": True,
        "po_id": po.lastrowid,
        "request_id": req.lastrowid,
        "vendor": v["name"],
        "sku": sku,
        "size": size,
        "qty": qty,
        "unit_cost": p["unit_cost"],
        "total": total,
        "arrival_if_approved_today": _add_days(today, v["lead_days"]),
        "vendor_blocked_now": bool(open_inv),
        "blocking_invoices": open_inv,
        "note": "Waiting for human approval. No money has moved.",
    }


@mcp.tool
def update_ticket_status(ticket_id: int, status: str, resolution_note: str, updated_by: str) -> dict:
    """Set a ticket's status and record why on its board.

    Writes `tickets.status` and a 'decision' row in `board_notes`. status is
    one of: open, in_progress, waiting_on_approval, escalated, resolved.
    """
    if status not in TICKET_STATUSES:
        return _refuse(f"status must be one of {sorted(TICKET_STATUSES)}.")
    with _connect() as conn:
        old = conn.execute("SELECT status FROM tickets WHERE id = ?", (ticket_id,)).fetchone()
        if old is None:
            return _refuse(f"No ticket {ticket_id}.")
        conn.execute("UPDATE tickets SET status = ? WHERE id = ?", (status, ticket_id))
        conn.execute(
            "INSERT INTO board_notes (ticket_id, author, kind, content, created_at) VALUES (?,?,'decision',?,?)",
            (ticket_id, updated_by, f"Status {old['status']} -> {status}: {resolution_note}", _now()),
        )
    return {"ok": True, "ticket_id": ticket_id, "old_status": old["status"], "new_status": status}


# ---------------------------------------------------------------- human-only tools

@mcp.tool
def approve_payment(request_id: int, approved_by: str) -> dict:
    """HUMAN ONLY: approve a pending payment request and pay it.

    Reads `payment_requests`, `cash_accounts`, `invoices`, `purchase_orders`,
    `vendors`, and `desk`. On success, in one transaction: lowers
    `cash_accounts.balance`, inserts `payments` (with approved_by), and marks the
    invoice paid, moves `leases.next_due` forward one month, or sets the PO to
    'ordered' with an expected arrival. Refuses if cash is short (no negative
    balances) or if a PO's vendor still has an open invoice.
    """
    approver = (approved_by or "").strip()
    if not approver or approver.lower() in AGENT_NAMES:
        return _refuse("approved_by must be a named human, not an agent.")
    with _connect() as conn:
        today = _today(conn)
        req = conn.execute("SELECT * FROM payment_requests WHERE id = ?", (request_id,)).fetchone()
        if req is None:
            return _refuse(f"No payment request {request_id}.")
        if req["status"] != "pending":
            return _refuse(f"Request {request_id} is already {req['status']}.")
        acct = conn.execute(
            "SELECT balance FROM cash_accounts WHERE name = ?", (req["account"],)
        ).fetchone()
        if acct is None:
            return _refuse(f"No cash account named {req['account']!r}.")
        if acct["balance"] < req["amount"]:
            return _refuse(
                "Not enough cash. Payment refused; no negative balances.",
                balance=acct["balance"],
                amount=req["amount"],
                short_by=round(req["amount"] - acct["balance"], 2),
            )

        effect = {}
        if req["kind"] == "invoice":
            inv = conn.execute("SELECT status FROM invoices WHERE id = ?", (req["ref_id"],)).fetchone()
            if inv is None or inv["status"] != "open":
                return _refuse(f"Invoice {req['ref_id']} is no longer open.")
        elif req["kind"] == "purchase_order":
            po = conn.execute("SELECT * FROM purchase_orders WHERE id = ?", (req["ref_id"],)).fetchone()
            if po is None or po["status"] != "pending_approval":
                return _refuse(f"PO {req['ref_id']} is not pending approval.")
            blocking = _open_invoices_for_vendor(conn, po["vendor_id"])
            if blocking:
                return _refuse(
                    "Vendor has an open unpaid invoice and will not ship. Pay that invoice first.",
                    blocking_invoices=blocking,
                )

        # All checks passed: move the money in one transaction.
        new_balance = round(acct["balance"] - req["amount"], 2)
        conn.execute(
            "UPDATE cash_accounts SET balance = ?, date = ? WHERE name = ?",
            (new_balance, today, req["account"]),
        )
        pay = conn.execute(
            "INSERT INTO payments (kind, ref_id, amount, account, paid_at, approved_by) VALUES (?,?,?,?,?,?)",
            (req["kind"], req["ref_id"], req["amount"], req["account"], today, approver),
        )
        if req["kind"] == "invoice":
            conn.execute("UPDATE invoices SET status = 'paid' WHERE id = ?", (req["ref_id"],))
            effect = {"invoice_id": req["ref_id"], "invoice_status": "paid"}
        elif req["kind"] == "rent":
            old_due = conn.execute("SELECT next_due FROM leases WHERE id = ?", (req["ref_id"],)).fetchone()["next_due"]
            new_due = _add_month(old_due)
            conn.execute("UPDATE leases SET next_due = ? WHERE id = ?", (new_due, req["ref_id"]))
            effect = {"lease_id": req["ref_id"], "old_next_due": old_due, "new_next_due": new_due}
        else:
            lead = conn.execute(
                "SELECT v.lead_days FROM purchase_orders p JOIN vendors v ON v.id = p.vendor_id WHERE p.id = ?",
                (req["ref_id"],),
            ).fetchone()["lead_days"]
            arrival = _add_days(today, lead)
            conn.execute(
                "UPDATE purchase_orders SET status = 'ordered', expected_arrival = ? WHERE id = ?",
                (arrival, req["ref_id"]),
            )
            effect = {"po_id": req["ref_id"], "po_status": "ordered", "expected_arrival": arrival}
        conn.execute(
            """UPDATE payment_requests SET status = 'paid', decided_by = ?, decided_at = ?,
               payment_id = ? WHERE id = ?""",
            (approver, _now(), pay.lastrowid, request_id),
        )
    return {
        "ok": True,
        "request_id": request_id,
        "payment_id": pay.lastrowid,
        "amount": req["amount"],
        "account": req["account"],
        "balance_before": acct["balance"],
        "balance_after": new_balance,
        "approved_by": approver,
        "paid_at": today,
        **effect,
    }


@mcp.tool
def reject_payment(request_id: int, rejected_by: str, reason: str) -> dict:
    """HUMAN ONLY: reject a pending payment request. Moves no money.

    Writes `payment_requests` (status 'rejected') and, for a PO request,
    `purchase_orders` (status 'rejected').
    """
    who = (rejected_by or "").strip()
    if not who or who.lower() in AGENT_NAMES:
        return _refuse("rejected_by must be a named human, not an agent.")
    with _connect() as conn:
        req = conn.execute("SELECT * FROM payment_requests WHERE id = ?", (request_id,)).fetchone()
        if req is None:
            return _refuse(f"No payment request {request_id}.")
        if req["status"] != "pending":
            return _refuse(f"Request {request_id} is already {req['status']}.")
        conn.execute(
            """UPDATE payment_requests SET status = 'rejected', decided_by = ?, decided_at = ?,
               decision_note = ? WHERE id = ?""",
            (who, _now(), reason, request_id),
        )
        if req["kind"] == "purchase_order":
            conn.execute("UPDATE purchase_orders SET status = 'rejected' WHERE id = ?", (req["ref_id"],))
    return {"ok": True, "request_id": request_id, "status": "rejected", "rejected_by": who}



if __name__ == "__main__":
    mcp.run(show_banner=False, log_level="WARNING")
