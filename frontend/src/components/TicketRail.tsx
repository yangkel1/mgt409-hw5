import { TICKET_TYPES } from '../agents'
import type { Ticket } from '../types'

function stampFor(t: Ticket, running: boolean) {
  if (running) return { text: 'with the team', cls: 'stamp-working' }
  if (t.status === 'resolved') return { text: 'Resolved', cls: 'stamp-resolved' }
  if (t.status === 'escalated') return { text: 'Escalated', cls: 'stamp-escalated' }
  return null
}

export function TicketRail({
  tickets, selected, onSelect, runningIds,
}: {
  tickets: Ticket[]
  selected: number | null
  onSelect: (id: number) => void
  runningIds: Set<number>
}) {
  const open = tickets.filter((t) => t.status !== 'resolved').length
  return (
    <aside className="rail">
      <div className="rail-head">
        <h2>Ticket spike</h2>
        <span>{open} open · {tickets.length - open} resolved</span>
      </div>
      <ul>
        {tickets.map((t, i) => {
          const type = TICKET_TYPES[t.type] ?? { label: t.type, tone: '#888' }
          const running = runningIds.has(t.id) || t.agent_run_in_progress
          const stamp = stampFor(t, running)
          return (
            <li key={t.id} style={{ ['--tilt' as string]: `${(i % 2 ? 1 : -1) * 0.6}deg` }}>
              <button
                className={`ticket ${selected === t.id ? 'selected' : ''} ${t.status === 'resolved' ? 'done' : ''}`}
                onClick={() => onSelect(t.id)}
                style={{ ['--tone' as string]: type.tone }}
              >
                <div className="ticket-top">
                  <span className="ticket-no">#{t.id}</span>
                  <span className="ticket-type">{type.label}</span>
                </div>
                <h3>{t.subject}</h3>
                <p className="ticket-from">from {t.requester}</p>
                <p className="ticket-notes">“{t.notes}”</p>
                <div className="ticket-meta">
                  {t.sku && <span>{t.sku}{t.size ? ` · ${t.size}` : ''}{t.qty ? ` × ${t.qty}` : ''}</span>}
                  {t.lease_id && <span>lease {t.lease_id}</span>}
                  {t.invoice_id && <span>invoice {t.invoice_id}</span>}
                </div>
                {stamp && <span className={`stamp ${stamp.cls}`}>{stamp.text}</span>}
              </button>
            </li>
          )
        })}
      </ul>
    </aside>
  )
}
