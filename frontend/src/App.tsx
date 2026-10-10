import { useCallback, useEffect, useMemo, useRef, useState } from 'react'
import {
  API, approve, closeoutTicket, getApprovals, getCash, getEvents, getRun, getTicketDetail, getTickets, reject,
  resetDatabase, runTicket,
} from './api'
import { AgentIcon, TYPE_LABEL } from './agents'
import { CashTill } from './components/CashTill'
import { Drafts } from './components/Drafts'
import { Feed } from './components/Feed'
import { FloorPlan } from './components/FloorPlan'
import { PaySlips } from './components/PaySlips'
import { RunReport } from './components/RunReport'
import { TicketBoard } from './components/TicketBoard'
import { useStoredState, usePoll } from './hooks'
import { buildFeed, compactFeed, deriveAgents, deriveEdges, prettyDate } from './lib'
import type { AgentEvent, Approval, Cash, Payment, RunInfo, Ticket, TicketDetail } from './types'

/** The newest agent run in a list of events. Human actions (approve, decline, pay) have no run, so skip them. */
const lastRunId = (events: AgentEvent[]) => [...events].reverse().find(e => e.run_id && e.run_id !== '-')?.run_id ?? null

const msg = (e: unknown) => (e instanceof Error ? e.message : String(e))

