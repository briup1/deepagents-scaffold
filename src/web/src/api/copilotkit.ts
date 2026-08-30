import { apiFetch } from "./auth"
export interface AgentInfo {
  name: string
  type: string
}

export async function listAgents(): Promise<{ agents: AgentInfo[] }> {
  const res = await apiFetch('/api/agents/')
  if (!res.ok) throw new Error(`HTTP ${res.status}`)
  return res.json()
}
