import { approvalLabel, money, prettyDate } from '../lib'
import type { Approval } from '../types'

export function PaySlips({ approvals, name, setName, busyId, errors, onApprove, onReject }: {
  approvals: Approval[]
  name: string
  setName: (v: string) => void
  busyId: number | null
  errors: Record<number, string>
  onApprove: (a: Approval) => void
  onReject: (a: Approval) => void
}) {
  const waiting = approvals.filter(a => a.status === 'pending' || a.status === 'approved')
  const settled = approvals.filter(a => a.status === 'executed' || a.status === 'rejected').slice().reverse()
  const signed = name.trim().length >= 2

  return (
    <section aria-label="Pay slips">
      <h2 className="section-title">Pay slips <span className="count">{waiting.length} to sign</span></h2>
      <p className="slip-help">Agents only prepare payments. Nothing moves until you sign here.</p>

      <label className="signature">
        <span>Signing as</span>
        <input value={name} onChange={e => setName(e.target.value)} placeholder="Your name" autoComplete="name" maxLength={40} />
      </label>

      <div className="slips">
        {waiting.length === 0 && <p className="empty">Nothing waiting. When Accounting prepares a payment it shows up here.</p>}
        {waiting.map(a => (
          <article key={a.id} className="slip">
            <div className="slip-top">
              <span className="slip-kind">{approvalLabel(a.kind)}</span>
              {a.ticket_id && <span className="slip-ticket">ticket {a.ticket_id}</span>}
            </div>
            <div className="slip-amount">{money(a.amount)}</div>
            <p className="slip-desc">{a.description}</p>
            <p className="slip-by">Prepared by {a.requested_by}. Not paid yet.</p>
            {errors[a.id] && <p className="slip-error"><b>Refused.</b> {errors[a.id].replace(/^Refused:\s*/, '')}</p>}
            {a.status === 'approved' && !errors[a.id] && <p className="slip-error">Approved, but not paid yet.</p>}
            <div className="slip-actions">
              <button className="sign" disabled={!signed || busyId === a.id} onClick={() => onApprove(a)}
                title={signed ? '' : 'Type your name first'}>
                {busyId === a.id ? 'Paying…' : a.status === 'approved' ? 'Try the payment again' : `Approve & pay ${money(a.amount)}`}
              </button>
              <button className="decline" disabled={!signed || busyId === a.id} onClick={() => onReject(a)}>Decline</button>
            </div>
            {!signed && <p className="hint">Type your name above to sign.</p>}
          </article>
        ))}

        {settled.map(a => (
          <article key={a.id} className={`slip settled ${a.status}`}>
            <div className="slip-top">
              <span className="slip-kind">{approvalLabel(a.kind)}</span>
              {a.ticket_id && <span className="slip-ticket">ticket {a.ticket_id}</span>}
            </div>
            <div className="slip-amount">{money(a.amount)}</div>
            <p className="slip-desc">{a.description}</p>
            <span className={`stamp ${a.status === 'executed' ? 'paid' : 'declined'}`}>{a.status === 'executed' ? 'PAID' : 'DECLINED'}</span>
            <p className="slip-by">
              {a.status === 'executed' ? 'Signed' : 'Declined'} by {a.decided_by}
              {a.executed_at ? ` · ${prettyDate(a.executed_at)}` : ''}
            </p>
          </article>
        ))}
      </div>
    </section>
  )
}
