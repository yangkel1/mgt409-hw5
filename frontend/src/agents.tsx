import type { AgentName } from './types'

export interface AgentMeta {
  name: AgentName
  label: string
  role: string
  voice: string // what their lines on the board feel like
  color: string
  x: number // position on the agent floor, % of width
  y: number // % of height
}

export const AGENTS: Record<AgentName, AgentMeta> = {
  boss: {
    name: 'boss', label: 'Boss', role: 'Reads tickets · routes · decides',
    voice: 'memo', color: '#d9a441', x: 50, y: 19,
  },
  inventory: {
    name: 'inventory', label: 'Inventory', role: 'Stock · shortfalls · restock',
    voice: 'slip', color: '#2fa39a', x: 12.5, y: 72,
  },
  accounting: {
    name: 'accounting', label: 'Accounting', role: 'Cash · invoices · approvals',
    voice: 'ledger', color: '#4c9a52', x: 37.5, y: 72,
  },
  facilities: {
    name: 'facilities', label: 'Facilities', role: 'Lease · rent · landlord',
    voice: 'blueprint', color: '#4a7fd0', x: 62.5, y: 72,
  },
  customer_service: {
    name: 'customer_service', label: 'Customer Service', role: 'Drafts customer messages',
    voice: 'chat', color: '#d0648a', x: 87.5, y: 72,
  },
}

export const AGENT_ORDER: AgentName[] = ['boss', 'inventory', 'accounting', 'facilities', 'customer_service']

export const isAgent = (s: string): s is AgentName => s in AGENTS

const ICON_PATHS: Record<AgentName | 'human', string> = {
  boss: 'M4 18h16M5 8l4 4 3-6 3 6 4-4-1.5 10h-11z',
  inventory: 'M3.5 7.5 12 3.5l8.5 4v9L12 20.5l-8.5-4zM3.5 7.5 12 11.5l8.5-4M12 11.5v9',
  accounting: 'M6 3.5h9l3 3v14H6zM9 9h6M9 12.5h6M9 16h3.5',
  facilities: 'M4 20.5V9l8-5.5L20 9v11.5M9.5 20.5V15h5v5.5',
  customer_service: 'M4 5h16v10.5H10l-5 4v-4H4zM8 10.2h8',
  human: 'M12 12a4 4 0 1 0 0-8 4 4 0 0 0 0 8zM4.5 20.5c1.2-3.6 4-5.5 7.5-5.5s6.3 1.9 7.5 5.5',
}

export function AgentIcon({ name, size = 22 }: { name: AgentName | 'human'; size?: number }) {
  return (
    <svg width={size} height={size} viewBox="0 0 24 24" fill="none" stroke="currentColor"
      strokeWidth={1.7} strokeLinecap="round" strokeLinejoin="round" aria-hidden>
      <path d={ICON_PATHS[name]} />
    </svg>
  )
}

export const TICKET_TYPES: Record<string, { label: string; tone: string }> = {
  customer_order: { label: 'Customer order', tone: '#2fa39a' },
  rent_notice: { label: 'Rent notice', tone: '#4a7fd0' },
  price_override: { label: 'Discount request', tone: '#d0648a' },
}

export const money = (n: number) =>
  n.toLocaleString('en-US', { style: 'currency', currency: 'USD' })

export const clockTime = (ts: string) =>
  new Date(ts).toLocaleTimeString([], { hour: 'numeric', minute: '2-digit', second: '2-digit' })

export const prettyTool = (t: string) => t.replace(/_/g, ' ')
