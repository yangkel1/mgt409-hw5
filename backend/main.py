"""Campus Customs backend (FastAPI).

Start from the backend/ folder:
    uvicorn main:app --reload --port 8000

Every shop read and write goes through the campus-customs MCP server. Agents
only *prepare* payments; the approve route below is the one place cash changes,
and only after a human clicks approve.
"""

import asyncio
import shutil
import sys
from contextlib import asynccontextmanager
from datetime import datetime
from pathlib import Path
from typing import Any

from fastapi import FastAPI, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field

# `uvicorn main:app` runs this file as a top-level module; make `backend.*` importable.
ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from backend import audit  # noqa: E402
from backend.agents import (  # noqa: E402
    MCP, MODEL_NAME, human_decide_payment, human_decide_ticket, mcp_call, new_run_id, run_ticket,
)
from backend.models import AuditEvent, TicketRunResult  # noqa: E402

ORIGINAL_DB = ROOT / "data" / "campus_customs.db"
WORKING_DB = ROOT / "data" / "campus_customs_new.db"

# In-memory run registry: run_id -> {"ticket_id", "status", "started_at", "result"}
RUNS: dict[str, dict[str, Any]] = {}
_run_tasks: set[asyncio.Task] = set()


def _active_runs() -> list[dict[str, Any]]:
    return [r for r in RUNS.values() if r["status"] == "running"]


@asynccontextmanager
async def lifespan(app: FastAPI):
    # Keep one MCP server process alive for the app's lifetime (calls re-use it).
    async with MCP:
        yield


app = FastAPI(title="Campus Customs Multi-Agent Operations", version="1.0", lifespan=lifespan)
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:5173", "http://127.0.0.1:5173", "http://localhost:3000"],
    allow_methods=["*"],
    allow_headers=["*"],
)


# ------------------------------------------------------------------ schemas

class ApproveBody(BaseModel):
    approved_by: str = Field(min_length=1, description="Name of the human approving the payment.")


class DecisionBody(BaseModel):
    decided_by: str = Field(min_length=1, description="Name of the human making the call.")
    decision: str = Field(min_length=1, description="What the team should do.")


class RejectBody(BaseModel):
    rejected_by: str = Field(min_length=1)
    reason: str = ""


# ------------------------------------------------------------------ helpers

def _refused(result: Any) -> bool:
    return isinstance(result, dict) and result.get("ok") is False


def _summarize_event(index: int, e: dict[str, Any]) -> dict[str, Any]:
    """Turn a raw audit event into what the board shows: who, what they said, which tools."""
    d = e.get("detail", {})
    said, tools = None, []
    kind = e["event"]
    if kind == "model_response":
        texts = [p["content"] for p in d.get("parts", []) if p["kind"] == "text"]
        tools = [p["tool"] for p in d.get("parts", []) if p["kind"] == "tool_call" and p["tool"] != "final_result"]
        if any(p["kind"] == "tool_call" and p["tool"] == "final_result" for p in d.get("parts", [])):
            said = (" ".join(texts) + " [final answer]").strip()
        else:
            said = " ".join(texts) or None
    elif kind == "model_request":
        tools = [p["tool"] for p in d.get("parts", []) if p["kind"] == "tool_return" and p.get("tool") != "final_result"]
    elif kind == "agent_start":
        said = f"Received brief: {d.get('prompt')}"
    elif kind == "delegation":
        said = f"Delegated to {d.get('to_agent')}: {d.get('task')}"
        tools = ["delegate"]
    elif kind == "delegation_refused":
        said = f"Delegation to {d.get('to_agent')} refused: {d.get('reason')}"
        tools = ["delegate"]
    elif kind == "agent_end":
        out = d.get("output")
        if isinstance(out, dict):
            said = out.get("decision") or out.get("summary")
        else:
            said = str(out)
    elif kind == "agent_error":
        said = d.get("error")
    elif kind == "human_decision":
        said = f"{d.get('tool')} -> {d.get('result')}"
        tools = [d.get("tool")]
    elif kind in ("run_start", "run_end", "db_reset", "identity_stamped", "tool_blocked"):
        said = None
    return {
        "id": index,
        "ts": e["ts"],
        "run_id": e["run_id"],
        "ticket_id": e["ticket_id"],
        "agent": e["agent"],
        "depth": e["depth"],
        "chain": e["chain"],
        "event": kind,
        "said": said,
        "tools": tools,
        "detail": d,
    }


