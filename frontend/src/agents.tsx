import type { ReactNode } from 'react'
import type { AgentName } from './types'

export interface Theme {
  name: string
  role: string
  color: string      // strong colour: ring, name, arrows
  tint: string       // soft background for bubbles
  voice: string      // how this agent reads on the page (also used as a CSS class)
  tag: string        // the little label on its messages
}

// Each agent reads differently on purpose: a different paper, shape, and label,
// matching the voice written into its prompt.
export const THEMES: Record<AgentName, Theme> = {
  boss: { name: 'Boss', role: 'Gives the orders', color: '#00356b', tint: '#e8eef7', voice: 'voice-boss', tag: 'ORDER' },
  inventory: { name: 'Inventory', role: 'Counts the shelves', color: '#2f6f68', tint: '#e5f1ee', voice: 'voice-inventory', tag: 'STOCK NOTE' },
  accounting: { name: 'Accounting', role: 'Watches the cash', color: '#2f7d4f', tint: '#eaf5ec', voice: 'voice-accounting', tag: 'LEDGER' },
  facilities: { name: 'Facilities', role: 'Minds the space', color: '#c8561e', tint: '#fff0e4', voice: 'voice-facilities', tag: 'WORK ORDER' },
  customer_service: { name: 'Customer Service', role: 'Writes the drafts', color: '#b83a72', tint: '#fdeaf3', voice: 'voice-service', tag: 'DRAFT NOTE' },
}

export const AGENT_ORDER: AgentName[] = ['boss', 'inventory', 'accounting', 'facilities', 'customer_service']

export function isAgent(name: string): name is AgentName {
  return name in THEMES
}

/** Small line icons, drawn on a 24x24 grid. */
export function AgentIcon({ agent, size = 24, color }: { agent: AgentName; size?: number; color?: string }): ReactNode {
  const c = color ?? THEMES[agent].color
  const common = { width: size, height: size, viewBox: '0 0 24 24', fill: 'none', stroke: c, strokeWidth: 1.8, strokeLinecap: 'round' as const, strokeLinejoin: 'round' as const }
  switch (agent) {
    case 'boss':
      return <svg {...common}><path d="M3.5 18.5h17l-1.4-9.5-4.6 4.2L12 6.5l-2.5 6.7L4.9 9z" fill={c} fillOpacity=".18" /><path d="M5 21h14" /></svg>
    case 'inventory':
      return <svg {...common}><path d="M4 8l8-4 8 4v9l-8 4-8-4z" fill={c} fillOpacity=".15" /><path d="M4 8l8 4 8-4M12 12v9" /></svg>
    case 'accounting':
      return <svg {...common}><circle cx="12" cy="12" r="8.5" fill={c} fillOpacity=".15" /><path d="M12 7v10M9.3 9.6c0-2 5.4-2 5.4 0s-5.4 1.4-5.4 3.2 5.4 2 5.4 0" /></svg>
    case 'facilities':
      return <svg {...common}><path d="M14.8 5.2a4.2 4.2 0 0 0-5.3 5.4L4 16.1 7.9 20l5.4-5.5a4.2 4.2 0 0 0 5.4-5.3l-2.8 2.8-2.4-.6-.6-2.4z" fill={c} fillOpacity=".15" /></svg>
    case 'customer_service':
      return <svg {...common}><path d="M4 5.5h16v11H9.5L5 20.5v-4H4z" fill={c} fillOpacity=".15" /><path d="M8 10h8M8 13h5" /></svg>
  }
}

export const TYPE_LABEL: Record<string, string> = {
  customer_order: 'Customer order',
  rent_notice: 'Rent notice',
  price_override: 'Price request',
}
