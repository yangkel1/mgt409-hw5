import { AGENTS, AGENT_ORDER, AgentIcon, money, prettyTool } from '../agents'
import type { RunView } from '../runState'
import type { AgentReport, BoardNote, TicketDetail, TicketResolution } from '../types'

function isResolution(r: unknown): r is TicketResolution {
  return !!r && typeof r === 'object' && 'decision' in r
}

function Draft({ note }: { note: BoardNote }) {
  const who = note.kind === 'landlord_draft' ? 'To the landlord' : note.kind === 'vendor_draft' ? 'To the vendor' : 'To the customer'
  return (
    <figure className="letter">
      <figcaption>
        <span>{who}</span>
        <em>Draft #{note.id} · by {note.author.replace('_', ' ')} · not sent</em>
      </figcaption>
      <blockquote>{note.content}</blockquote>
    </figure>
  )
}

export function Summary({ run, detail }: { run: RunView; detail: TicketDetail | null }) {
  const boss = run.agents.boss.report
  const drafts = (detail?.board.notes ?? []).filter((n) => n.kind.endsWith('_draft'))
  const reqs = detail?.board.payment_requests ?? []
  const humanCalls = (detail?.board.notes ?? []).filter((n) => n.author.startsWith('human:') && n.kind === 'decision' && !n.content.startsWith('Status '))
  const waiting = reqs.some((r) => r.status === 'pending')

  if (!run.runId) {
    return <div className="empty">The after-action summary appears here once the team has worked this ticket.</div>
  }

  return (
    <div className="summary">
      {isResolution(boss) && (
        <section className={`verdict verdict-${boss.final_status}`}>
          <div className="verdict-head">
            <span className="verdict-stamp">{boss.final_status.replace(/_/g, ' ')}</span>
            <h3>The Boss's call</h3>
          </div>
          <p className="verdict-decision">{boss.decision}</p>
          <p className="verdict-summary">{boss.summary}</p>
          {reqs.length > 0 ? (
            <div className={`verdict-actions ${waiting ? '' : 'all-done'}`}>
              <strong>{waiting ? 'Waiting on you' : 'Human approvals: done'}</strong>
              <ul>
                {reqs.map((r) => (
                  <li key={r.id}>
                    Request #{r.id}: {money(r.amount)} to {r.payee} ({r.kind.replace('_', ' ')}){' '}
                    <b className={`req-${r.status}`}>
                      {r.status === 'pending' ? 'pending approval' : `${r.status} · signed ${r.decided_by}`}
                    </b>
                  </li>
                ))}
              </ul>
            </div>
          ) : boss.human_actions_needed.length > 0 && (
            <div className="verdict-actions">
              <strong>Waiting on you</strong>
              <ul>{boss.human_actions_needed.map((a, i) => <li key={i}>{a}</li>)}</ul>
            </div>
          )}
        </section>
      )}

      <div className="reports">
        {AGENT_ORDER.filter((n) => n !== 'boss').map((name) => {
          const s = run.agents[name]
          const meta = AGENTS[name]
          const r = s.report as AgentReport | null
          if (s.status === 'idle') {
            return (
              <article key={name} className="report not-called" style={{ ['--agent' as string]: meta.color }}>
                <header><AgentIcon name={name} size={16} /><strong>{meta.label}</strong></header>
                <p>Not called on this ticket.</p>
              </article>
            )
          }
          return (
            <article key={name} className="report" style={{ ['--agent' as string]: meta.color }}>
              <header>
                <AgentIcon name={name} size={16} />
                <strong>{meta.label}</strong>
                {r?.needs_human && <span className="needs-human">needs human</span>}
              </header>
              <p>{r && typeof r === 'object' ? r.summary : s.line}</p>
              {r && typeof r === 'object' && r.actions_taken?.length > 0 && (
                <ul className="did">{r.actions_taken.map((a, i) => <li key={i}>{a}</li>)}</ul>
              )}
              {s.tools.length > 0 && (
                <div className="t-tools">{s.tools.map((t) => <code key={t} className="chip">{prettyTool(t)}</code>)}</div>
              )}
            </article>
          )
        })}
      </div>

      {humanCalls.length > 0 && (
        <section className="human-calls">
          <h3>Human decisions</h3>
          {humanCalls.map((n) => (
            <blockquote key={n.id}><b>{n.author.replace('human:', '')}:</b> {n.content}</blockquote>
          ))}
        </section>
      )}

      {drafts.length > 0 && (
        <section className="drafts">
          <h3>Drafts on the board</h3>
          {drafts.map((n) => <Draft key={n.id} note={n} />)}
        </section>
      )}
    </div>
  )
}
