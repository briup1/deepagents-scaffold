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

/**
 * 包装用户传入的 AgentSubscriber，在关键生命周期输出 console.debug 日志。
 * 不记录消息内容，只记录 threadId / runId / event type / 相关标识，用于复现时定位
 * 是前端未收到事件、SSE 中断还是 run 报错。
 */
function _wrapSubscriber(
  subscriber: AgentSubscriber,
  context: { threadId: string; runId: string },
): AgentSubscriber {
  return new Proxy(subscriber, {
    get(target, prop, receiver) {
      const value = Reflect.get(target, prop, receiver)
      if (typeof value !== 'function') {
        return value
      }
      return function (this: unknown, ...args: unknown[]) {
        const payload = args[0] as any
        const event = payload?.event ?? {}
        console.debug(
          `[ag-ui] ${String(prop)}: threadId=${context.threadId} runId=${context.runId} ` +
            `type=${event.type ?? '-'} ` +
            `messageId=${event.messageId ?? '-'} ` +
            `toolCallId=${event.toolCallId ?? '-'}`,
        )
        return value.apply(this, args)
      }
    },
  }) as AgentSubscriber
}

export async function sendAgentMessage(
  agent: HttpAgent,
  content: string,
  subscriber: AgentSubscriber,
): Promise<void> {
  const messageId = `msg-${crypto.randomUUID()}`
  const runId = `run-${crypto.randomUUID()}`
  const threadId = (agent as any).threadId ?? 'unknown'

  agent.addMessage({
    id: messageId,
    role: 'user',
    content,
  })

  console.debug(`[ag-ui] send start: threadId=${threadId} runId=${runId} messageId=${messageId}`)

  try {
    await agent.runAgent({ runId }, _wrapSubscriber(subscriber, { threadId, runId }))
    console.debug(`[ag-ui] send complete: threadId=${threadId} runId=${runId}`)
  } catch (err) {
    console.debug(`[ag-ui] send error: threadId=${threadId} runId=${runId}`, err)
    throw err
  }
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
