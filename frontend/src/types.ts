export type AgentName = 'boss' | 'inventory' | 'accounting' | 'facilities' | 'customer_service'

export interface Ticket {
  id: number
  type: string
  requester: string
  subject: string
  sku: string | null
  size: string | null
  qty: number | null
  lease_id: number | null
  invoice_id: number | null
  status: string
  notes: string | null
  created_at: string
  is_resolved: boolean
  state: 'open' | 'resolved'
  agent_run_in_progress: boolean
}

export interface AgentEvent {
  id: number
  ts: string
  run_id: string
  ticket_id: number | null
  agent: string
  depth: number
  chain: string[]
  event: string
  said: string | null
  tools: string[]
  // eslint-disable-next-line @typescript-eslint/no-explicit-any
  detail: Record<string, any>
}

export interface TicketResolution {
  ticket_id: number
  final_status: 'resolved' | 'escalated'
  decision: string
  summary: string
  agents_consulted: AgentName[]
  payment_request_ids: number[]
  purchase_order_ids: number[]
  customer_draft_note_ids: number[]
  human_actions_needed: string[]
}

export interface AgentReport {
  agent: AgentName
  ticket_id: number | null
  summary: string
  facts: string[]
  actions_taken: string[]
  payment_request_ids: number[]
  purchase_order_ids: number[]
  board_note_ids: number[]
  needs_human: boolean
  open_questions: string[]
}

export interface RunInfo {
  run_id: string
  ticket_id: number
  status: 'running' | 'done' | 'failed'
  started_at: string
  finished_at?: string
  result: {
    ok?: boolean
    resolution?: TicketResolution | null
    error?: string | null
    usage?: { requests: number; tool_calls: number; total_tokens: number }
    delegations?: number
  } | null
}

export interface PaymentRequest {
  id: number
  ticket_id: number | null
  kind: 'invoice' | 'rent' | 'purchase_order'
  ref_id: number
  payee: string
  amount: number
  account: string
  reason: string | null
  status: 'pending' | 'paid' | 'rejected'
  requested_by: string
  decided_by: string | null
  decided_at: string | null
  decision_note: string | null
  payment_id: number | null
  created_at: string
}

export interface Cash {
  account: string
  balance: number
  as_of: string
  pending_requests_total: number
  available_after_pending: number
  payments_made: { count: number; total: number }
  paid_requests: PaymentRequest[]
}

export interface BoardNote {
  id: number
  ticket_id: number
  author: string
  kind: 'finding' | 'customer_draft' | 'vendor_draft' | 'landlord_draft' | 'decision'
  content: string
  created_at: string
}

export interface PurchaseOrder {
  id: number
  vendor_id: number
  sku: string
  size: string
  qty: number
  total: number
  status: string
  expected_arrival: string | null
}

export interface TicketDetail {
  found: boolean
  ticket: Ticket
  date_today: string
  board: {
    notes: BoardNote[]
    payment_requests: PaymentRequest[]
    purchase_orders: PurchaseOrder[]
  }
}

export interface Health {
  ok: boolean
  model: string
  working_db: string
  date_today: string
}
