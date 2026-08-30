import { apiFetchJson } from './auth'

export interface AgentInfo {
  name: string
  type: string
}

export async function listAgents(): Promise<{ agents: AgentInfo[] }> {
  return apiFetchJson('/api/agents/')
}