export default function App() {
  const [tickets, setTickets] = useState<Ticket[]>([])
  const [today, setToday] = useState('')
  const [running, setRunning] = useState<RunInfo | null>(null)
  const [cash, setCash] = useState<Cash | null>(null)
  const [approvals, setApprovals] = useState<Approval[]>([])
  const [payments, setPayments] = useState<Payment[]>([])
  const [selectedId, setSelectedId] = useState<number | null>(null)
  const [detail, setDetail] = useState<TicketDetail | null>(null)
  const [events, setEvents] = useState<AgentEvent[]>([])
  const [runs, setRuns] = useState<Record<string, RunInfo>>({})
  const [offline, setOffline] = useState<string | null>(null)
  const [notice, setNotice] = useState<string | null>(null)
  const [starting, setStarting] = useState(false)
  const [busyId, setBusyId] = useState<number | null>(null)
  const [slipErrors, setSlipErrors] = useState<Record<number, string>>({})
  const [name, setName] = useStoredState('desk.name', '')
  const selectedRef = useRef<number | null>(null)
  useEffect(() => { selectedRef.current = selectedId }, [selectedId])

  const isRunning = running !== null

  const refreshBoard = useCallback(async () => {
    try {
      const [t, c, a] = await Promise.all([getTickets(), getCash(), getApprovals()])
      setTickets(t.tickets); setToday(t.today); setRunning(t.running)
      setCash(c); setApprovals(a.approvals); setPayments(a.payments_made)
      setOffline(null)
      setSelectedId(prev => prev ?? (t.tickets.find(x => x.open)?.id ?? t.tickets[0]?.id ?? null))
    } catch (e) {
      setOffline(msg(e))
    }
  }, [])

  usePoll(refreshBoard, isRunning ? 1200 : 3000, [isRunning])

  usePoll(async () => {
    const id = selectedId
    if (id == null) return
    const [ev, det] = await Promise.all([getEvents(id), getTicketDetail(id)])
    if (selectedRef.current !== id) return
    setEvents(ev.events); setDetail(det)
    const rid = lastRunId(ev.events)
    if (rid) {
      const known = runs[rid]
      if (!known || known.status === 'running') {
        try { const info = await getRun(rid); setRuns(r => ({ ...r, [rid]: info })) } catch { /* server restarted: no outcome */ }
      }
    }
  }, isRunning ? 1000 : 3000, [selectedId, isRunning])

  const select = useCallback((id: number) => {
    if (id === selectedRef.current) return
    selectedRef.current = id
    setSelectedId(id); setEvents([]); setDetail(null)
  }, [])

  useEffect(() => {
    const onKey = (e: KeyboardEvent) => {
      if ((e.target as HTMLElement)?.tagName === 'INPUT' || e.metaKey || e.ctrlKey || e.altKey) return
      const t = tickets[Number(e.key) - 1]
      if (t) select(t.id)
    }
    window.addEventListener('keydown', onKey)
    return () => window.removeEventListener('keydown', onKey)
  }, [tickets, select])

  const latestRunId = lastRunId(events)
  // Everything that happened on this ticket since the last reset: the first run and any close-outs.
  const runEvents = events
  const thisRunning = running?.ticket_id === selectedId && running?.status === 'running'
  const states = useMemo(() => deriveAgents(runEvents, thisRunning), [runEvents, thisRunning])
  const edges = useMemo(() => deriveEdges(runEvents), [runEvents])
  const [showLookups, setShowLookups] = useState(false)
  const [decision, setDecision] = useState('')
  const fullFeed = useMemo(() => buildFeed(runEvents), [runEvents])
  const feed = useMemo(() => (showLookups ? fullFeed : compactFeed(fullFeed)), [fullFeed, showLookups])
  const runInfo = latestRunId ? runs[latestRunId] ?? (running?.run_id === latestRunId ? running : null) : null
  const selected = tickets.find(t => t.id === selectedId) ?? null

  const slipsByTicket = useMemo(() => {
    const m: Record<number, number> = {}
    for (const a of approvals) if ((a.status === 'pending' || a.status === 'approved') && a.ticket_id) m[a.ticket_id] = (m[a.ticket_id] ?? 0) + 1
    return m
  }, [approvals])
  const spent = payments.reduce((s, p) => s + p.amount, 0)

  async function startRun(id: number, focus = true) {
    setStarting(true); setNotice(null)
    try {
      if (focus) select(id)
      const info = await runTicket(id)
      setRuns(r => ({ ...r, [info.run_id]: info })); setRunning(info)
      if (focus) setEvents([])
    } catch (e) {
      setNotice(msg(e))
    } finally {
      setStarting(false)
      refreshBoard()
    }
  }
  const start = () => (selectedId == null ? Promise.resolve() : startRun(selectedId))

  /** The boss re-checks a ticket once a human has decided every slip on it. */
  async function closeOut(ticketId: number, focus = true, note?: string) {
    setNotice(null)
    try {
      if (focus) select(ticketId)
      const info = await closeoutTicket(ticketId, note, name.trim())
      setRuns(r => ({ ...r, [info.run_id]: info })); setRunning(info)
      if (note) setDecision('')
    } catch (e) {
      setNotice(msg(e))
    } finally {
      refreshBoard()
    }
  }

  // Close-outs wait their turn: the backend runs one thing at a time.
  const [queue, setQueue] = useState<{ id: number; focus: boolean; kind: 'run' | 'closeout' }[]>([])
  const [tick, setTick] = useState(0)
  const launching = useRef(false)  // true from the moment a close-out is requested until the backend has accepted it
  useEffect(() => {
    if (isRunning || launching.current || queue.length === 0) return
    const [next, ...rest] = queue
    setQueue(rest)
    launching.current = true;
    (next.kind === 'run' ? startRun(next.id, next.focus) : closeOut(next.id, next.focus))
      .finally(() => { launching.current = false; setTick(t => t + 1) })
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [isRunning, queue, tick])

  /** After a decision, hand the ticket back to the boss if nothing is left waiting on it.
   *  Paying an invoice can lift a vendor's hold, so tickets stuck waiting get re-checked too. */
  async function afterDecision(ticketId: number | null, kind: Approval['kind']) {
    const [fresh, board] = await Promise.all([getApprovals(), getTickets()])
    setApprovals(fresh.approvals); setPayments(fresh.payments_made)
    const waiting = (id: number) => fresh.approvals.some(x => x.ticket_id === id && (x.status === 'pending' || x.status === 'approved'))
    const next: { id: number; focus: boolean; kind: 'run' | 'closeout' }[] = []
    if (ticketId != null && !waiting(ticketId)) next.push({ id: ticketId, focus: true, kind: 'closeout' })
    if (kind === 'invoice_payment') {
      for (const t of board.tickets) {
        if (t.status === 'needs_human' && t.id !== ticketId && !waiting(t.id)) next.push({ id: t.id, focus: false, kind: 'closeout' })
      }
    }
    setQueue(q => [...q, ...next.filter(n => !q.some(x => x.id === n.id))])
  }

  /** Rent first, then the customer order that has an overdue invoice behind it, then the discount request. */
  function runWholeBoard() {
    const rank: Record<string, number> = { rent_notice: 0, customer_order: 1, price_override: 2 }
    const open = tickets.filter(t => t.open).sort((a, b) => (rank[a.type] ?? 9) - (rank[b.type] ?? 9))
    if (open.length === 0) return
    select(open[0].id)
    setQueue(q => [...q, ...open.filter(t => !q.some(x => x.id === t.id && x.kind === 'run')).map((t, i) => ({ id: t.id, focus: i === 0, kind: 'run' as const }))])
  }

  async function sign(a: Approval) {
    setBusyId(a.id)
    setSlipErrors(e => { const { [a.id]: _gone, ...rest } = e; return rest })
    let paid = false
    try {
      await approve(a.id, name.trim())
      paid = true
    } catch (e) {
      setSlipErrors(s => ({ ...s, [a.id]: msg(e) }))
    } finally {
      setBusyId(null)
      refreshBoard()
    }
    if (paid) await afterDecision(a.ticket_id, a.kind)
  }

  async function decline(a: Approval) {
    setBusyId(a.id)
    let done = false
    try { await reject(a.id, name.trim()); done = true } catch (e) { setNotice(msg(e)) } finally { setBusyId(null); refreshBoard() }
    if (done) await afterDecision(a.ticket_id, a.kind)
  }

  async function freshDay() {
    if (!window.confirm('Start a fresh day? This puts the database back to the original values. The audit trail is kept.')) return
    setNotice(null)
    try {
      await resetDatabase()
      setRuns({}); setEvents([]); setSlipErrors({}); setDetail(null)
      await refreshBoard()
    } catch (e) {
      setNotice(msg(e))
    }
  }

  const canRun = selected?.open && !isRunning && !starting
  const canCloseOut = selected?.status === 'needs_human' && !isRunning && !slipsByTicket[selected.id]
  const runLabel = thisRunning ? 'The team is on it…'
    : isRunning ? 'Another run is going…'
    : !selected ? 'Pick a ticket'
    : !selected.open ? (selected.status === 'resolved' ? 'Resolved. Start a fresh day to run it again.' : 'Worked. Waiting on a human.')
    : starting ? 'Starting…' : `Start the team on ${selected.id}`

  return (
    <div className="app">
      <header className="top">
        <div className="brand">
          <svg width="34" height="34" viewBox="0 0 64 64" aria-hidden><rect width="64" height="64" rx="14" fill="#f2c14e" /><path d="M14 44V26l18-10 18 10v18l-18 10z" fill="none" stroke="#00356b" strokeWidth="4" strokeLinejoin="round" /><circle cx="32" cy="35" r="5" fill="#00356b" /></svg>
          <div>
            <h1>Campus Customs <em>The Desk</em></h1>
            <p>Back office · 57 Broadway, New Haven</p>
          </div>
        </div>
        <div className="top-right">
          {today && <span className="date-chip" title="The shop's date (desk.date_today)">Shop date · {prettyDate(today)}</span>}
          <span className={`conn ${offline ? 'down' : 'up'}`}>{offline ? 'Backend offline' : 'Backend connected'}</span>
          <button className="ghost-btn" onClick={freshDay}>Start a fresh day</button>
        </div>
      </header>

      {offline && <div className="banner bad" role="alert">{offline} <span className="muted">(expected at {API})</span></div>}
      {notice && <div className="banner" role="status">{notice} <button onClick={() => setNotice(null)} aria-label="Dismiss">×</button></div>}

      <main className="layout">
        <aside className="col left">
          <CashTill cash={cash} spent={spent} />
          <TicketBoard tickets={tickets} selectedId={selectedId} runningId={running?.ticket_id ?? null} slips={slipsByTicket} onSelect={select}
            onRunAll={runWholeBoard} canRunAll={!isRunning && queue.length === 0 && tickets.some(t => t.open)} />
        </aside>

        <section className="col center">
          <div className="card ticket-head">
            {selected ? (
              <>
                <div className="th-top">
                  <div>
                    <span className="th-type">{TYPE_LABEL[selected.type] ?? selected.type}</span>
                    <h2>№ {selected.id} · {selected.subject}</h2>
                    <p className="muted">from {selected.requester}</p>
                  </div>
                  <div className="run-actions">
                    <button className="run-btn" disabled={!canRun} onClick={start}>
                      <AgentIcon agent="boss" size={18} color="currentColor" /> {runLabel}
                    </button>
                  </div>
                </div>
                {detail?.notes && <blockquote>{detail.notes}</blockquote>}
                {canCloseOut && (
                  <div className="decision">
                    <label htmlFor="decision">Waiting on you. Say your decision in your own words, then hand it back to the boss.</label>
                    <textarea id="decision" rows={2} maxLength={500} value={decision} onChange={e => setDecision(e.target.value)}
                      placeholder="For example: No discount, the list price stands. Don't restock." />
                    <div className="decision-row">
                      <span className="hint">{decision.trim() && name.trim().length < 2 ? 'Type your name in the signature box first.' : 'Optional if nothing needs deciding.'}</span>
                      <button className="run-btn secondary" disabled={!!decision.trim() && name.trim().length < 2}
                        onClick={() => closeOut(selected.id, true, decision.trim() || undefined)}>
                        Close out with the boss
                      </button>
                    </div>
                  </div>
                )}
                {detail && (detail.sku || detail.qty) ? (
                  <div className="th-chips">
                    {detail.sku && <span>{detail.sku}</span>}{detail.size && <span>size {detail.size}</span>}{detail.qty ? <span>qty {detail.qty}</span> : null}
                  </div>
                ) : null}
              </>
            ) : <p className="muted">Waiting for the board…</p>}
          </div>

          <div className="card floor-card">
            <h2 className="section-title">The floor <span className="count">anyone can ask anyone</span></h2>
            <FloorPlan states={states} edges={edges} />
          </div>

          <div className="card feed-card">
            <h2 className="section-title">What they're saying and doing
              <span className="count">
                {thisRunning ? 'live' : runEvents.length ? 'replay' : ''}
                <label className="toggle"><input type="checkbox" checked={showLookups} onChange={e => setShowLookups(e.target.checked)} /> show every lookup</label>
              </span></h2>
            <Feed items={feed} running={thisRunning} />
          </div>

          {selectedId != null && runEvents.length > 0 && (
            <RunReport ticketId={selectedId} run={runInfo} states={states} running={thisRunning} />
          )}
          {detail && <Drafts drafts={detail.drafts} />}
        </section>

        <aside className="col right">
          <PaySlips approvals={approvals} name={name} setName={setName} busyId={busyId} errors={slipErrors}
            onApprove={sign} onReject={decline} />
        </aside>
      </main>
    </div>
  )
}
