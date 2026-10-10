import { AGENT_ORDER, AgentIcon, THEMES } from '../agents'
import type { AgentState, Edge } from '../lib'
import type { AgentName } from '../types'

const POS: Record<AgentName, { x: number; y: number }> = {
  boss: { x: 380, y: 58 },
  inventory: { x: 655, y: 168 },
  accounting: { x: 565, y: 318 },
  facilities: { x: 195, y: 318 },
  customer_service: { x: 105, y: 168 },
}
const R = 36

function curve(a: AgentName, b: AgentName, bend = 24) {
  const p = POS[a], q = POS[b]
  const dx = q.x - p.x, dy = q.y - p.y
  const len = Math.hypot(dx, dy)
  const ux = dx / len, uy = dy / len
  const nx = -uy, ny = ux
  const sx = p.x + ux * (R + 4), sy = p.y + uy * (R + 4)
  const ex = q.x - ux * (R + 8), ey = q.y - uy * (R + 8)
  const cx = (sx + ex) / 2 + nx * bend, cy = (sy + ey) / 2 + ny * bend
  return { d: `M${sx},${sy} Q${cx},${cy} ${ex},${ey}`, mx: 0.25 * sx + 0.5 * cx + 0.25 * ex, my: 0.25 * sy + 0.5 * cy + 0.25 * ey }
}

const clip = (s: string, n = 34) => (s.length > n ? s.slice(0, n - 1) + '…' : s)

export function FloorPlan({ states, edges }: { states: Record<AgentName, AgentState>; edges: Edge[] }) {
  return (
    <svg className="floor" viewBox="0 0 760 420" role="img" aria-label="The five agents and who has handed work to whom">
      <defs>
        {AGENT_ORDER.map(a => (
          <marker key={a} id={`arrow-${a}`} viewBox="0 0 10 10" refX="8" refY="5" markerWidth="7" markerHeight="7" orient="auto-start-reverse">
            <path d="M0,0 L10,5 L0,10 z" fill={THEMES[a].color} />
          </marker>
        ))}
      </defs>

      {/* Anyone can ask anyone: the faint web is the full connectivity. */}
      {AGENT_ORDER.flatMap((a, i) => AGENT_ORDER.slice(i + 1).map(b => {
        const p = POS[a], q = POS[b]
        return <line key={`${a}-${b}`} className="ghost" x1={p.x} y1={p.y} x2={q.x} y2={q.y} />
      }))}

      {edges.map(e => {
        const c = curve(e.from, e.to)
        const color = THEMES[e.from].color
        return (
          <g key={`${e.from}>${e.to}`}>
            <path d={c.d} className={`edge ${e.recent ? 'recent' : ''}`} stroke={color} strokeWidth={2 + Math.min(e.count, 4)}
              markerEnd={`url(#arrow-${e.from})`} fill="none" />
            {e.count > 1 && (
              <g>
                <circle cx={c.mx} cy={c.my} r="10" fill="#fffdf6" stroke={color} />
                <text x={c.mx} y={c.my + 4} textAnchor="middle" className="edge-count" fill={color}>×{e.count}</text>
              </g>
            )}
          </g>
        )
      })}

      {AGENT_ORDER.map(a => {
        const t = THEMES[a], s = states[a], p = POS[a]
        return (
          <g key={a} className={`node ${s.state}`} transform={`translate(${p.x},${p.y})`}>
            <circle r={R + 7} className="halo" fill={t.color} />
            <circle r={R} className="disc" fill={t.tint} stroke={t.color} />
            <g transform="translate(-16,-16) scale(1.34)"><AgentIcon agent={a} size={24} /></g>
            {s.state === 'done' && (
              <g transform={`translate(${R - 6},${-R + 6})`}>
                <circle r="9" fill={t.color} />
                <path d="M-4,0 L-1,3 L4,-3" stroke="#fff" strokeWidth="2" fill="none" strokeLinecap="round" strokeLinejoin="round" />
              </g>
            )}
            <text y={R + 20} textAnchor="middle" className="node-name" fill={t.color}>{t.name}</text>
            <text y={R + 36} textAnchor="middle" className="node-doing">{clip(s.doing)}</text>
          </g>
        )
      })}
    </svg>
  )
}
