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

    const frames = buffer.split('\n\n')
    buffer = frames.pop() || ''

    for (const frame of frames) {
      const eventName = frame
        .split('\n')
        .find((l) => l.startsWith('event:'))
        ?.slice(6)
        .trim()
      const dataLine = frame.split('\n').find((l) => l.startsWith('data:'))
      if (!dataLine) continue
      const jsonStr = dataLine.slice(5).trim()
      if (!jsonStr) continue

      let payload: unknown
      try {
        payload = JSON.parse(jsonStr)
      } catch {
        // ignore malformed JSON
        continue
      }

      if (eventName === 'error') {
        const message =
          typeof (payload as Record<string, unknown>).message === 'string'
            ? ((payload as Record<string, unknown>).message as string)
            : JSON.stringify(payload)
        throw new Error(message)
      }
      if (eventName !== 'heartbeat' && eventName !== 'end') {
        onEvent(payload)
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
