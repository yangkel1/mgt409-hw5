"""Campus Customs agent team (PydanticAI).

Five agents (boss, inventory, accounting, facilities, customer_service) share
one model, gpt-6-luna through Portkey, and one tool layer, the campus-customs
MCP server. Every shop fact comes from that server; this file adds no shop
tools of its own. The only local tool is `delegate`, which lets any agent hand
work to any other agent (full connectivity), with caps on depth, count, and tokens.

Every agent loop step is appended to output/audit_trail.json.

CLI (from hw5/):
    .venv/bin/python -m backend.agents --ticket 101
    .venv/bin/python -m backend.agents --all
"""

import argparse
import asyncio
import json
import os
import sys
import uuid
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Any

from dotenv import load_dotenv
from fastmcp.client.transports import StdioTransport
from openai import AsyncOpenAI
from pydantic_ai import Agent, ModelSettings, RunContext, RunUsage, UsageLimitExceeded, UsageLimits
from pydantic_ai.mcp import MCPToolset
from pydantic_ai.models.openai import OpenAIResponsesModel
from pydantic_ai.providers.openai import OpenAIProvider

from . import audit
from .audit import clip
from .models import AGENT_NAMES, AgentName, AgentReport, AuditEvent, TicketResolution, TicketRunResult

ROOT = Path(__file__).resolve().parents[1]
PROMPTS_DIR = Path(__file__).resolve().parent / "prompts"
load_dotenv(ROOT / ".env")
os.environ.setdefault("PYDANTIC_AI_NO_BANNER", "1")

# ------------------------------------------------------------------ config

MODEL_NAME = "gpt-6-luna"  # the only model allowed in this project, for every agent
PORTKEY_BASE_URL = os.getenv("PORTKEY_BASE_URL", "https://api.portkey.ai/v1")

# Token and loop limits (per ticket; shared by every agent working that ticket)
MAX_OUTPUT_TOKENS = 4000  # per model response (sent as max_output_tokens)
MAX_DEPTH = 2  # boss (0) -> specialist (1) -> specialist (2), and no deeper
MAX_DELEGATIONS_PER_TICKET = 8
TICKET_LIMITS = UsageLimits(request_limit=40, tool_calls_limit=80, total_tokens_limit=250_000)

# ------------------------------------------------------------------ MCP tool scoping

HUMAN_ONLY_TOOLS = {"approve_payment", "reject_payment"}  # never given to any agent

AGENT_TOOLS: dict[AgentName, set[str]] = {
    "boss": {
        "get_desk_today", "list_open_tickets", "get_ticket", "get_ticket_board",
        "get_cash_position", "list_payment_requests", "post_board_note", "update_ticket_status",
    },
    "inventory": {
        "get_desk_today", "get_ticket", "get_ticket_board", "check_stock", "list_vendors",
        "get_invoice_status", "post_board_note",
    },
    "accounting": {
        "get_desk_today", "get_ticket", "get_ticket_board", "check_stock", "list_vendors",
        "get_invoice_status", "list_open_invoices", "get_lease_and_cash", "get_cash_position",
        "quote_margin", "list_payment_requests", "request_payment", "create_purchase_order",
        "post_board_note",
    },
    "facilities": {
        "get_desk_today", "get_ticket", "get_ticket_board", "get_lease_and_cash",
        "get_cash_position", "post_board_note",
    },
    "customer_service": {
        "get_desk_today", "get_ticket", "get_ticket_board", "check_stock", "quote_margin",
        "list_vendors", "post_board_note",
    },
}
assert not any(tools & HUMAN_ONLY_TOOLS for tools in AGENT_TOOLS.values())

# Tools the backend may call directly for the dashboard (read-only).
BACKEND_READ_TOOLS = {
    "get_desk_today", "list_tickets", "list_open_tickets", "get_ticket", "get_ticket_board", "check_stock",
    "list_vendors", "get_invoice_status", "list_open_invoices", "get_lease_and_cash",
    "get_cash_position", "quote_margin", "list_payment_requests",
}

