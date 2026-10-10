export type AgentName = 'boss' | 'inventory' | 'accounting' | 'facilities' | 'customer_service'

export interface Ticket {
  id: number
  type: string
  requester: string
  subject: string
  status: 'open' | 'resolved' | 'needs_human'
  open: boolean
  created_at: string
}

export interface TicketOutcome {
  ticket_id: number
  status: string
  decision: string
  who_did_what: string[]
  money: string
  needs_human: string
}

export interface BoardOutcome {
  priority_order: number[]
  priority_reasoning: string
  tickets: TicketOutcome[]
}

export interface RunInfo {
  run_id: string
  ticket_id: number
  status: 'running' | 'finished' | 'stopped' | 'error'
  started_at: string
  finished_at?: string
  error?: string
  outcome?: BoardOutcome
}

export interface TicketsResponse {
  today: string
  tickets: Ticket[]
  running: RunInfo | null
}

export interface Draft {
  id: number
  audience: string
  body: string
  created_by: string
}

export interface TicketDetail extends Ticket {
  notes: string | null
  sku: string | null
  size: string | null
  qty: number | null
  drafts: Draft[]
  summaries: { status: string; summary: string; created_at: string }[]
}

export interface ToolCall {
  tool: string
  args: Record<string, unknown>
}

export interface ToolResult {
  tool: string
  result?: string
  retry?: string
}

export interface AgentEvent {
  seq: number
  run_id: string
  tickets: number[]
  agent: string
  depth: number
  parent: string | null
  kind: string
  text?: string
  tool_calls?: ToolCall[]
  tool_results?: ToolResult[]
  headline: string
  timestamp: string
}

export interface EventsResponse {
  total: number
  next_after: number
  events: AgentEvent[]
}

export interface Approval {
  id: number
  kind: 'invoice_payment' | 'rent_payment' | 'purchase_order'
  ref_id: number
  amount: number
  description: string
  ticket_id: number | null
  requested_by: string
  status: 'pending' | 'approved' | 'rejected' | 'executed'
  decided_by: string | null
  decided_at: string | null
  executed_at: string | null
  created_at: string
}

export interface Payment {
  id: number
  kind: string
  ref_id: number
  amount: number
  approved_by: string
  paid_at: string
}

export interface ApprovalsResponse {
  approvals: Approval[]
  payments_made: Payment[]
}

export interface Cash {
  account: string
  balance: number
  as_of: string
  committed_not_yet_paid: number
  available_after_commitments: number
}

export interface AgentReport {
  agent: string
  answer: string
  facts?: string[]
  blockers?: string[]
  needs_human?: string[]
}
