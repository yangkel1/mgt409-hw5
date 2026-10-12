import { AGENT_ORDER, isAgent, prettyTool } from './agents'
import type { AgentEvent, AgentName, AgentReport, TicketResolution } from './types'

export type AgentStatus = 'idle' | 'working' | 'done' | 'error'

export interface AgentState {
  name: AgentName
  status: AgentStatus
  briefs: number
  line: string | null // what they're saying or doing right now
  lineKind: 'said' | 'doing' | 'brief' | null
  lastTs: string | null
  tools: string[] // unique MCP tools used this run, in order
  toolCalls: number
  report: AgentReport | TicketResolution | null
}

export interface Edge {
  from: AgentName
  to: AgentName
  count: number
  lastTs: string
}

export interface RunView {
  runId: string | null
  agents: Record<AgentName, AgentState>
  edges: Edge[]
  events: AgentEvent[]
  finished: boolean
  totalTokens: number | null
}

const blank = (name: AgentName): AgentState => ({
  name, status: 'idle', briefs: 0, line: null, lineKind: null, lastTs: null, tools: [], toolCalls: 0, report: null,
})

/** Latest run_id for a ticket (by its run_start event), ignoring runs from before the last DB reset. */
export function latestRunId(events: AgentEvent[], ticketId: number): string | null {
  for (let i = events.length - 1; i >= 0; i--) {
    const e = events[i]
    if (e.event === 'db_reset') return null
    if (e.ticket_id === ticketId && e.event === 'run_start') return e.run_id
  }
  return null
}

export function deriveRun(all: AgentEvent[], runId: string | null): RunView {
  const agents = Object.fromEntries(AGENT_ORDER.map((n) => [n, blank(n)])) as Record<AgentName, AgentState>
  const events = runId ? all.filter((e) => e.run_id === runId) : []
  const edges = new Map<string, Edge>()
  const open: Record<string, number> = {}
  let finished = false
  let totalTokens: number | null = null

  for (const e of events) {
    if (e.event === 'run_end') {
      finished = true
      totalTokens = e.detail?.usage?.total_tokens ?? null
    }
    if (!isAgent(e.agent)) continue
    const a = agents[e.agent]
    a.lastTs = e.ts
    switch (e.event) {
      case 'agent_start':
        a.briefs += 1
        open[a.name] = (open[a.name] ?? 0) + 1
        a.status = 'working'
        a.line = 'Reading the brief…'
        a.lineKind = 'brief'
        break
      case 'model_response': {
        const tools = e.tools ?? []
        tools.forEach((t) => {
          if (t !== 'delegate' && !a.tools.includes(t)) a.tools.push(t)
        })
        a.toolCalls += tools.filter((t) => t !== 'delegate').length
        if (e.said && !e.said.endsWith('[final answer]')) {
          a.line = e.said
          a.lineKind = 'said'
        } else if (tools.length) {
          const named = tools.filter((t) => t !== 'delegate').map(prettyTool)
          a.line = named.length ? `Checking ${named.join(', ')}…` : 'Handing work to a teammate…'
          a.lineKind = 'doing'
        } else if (e.said) {
          a.line = 'Writing up the final report…'
          a.lineKind = 'doing'
        }
        break
      }
      case 'delegation': {
        const to = e.detail?.to_agent
        if (isAgent(to)) {
          const key = `${a.name}>${to}`
          const prev = edges.get(key)
          edges.set(key, { from: a.name, to, count: (prev?.count ?? 0) + 1, lastTs: e.ts })
          a.line = `Asked ${to.replace('_', ' ')}: ${e.detail?.task ?? ''}`
          a.lineKind = 'doing'
        }
        break
      }
      case 'agent_end':
        open[a.name] = Math.max((open[a.name] ?? 1) - 1, 0)
        a.status = open[a.name] > 0 ? 'working' : 'done'
        a.report = (e.detail?.output ?? null) as AgentReport | TicketResolution | null
        if (a.report && typeof a.report === 'object') {
          a.line = 'decision' in a.report ? a.report.decision : a.report.summary
          a.lineKind = 'said'
        }
        break
      case 'agent_error':
        a.status = 'error'
        a.line = e.said
        a.lineKind = 'said'
        break
    }
  }
  return { runId, agents, edges: [...edges.values()], events, finished, totalTokens }
}