async def _run_in_background(run_id: str, ticket_id: int) -> None:
    try:
        result: TicketRunResult = await run_ticket(ticket_id, run_id=run_id)
        RUNS[run_id].update(status="done" if result.ok else "failed", result=result.model_dump())
    except Exception as exc:  # run_ticket already catches; this is a last resort
        RUNS[run_id].update(status="failed", result={"error": f"{type(exc).__name__}: {exc}"})
    RUNS[run_id]["finished_at"] = datetime.now().isoformat(timespec="seconds")


# ------------------------------------------------------------------ routes

@app.get("/api/health")
async def health() -> dict:
    desk = await mcp_call("get_desk_today")
    return {"ok": True, "model": MODEL_NAME, "working_db": str(WORKING_DB.relative_to(ROOT)),
            "date_today": desk.get("date_today")}


@app.get("/api/tickets")
async def list_tickets() -> dict:
    """All tickets with open/resolved status, plus whether an agent run is in progress."""
    data = await mcp_call("list_tickets")
    running = {r["ticket_id"] for r in _active_runs()}
    for t in data["tickets"]:
        t["state"] = "resolved" if t["is_resolved"] else "open"
        t["agent_run_in_progress"] = t["id"] in running
    return data


@app.get("/api/tickets/{ticket_id}")
async def ticket_detail(ticket_id: int) -> dict:
    """One ticket, its linked rows, and everything the team posted to its board."""
    ticket = await mcp_call("get_ticket", {"ticket_id": ticket_id})
    if not ticket.get("found"):
        raise HTTPException(404, f"No ticket {ticket_id}")
    board = await mcp_call("get_ticket_board", {"ticket_id": ticket_id})
    return {**ticket, "board": board}


@app.post("/api/tickets/{ticket_id}/run", status_code=202)
async def run_ticket_route(ticket_id: int, wait: bool = False) -> dict:
    """Run the agent team (Boss first) on one ticket.

    Returns immediately with a run_id (poll /api/runs/{run_id} and /api/events),
    or blocks until the run finishes with ?wait=true.
    """
    ticket = await mcp_call("get_ticket", {"ticket_id": ticket_id})
    if not ticket.get("found"):
        raise HTTPException(404, f"No ticket {ticket_id}")
    if any(r["ticket_id"] == ticket_id for r in _active_runs()):
        raise HTTPException(409, f"Ticket {ticket_id} already has an agent run in progress.")
    run_id = new_run_id()
    RUNS[run_id] = {"run_id": run_id, "ticket_id": ticket_id, "status": "running",
                    "started_at": datetime.now().isoformat(timespec="seconds"), "result": None}
    if wait:
        await _run_in_background(run_id, ticket_id)
    else:
        task = asyncio.create_task(_run_in_background(run_id, ticket_id))
        _run_tasks.add(task)
        task.add_done_callback(_run_tasks.discard)
    return RUNS[run_id]


@app.post("/api/tickets/{ticket_id}/human-decision")
async def human_decision(ticket_id: int, body: DecisionBody) -> dict:
    """A person answers an escalated ticket. Posts the decision to the board and reopens the
    ticket so the team can be run again to carry it out. No money moves."""
    ticket = await mcp_call("get_ticket", {"ticket_id": ticket_id})
    if not ticket.get("found"):
        raise HTTPException(404, f"No ticket {ticket_id}")
    if ticket["ticket"]["status"] != "escalated":
        raise HTTPException(409, f"Ticket {ticket_id} is {ticket['ticket']['status']}, not escalated.")
    if any(r["ticket_id"] == ticket_id for r in _active_runs()):
        raise HTTPException(409, f"Ticket {ticket_id} has an agent run in progress.")
    return await human_decide_ticket(ticket_id, body.decided_by, body.decision)


