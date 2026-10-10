import { AgentIcon } from '../agents'
import type { Draft } from '../types'

export function Drafts({ drafts }: { drafts: Draft[] }) {
  if (drafts.length === 0) return null
  return (
    <section aria-label="Draft replies">
      <h2 className="section-title">Drafts on the board <span className="count">never sent</span></h2>
      {drafts.map(d => (
        <article key={d.id} className="draft">
          <span className="stamp draft-stamp">DRAFT · NOT SENT</span>
          <div className="draft-to"><AgentIcon agent="customer_service" size={16} /> To {d.audience}</div>
          <p>{d.body}</p>
        </article>
      ))}
    </section>
  )
}
