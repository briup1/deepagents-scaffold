export interface ThreadSummary {
  thread_id: string
  agent_id: string
  title: string | null
  last_message_preview: string | null
  created_at: string
  updated_at: string
}

export interface ThreadMessage {
  message_id: string
  run_id: string | null
  role: 'user' | 'assistant' | 'system' | 'tool'
  content: string | null
  name: string | null
  tool_call_id: string | null
  tool_calls: Array<Record<string, unknown>> | null
  created_at: string
}

export async function listThreads(agentId?: string): Promise<{ threads: ThreadSummary[]; total: number }> {
  const params = new URLSearchParams()
  if (agentId) params.set('agent_id', agentId)
  const res = await fetch(`/api/threads/?${params.toString()}`)
  if (!res.ok) throw new Error(`HTTP ${res.status}`)
  return res.json()
}

export async function getThreadMessages(threadId: string): Promise<{ thread_id: string; messages: ThreadMessage[] }> {
  const res = await fetch(`/api/threads/${encodeURIComponent(threadId)}/messages`)
  if (!res.ok) throw new Error(`HTTP ${res.status}`)
  return res.json()
}

export async function createThread(agentId?: string): Promise<{ thread_id: string }> {
  const res = await fetch('/api/threads/', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ agent_id: agentId ?? 'default' }),
  })
  if (!res.ok) throw new Error(`HTTP ${res.status}`)
  return res.json()
}
