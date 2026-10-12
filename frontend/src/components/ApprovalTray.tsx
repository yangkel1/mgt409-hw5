import { useState } from 'react'
import { money } from '../agents'
import type { PaymentRequest } from '../types'

const KIND_LABEL = { invoice: 'Vendor invoice', rent: 'Rent', purchase_order: 'Purchase order' } as const

const ONES = ['', 'one', 'two', 'three', 'four', 'five', 'six', 'seven', 'eight', 'nine', 'ten', 'eleven',
  'twelve', 'thirteen', 'fourteen', 'fifteen', 'sixteen', 'seventeen', 'eighteen', 'nineteen']
const TENS = ['', '', 'twenty', 'thirty', 'forty', 'fifty', 'sixty', 'seventy', 'eighty', 'ninety']
function words(n: number): string {
  if (n < 20) return ONES[n]
  if (n < 100) return TENS[Math.floor(n / 10)] + (n % 10 ? '-' + ONES[n % 10] : '')
  if (n < 1000) return ONES[Math.floor(n / 100)] + ' hundred' + (n % 100 ? ' ' + words(n % 100) : '')
  return words(Math.floor(n / 1000)) + ' thousand' + (n % 1000 ? ' ' + words(n % 1000) : '')
}
const amountInWords = (amt: number) => {
  const dollars = Math.floor(amt)
  const cents = Math.round((amt - dollars) * 100)
  const w = dollars ? words(dollars) : 'zero'
  return `${w.charAt(0).toUpperCase()}${w.slice(1)} and ${String(cents).padStart(2, '0')}/100 dollars`
}

function Check({
  req, approver, balance, highlight, onApprove, onReject,
}: {
  req: PaymentRequest
  approver: string
  balance: number
  highlight: boolean
  onApprove: (r: PaymentRequest) => Promise<void>
  onReject: (r: PaymentRequest, reason: string) => Promise<void>
}) {
  const [busy, setBusy] = useState(false)
  const [rejecting, setRejecting] = useState(false)
  const [reason, setReason] = useState('')
  const short = req.amount > balance

  const act = async (fn: () => Promise<void>) => {
    setBusy(true)
    try { await fn() } finally { setBusy(false) }
  }

  return (
    <article className={`check ${highlight ? 'highlight' : ''}`}>
      <div className="check-top">
        <span className="check-kind">{KIND_LABEL[req.kind]}</span>
        <span className="check-no">No. {String(req.id).padStart(4, '0')} · ticket #{req.ticket_id}</span>
      </div>
      <div className="check-pay">
        <span>Pay to the order of</span>
        <strong>{req.payee}</strong>
        <b className="check-amount">{money(req.amount)}</b>
      </div>
      <div className="check-words">{amountInWords(req.amount)}</div>
      <div className="check-memo">
        <span>Memo: {req.reason ?? '—'}</span>
        <span>Prepared by {req.requested_by}</span>
      </div>
      {short && <p className="check-warn">More than the {money(balance)} in checking. The register will refuse it.</p>}
      {rejecting ? (
        <div className="check-actions">
          <input value={reason} onChange={(e) => setReason(e.target.value)} placeholder="Reason for rejecting" autoFocus />
          <button className="btn ghost" onClick={() => setRejecting(false)}>Back</button>
          <button className="btn danger" disabled={busy || !approver}
            onClick={() => act(() => onReject(req, reason))}>Reject</button>
        </div>
      ) : (
        <div className="check-actions">
          <span className="signature">{approver || 'unsigned'}</span>
          <button className="btn ghost" disabled={busy || !approver} onClick={() => setRejecting(true)}>Reject</button>
          <button className="btn approve" disabled={busy || !approver} onClick={() => act(() => onApprove(req))}>
            {busy ? 'Signing…' : 'Approve & pay'}
          </button>
        </div>
      )}
    </article>
  )
}

export function ApprovalTray({
  pending, approver, setApprover, balance, selectedTicket, onApprove, onReject,
}: {
  pending: PaymentRequest[]
  approver: string
  setApprover: (s: string) => void
  balance: number
  selectedTicket: number | null
  onApprove: (r: PaymentRequest) => Promise<void>
  onReject: (r: PaymentRequest, reason: string) => Promise<void>
}) {
  return (
    <section className="panel tray">
      <div className="panel-head">
        <h2>Approval tray</h2>
        <span>{pending.length ? `${pending.length} waiting` : 'all clear'}</span>
      </div>
      <label className="signer">
        <span>Signing as</span>
        <input value={approver} onChange={(e) => setApprover(e.target.value)} placeholder="Your name" />
      </label>
      <p className="tray-note">Agents only prepare payments. Nothing moves until a person signs here.</p>
      {pending.length === 0 && <div className="empty small">No payments are waiting for approval.</div>}
      {pending.map((r) => (
        <Check key={r.id} req={r} approver={approver.trim()} balance={balance}
          highlight={r.ticket_id === selectedTicket} onApprove={onApprove} onReject={onReject} />
      ))}
    </section>
  )
}