# Arguments that record who did something. The MCP layer overwrites them with
# the real calling agent so a model can't sign as someone else.
IDENTITY_ARGS = ("author", "requested_by", "updated_by")


# ------------------------------------------------------------------ deps

@dataclass
class TicketBudget:
    delegations: int = 0


@dataclass
class TeamDeps:
    run_id: str
    ticket_id: int | None
    agent: AgentName
    depth: int = 0
    chain: list[str] = field(default_factory=list)
    budget: TicketBudget = field(default_factory=TicketBudget)


def _log(deps: TeamDeps, event: str, step: int | None = None, **detail: Any) -> None:
    audit.append(
        AuditEvent(
            ts=datetime.now().isoformat(timespec="milliseconds"),
            run_id=deps.run_id,
            ticket_id=deps.ticket_id,
            agent=deps.agent,
            depth=deps.depth,
            chain=list(deps.chain),
            step=step,
            event=event,
            detail=detail,
        )
    )


# ------------------------------------------------------------------ model + MCP

def build_model() -> OpenAIResponsesModel:
    api_key = os.getenv("PORTKEY_API_KEY")
    if not api_key:
        raise RuntimeError("PORTKEY_API_KEY is missing. Copy .env.example to .env and fill it in.")
    headers = {"x-portkey-api-key": api_key, "x-portkey-provider": "openai"}
    # Portkey can replay cached responses for identical requests (e.g. a re-run
    # right after a DB reset). Force a fresh model call unless caching is opted into.
    if os.getenv("PORTKEY_USE_CACHE", "false").lower() != "true":
        headers["x-portkey-cache-force-refresh"] = "true"
    client = AsyncOpenAI(api_key=api_key, base_url=PORTKEY_BASE_URL, default_headers=headers)
    # Responses API: Portkey's gpt-6-luna deployment rejects function tools on
    # /v1/chat/completions while reasoning is on.
    return OpenAIResponsesModel(MODEL_NAME, provider=OpenAIProvider(openai_client=client))


async def _process_tool_call(ctx: RunContext[TeamDeps], call_tool, name: str, args: dict[str, Any]):
    """Runs on every agent -> MCP tool call: block human-only tools and stamp identity."""
    if name in HUMAN_ONLY_TOOLS:  # defense in depth; these are already filtered out
        _log(ctx.deps, "tool_blocked", tool=name, args=clip(args))
        return {"ok": False, "refused": True, "reason": f"{name} requires a human approver."}
    for key in IDENTITY_ARGS:
        if key in args and args[key] != ctx.deps.agent:
            _log(ctx.deps, "identity_stamped", tool=name, arg=key, model_value=args[key], set_to=ctx.deps.agent)
            args[key] = ctx.deps.agent
    return await call_tool(name, args)


MCP = MCPToolset(
    StdioTransport(command=sys.executable, args=[str(ROOT / "mcp_server" / "server.py")], cwd=str(ROOT)),
    id="campus-customs",
    process_tool_call=_process_tool_call,
)


# ------------------------------------------------------------------ delegation tool

