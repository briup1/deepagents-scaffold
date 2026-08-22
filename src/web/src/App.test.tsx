import { cleanup, render, screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import App from './App'

let latestCopilotKitProps: Record<string, unknown> = {}
let latestCopilotChatProps: Record<string, unknown> = {}
const mockSetMessages = vi.fn()

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
    agent: { setMessages: mockSetMessages, runAgent: vi.fn() },
    isReady: true,
  }),
  useRenderTool: vi.fn(),
}))

vi.mock('@ag-ui/client', () => ({
  HttpAgent: vi.fn(),
}))

const mockFetch = vi.fn()

describe('App', () => {
  beforeEach(() => {
    vi.stubGlobal('fetch', mockFetch)
    latestCopilotKitProps = {}
    latestCopilotChatProps = {}
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
          json: async () => ({
            threads: [
              {
                thread_id: 't-history',
                agent_id: 'default',
                title: '历史会话',
                last_message_preview: '历史消息预览',
                created_at: '2026-08-18T10:00:00Z',
                updated_at: '2026-08-18T10:05:00Z',
              },
            ],
            total: 1,
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
    expect(latestCopilotKitProps.threadId).toMatch(/^thread-/)
    expect(Object.keys((latestCopilotKitProps.agents__unsafe_dev_only as Record<string, unknown>) ?? {})).toEqual(
      expect.arrayContaining(['default', 'coding', 'code_reviewer']),
    )
  })

  it('切换 Agent 时重置 threadId 以隔离不同 Agent 的历史消息', async () => {
    const user = userEvent.setup()
    render(<App />)

    const trigger = await screen.findByRole('button', { name: '选择 Agent' })
    const firstThreadId = latestCopilotKitProps.threadId as string

    await user.click(trigger)
    const option = await screen.findByRole('option', { name: 'code_reviewer' })
    await user.click(option)

    await waitFor(() => expect(latestCopilotChatProps.agentId).toBe('code_reviewer'))
    await waitFor(() => expect(latestCopilotKitProps.threadId).not.toBe(firstThreadId))
  })

  it('点击新建会话重置 threadId', async () => {
    const user = userEvent.setup()
    render(<App />)

    await waitFor(() => expect(screen.getByRole('button', { name: '新建会话' })).toBeInTheDocument())

    const firstThreadId = latestCopilotKitProps.threadId as string
    await user.click(screen.getByRole('button', { name: '新建会话' }))

    await waitFor(() => expect(latestCopilotKitProps.threadId).not.toBe(firstThreadId))
  })

  it('点击历史会话后更新 threadId 并注入历史消息', async () => {
    const user = userEvent.setup()
    render(<App />)

    await waitFor(() => expect(screen.getByText('历史会话')).toBeInTheDocument())
    const historyThread = await screen.findByRole('button', { name: '历史会话' })
    await user.click(historyThread)

    await waitFor(() => expect(latestCopilotKitProps.threadId).toBe('t-history'))
    await waitFor(() =>
      expect(mockSetMessages).toHaveBeenCalledWith(expect.arrayContaining([
        expect.objectContaining({ id: 'm1', role: 'user', content: 'hello' }),
      ])),
    )
  })
})
