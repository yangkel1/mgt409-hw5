"""Data types shared by the Campus Customs agent team and the backend."""

from typing import Any, Literal

from pydantic import BaseModel, Field

AgentName = Literal["boss", "inventory", "accounting", "facilities", "customer_service"]
AGENT_NAMES: tuple[AgentName, ...] = ("boss", "inventory", "accounting", "facilities", "customer_service")

TicketStatus = Literal["open", "in_progress", "waiting_on_approval", "escalated", "resolved"]


class AgentReport(BaseModel):
    """What a specialist (Inventory, Accounting, Facilities, Customer Service)
    hands back to whoever delegated to it."""

    agent: AgentName
    ticket_id: int | None = Field(description="Ticket this work was for, if any.")
    summary: str = Field(description="Two to four sentences: what you found and what you did.")
    facts: list[str] = Field(
        default_factory=list,
        description="Key numbers you relied on, each with the MCP tool it came from, "
        "e.g. 'CC-HOOD-NAVY M on hand = 8 (check_stock)'.",
    )
    actions_taken: list[str] = Field(
        default_factory=list, description="Writes you made: board notes, payment requests, POs."
    )
    payment_request_ids: list[int] = Field(default_factory=list)
    purchase_order_ids: list[int] = Field(default_factory=list)
    board_note_ids: list[int] = Field(default_factory=list)
    needs_human: bool = Field(description="True if a person must approve or decide something.")
    open_questions: list[str] = Field(
        default_factory=list, description="Anything you could not answer from the database."
    )


class TicketResolution(BaseModel):
    """The Boss's final call on one ticket."""

    ticket_id: int
    final_status: Literal["resolved", "escalated"] = Field(
        description="resolved = the team finished its part (approvals may still be pending for a human); "
        "escalated = the team could not handle it within the shop rules."
    )
    decision: str = Field(description="The Boss's decision in one or two sentences.")
    summary: str = Field(description="What the team found and did, in plain language.")
    agents_consulted: list[AgentName] = Field(default_factory=list)
    payment_request_ids: list[int] = Field(default_factory=list)
    purchase_order_ids: list[int] = Field(default_factory=list)
    customer_draft_note_ids: list[int] = Field(default_factory=list)
    human_actions_needed: list[str] = Field(
        default_factory=list,
        description="Exact approvals or decisions a person must make, e.g. "
        "'Approve payment request 1 ($840 to Bulldog Print Co)'.",
    )


class AuditEvent(BaseModel):
    """One line in output/audit_trail.json."""

    ts: str
    run_id: str
    ticket_id: int | None
    agent: str
    depth: int
    chain: list[str]
    step: int | None = None
    event: str = Field(
        description="run_start, agent_start, user_prompt, model_request, model_response, "
        "delegation, delegation_refused, identity_stamped, agent_end, agent_error, run_end, human_decision"
    )
    detail: dict[str, Any] = Field(default_factory=dict)


class TicketRunResult(BaseModel):
    run_id: str
    ticket_id: int
    ok: bool
    resolution: TicketResolution | None = None
    error: str | None = None
    usage: dict[str, Any] = Field(default_factory=dict)
    delegations: int = 0


class PaymentDecision(BaseModel):
    """Body of a human approve or reject action from the dashboard."""

    request_id: int
    decided_by: str = Field(min_length=1, description="Name of the human approver.")
    reason: str = ""
