import { TYPE_LABEL } from '../agents'
import type { Ticket } from '../types'

function stamp(t: Ticket, running: boolean) {
  if (running) return { text: 'ON IT', cls: 'on-it' }
  if (t.status === 'resolved') return { text: 'RESOLVED', cls: 'resolved' }
  if (t.status === 'needs_human') return { text: 'NEEDS YOU', cls: 'needs-you' }
  return { text: 'OPEN', cls: 'open' }
}

export function TicketBoard({ tickets, selectedId, runningId, slips, onSelect, onRunAll, canRunAll }: {
  tickets: Ticket[]
  selectedId: number | null
  runningId: number | null
  slips: Record<number, number>
  onSelect: (id: number) => void
  onRunAll: () => void
  canRunAll: boolean
}) {
  return (
    <section aria-label="Tickets">
      <h2 className="section-title">The board</h2>
      <button className="run-all" disabled={!canRunAll} onClick={onRunAll}
        title="Runs every open ticket one after another: rent first, then the customer order, then the discount request">
        Run the whole board
      </button>
      <div className="board">
        {tickets.map((t, i) => {
          const s = stamp(t, runningId === t.id)
          return (
            <button key={t.id} className={`work-order ${selectedId === t.id ? 'selected' : ''}`}
              onClick={() => onSelect(t.id)} aria-pressed={selectedId === t.id}
              style={{ ['--tilt' as string]: `${(i % 2 ? 0.6 : -0.5)}deg` }}>
              <span className="tape" aria-hidden />
              <span className="wo-top">
                <span className="wo-no">№ {t.id}</span>
                <span className="wo-type">{TYPE_LABEL[t.type] ?? t.type}</span>
              </span>
              <span className="wo-subject">{t.subject}</span>
              <span className="wo-from">from {t.requester}</span>
              <span className="wo-bottom">
                <span className={`stamp ${s.cls}`}>{s.text}</span>
                {slips[t.id] ? <span className="slip-chip">{slips[t.id]} slip{slips[t.id] > 1 ? 's' : ''} to sign</span> : null}
              </span>
              <kbd className="hotkey" aria-hidden>{i + 1}</kbd>
            </button>
          )
        })}
        {tickets.length === 0 && <p className="empty">No tickets yet. Waiting on the backend…</p>}
      </div>
    </section>
  )
}
