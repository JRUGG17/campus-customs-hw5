import { AGENT_ORDER, AgentIcon, THEMES } from '../agents'
import type { AgentState } from '../lib'
import type { RunInfo, TicketOutcome } from '../types'

const clip = (s: string, n: number) => (s.length > n ? s.slice(0, n - 1).trimEnd() + '…' : s)

export function RunReport({ ticketId, run, states, running }: {
  ticketId: number
  run: RunInfo | null
  states: Record<string, AgentState>
  running: boolean
}) {
  const outcome: TicketOutcome | undefined = run?.outcome?.tickets.find(t => t.ticket_id === ticketId)
  const tookPart = AGENT_ORDER.filter(a => states[a].seen).length

  return (
    <section className="report" aria-label="What each agent did">
      <h2 className="section-title">
        {running ? 'Report (filling in as they go)' : 'What each agent did'}
        <span className="count">{tookPart} of 5 took part</span>
      </h2>

      {outcome && (
        <div className={`verdict ${outcome.status}`}>
          <div className="verdict-top">
            <span className={`stamp ${outcome.status === 'resolved' ? 'resolved' : 'needs-you'}`}>
              {outcome.status === 'resolved' ? 'RESOLVED' : 'NEEDS YOU'}
            </span>
            <span className="verdict-by"><AgentIcon agent="boss" size={16} /> The boss's call</span>
          </div>
          <p className="verdict-decision">{outcome.decision}</p>
          <dl>
            <dt>Money</dt><dd>{outcome.money}</dd>
            <dt>Needs a human</dt><dd>{outcome.needs_human}</dd>
          </dl>
        </div>
      )}
      {run?.status === 'stopped' || run?.status === 'error' ? (
        <div className="verdict bad"><p>{run.error ?? 'The run stopped early.'}</p></div>
      ) : null}

      <div className="agent-cards">
        {AGENT_ORDER.map(a => {
          const t = THEMES[a], s = states[a]
          const tools = Object.entries(s.tools)
          const last = s.reports[s.reports.length - 1]
          return (
            <article key={a} className={`agent-card ${s.seen ? '' : running ? 'waiting-turn' : 'sat-out'}`} style={{ ['--c' as string]: t.color, ['--t' as string]: t.tint }}>
              <header>
                <AgentIcon agent={a} size={20} />
                <b>{t.name}</b>
                <span className="role">{s.seen ? (s.state === 'done' ? 'done' : s.doing) : running ? 'not called yet' : 'sat this one out'}</span>
              </header>
              {s.seen ? (
                <>
                  {last && <p className="their-words">“{clip(last.answer, 230)}”</p>}
                  <p className="facts-line">
                    {tools.length ? tools.map(([n, c]) => <code key={n}>{n}{c > 1 ? ` ×${c}` : ''}</code>) : <span className="muted">no tools of their own</span>}
                  </p>
                  <p className="hand-line">
                    {s.received ? `asked ${s.received}×` : 'not asked'}{s.sent ? ` · handed work on ${s.sent}×` : ''}
                  </p>
                </>
              ) : <p className="muted small">{running ? 'Nobody has asked them yet.' : 'Not sent this ticket.'}</p>}
            </article>
          )
        })}
      </div>

      {run?.outcome && outcome && outcome.who_did_what.length > 0 && (
        <details className="boss-notes">
          <summary>The boss's account of who did what</summary>
          <ul>{outcome.who_did_what.map((w, i) => <li key={i}>{w}</li>)}</ul>
        </details>
      )}
    </section>
  )
}
