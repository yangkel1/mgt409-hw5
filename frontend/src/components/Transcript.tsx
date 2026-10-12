import { useEffect, useRef } from 'react'
import { AGENTS, AgentIcon, clockTime, isAgent, prettyTool } from '../agents'
import type { AgentEvent } from '../types'

const SHOWN = new Set([
  'run_start', 'agent_start', 'model_response', 'delegation', 'delegation_refused',
  'agent_end', 'agent_error', 'run_end', 'identity_stamped', 'final_status_recorded',
])

function Row({ e }: { e: AgentEvent }) {
  const agent = isAgent(e.agent) ? AGENTS[e.agent] : null
  const style = { ['--agent' as string]: agent?.color ?? '#8a93a3', marginLeft: `${e.depth * 22}px` }

  if (e.event === 'run_start' || e.event === 'run_end') {
    const u = e.detail?.usage
    return (
      <li className="t-marker">
        <span>{e.event === 'run_start' ? 'Ticket handed to the team' : e.detail?.ok ? 'Run complete' : 'Run stopped'}</span>
        {u && <em>{u.requests} model calls · {u.tool_calls} tool calls · {u.total_tokens.toLocaleString()} tokens</em>}
        <time>{clockTime(e.ts)}</time>
      </li>
    )
  }
  if (e.event === 'delegation' || e.event === 'delegation_refused') {
    const to = e.detail?.to_agent
    return (
      <li className={`t-handoff ${e.event === 'delegation_refused' ? 'refused' : ''}`} style={style}>
        <span className="t-from">{agent?.label}</span>
        <span className="t-arrow">→</span>
        <span className="t-to" style={{ color: isAgent(to) ? AGENTS[to].color : undefined }}>
          {isAgent(to) ? AGENTS[to].label : to}
        </span>
        <p>{e.event === 'delegation_refused' ? `Refused: ${e.detail?.reason}` : e.detail?.task}</p>
        <time>{clockTime(e.ts)}</time>
      </li>
    )
  }
  if (e.event === 'identity_stamped' || e.event === 'final_status_recorded') {
    return (
      <li className="t-system" style={style}>
        {e.event === 'identity_stamped'
          ? `Guardrail: "${e.detail?.model_value}" signature corrected to ${e.detail?.set_to}`
          : `Status recorded: ${e.detail?.new_status}`}
      </li>
    )
  }

  const tools = (e.tools ?? []).filter((t) => t !== 'delegate')
  let text: string | null = e.said
  if (e.event === 'agent_start') text = null
  if (e.event === 'model_response' && text?.endsWith('[final answer]')) text = text.replace('[final answer]', '').trim() || null
  if (e.event === 'model_response' && !text && !tools.length) return null
  const final = e.event === 'agent_end'

  return (
    <li className={`t-line voice-${agent?.voice ?? 'plain'} ${final ? 'is-final' : ''}`} style={style}>
      <span className="t-avatar">{isAgent(e.agent) ? <AgentIcon name={e.agent} size={15} /> : null}</span>
      <div className="t-body">
        <div className="t-head">
          <strong>{agent?.label ?? e.agent}</strong>
          <span className="t-tag">
            {e.event === 'agent_start' ? 'picked up the brief' : final ? 'final report' : e.event === 'agent_error' ? 'error' : tools.length ? 'tool call' : 'says'}
          </span>
          <time>{clockTime(e.ts)}</time>
        </div>
        {text && <p>{text}</p>}
        {tools.length > 0 && (
          <div className="t-tools">
            {tools.map((t, i) => <code key={i} className="chip">{prettyTool(t)}</code>)}
          </div>
        )}
      </div>
    </li>
  )
}

export function Transcript({ events, running }: { events: AgentEvent[]; running: boolean }) {
  const end = useRef<HTMLLIElement>(null)
  const shown = events.filter((e) => SHOWN.has(e.event))
  useEffect(() => {
    if (running) end.current?.scrollIntoView({ behavior: 'smooth', block: 'nearest' })
  }, [shown.length, running])

  if (!shown.length) {
    return <div className="empty">No activity yet. Send this ticket to the team to watch them work.</div>
  }
  return (
    <ol className="transcript">
      {shown.map((e) => <Row key={e.id} e={e} />)}
      {running && (
        <li className="t-typing" ref={end}><i className="dots"><b /><b /><b /></i> agents are working…</li>
      )}
      {!running && <li ref={end} />}
    </ol>
  )
}

