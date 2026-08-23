import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { HistoryHttpAgent, toAgentMessage } from './historyAgent'
import type { ThreadMessage } from './threads'

const mockFetch = vi.fn()

function makeThreadMessage(overrides: Partial<ThreadMessage> = {}): ThreadMessage {
  return {
    message_id: 'm1',
    run_id: 'r1',
    role: 'user',
    content: '你好',
    name: null,
    tool_call_id: null,
    tool_calls: null,
    created_at: '2026-08-18T10:00:00Z',
    ...overrides,
  }
}

describe('toAgentMessage', () => {
  it('转换 user 消息', () => {
    expect(toAgentMessage(makeThreadMessage())).toEqual({
      id: 'm1',
      role: 'user',
      content: '你好',
      name: undefined,
    })
  })

  it('转换带工具调用的 assistant 消息', () => {
    const result = toAgentMessage(
      makeThreadMessage({
        role: 'assistant',
        content: null,
        tool_calls: [{ id: 'tc1', function: { name: 'render_ui', arguments: { a: 1 } } }],
      }),
    )
    expect(result).toMatchObject({
      id: 'm1',
      role: 'assistant',
      toolCalls: [
        { id: 'tc1', type: 'function', function: { name: 'render_ui', arguments: '{"a":1}' } },
      ],
    })
  })

  it('转换 tool 消息并携带 toolCallId', () => {
    const result = toAgentMessage(
      makeThreadMessage({ role: 'tool', tool_call_id: 'tc1', content: '结果' }),
    )
    expect(result).toMatchObject({ id: 'm1', role: 'tool', toolCallId: 'tc1', content: '结果' })
  })

  it('过滤 system 消息', () => {
    expect(toAgentMessage(makeThreadMessage({ role: 'system' }))).toBeNull()
  })
})

describe('HistoryHttpAgent.connectAgent', () => {
  beforeEach(() => {
    vi.stubGlobal('fetch', mockFetch)
    mockFetch.mockReset()
  })

  afterEach(() => {
    vi.unstubAllGlobals()
  })

  it('connect 时从后端拉取线程消息并灌入 agent（历史回放）', async () => {
    mockFetch.mockResolvedValue({
      ok: true,
      json: async () => ({
        thread_id: 'thread-h1',
        messages: [
          makeThreadMessage({ message_id: 'm1', role: 'user', content: '你好' }),
          makeThreadMessage({ message_id: 'm2', role: 'assistant', content: '你好！有什么可以帮你的吗？' }),
        ],
      }),
    })
    const agent = new HistoryHttpAgent({ url: '/agent', threadId: 'thread-h1', agentId: 'default' })

    const result = await agent.connectAgent()

    expect(mockFetch).toHaveBeenCalledWith('/api/threads/thread-h1/messages')
    expect(agent.messages).toHaveLength(2)
    expect(agent.messages[0]).toMatchObject({ id: 'm1', role: 'user', content: '你好' })
    expect(agent.messages[1]).toMatchObject({ id: 'm2', role: 'assistant' })
    // 不回放出新消息，避免 CopilotKitCore 误触发前端工具执行
    expect(result.newMessages).toEqual([])
  })

  it('线程不存在（新会话）时灌入空列表且不抛错', async () => {
    mockFetch.mockResolvedValue({
      ok: true,
      json: async () => ({ thread_id: 'thread-new', messages: [] }),
    })
    const agent = new HistoryHttpAgent({ url: '/agent', threadId: 'thread-new', agentId: 'default' })

    await expect(agent.connectAgent()).resolves.toEqual({ result: undefined, newMessages: [] })
    expect(agent.messages).toEqual([])
  })

  it('后端异常时上抛错误（由 CopilotKit 记录连接失败）', async () => {
    mockFetch.mockResolvedValue({ ok: false, status: 500 })
    const agent = new HistoryHttpAgent({ url: '/agent', threadId: 'thread-err', agentId: 'default' })

    await expect(agent.connectAgent()).rejects.toThrow('HTTP 500')
  })

  it('setMessages 通知订阅者（驱动聊天界面渲染历史消息）', async () => {
    mockFetch.mockResolvedValue({
      ok: true,
      json: async () => ({ thread_id: 'thread-h1', messages: [makeThreadMessage()] }),
    })
    const agent = new HistoryHttpAgent({ url: '/agent', threadId: 'thread-h1', agentId: 'default' })
    const onMessagesChanged = vi.fn()
    agent.subscribe({ onMessagesChanged })

    await agent.connectAgent()

    await vi.waitFor(() => expect(onMessagesChanged).toHaveBeenCalled())
    expect(onMessagesChanged.mock.calls[0][0].messages).toHaveLength(1)
  })
})
