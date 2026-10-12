import { useCallback, useEffect, useMemo, useRef, useState } from 'react'
import { API_BASE, api } from './api'
import { AgentIcon, TICKET_TYPES, money } from './agents'
import { AgentFloor } from './components/AgentFloor'
import { ApprovalTray } from './components/ApprovalTray'
import { CashDrawer } from './components/CashDrawer'
import { Summary } from './components/Summary'
import { TicketRail } from './components/TicketRail'
import { Transcript } from './components/Transcript'
import { deriveRun, latestRunId } from './runState'
import type { AgentEvent, Cash, Health, PaymentRequest, RunInfo, Ticket, TicketDetail } from './types'

type Toast = { id: number; tone: 'ok' | 'err' | 'info'; text: string }

function useInterval(fn: () => void, ms: number) {
  const saved = useRef(fn)
  useEffect(() => { saved.current = fn }, [fn])
  useEffect(() => {
    const t = setInterval(() => saved.current(), ms)
    return () => clearInterval(t)
  }, [ms])
}

const deskDate = (d?: string) =>
  d ? new Date(`${d}T12:00:00`).toLocaleDateString('en-US', { weekday: 'long', month: 'long', day: 'numeric', year: 'numeric' }) : '…'

export default function App() {
  const [health, setHealth] = useState<Health | null>(null)
  const [online, setOnline] = useState(true)
  const [tickets, setTickets] = useState<Ticket[]>([])
  // ?ticket=101 opens a specific ticket (handy for links and screenshots)
  const [selected, setSelected] = useState<number | null>(() => {
    const t = Number(new URLSearchParams(window.location.search).get('ticket'))
    return Number.isFinite(t) && t > 0 ? t : null
  })
  const [events, setEvents] = useState<AgentEvent[]>([])
  const lastId = useRef(-1)
  const [runs, setRuns] = useState<Record<string, RunInfo>>({})
  const [pending, setPending] = useState<PaymentRequest[]>([])
  const [cash, setCash] = useState<Cash | null>(null)
  const [detail, setDetail] = useState<TicketDetail | null>(null)
  const [tab, setTab] = useState<'live' | 'summary'>('live')
  const [approver, setApproverState] = useState(() => localStorage.getItem('cc-approver') ?? '')
  const [toasts, setToasts] = useState<Toast[]>([])
  const [confirmReset, setConfirmReset] = useState(false)
  const [decision, setDecision] = useState('')

  const setApprover = (s: string) => {
    setApproverState(s)
    localStorage.setItem('cc-approver', s)
  }
  const toast = useCallback((tone: Toast['tone'], text: string) => {
    const id = Date.now() + Math.random()
    setToasts((t) => [...t, { id, tone, text }])
    setTimeout(() => setToasts((t) => t.filter((x) => x.id !== id)), 6500)
  }, [])

  // ------------------------------------------------------------ data loading
  const refreshDesk = useCallback(async () => {
    try {
      const [t, p, c] = await Promise.all([api.tickets(), api.payments('pending'), api.cash()])
      setTickets(t)
      setPending(p)
      setCash(c)
      setOnline(true)
      setSelected((s) => s ?? t.find((x) => x.status !== 'resolved')?.id ?? t[0]?.id ?? null)
    } catch {
      setOnline(false)
    }
  }, [])

  const polling = useRef(false)
  const pollEvents = useCallback(async () => {
    if (polling.current) return // single-flight: overlapping polls would append the same batch twice
    polling.current = true
    try {
      const since = lastId.current >= 0 ? lastId.current : undefined
      const r = await api.events({ since_id: since })
      if (r.last_id < lastId.current) {
        // trail was replaced; reload everything
        lastId.current = -1
        const all = await api.events({})
        setEvents(all.events)
        lastId.current = all.last_id
        return
      }
      if (r.events.length) {
        setEvents((prev) => {
          const seen = new Set(prev.map((e) => e.id))
          const merged = [...prev, ...r.events.filter((e) => !seen.has(e.id))]
          return merged.sort((a, b) => a.id - b.id)
        })
      }
      lastId.current = r.last_id
    } catch {
      /* desk refresh reports offline */
    } finally {
      polling.current = false
    }
  }, [])

  const loadDetail = useCallback(async (id: number | null) => {
    if (id === null) return setDetail(null)
    try { setDetail(await api.ticket(id)) } catch { /* ignore */ }
  }, [])

  useEffect(() => {
    api.health().then(setHealth).catch(() => setOnline(false))
    refreshDesk()
    pollEvents()
    api.runs().then((rs) => setRuns(Object.fromEntries(rs.map((r) => [r.run_id, r])))).catch(() => {})
  }, [refreshDesk, pollEvents])

  useEffect(() => { loadDetail(selected) }, [selected, loadDetail])

  const activeRuns = Object.values(runs).filter((r) => r.status === 'running')
  useInterval(pollEvents, activeRuns.length ? 1200 : 4000)
  useInterval(refreshDesk, activeRuns.length ? 3000 : 6000)
  useInterval(async () => {
    for (const r of activeRuns) {
      try {
        const now = await api.run(r.run_id)
        if (now.status !== 'running') {
          setRuns((rs) => ({ ...rs, [now.run_id]: now }))
          await Promise.all([refreshDesk(), pollEvents()])
          if (now.ticket_id === selected) {
            loadDetail(now.ticket_id)
            setTab('summary')
          }
          const res = now.result?.resolution
          if (now.status === 'done' && res) {
            toast('ok', `Ticket #${now.ticket_id} ${res.final_status}. ${res.human_actions_needed.length ? 'Check the approval tray.' : ''}`)
          } else {
            toast('err', `Ticket #${now.ticket_id} run failed: ${now.result?.error ?? 'unknown error'}`)
          }
        }
      } catch { /* retry next tick */ }
    }
  }, 2000)

  // ------------------------------------------------------------ derived
  const runningIds = new Set(activeRuns.map((r) => r.ticket_id))
  const ticket = tickets.find((t) => t.id === selected) ?? null
  const activeForSelected = activeRuns.find((r) => r.ticket_id === selected)
  const runId = activeForSelected?.run_id ?? (selected !== null ? latestRunId(events, selected) : null)
  const view = useMemo(() => deriveRun(events, runId), [events, runId])
  const running = !!activeForSelected

  // When you open a ticket the team already worked, start on its after-action summary.
  const tabFor = useRef<number | null>(null)
  useEffect(() => {
    if (selected === null || tabFor.current === selected || !events.length) return
    tabFor.current = selected
    setTab(!running && view.finished ? 'summary' : 'live')
  }, [selected, events.length, running, view.finished])
  const startBalance = cash ? cash.balance + cash.payments_made.total : null

  // ------------------------------------------------------------ actions
  const startRun = async () => {
    if (!ticket) return
    try {
      const r = await api.runTicket(ticket.id)
      setRuns((rs) => ({ ...rs, [r.run_id]: r }))
      setTab('live')
      toast('info', `Ticket #${ticket.id} is on the Boss's desk.`)
      setTimeout(pollEvents, 400)
    } catch (e) {
      toast('err', (e as Error).message)
    }
  }

  const sendDecision = async () => {
    if (!ticket || !decision.trim() || !approver.trim()) return
    try {
      await api.decide(ticket.id, approver.trim(), decision.trim())
      toast('info', `Your decision is on the board. Sending #${ticket.id} back to the team.`)
      setDecision('')
      await refreshDesk()
      await startRun()
    } catch (e) {
      toast('err', (e as Error).message)
    }
  }

  const approve = async (r: PaymentRequest) => {
    try {
      const res = await api.approve(r.id, approver.trim())
      toast('ok', `Paid ${money(r.amount)} to ${r.payee}. Checking is now ${money(res.balance_after)}.`)
    } catch (e) {
      toast('err', `Payment refused: ${(e as Error).message}`)
    }
    await Promise.all([refreshDesk(), pollEvents()])
    loadDetail(selected)
  }

  const reject = async (r: PaymentRequest, reason: string) => {
    try {
      await api.reject(r.id, approver.trim(), reason)
      toast('info', `Rejected request #${r.id} (${r.payee}). No money moved.`)
    } catch (e) {
      toast('err', (e as Error).message)
    }
    await refreshDesk()
    loadDetail(selected)
  }

  const reset = async () => {
    setConfirmReset(false)
    try {
      const r = await api.reset()
      setRuns({})
      toast('info', `Desk reset to the original data. Checking ${money(r.balance)}.`)
      setTab('live')
      await Promise.all([refreshDesk(), pollEvents()])
      loadDetail(selected)
    } catch (e) {
      toast('err', (e as Error).message)
    }
  }

  // ------------------------------------------------------------ render
  const type = ticket ? TICKET_TYPES[ticket.type] : null
  const finalStatus = ticket?.status
  const canRun = !!ticket && !running && finalStatus !== 'resolved' && finalStatus !== 'escalated'

  return (
    <div className="app">
      <header className="topbar">
        <div className="brand">
          <span className="brand-mark"><AgentIcon name="boss" size={20} /></span>
          <div>
            <h1>Campus Customs <em>Ops Desk</em></h1>
            <p>Chapel Street · multi-agent operations</p>
          </div>
        </div>
        <div className="topbar-mid">
          <span className="shop-date"><small>Shop date</small>{deskDate(health?.date_today)}</span>
        </div>
        <div className="topbar-right">
          <span className="model-chip" title="Every agent runs on this model via Portkey">{health?.model ?? 'gpt-6-luna'}</span>
          <span className={`conn ${online ? 'on' : 'off'}`} title={API_BASE}>{online ? 'backend live' : 'backend offline'}</span>
          <button className="btn ghost light" onClick={() => setConfirmReset(true)}>Reset desk</button>
        </div>
      </header>

      {!online && (
        <div className="offline">
          Can't reach the backend at <code>{API_BASE}</code>. Start it from <code>backend/</code> with{' '}
          <code>uvicorn main:app --reload --port 8000</code>.
        </div>
      )}

      <main className="desk">
        <TicketRail tickets={tickets} selected={selected} onSelect={setSelected} runningIds={runningIds} />

        <section className="center">
          {ticket && (
            <div className="brief" style={{ ['--tone' as string]: type?.tone ?? '#888' }}>
              <div className="brief-text">
                <span className="brief-kicker">#{ticket.id} · {type?.label ?? ticket.type} · from {ticket.requester}</span>
                <h2>{ticket.subject}</h2>
                <p>“{ticket.notes}”</p>
              </div>
              <div className="brief-action">
                <span className={`status-badge s-${running ? 'running' : finalStatus}`}>
                  {running ? 'team working' : finalStatus?.replace(/_/g, ' ')}
                </span>
                <button className="btn primary big" disabled={!canRun} onClick={startRun}>
                  {running ? 'Team is on it…' : finalStatus === 'resolved' ? 'Resolved ✓' : finalStatus === 'escalated' ? 'Escalated' : 'Send to the team →'}
                </button>
                {view.finished && view.totalTokens !== null && (
                  <small>{view.totalTokens.toLocaleString()} tokens · {view.edges.reduce((n, e) => n + e.count, 0)} handoffs</small>
                )}
                {!canRun && !running && finalStatus === 'resolved' && <small>Reset the desk to run it again.</small>}
              </div>
            </div>
          )}

          {ticket && finalStatus === 'escalated' && !running && (
            <div className="decision">
              <div>
                <strong>The team escalated this ticket to you.</strong>
                <span>Make the call, and the Boss will carry it out within the shop rules. Signed as {approver.trim() || '— set your name in the approval tray'}.</span>
              </div>
              <textarea value={decision} onChange={(e) => setDecision(e.target.value)} rows={2}
                placeholder="e.g. Go ahead with the partial offer for the 8 on hand; defer the restock." />
              <button className="btn primary" disabled={!decision.trim() || !approver.trim()} onClick={sendDecision}>
                Send decision to the team →
              </button>
            </div>
          )}

          <div className="panel floor-panel">
            <div className="panel-head">
              <h2>The floor</h2>
              <span>{running ? 'live' : view.runId ? 'last run' : 'idle'}</span>
            </div>
            <AgentFloor agents={view.agents} edges={view.edges} running={running}
              idleHint={ticket ? `Ticket #${ticket.id} is on my desk. Send it over when you're ready.` : 'No ticket selected.'} />
          </div>

          <div className="panel feed-panel">
            <div className="tabs">
              <button className={tab === 'live' ? 'on' : ''} onClick={() => setTab('live')}>
                Live feed {running && <i className="live-dot" />}
              </button>
              <button className={tab === 'summary' ? 'on' : ''} onClick={() => setTab('summary')}>After-action summary</button>
            </div>
            {tab === 'live' ? <Transcript events={view.events} running={running} /> : <Summary run={view} detail={detail} />}
          </div>
        </section>

        <aside className="side">
          <CashDrawer cash={cash} start={startBalance} />
          <ApprovalTray pending={pending} approver={approver} setApprover={setApprover}
            balance={cash?.balance ?? 0} selectedTicket={selected} onApprove={approve} onReject={reject} />
        </aside>
      </main>

      <div className="toasts">
        {toasts.map((t) => <div key={t.id} className={`toast ${t.tone}`}>{t.text}</div>)}
      </div>

      {confirmReset && (
        <div className="modal-bg" onClick={() => setConfirmReset(false)}>
          <div className="modal" onClick={(e) => e.stopPropagation()}>
            <h3>Reset the desk?</h3>
            <p>This copies <code>data/campus_customs.db</code> over the working copy: tickets reopen, payments and drafts are cleared, and checking goes back to the original balance. The audit trail is kept.</p>
            <div className="modal-actions">
              <button className="btn ghost" onClick={() => setConfirmReset(false)}>Cancel</button>
              <button className="btn danger" onClick={reset}>Reset to original</button>
            </div>
          </div>
        </div>
      )}
    </div>
  )
}
