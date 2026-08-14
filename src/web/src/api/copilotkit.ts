export interface AgentInfo {
  name: string
  type: string
}

export async function listAgents(): Promise<{ agents: AgentInfo[] }> {
  const res = await fetch('/api/agents/')
  if (!res.ok) throw new Error(`HTTP ${res.status}`)
  return res.json()
}
