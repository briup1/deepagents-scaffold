import { cleanup, render, screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import type { ThreadSummary } from './api/threads'
import App from './App'

let latestCopilotKitProps: Record<string, unknown> = {}
let latestCopilotChatProps: Record<string, unknown> = {}
const mockSetMessages = vi.fn()

// 可变的 agent 状态：测试中通过修改它 + rerender 模拟真实 agent 的消息/运行状态变化
const mockAgentState: {
  messages: Array<{ id: string; role: string; content?: string }>
  isRunning: boolean
} = { messages: [], isRunning: false }

vi.mock('@copilotkit/react-core/v2', () => ({
  CopilotKit: (props: React.PropsWithChildren<Record<string, unknown>>) => {
    latestCopilotKitProps = props
    return <div data-testid="copilot-kit">{props.children}</div>
  },
  CopilotChat: (props: Record<string, unknown>) => {
    latestCopilotChatProps = props
    return <div data-testid="copilot-chat">{String((props.labels as Record<string, string>)?.chatInputPlaceholder ?? '')}</div>
  },
  useAgent: () => ({
    agent: {
      setMessages: mockSetMessages,
      runAgent: vi.fn(),
      get messages() {
        return mockAgentState.messages
      },
      get isRunning() {
        return mockAgentState.isRunning
      },
    },
    isReady: true,
  }),
  useRenderTool: vi.fn(),
}))

let latestHttpAgentCall: { threadId?: string; url?: string } = {}

vi.mock('@ag-ui/client', () => ({
  HttpAgent: vi.fn((args: { threadId?: string; url?: string }) => {
    latestHttpAgentCall = args
    return {}
  }),
}))

const mockFetch = vi.fn()

const historyThread: ThreadSummary = {
  thread_id: 't-history',
  agent_id: 'default',
  title: '历史会话',
  last_message_preview: '历史消息预览',
  created_at: '2026-08-18T10:00:00Z',
  updated_at: '2026-08-18T10:05:00Z',
}

// 模拟服务端 threads 表：测试中可追加“已落库”的会话
let serverThreads: ThreadSummary[] = []

describe('App', () => {
  beforeEach(() => {
    // 认证：测试环境预设有效 token，跳过 TokenGate
    localStorage.setItem('scaffold_token', 'test-token')
    vi.stubGlobal('fetch', mockFetch)
    latestCopilotKitProps = {}
    latestCopilotChatProps = {}
    latestHttpAgentCall = {}
    serverThreads = [historyThread]
    mockAgentState.messages = []
    mockAgentState.isRunning = false
    mockFetch.mockReset()
    mockSetMessages.mockReset()
    mockFetch.mockImplementation(async (url: string) => {
      if (url === '/api/agents/') {
        return {
          ok: true,
          json: async () => ({
            agents: [{ name: 'default' }, { name: 'coding' }, { name: 'code_reviewer' }],
          }),
        }
      }
      if (url === '/api/threads/t-history/messages') {
        return {
          ok: true,
          json: async () => ({
            thread_id: 't-history',
            messages: [
              {
                message_id: 'm1',
                run_id: 'r1',
                role: 'user',
                content: 'hello',
                name: null,
                tool_call_id: null,
                tool_calls: null,
                created_at: '2026-08-18T10:00:00Z',
              },
            ],
          }),
        }
      }
      if (url.startsWith('/api/threads/')) {
        return {
          ok: true,
          json: async () => ({ threads: serverThreads, total: serverThreads.length }),
        }
      }
      if (url === '/api/files/upload') {
        return {
          ok: true,
          json: async () => ({
            artifact_id: 'art-test-upload',
            thread_id: 'thread-test',
            artifact_type: 'upload',
            original_name: 'quote.xlsx',
            stored_path: 'thread-test/uploads/art-test-upload-quote.xlsx',
            mime_type: 'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet',
            size_bytes: 1024,
            created_at: '2026-08-22T10:00:00Z',
          }),
        }
      }
      return { ok: false, status: 404 }
    })
  })

  afterEach(() => {
    cleanup()
    vi.unstubAllGlobals()
    vi.clearAllMocks()
  })

  it('加载 Agent 列表并渲染选择器、新建会话按钮与历史列表', async () => {
    render(<App />)

    await waitFor(() => expect(screen.getByRole('button', { name: '选择 Agent' })).toBeInTheDocument())
    expect(screen.getByRole('button', { name: '新建会话' })).toBeInTheDocument()
    await waitFor(() => expect(screen.getByText('历史会话')).toBeInTheDocument())
    expect(screen.getByTestId('copilot-kit')).toBeInTheDocument()
    expect(latestHttpAgentCall.threadId).toMatch(/^thread-/)
    expect(Object.keys((latestCopilotKitProps.agents__unsafe_dev_only as Record<string, unknown>) ?? {})).toEqual(
      expect.arrayContaining(['default', 'coding', 'code_reviewer']),
    )
  })

  it('切换 Agent 时重置 threadId 以隔离不同 Agent 的历史消息', async () => {
    const user = userEvent.setup()
    render(<App />)

    const trigger = await screen.findByRole('button', { name: '选择 Agent' })
    const firstThreadId = latestHttpAgentCall.threadId

    await user.click(trigger)
    const option = await screen.findByRole('option', { name: 'code_reviewer' })
    await user.click(option)

    await waitFor(() => expect(latestCopilotChatProps.agentId).toBe('code_reviewer'))
    await waitFor(() => expect(latestHttpAgentCall.threadId).not.toBe(firstThreadId))
  })

  it('点击新建会话重置 threadId', async () => {
    const user = userEvent.setup()
    render(<App />)

    await waitFor(() => expect(screen.getByRole('button', { name: '新建会话' })).toBeInTheDocument())

    const firstThreadId = latestHttpAgentCall.threadId
    await user.click(screen.getByRole('button', { name: '新建会话' }))

    await waitFor(() => expect(latestHttpAgentCall.threadId).not.toBe(firstThreadId))
  })

  it('点击历史会话后更新 threadId（历史消息由 HistoryHttpAgent.connectAgent 回放）', async () => {
    const user = userEvent.setup()
    render(<App />)

    await waitFor(() => expect(screen.getByText('历史会话')).toBeInTheDocument())
    const historyThread = await screen.findByRole('button', { name: '历史会话' })
    await user.click(historyThread)

    // App 层只负责切换 threadId；消息回放发生在 HistoryHttpAgent.connectAgent，
    // 其灌入逻辑由 src/api/historyAgent.test.ts 覆盖
    await waitFor(() => expect(latestHttpAgentCall.threadId).toBe('t-history'))
  })

  it('删除当前历史会话后调用删除接口、移除条目并创建新会话', async () => {
    const user = userEvent.setup()
    vi.spyOn(window, 'confirm').mockReturnValue(true)
    render(<App />)

    await user.click(await screen.findByRole('button', { name: '历史会话' }))
    await waitFor(() => expect(latestHttpAgentCall.threadId).toBe('t-history'))
    mockFetch.mockImplementation(async (url: string, init?: RequestInit) => {
      if (url === '/api/threads/t-history' && init?.method === 'DELETE') {
        serverThreads = []
        return { ok: true, json: async () => ({ thread_id: 't-history', deleted: true }) }
      }
      if (url === '/api/agents/') {
        return { ok: true, json: async () => ({ agents: [{ name: 'default' }] }) }
      }
      if (url.startsWith('/api/threads/')) {
        return { ok: true, json: async () => ({ threads: serverThreads, total: serverThreads.length }) }
      }
      return { ok: false, status: 404 }
    })

    await user.click(screen.getByRole('button', { name: '删除会话：历史会话' }))

    await waitFor(() => expect(screen.queryByRole('button', { name: '历史会话' })).not.toBeInTheDocument())
    expect(mockFetch).toHaveBeenCalledWith('/api/threads/t-history', expect.objectContaining({ method: 'DELETE' }))
    expect(latestHttpAgentCall.threadId).toMatch(/^thread-/)
    expect(latestHttpAgentCall.threadId).not.toBe('t-history')
  })

  it('将当前 threadId 显式传给 CopilotChat，避免其自动生成随机线程 id', async () => {
    render(<App />)

    await waitFor(() => expect(screen.getByTestId('copilot-chat')).toBeInTheDocument())
    // 修复前：不传 threadId 时 CopilotChat 挂载时会 randomUUID() 覆盖 agent.threadId，
    // 导致刷新后新消息写入另一条孤儿线程（看不到历史命令）。
    expect(latestCopilotChatProps.threadId).toBe(latestHttpAgentCall.threadId)
  })

  it('点击历史会话后 CopilotChat 的 threadId 与选中线程一致', async () => {
    const user = userEvent.setup()
    render(<App />)

    await waitFor(() => expect(screen.getByText('历史会话')).toBeInTheDocument())
    const historyThread = await screen.findByRole('button', { name: '历史会话' })
    await user.click(historyThread)

    await waitFor(() => expect(latestCopilotChatProps.threadId).toBe('t-history'))
    expect(latestCopilotChatProps.threadId).toBe(latestHttpAgentCall.threadId)
  })

  it('聊天输入区占位符提示支持拖拽上传', async () => {
    render(<App />)

    await waitFor(() => expect(screen.getByTestId('copilot-kit')).toBeInTheDocument())
    await waitFor(() => expect(screen.getByText('拖拽 Excel 到此处或输入消息...')).toBeInTheDocument())
  })

  it('S1: 点击新建会话后侧栏立即出现高亮的“新会话”占位条目，且不发后端建线程请求', async () => {
    const user = userEvent.setup()
    render(<App />)

    await waitFor(() => expect(screen.getByRole('button', { name: '新建会话' })).toBeInTheDocument())
    // 等待列表加载完成（标题含“历史会话”的条目按钮出现）
    await screen.findByRole('button', { name: '历史会话' })

    await user.click(screen.getByRole('button', { name: '新建会话' }))

    // 占位条目立即出现且位于列表最顶
    const placeholder = await screen.findByRole('button', { name: '新会话' })
    expect(placeholder).toBeInTheDocument()
    const options = screen.getAllByRole('option')
    expect(options[0].textContent).toContain('新会话')
    // 高亮条目与当前聊天 threadId 一致
    expect(options[0].getAttribute('aria-selected')).toBe('true')
    expect(latestCopilotChatProps.threadId).toBe(latestHttpAgentCall.threadId)
    // 纯本地乐观占位：不调用 POST /api/threads/
    const hasCreateCall = mockFetch.mock.calls.some(
      ([url, init]) => String(url) === '/api/threads/' && (init as RequestInit | undefined)?.method === 'POST',
    )
    expect(hasCreateCall).toBe(false)
  })

  it('连续点击新建会话且当前会话仍为空时复用，不产生第二个占位条目', async () => {
    const user = userEvent.setup()
    render(<App />)

    await waitFor(() => expect(screen.getByRole('button', { name: '新建会话' })).toBeInTheDocument())
    await user.click(screen.getByRole('button', { name: '新建会话' }))
    await screen.findByRole('button', { name: '新会话' })
    const firstThreadId = latestHttpAgentCall.threadId

    await user.click(screen.getByRole('button', { name: '新建会话' }))

    expect(screen.getAllByRole('button', { name: '新会话' })).toHaveLength(1)
    expect(latestHttpAgentCall.threadId).toBe(firstThreadId)
  })

  it('S2: 发出第一条消息后占位条目标题立即变为首条消息前 20 字，并显示运行中指示', async () => {
    const user = userEvent.setup()
    const { rerender } = render(<App />)

    await waitFor(() => expect(screen.getByRole('button', { name: '新建会话' })).toBeInTheDocument())
    await user.click(screen.getByRole('button', { name: '新建会话' }))
    await screen.findByRole('button', { name: '新会话' })

    const firstMessage = '你好，请自我介绍，顺便说说你能做什么菜'
    mockAgentState.messages = [{ id: 'm-user-1', role: 'user', content: firstMessage }]
    mockAgentState.isRunning = true
    rerender(<App />)

    await waitFor(() =>
      expect(screen.getByRole('button', { name: firstMessage.slice(0, 20) })).toBeInTheDocument(),
    )
    expect(screen.queryByRole('button', { name: '新会话' })).not.toBeInTheDocument()
    expect(screen.getByTestId('thread-running-indicator')).toBeInTheDocument()
  })

  it('S3: run 完成后触发 refetch，占位条目与服务器真实条目收敛为同一条', async () => {
    const user = userEvent.setup()
    const { rerender } = render(<App />)

    await waitFor(() => expect(screen.getByRole('button', { name: '新建会话' })).toBeInTheDocument())
    await user.click(screen.getByRole('button', { name: '新建会话' }))
    await screen.findByRole('button', { name: '新会话' })
    const pendingThreadId = String(latestHttpAgentCall.threadId)

    mockAgentState.messages = [{ id: 'm-user-1', role: 'user', content: '你好，请自我介绍' }]
    mockAgentState.isRunning = true
    rerender(<App />)
    await waitFor(() => expect(screen.getByTestId('thread-running-indicator')).toBeInTheDocument())

    // 服务端已落库该线程（ensure_thread），refetch 将返回真实条目
    serverThreads = [
      {
        thread_id: pendingThreadId,
        agent_id: 'default',
        title: '你好，请自我介绍',
        last_message_preview: '我是 DeepAgents 助手',
        created_at: '2026-08-22T10:00:00Z',
        updated_at: '2026-08-22T10:01:00Z',
      },
      historyThread,
    ]
    mockAgentState.isRunning = false
    rerender(<App />)

    // 收敛后：同 threadId 只剩一条（服务器版本），无占位残留，运行中指示消失
    await waitFor(() => expect(screen.getByText('我是 DeepAgents 助手')).toBeInTheDocument())
    const options = screen.getAllByRole('option')
    expect(options.filter((el) => el.textContent?.includes('你好，请自我介绍'))).toHaveLength(1)
    expect(screen.queryByTestId('thread-running-indicator')).not.toBeInTheDocument()
    // 高亮仍指向当前 threadId
    const active = options.find((el) => el.getAttribute('aria-selected') === 'true')
    expect(active?.textContent).toContain('你好，请自我介绍')
  })

  it('S5: 空会话占位在切换到历史会话后消失，全程不落库', async () => {
    const user = userEvent.setup()
    render(<App />)

    await waitFor(() => expect(screen.getByText('历史会话')).toBeInTheDocument())
    await user.click(screen.getByRole('button', { name: '新建会话' }))
    await screen.findByRole('button', { name: '新会话' })

    await user.click(screen.getByRole('button', { name: '历史会话' }))

    await waitFor(() => expect(screen.queryByRole('button', { name: '新会话' })).not.toBeInTheDocument())
    const hasCreateCall = mockFetch.mock.calls.some(
      ([url, init]) => String(url) === '/api/threads/' && (init as RequestInit | undefined)?.method === 'POST',
    )
    expect(hasCreateCall).toBe(false)
  })

  it('S7: 切换 Agent 后占位条目清除，不跨 Agent 泄漏', async () => {
    const user = userEvent.setup()
    render(<App />)

    await waitFor(() => expect(screen.getByRole('button', { name: '新建会话' })).toBeInTheDocument())
    await user.click(screen.getByRole('button', { name: '新建会话' }))
    await screen.findByRole('button', { name: '新会话' })

    await user.click(screen.getByRole('button', { name: '选择 Agent' }))
    await user.click(await screen.findByRole('option', { name: 'code_reviewer' }))

    await waitFor(() => expect(screen.queryByRole('button', { name: '新会话' })).not.toBeInTheDocument())
  })
})

// ---------------------------------------------------------------------------
// 认证（R1-2）：token 输入页 + 401 回到输入页
// ---------------------------------------------------------------------------

describe('App auth', () => {
  beforeEach(() => {
    localStorage.removeItem('scaffold_token')
    vi.stubGlobal('fetch', mockFetch)
    mockFetch.mockReset()
    mockFetch.mockImplementation(async () => ({ ok: true, status: 200, json: async () => ({ agents: [], threads: [] }) }))
  })

  afterEach(() => {
    localStorage.removeItem('scaffold_token')
  })

  it('A1: 无本地 token 时显示输入界面而非聊天界面', async () => {
    render(<App />)
    expect(screen.getByText('访问令牌')).toBeInTheDocument()
    expect(screen.queryByTestId('copilot-chat')).not.toBeInTheDocument()
  })

  it('A2: 输入 token 后进入聊天界面，且会话列表请求带 X-API-Key', async () => {
    const user = userEvent.setup()
    render(<App />)
    await user.type(screen.getByPlaceholderText('粘贴 Token'), 'tok-abc')
    await user.click(screen.getByRole('button', { name: '进入' }))

    await waitFor(() => expect(screen.getByTestId('copilot-kit')).toBeInTheDocument())
    expect(localStorage.getItem('scaffold_token')).toBe('tok-abc')
    const agentsCalls = mockFetch.mock.calls.filter(([url]) => String(url) === '/api/agents/')
    const agentsCall = agentsCalls[agentsCalls.length - 1]
    expect(agentsCall).toBeTruthy()
    expect(new Headers((agentsCall[1] as RequestInit | undefined)?.headers).get('X-API-Key')).toBe('tok-abc')
  })

  it('A3: 任意请求收到 401 后清空 token 并回到输入界面', async () => {
    localStorage.setItem('scaffold_token', 'stale-token')

    // 先装 401 响应再渲染：挂载后的首个请求（会话列表）即 401 → 回输入页
    mockFetch.mockImplementation(async (url: string) => {
      if (String(url) === '/api/agents/') {
        return { ok: true, status: 200, json: async () => ({ agents: [{ name: 'default' }] }) }
      }
      return { ok: false, status: 401, json: async () => ({ detail: 'unauthorized' }) }
    })
    render(<App />)

    await waitFor(() => expect(screen.getByText('访问令牌')).toBeInTheDocument())
    expect(localStorage.getItem('scaffold_token')).toBeNull()
  })
})
