import { useEffect, useRef, useState } from 'react'
import { money } from '../agents'
import type { Cash } from '../types'

/** Animate a number toward its new value (the register "rolls" down after a payment). */
function useTween(target: number, ms = 1100) {
  const [value, setValue] = useState(target)
  const from = useRef(target)
  const primed = useRef(false)
  useEffect(() => {
    if (!primed.current) {
      // first real value: show it as-is instead of rolling up from $0
      if (target !== 0) primed.current = true
      from.current = target
      setValue(target)
      return
    }
    const start = performance.now()
    const a = from.current
    let raf = 0
    const step = (now: number) => {
      const p = Math.min((now - start) / ms, 1)
      const eased = 1 - Math.pow(1 - p, 3)
      setValue(a + (target - a) * eased)
      if (p < 1) raf = requestAnimationFrame(step)
      else from.current = target
    }
    raf = requestAnimationFrame(step)
    return () => {
      cancelAnimationFrame(raf)
      from.current = target
    }
  }, [target, ms])
  return value
}

export function CashDrawer({ cash, start }: { cash: Cash | null; start: number | null }) {
  const balance = cash?.balance ?? 0
  const shown = useTween(balance)
  const prev = useRef<number | null>(null)
  const [drop, setDrop] = useState<{ amount: number; key: number } | null>(null)

  useEffect(() => {
    if (prev.current !== null && balance < prev.current) {
      setDrop({ amount: prev.current - balance, key: Date.now() })
    }
    prev.current = balance
  }, [balance])

  if (!cash) return <section className="panel drawer"><div className="empty">Loading cash…</div></section>

  const base = start && start > 0 ? start : Math.max(balance, 1)
  const pct = (n: number) => `${Math.max(Math.min((n / base) * 100, 100), 0)}%`
  const pending = Math.min(cash.pending_requests_total, balance)
  const over = cash.available_after_pending < 0

  return (
    <section className="panel drawer">
      <div className="panel-head">
        <h2>Cash drawer</h2>
        <span>checking · as of {cash.as_of}</span>
      </div>
      <div className="register">
        <span className="register-label">BALANCE</span>
        <output className="register-digits">{money(shown)}</output>
        {drop && <span key={drop.key} className="register-drop">−{money(drop.amount)}</span>}
      </div>
      <div className="meter" title="Balance · pending approval · free">
        <span className="meter-free" style={{ width: pct(balance) }} />
        <span className="meter-pending" style={{ width: pct(pending), left: `calc(${pct(balance)} - ${pct(pending)})` }} />
      </div>
      <dl className="drawer-stats">
        <div><dt>Pending approval</dt><dd>{money(cash.pending_requests_total)}</dd></div>
        <div className={over ? 'warn' : ''}><dt>Free after pending</dt><dd>{money(cash.available_after_pending)}</dd></div>
        <div><dt>Paid out</dt><dd>{money(cash.payments_made.total)}</dd></div>
      </dl>
      {over && <p className="drawer-warn">Pending requests exceed the balance. Not everything can be approved.</p>}
      {cash.paid_requests.length > 0 && (
        <ul className="ledger">
          {cash.paid_requests.map((p) => (
            <li key={p.id}>
              <span>{p.payee}<small>{p.kind.replace('_', ' ')} · signed {p.decided_by}</small></span>
              <b>−{money(p.amount)}</b>
            </li>
          ))}
        </ul>
      )}
      <p className="drawer-foot">Cash only goes out in this shop. No revenue is modeled.</p>
    </section>
  )
}
