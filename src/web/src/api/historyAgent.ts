import {
  HttpAgent,
  type AgentSubscriber,
  type Message,
  type RunAgentParameters,
  type RunAgentResult,
} from '@ag-ui/client'
import { getThreadMessages, type ThreadMessage } from './threads'
import { randomUUID } from '../lib/uuid'

interface ThreadToolCall {
  id?: string
  function?: {
    name?: string
    arguments?: string | Record<string, unknown>
  }
}

/**
 * 将后端历史消息转换为 AG-UI 消息；聊天界面只展示 user/assistant/tool 三类。
 */
export function toAgentMessage(m: ThreadMessage): Message | null {
  if (m.role !== 'user' && m.role !== 'assistant' && m.role !== 'tool') {
    return null
  }

  const base = {
    id: m.message_id,
    role: m.role,
    content: m.content ?? undefined,
    name: m.name ?? undefined,
  }

  if (m.role === 'assistant' && m.tool_calls && m.tool_calls.length > 0) {
    return {
      ...base,
      role: 'assistant',
      toolCalls: (m.tool_calls as ThreadToolCall[]).map((tc) => {
        const fn = tc.function ?? {}
        const args = fn.arguments ?? {}
        return {
          id: String(tc.id ?? randomUUID()),
          type: 'function' as const,
          function: {
            name: String(fn.name ?? ''),
            arguments: typeof args === 'string' ? args : JSON.stringify(args),
          },
        }
      }),
    } as Message
  }

  if (m.role === 'tool') {
    return { ...base, role: 'tool', toolCallId: m.tool_call_id ?? m.message_id } as Message
  }

  return base as Message
}

/**
 * 支持历史回放的 HttpAgent。
 *
 * CopilotKitCore 在检测到 threadId 切换（fresh restore）时会先清空本地消息，
 * 再调用 connectAgent 等待网关回放线程历史；HttpAgent 默认不支持 connect，
 * 导致点击历史会话后聊天区永远空白。这里重写 connectAgent，从后端 REST
 * 拉取该线程的持久化消息灌入本地，与框架的 fresh-restore 机制对齐
 * （与官方 IntelligenceAgent 重写 connectAgent 回放历史的做法同构）。
 */
export class HistoryHttpAgent extends HttpAgent {
  override async connectAgent(
    _parameters?: RunAgentParameters,
    _subscriber?: AgentSubscriber,
  ): Promise<RunAgentResult> {
    // 未知线程后端返回空列表；其余错误上抛，由 CopilotKit 记录连接失败
    const data = await getThreadMessages(this.threadId)
    const messages = (data.messages ?? [])
      .map(toAgentMessage)
      .filter((m): m is Message => m !== null)
    this.setMessages(messages)
    return { result: undefined, newMessages: [] }
  }
}
