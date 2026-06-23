const API_BASE = ''

export interface Message {
  role: 'user' | 'assistant' | 'tool'
  content: string
}

export async function sendMessageStream(
  messages: Message[],
  onEvent: (data: unknown) => void,
  assistantId = 'default',
): Promise<void> {
  const response = await fetch(`${API_BASE}/api/runs/stream`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({
      assistant_id: assistantId,
      input: { messages },
    }),
  })

  if (!response.ok) {
    throw new Error(`HTTP ${response.status}: ${await response.text()}`)
  }

  const reader = response.body?.getReader()
  const decoder = new TextDecoder()
  if (!reader) return

  let buffer = ''
  while (true) {
    const { done, value } = await reader.read()
    if (done) break
    buffer += decoder.decode(value, { stream: true })

    const lines = buffer.split('\n\n')
    buffer = lines.pop() || ''

    for (const chunk of lines) {
      const dataLine = chunk.split('\n').find((l) => l.startsWith('data:'))
      if (!dataLine) continue
      const jsonStr = dataLine.slice(5).trim()
      if (jsonStr) {
        try {
          onEvent(JSON.parse(jsonStr))
        } catch {
          // ignore malformed JSON
        }
      }
    }
  }
}

export async function listAgents(): Promise<{ agents: Array<{ name: string; type: string }> }> {
  const res = await fetch(`${API_BASE}/api/agents/`)
  if (!res.ok) throw new Error(`HTTP ${res.status}`)
  return res.json()
}

export async function listTools(): Promise<{ tools: Array<{ name: string; description?: string }> }> {
  const res = await fetch(`${API_BASE}/api/tools/`)
  if (!res.ok) throw new Error(`HTTP ${res.status}`)
  return res.json()
}
