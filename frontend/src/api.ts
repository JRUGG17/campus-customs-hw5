import type {
  ApprovalsResponse, Cash, EventsResponse, RunInfo, TicketDetail, TicketsResponse,
} from './types'

// The backend from Problem 7. It allows this page's origin (http://localhost:5173) through CORS.
export const API = (import.meta.env.VITE_API_URL as string | undefined) ?? 'http://localhost:8000'

export class ApiError extends Error {
  status: number
  constructor(message: string, status: number) {
    super(message)
    this.status = status
  }
}

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  let res: Response
  try {
    res = await fetch(`${API}${path}`, {
      ...init,
      headers: { 'Content-Type': 'application/json', ...(init?.headers ?? {}) },
    })
  } catch {
    throw new ApiError(`Can't reach the backend at ${API}. Is uvicorn running?`, 0)
  }
  if (!res.ok) {
    let message = `${res.status} ${res.statusText}`
    try {
      const body = await res.json()
      const d = body?.detail
      if (typeof d === 'string') message = d
      else if (d?.error) message = d.error
      else if (Array.isArray(d) && d[0]?.msg) message = d[0].msg
    } catch { /* keep the status text */ }
    throw new ApiError(message, res.status)
  }
  return res.json() as Promise<T>
}

export const getTickets = () => request<TicketsResponse>('/api/tickets')
export const getTicketDetail = (id: number) => request<TicketDetail>(`/api/tickets/${id}`)
export const runTicket = (id: number) => request<RunInfo>(`/api/tickets/${id}/run`, { method: 'POST' })
export const closeoutTicket = (id: number, note?: string, decidedBy?: string) =>
  request<RunInfo>(`/api/tickets/${id}/closeout`, {
    method: 'POST', body: JSON.stringify(note ? { note, decided_by: decidedBy } : {}),
  })
export const getRun = (runId: string) => request<RunInfo>(`/api/runs/${runId}`)
export const getEvents = (ticketId: number, limit = 500) =>
  request<EventsResponse>(`/api/events?ticket_id=${ticketId}&since_reset=true&limit=${limit}`)
export const getApprovals = () => request<ApprovalsResponse>('/api/approvals')
export const approve = (id: number, approvedBy: string) =>
  request<{ approval_id: number; paid: number; balance_after: number }>(`/api/approvals/${id}/approve`, {
    method: 'POST', body: JSON.stringify({ approved_by: approvedBy }),
  })
export const reject = (id: number, rejectedBy: string) =>
  request<{ ok: boolean }>(`/api/approvals/${id}/reject`, {
    method: 'POST', body: JSON.stringify({ rejected_by: rejectedBy }),
  })
export const getCash = () => request<Cash>('/api/cash')
export const resetDatabase = () => request<{ ok: boolean }>('/api/reset', { method: 'POST' })
