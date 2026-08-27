import { fetchJson } from './request'

export interface AgentInfo {
  name: string
  type: string
}

export async function listAgents(): Promise<{ agents: AgentInfo[] }> {
  return fetchJson('/api/agents/')
}
