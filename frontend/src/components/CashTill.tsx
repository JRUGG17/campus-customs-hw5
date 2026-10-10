import { useEffect, useState } from 'react'
import { usePrevious, useRollingNumber } from '../hooks'
import { money } from '../lib'
import type { Cash } from '../types'

export function CashTill({ cash, spent }: { cash: Cash | null; spent: number }) {
  const target = cash?.balance ?? 0
  const shown = useRollingNumber(target)
  const prev = usePrevious(target)
  const dropped = cash && prev !== undefined && target < prev ? prev - target : 0
  const [chips, setChips] = useState<{ id: number; amt: number }[]>([])

  useEffect(() => {
    if (dropped > 0) {
      const id = Date.now()
      setChips(c => [...c, { id, amt: dropped }])
      window.setTimeout(() => setChips(c => c.filter(x => x.id !== id)), 2800)
    }
  }, [dropped])

  const earmarked = cash?.committed_not_yet_paid ?? 0
  const free = Math.max(0, (cash?.balance ?? 0) - earmarked)
  const peak = Math.max(1, (cash?.balance ?? 0) + spent)
  const pct = (n: number) => `${Math.min(100, (n / peak) * 100)}%`

  return (
    <section className={`till ${chips.length ? 'flash' : ''}`} aria-label="Checking balance">
      <div className="till-head">
        <span>CHECKING</span>
        <span>{cash ? `as of ${cash.as_of}` : '…'}</span>
      </div>
      <div className="till-screen" aria-live="polite">
        <span className="till-digits">{cash ? money(Number(shown.toFixed(2))).replace(/^(\$[\d,]+)$/, '$1.00') : '$—'}</span>
        {chips.map(c => <span key={c.id} className="chip-out">−{money(c.amt)}</span>)}
      </div>
      <div className="till-bar" role="img" aria-label={`Free ${money(free)}, earmarked ${money(earmarked)}, paid out ${money(spent)}`}>
        <i className="seg free" style={{ width: pct(free) }} />
        <i className="seg earmarked" style={{ width: pct(earmarked) }} />
        <i className="seg spent" style={{ width: pct(spent) }} />
      </div>
      <ul className="till-legend">
        <li><i className="dot free" />Free <b>{money(free)}</b></li>
        <li><i className="dot earmarked" />Earmarked <b>{money(earmarked)}</b></li>
        <li><i className="dot spent" />Paid out <b>{money(spent)}</b></li>
      </ul>
      <p className="till-note">Cash only goes out here. Nothing can push it below $0.</p>
    </section>
  )
}
