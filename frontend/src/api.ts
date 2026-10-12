import type { AgentEvent, Cash, Health, PaymentRequest, RunInfo, Ticket, TicketDetail } from './types'

export const API_BASE: string = import.meta.env.VITE_API_BASE ?? 'http://localhost:8000'

export class ApiError extends Error {
  status: number
  constructor(message: string, status: number) {
    super(message)
    this.status = status
  }
}

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  let res: Response
  try {
    res = await fetch(API_BASE + path, {
      ...init,
      headers: { 'content-type': 'application/json', ...(init?.headers ?? {}) },
    })
  } catch {
    throw new ApiError(`Can't reach the backend at ${API_BASE}. Is uvicorn running?`, 0)
  }
  const body = await res.json().catch(() => null)
  if (!res.ok) {
    const d = body?.detail
    const msg =
      typeof d === 'string' ? d : d?.reason ?? (Array.isArray(d) ? d[0]?.msg : null) ?? `HTTP ${res.status}`
    throw new ApiError(msg, res.status)
  }
  return body as T
}

const post = <T>(path: string, body?: unknown) =>
  request<T>(path, { method: 'POST', body: body === undefined ? undefined : JSON.stringify(body) })

export const api = {
  health: () => request<Health>('/api/health'),
  tickets: () => request<{ tickets: Ticket[] }>('/api/tickets').then((r) => r.tickets),
  ticket: (id: number) => request<TicketDetail>(`/api/tickets/${id}`),
  runTicket: (id: number) => post<RunInfo>(`/api/tickets/${id}/run`),
  runs: () => request<{ runs: RunInfo[] }>('/api/runs').then((r) => r.runs),
  run: (runId: string) => request<RunInfo>(`/api/runs/${runId}`),
  events: (params: { since_id?: number; limit?: number }) => {
    const q = new URLSearchParams()
    if (params.since_id !== undefined) q.set('since_id', String(params.since_id))
    q.set('limit', String(params.limit ?? 1000))
    return request<{ count: number; last_id: number; events: AgentEvent[] }>(`/api/events?${q}`)
  },
  payments: (status = '') =>
    request<{ requests: PaymentRequest[] }>(`/api/payments?status=${status}`).then((r) => r.requests),
  approve: (id: number, approvedBy: string) =>
    post<{ balance_after: number; amount: number }>(`/api/payments/${id}/approve`, { approved_by: approvedBy }),
  reject: (id: number, rejectedBy: string, reason: string) =>
    post(`/api/payments/${id}/reject`, { rejected_by: rejectedBy, reason }),
  decide: (id: number, decidedBy: string, decision: string) =>
    post(`/api/tickets/${id}/human-decision`, { decided_by: decidedBy, decision }),
  cash: () => request<Cash>('/api/cash'),
  reset: () => post<{ ok: boolean; balance: number }>('/api/reset'),
}