async def delegate(ctx: RunContext[TeamDeps], to_agent: AgentName, task: str) -> str:
    """Hand a task to another Campus Customs agent and get their report back.

    to_agent: one of boss, inventory, accounting, facilities, customer_service.
    task: a complete brief, including the ticket id, what to find out, and what to
    do. The other agent can't see your conversation.
    """
    d = ctx.deps
    refusal = None
    if to_agent not in AGENT_NAMES:
        refusal = f"Unknown agent {to_agent!r}."
    elif to_agent == d.agent:
        refusal = "You can't delegate to yourself."
    elif to_agent in d.chain:
        refusal = f"{to_agent} is already waiting on this chain ({' -> '.join(d.chain)}). Answer in your report instead."
    elif d.depth >= MAX_DEPTH:
        refusal = f"Delegation depth limit ({MAX_DEPTH}) reached. Finish with what you have."
    elif d.budget.delegations >= MAX_DELEGATIONS_PER_TICKET:
        refusal = f"Delegation limit ({MAX_DELEGATIONS_PER_TICKET} per ticket) reached. Finish with what you have."
    if refusal:
        _log(d, "delegation_refused", to_agent=to_agent, task=clip(task), reason=refusal)
        return f"REFUSED: {refusal}"

    d.budget.delegations += 1
    _log(d, "delegation", to_agent=to_agent, task=clip(task), delegation_number=d.budget.delegations)
    child = TeamDeps(
        run_id=d.run_id,
        ticket_id=d.ticket_id,
        agent=to_agent,
        depth=d.depth + 1,
        chain=[*d.chain, to_agent],
        budget=d.budget,
    )
    try:
        output = await run_agent(to_agent, task, child, usage=ctx.usage)
    except UsageLimitExceeded:
        raise  # the ticket's token budget is spent; stop the whole run
    except Exception as exc:  # let the caller carry on without this report
        return f"FAILED: {to_agent} could not finish ({type(exc).__name__}: {exc})."
    return output.model_dump_json()


# ------------------------------------------------------------------ agents

def _load_prompt(name: AgentName) -> str:
    return (PROMPTS_DIR / f"{name}.md").read_text()


def _context_instructions(ctx: RunContext[TeamDeps]) -> str:
    d = ctx.deps
    return (
        f"Run context: you are '{d.agent}'. Ticket: {d.ticket_id}. "
        f"Delegation chain: {' -> '.join(d.chain)} (depth {d.depth} of max {MAX_DEPTH}). "
        f"Delegations used on this ticket: {d.budget.delegations} of {MAX_DELEGATIONS_PER_TICKET}."
    )


def build_team(model: OpenAIResponsesModel | None = None) -> dict[AgentName, Agent]:
    model = model or build_model()
    team: dict[AgentName, Agent] = {}
    for name in AGENT_NAMES:
        allowed = AGENT_TOOLS[name]
        agent = Agent(
            model,
            name=name,
            deps_type=TeamDeps,
            output_type=TicketResolution if name == "boss" else AgentReport,
            instructions=[_load_prompt(name), _context_instructions],
            toolsets=[MCP.filtered(lambda ctx, tool_def, allowed=allowed: tool_def.name in allowed)],
            tools=[delegate],
            model_settings=ModelSettings(max_tokens=MAX_OUTPUT_TOKENS),
            retries=2,
        )
        team[name] = agent
    return team


_TEAM: dict[AgentName, Agent] | None = None


def get_team() -> dict[AgentName, Agent]:
    global _TEAM
    if _TEAM is None:
        _TEAM = build_team()
    return _TEAM


# ------------------------------------------------------------------ audited agent loop

def _log_node(deps: TeamDeps, step: int, node: Any) -> None:
    if Agent.is_user_prompt_node(node):
        _log(deps, "user_prompt", step, prompt=clip(node.user_prompt))
    elif Agent.is_model_request_node(node):
        parts = []
        for p in node.request.parts:
            if p.part_kind == "tool-return":
                parts.append({"kind": "tool_return", "tool": p.tool_name, "tool_call_id": p.tool_call_id,
                              "content": clip(p.content)})
            elif p.part_kind == "retry-prompt":
                parts.append({"kind": "retry", "tool": getattr(p, "tool_name", None), "content": clip(p.content)})
            elif p.part_kind == "user-prompt":
                parts.append({"kind": "user_prompt", "content": clip(p.content)})
        _log(deps, "model_request", step, parts=parts)
    elif Agent.is_call_tools_node(node):
        resp = node.model_response
        parts = []
        for p in resp.parts:
            if p.part_kind == "text":
                parts.append({"kind": "text", "content": clip(p.content)})
            elif p.part_kind == "tool-call":
                parts.append({"kind": "tool_call", "tool": p.tool_name, "tool_call_id": p.tool_call_id,
                              "args": clip(p.args_as_dict())})
            elif p.part_kind == "thinking":
                parts.append({"kind": "thinking", "chars": len(p.content or "")})
        _log(deps, "model_response", step, model=resp.model_name, parts=parts,
             usage={"input_tokens": resp.usage.input_tokens, "output_tokens": resp.usage.output_tokens})
    elif Agent.is_end_node(node):
        # Final reports are small structured objects; keep them whole for the dashboard summary.
        _log(deps, "agent_end", step, output=node.data.output.model_dump())


