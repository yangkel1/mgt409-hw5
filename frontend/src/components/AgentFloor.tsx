import { AGENTS, AGENT_ORDER, AgentIcon, prettyTool } from '../agents'
import type { AgentState, Edge } from '../runState'
import type { AgentName } from '../types'

const STATUS_LABEL = { idle: 'Not called', working: 'Working', done: 'Done', error: 'Error' } as const

function edgePath(from: AgentName, to: AgentName) {
  const a = AGENTS[from]
  const b = AGENTS[to]
  if (a.y === b.y) {
    // specialist <-> specialist: arc beneath the row
    const mx = (a.x + b.x) / 2
    return `M ${a.x} ${a.y + 14} Q ${mx} ${a.y + 34} ${b.x} ${b.y + 14}`
  }
  return `M ${a.x} ${a.y} L ${b.x} ${b.y}`
}

export function AgentFloor({
  agents, edges, running, idleHint,
}: {
  agents: Record<AgentName, AgentState>
  edges: Edge[]
  running: boolean
  idleHint: string
}) {
  const pairs: [AgentName, AgentName][] = []
  AGENT_ORDER.forEach((a, i) => AGENT_ORDER.slice(i + 1).forEach((b) => pairs.push([a, b])))
  const anyActivity = AGENT_ORDER.some((n) => agents[n].status !== 'idle')

  return (
    <div className={`floor ${running ? 'is-running' : ''}`}>
      <svg className="floor-wires" viewBox="0 0 100 100" preserveAspectRatio="none" aria-hidden>
        {/* faint mesh: every agent can reach every other agent */}
        {pairs.map(([a, b]) => (
          <path key={`${a}-${b}`} d={edgePath(a, b)} className="wire wire-mesh" />
        ))}
        {edges.map((e) => (
          <path
            key={`${e.from}>${e.to}`}
            d={edgePath(e.from, e.to)}
            className={`wire wire-live ${running ? 'flowing' : ''}`}
            style={{ stroke: AGENTS[e.from].color }}
          />
        ))}
      </svg>

      {AGENT_ORDER.map((name) => {
        const meta = AGENTS[name]
        const s = agents[name]
        const handoffs = edges.filter((e) => e.to === name).reduce((n, e) => n + e.count, 0)
        return (
          <article
            key={name}
            className={`station station-${name} status-${s.status}`}
            style={{ left: `${meta.x}%`, top: `${meta.y}%`, ['--agent' as string]: meta.color }}
          >
            <header>
              <span className="avatar">
                <AgentIcon name={name} />
                {s.status === 'working' && <span className="pulse" />}
              </span>
              <div className="who">
                <strong>{meta.label}</strong>
                <small>{meta.role}</small>
              </div>
              <span className={`pill pill-${s.status}`}>
                {s.status === 'working' && <i className="dots"><b /><b /><b /></i>}
                {STATUS_LABEL[s.status]}
              </span>
            </header>
            <p className={`bubble voice-${meta.voice} kind-${s.lineKind ?? 'none'}`}>
              {s.line ?? (name === 'boss' ? idleHint : 'Waiting for a brief.')}
            </p>
            <footer>
              {s.tools.slice(-3).map((t) => (
                <code key={t} className="chip">{prettyTool(t)}</code>
              ))}
              {s.tools.length > 3 && <code className="chip more">+{s.tools.length - 3}</code>}
              {handoffs > 0 && <span className="handoffs">{handoffs}× brief</span>}
            </footer>
          </article>
        )
      })}
      {!anyActivity && <div className="floor-hint">Full connectivity: any agent can hand work to any other.</div>}
    </div>
  )
}
