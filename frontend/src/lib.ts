import { isAgent } from './agents'
import type { AgentEvent, AgentName, AgentReport, Approval } from './types'

export const money = (n: number) =>
  n.toLocaleString('en-US', { style: 'currency', currency: 'USD', minimumFractionDigits: n % 1 ? 2 : 0 })

/** '2026-08-31' -> 'Mon, Aug 31, 2026' without letting the time zone shift the day. */
export function prettyDate(iso: string): string {
  const [y, m, d] = iso.split('-').map(Number)
  return new Date(Date.UTC(y, m - 1, d)).toLocaleDateString('en-US', {
    weekday: 'short', month: 'short', day: 'numeric', year: 'numeric', timeZone: 'UTC',
  })
}

export function parseJson<T>(s?: string): T | null {
  if (!s) return null
  try { return JSON.parse(s) as T } catch { return null }
}

/** Final reports are JSON. If one was cut off, still pull the answer text out of it. */
export function parseReport(text?: string): AgentReport | null {
  const whole = parseJson<AgentReport>(text)
  if (whole && typeof whole.answer === 'string') return whole
  const m = text?.match(/"answer":\s*"((?:[^"\\]|\\.)*)/)
  return m ? { agent: '', answer: m[1].replace(/\\"/g, '"').replace(/\\n/g, ' ') } : null
}

export function argsText(args: Record<string, unknown>): string {
  return Object.entries(args)
    .filter(([k]) => k !== 'task')
    .map(([k, v]) => {
      const text = typeof v === 'string' ? v : JSON.stringify(v)
      return `${k}=${text.length > 44 ? text.slice(0, 43) + '…' : text}`
    })
    .join(', ')
}

const GIST_KEYS = ['error', 'ok', 'subject', 'vendor_name', 'lead_days', 'qty', 'location', 'balance', 'available_after_commitments', 'amount', 'status',
  'is_overdue', 'days_overdue', 'days_until_due', 'on_hold', 'monthly_rent', 'margin_percent', 'list_price',
  'total', 'approval_id', 'draft_id', 'sent']

/** A short human-readable gist of a tool result. */
export function resultGist(result?: string): string {
  const obj = parseJson<Record<string, unknown>>(result)
  if (!obj || typeof obj !== 'object') {
    // The audit trail trims long results, so the JSON may be cut off. Pull out the key fields anyway.
    const found: string[] = []
    for (const k of GIST_KEYS) {
      const m = result?.match(new RegExp(`"${k}":\\s*("(?:[^"\\\\]|\\\\.)*"|-?[\\d.]+|true|false|null)`))
      if (m) found.push(`${k.replace(/_/g, ' ')} ${m[1].replace(/^"|"$/g, '')}`)
      if (found.length >= 4) break
    }
    return found.join(' · ') || (result ?? '').slice(0, 120)
  }
  if (Array.isArray(obj.tickets)) return `${obj.tickets.length} ticket(s) on the board`
  if (Array.isArray(obj.vendors)) {
    const held = (obj.vendors as { on_hold?: boolean }[]).filter(v => v.on_hold).length
    return `${obj.vendors.length} vendor(s), ${held} on hold`
  }
  if (Array.isArray(obj.open_invoices)) return `${obj.open_invoices.length} open invoice(s)`
  if (Array.isArray(obj.approvals)) return `${obj.approvals.length} approval(s) on file`
  const parts: string[] = []
  for (const k of GIST_KEYS) {
    const v = obj[k]
    if (v !== undefined && v !== null && typeof v !== 'object') parts.push(`${k.replace(/_/g, ' ')} ${v}`)
    if (parts.length >= 4) break
  }
  return parts.join(' · ') || (result ?? '').slice(0, 140)
}

// ---------------------------------------------------------------- the feed

export type FeedItem =
  | { kind: 'say'; seq: number; from: string; to?: string; text: string }
  | { kind: 'act'; seq: number; agent: string; tool: string; args: string }
  | { kind: 'tools'; seq: number; agent: string; tools: string[] }
  | { kind: 'got'; seq: number; agent: string; tool: string; gist: string; full: string; bad: boolean }
  | { kind: 'refused'; seq: number; agent: string; text: string }
  | { kind: 'report'; seq: number; agent: string; report: AgentReport }
  | { kind: 'boss_wrap'; seq: number; text: string }
  | { kind: 'note'; seq: number; text: string; bad: boolean }

export function buildFeed(events: AgentEvent[]): FeedItem[] {
  const out: FeedItem[] = []
  for (const e of events) {
    switch (e.kind) {
      case 'run_start':
        out.push({ kind: 'note', seq: e.seq, bad: false,
          text: e.text?.startsWith('Follow-up') ? 'A human acted. The boss re-checks the ticket.' : 'The boss is handed the ticket.' })
        break
      case 'delegation': {
        const call = e.tool_calls?.[0]
        const to = String(call?.args?.to ?? '')
        out.push({ kind: 'say', seq: e.seq, from: e.agent, to, text: String(call?.args?.task ?? '') })
        break
      }
      case 'delegation_refused':
        out.push({ kind: 'refused', seq: e.seq, agent: e.agent, text: (e.text ?? '').replace(/^.*?:\s*/, '') })
        break
      case 'model_response': {
        const calls = (e.tool_calls ?? []).filter(c => c.tool !== 'delegate' && c.tool !== 'final_result')
        if (e.text) out.push({ kind: 'say', seq: e.seq, from: e.agent, text: e.text })
        for (const c of calls) out.push({ kind: 'act', seq: e.seq, agent: e.agent, tool: c.tool, args: argsText(c.args) })
        break
      }
      case 'tool_results':
        for (const r of e.tool_results ?? []) {
          if (r.tool === 'delegate' || r.tool === 'final_result') continue
          const text = r.result ?? r.retry ?? ''
          out.push({ kind: 'got', seq: e.seq, agent: e.agent, tool: r.tool, gist: resultGist(text), full: text,
            bad: Boolean(r.retry) || /"ok":\s*false|"error"/.test(text) })
        }
        break
      case 'final': {
        if (e.agent === 'boss') {
          const wrap = parseJson<{ priority_reasoning?: string }>(e.text)
          if (wrap?.priority_reasoning) out.push({ kind: 'boss_wrap', seq: e.seq, text: wrap.priority_reasoning })
        } else {
          const report = parseReport(e.text)
          if (report) out.push({ kind: 'report', seq: e.seq, agent: e.agent, report })
        }
        break
      }
      case 'run_end':
        out.push({ kind: 'note', seq: e.seq, text: 'The boss is done with this pass.', bad: false })
        break
      case 'run_stopped':
      case 'run_error':
        out.push({ kind: 'note', seq: e.seq, text: e.text ?? 'The run stopped.', bad: true })
        break
      case 'human_approved':
      case 'human_declined':
      case 'payment_made':
        out.push({ kind: 'note', seq: e.seq, text: e.text ?? '', bad: false })
        break
      case 'payment_refused':
        out.push({ kind: 'note', seq: e.seq, text: `Payment refused. ${e.text ?? ''}`, bad: true })
        break
    }
  }
  return out
}

// ---------------------------------------------------------------- who is doing what

export interface AgentState {
  state: 'idle' | 'working' | 'waiting' | 'done'
  doing: string
  tools: Record<string, number>
  sent: number
  received: number
  reports: AgentReport[]
  seen: boolean
}

export interface Edge { from: AgentName; to: AgentName; count: number; recent: boolean }

const blank = (): AgentState => ({ state: 'idle', doing: 'on the sidelines', tools: {}, sent: 0, received: 0, reports: [], seen: false })

export function deriveAgents(events: AgentEvent[], running: boolean): Record<AgentName, AgentState> {
  const st: Record<AgentName, AgentState> = {
    boss: blank(), inventory: blank(), accounting: blank(), facilities: blank(), customer_service: blank(),
  }
  for (const e of events) {
    if (!isAgent(e.agent)) continue
    const a = st[e.agent]
    a.seen = true
    if (e.kind === 'prompt') {
      a.state = 'working'
      a.doing = e.agent === 'boss' ? 'reading the board' : `reading a request from ${nice(e.parent)}`
    } else if (e.kind === 'model_response') {
      const calls = e.tool_calls ?? []
      const dele = calls.filter(c => c.tool === 'delegate').map(c => nice(String(c.args.to)))
      const others = calls.filter(c => c.tool !== 'delegate' && c.tool !== 'final_result')
      for (const c of others) a.tools[c.tool] = (a.tools[c.tool] ?? 0) + 1
      if (dele.length) { a.state = 'waiting'; a.doing = `waiting on ${dele.join(' and ')}` }
      else if (others.length) { a.state = 'working'; a.doing = `calling ${others.map(c => c.tool).join(', ')}` }
      else if (calls.some(c => c.tool === 'final_result')) { a.state = 'working'; a.doing = 'writing the report' }
      else { a.state = 'working'; a.doing = 'thinking' }
    } else if (e.kind === 'tool_results') {
      a.state = 'working'
      a.doing = `reading ${(e.tool_results ?? []).map(r => r.tool).filter(t => t !== 'delegate').join(', ') || 'the answers'}`
    } else if (e.kind === 'delegation') {
      a.sent += 1
      const to = String(e.tool_calls?.[0]?.args?.to ?? '')
      if (isAgent(to)) st[to].received += 1
    } else if (e.kind === 'final') {
      a.state = 'done'
      a.doing = 'reported back'
      const r = e.agent === 'boss' ? null : parseReport(e.text)
      if (r) a.reports.push(r)
    }
  }
  if (!running) {
    for (const k of Object.keys(st) as AgentName[]) {
      if (st[k].seen && st[k].state !== 'done') { st[k].state = 'done'; st[k].doing = 'finished' }
    }
  }
  return st
}

export function deriveEdges(events: AgentEvent[]): Edge[] {
  const map = new Map<string, Edge>()
  const delegations = events.filter(e => e.kind === 'delegation')
  delegations.forEach((e, i) => {
    const to = String(e.tool_calls?.[0]?.args?.to ?? '')
    if (!isAgent(e.agent) || !isAgent(to)) return
    const key = `${e.agent}>${to}`
    const edge = map.get(key) ?? { from: e.agent, to, count: 0, recent: false }
    edge.count += 1
    edge.recent = i >= delegations.length - 2
    map.set(key, edge)
  })
  return [...map.values()]
}

export function nice(name: string | null | undefined): string {
  if (!name) return 'someone'
  return isAgent(name) ? name.replace('_', ' ').replace(/\b\w/g, c => c.toUpperCase()) : name
}

export function approvalLabel(kind: Approval['kind']): string {
  return kind === 'rent_payment' ? 'Rent' : kind === 'invoice_payment' ? 'Vendor invoice' : 'Purchase order'
}

/** The readable view: orders, reports and refusals, with each agent's lookups folded into one line. */
export function compactFeed(items: FeedItem[]): FeedItem[] {
  const out: FeedItem[] = []
  for (const it of items) {
    if (it.kind === 'act') {
      const last = out[out.length - 1]
      if (last && last.kind === 'tools' && last.agent === it.agent) {
        if (!last.tools.includes(it.tool)) last.tools.push(it.tool)
      } else {
        out.push({ kind: 'tools', seq: it.seq, agent: it.agent, tools: [it.tool] })
      }
    } else if (it.kind === 'got') {
      if (it.bad) out.push(it)  // keep the lookups that were refused or failed
    } else {
      out.push(it)
    }
  }
  return out
}
