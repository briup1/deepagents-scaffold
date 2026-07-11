import { HttpAgent, type AgentSubscriber, type Message } from '@ag-ui/client'

export type { Message, AgentSubscriber }

export interface DisplayItem {
  id: string
  type: 'text' | 'reasoning' | 'tool' | 'error'
  role?: 'user' | 'assistant'
  content?: string
  toolName?: string
  args?: string
  result?: string
}

export function createAgent(threadId: string, url = '/agent'): HttpAgent {
  return new HttpAgent({ url, threadId })
}

export async function sendAgentMessage(
  agent: HttpAgent,
  content: string,
  subscriber: AgentSubscriber,
): Promise<void> {
  agent.addMessage({
    id: `msg-${Date.now()}-${Math.random().toString(36).slice(2, 7)}`,
    role: 'user',
    content,
  })
  await agent.runAgent({ runId: `run-${Date.now()}` }, subscriber)
}

export async function listAgents(): Promise<{ agents: Array<{ name: string; type: string }> }> {
  const res = await fetch('/api/agents/')
  if (!res.ok) throw new Error(`HTTP ${res.status}`)
  return res.json()
}

export async function listTools(): Promise<{ tools: Array<{ name: string; description?: string }> }> {
  const res = await fetch('/api/tools/')
  if (!res.ok) throw new Error(`HTTP ${res.status}`)
  return res.json()
}