async def run_agent(name: AgentName, prompt: str, deps: TeamDeps, usage: RunUsage | None = None):
    agent = get_team()[name]
    _log(deps, "agent_start", prompt=clip(prompt), tools=sorted(AGENT_TOOLS[name]) + ["delegate"])
    try:
        async with agent.iter(prompt, deps=deps, usage=usage, usage_limits=TICKET_LIMITS) as run:
            step = 0
            async for node in run:
                step += 1
                _log_node(deps, step, node)
        return run.result.output
    except Exception as exc:
        _log(deps, "agent_error", error=f"{type(exc).__name__}: {clip(str(exc), 500)}")
        raise


def _usage_dict(u: RunUsage) -> dict[str, Any]:
    return {"requests": u.requests, "tool_calls": u.tool_calls,
            "input_tokens": u.input_tokens, "output_tokens": u.output_tokens,
            "total_tokens": u.input_tokens + u.output_tokens}


def new_run_id() -> str:
    return f"run-{datetime.now():%Y%m%d-%H%M%S}-{uuid.uuid4().hex[:6]}"


async def _record_final_status(deps: TeamDeps, resolution: TicketResolution) -> None:
    """Safety net: if the Boss returned a final status but didn't record it on the
    ticket, record it through the MCP tool (still MCP, still audited)."""
    ticket = _tool_payload(await MCP.direct_call_tool("get_ticket", {"ticket_id": resolution.ticket_id}))
    current = ticket.get("ticket", {}).get("status")
    if current != resolution.final_status:
        result = _tool_payload(await MCP.direct_call_tool("update_ticket_status", {
            "ticket_id": resolution.ticket_id, "status": resolution.final_status,
            "resolution_note": f"Recorded from the Boss's final decision: {resolution.decision}",
            "updated_by": "boss"}))
        _log(deps, "final_status_recorded", old_status=current, new_status=resolution.final_status,
             result=clip(result))


async def run_ticket(ticket_id: int, run_id: str | None = None) -> TicketRunResult:
    """Have the Boss work one ticket end to end."""
    deps = TeamDeps(run_id=run_id or new_run_id(), ticket_id=ticket_id, agent="boss", chain=["boss"])
    usage = RunUsage()
    _log(deps, "run_start", model=MODEL_NAME, limits={
        "max_output_tokens": MAX_OUTPUT_TOKENS, "max_depth": MAX_DEPTH,
        "max_delegations": MAX_DELEGATIONS_PER_TICKET,
        "request_limit": TICKET_LIMITS.request_limit, "tool_calls_limit": TICKET_LIMITS.tool_calls_limit,
        "total_tokens_limit": TICKET_LIMITS.total_tokens_limit})
    prompt = (
        f"Work ticket {ticket_id} from the Campus Customs board. Follow your process, "
        "delegate to the right specialists, record your decision, and return a TicketResolution."
    )
    try:
        async with MCP:
            resolution = await run_agent("boss", prompt, deps, usage=usage)
            await _record_final_status(deps, resolution)
        result = TicketRunResult(run_id=deps.run_id, ticket_id=ticket_id, ok=True, resolution=resolution,
                                 usage=_usage_dict(usage), delegations=deps.budget.delegations)
    except Exception as exc:
        result = TicketRunResult(run_id=deps.run_id, ticket_id=ticket_id, ok=False,
                                 error=f"{type(exc).__name__}: {exc}", usage=_usage_dict(usage),
                                 delegations=deps.budget.delegations)
    _log(deps, "run_end", ok=result.ok, error=result.error, usage=result.usage, delegations=result.delegations)
    return result