@app.get("/api/runs")
async def list_runs() -> dict:
    return {"runs": list(RUNS.values())}


@app.get("/api/runs/{run_id}")
async def get_run(run_id: str) -> dict:
    if run_id not in RUNS:
        raise HTTPException(404, f"No run {run_id}")
    return RUNS[run_id]


@app.get("/api/events")
async def recent_events(
    limit: int = Query(100, ge=1, le=1000),
    since_id: int | None = Query(None, description="Only events with id greater than this (for polling)."),
    ticket_id: int | None = None,
    run_id: str | None = None,
    verbose: bool = Query(False, description="Include raw model_request/tool-result events."),
) -> dict:
    """Recent agent events from output/audit_trail.json: what each agent said and which tools it used."""
    events = audit.read_all()
    out = []
    for i, e in enumerate(events):
        if since_id is not None and i <= since_id:
            continue
        if ticket_id is not None and e.get("ticket_id") != ticket_id:
            continue
        if run_id is not None and not str(e.get("run_id", "")).startswith(run_id):
            continue
        if not verbose and e["event"] in ("model_request", "user_prompt"):
            continue
        out.append(_summarize_event(i, e))
    out = out[-limit:]
    return {"count": len(out), "last_id": len(events) - 1, "events": out}


@app.get("/api/payments")
async def payment_requests(status: str = "") -> dict:
    """Payment requests the agents prepared (filter: pending, paid, rejected)."""
    return await mcp_call("list_payment_requests", {"status": status})


@app.post("/api/payments/{request_id}/approve")
async def approve_payment(request_id: int, body: ApproveBody) -> dict:
    """A human approves a pending payment or purchase order. This is the only route that changes cash.

    The MCP approve_payment tool refuses (409 here) if cash would go negative,
    the vendor still has an open invoice, or the request isn't pending.
    """
    result = await human_decide_payment(request_id, body.approved_by.strip(), approve=True)
    if _refused(result):
        raise HTTPException(409, detail=result)
    return result


@app.post("/api/payments/{request_id}/reject")
async def reject_payment(request_id: int, body: RejectBody) -> dict:
    """A human rejects a pending payment or purchase order. No money moves."""
    result = await human_decide_payment(request_id, body.rejected_by.strip(), approve=False, reason=body.reason)
    if _refused(result):
        raise HTTPException(409, detail=result)
    return result


@app.get("/api/cash")
async def cash() -> dict:
    """Current checking balance from cash_accounts, plus what is pending approval."""
    pos = await mcp_call("get_cash_position")
    checking = next((a for a in pos["accounts"] if a["name"] == "checking"), None)
    if checking is None:
        raise HTTPException(404, "No checking account in cash_accounts")
    payments = await mcp_call("list_payment_requests", {"status": "paid"})
    return {
        "account": "checking",
        "balance": checking["balance"],
        "as_of": checking["date"],
        "pending_requests_total": checking["pending_requests_total"],
        "available_after_pending": checking["available_after_pending"],
        "payments_made": pos["payments_made"],
        "paid_requests": payments["requests"],
    }


@app.post("/api/reset")
async def reset_database() -> dict:
    """Copy data/campus_customs.db over data/campus_customs_new.db for a fresh run.

    The audit trail is kept (append-only); a db_reset event marks the boundary.
    """
    if _active_runs():
        raise HTTPException(409, "An agent run is in progress; wait for it to finish before resetting.")
    shutil.copyfile(ORIGINAL_DB, WORKING_DB)
    RUNS.clear()
    audit.append(AuditEvent(ts=datetime.now().isoformat(timespec="milliseconds"), run_id="reset",
                            ticket_id=None, agent="human", depth=0, chain=["human"], event="db_reset",
                            detail={"copied": "data/campus_customs.db -> data/campus_customs_new.db"}))
    cash_now = await cash()
    tickets = await list_tickets()
    return {"ok": True, "message": "Working database reset to the original values.",
            "balance": cash_now["balance"],
            "tickets": [{"id": t["id"], "status": t["status"]} for t in tickets["tickets"]]}