async def run_open_tickets() -> list[TicketRunResult]:
    """Work every open ticket, oldest first. Run sequentially so tickets see
    each other's pending payment requests when doing cash math."""
    run_id = new_run_id()
    tickets = (await mcp_call("list_open_tickets"))["tickets"]
    return [await run_ticket(t["id"], run_id=f"{run_id}-t{t['id']}") for t in tickets]


# ------------------------------------------------------------------ backend helpers (no agents)

def _tool_payload(result: Any) -> Any:
    if isinstance(result, str):
        try:
            return json.loads(result)
        except json.JSONDecodeError:
            return result
    return result


async def mcp_call(tool: str, args: dict[str, Any] | None = None) -> Any:
    """Read-only MCP call for the backend/dashboard."""
    if tool not in BACKEND_READ_TOOLS:
        raise PermissionError(f"{tool} is not a read-only tool.")
    async with MCP:
        return _tool_payload(await MCP.direct_call_tool(tool, args or {}))


async def human_decide_payment(request_id: int, decided_by: str, approve: bool, reason: str = "") -> Any:
    """The only path to approve_payment / reject_payment: a person's decision on the dashboard."""
    tool = "approve_payment" if approve else "reject_payment"
    args = {"request_id": request_id, "approved_by": decided_by} if approve else \
        {"request_id": request_id, "rejected_by": decided_by, "reason": reason}
    async with MCP:
        result = _tool_payload(await MCP.direct_call_tool(tool, args))
    deps = TeamDeps(run_id=f"human-{datetime.now():%Y%m%d-%H%M%S}", ticket_id=None, agent="human", chain=["human"])
    _log(deps, "human_decision", tool=tool, args=args, result=clip(result))
    return result


async def human_decide_ticket(ticket_id: int, decided_by: str, decision: str) -> dict:
    """A person answers an escalated ticket: their decision is posted to the board
    (author 'human:<name>') and the ticket is reopened so the team can finish it."""
    author = f"human:{decided_by.strip()}"
    async with MCP:
        note = _tool_payload(await MCP.direct_call_tool("post_board_note", {
            "ticket_id": ticket_id, "kind": "decision", "content": decision.strip(), "author": author}))
        status = _tool_payload(await MCP.direct_call_tool("update_ticket_status", {
            "ticket_id": ticket_id, "status": "open",
            "resolution_note": "Reopened with a human decision for the team to carry out.", "updated_by": author}))
    deps = TeamDeps(run_id=f"human-{datetime.now():%Y%m%d-%H%M%S}", ticket_id=ticket_id, agent="human", chain=["human"])
    _log(deps, "human_decision", tool="post_board_note+update_ticket_status",
         args={"ticket_id": ticket_id, "decided_by": decided_by, "decision": decision}, result=clip([note, status]))
    return {"ok": True, "note": note, "status": status}


# ------------------------------------------------------------------ CLI

def main() -> None:
    parser = argparse.ArgumentParser(description="Run the Campus Customs agent team.")
    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument("--ticket", type=int, help="ticket id to work")
    group.add_argument("--all", action="store_true", help="work every open ticket")
    a = parser.parse_args()
    results = asyncio.run(run_open_tickets() if a.all else run_ticket(a.ticket))
    results = results if isinstance(results, list) else [results]
    print(json.dumps([r.model_dump() for r in results], indent=2, default=str))


if __name__ == "__main__":
    main()
