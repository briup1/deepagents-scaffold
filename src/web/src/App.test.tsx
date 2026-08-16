import { cleanup, render, screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import App from './App'

let latestCopilotKitProps: Record<string, unknown> = {}
let latestCopilotChatProps: Record<string, unknown> = {}

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
    agent: { addMessage: vi.fn(), runAgent: vi.fn() },
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
    mockFetch.mockResolvedValue({
      ok: true,
      json: async () => ({
        agents: [{ name: 'default' }, { name: 'coding' }, { name: 'code_reviewer' }],
      }),
    })
  })

  afterEach(() => {
    cleanup()
    vi.unstubAllGlobals()
    vi.clearAllMocks()
  })

  it('加载 Agent 列表并渲染选择器与新建会话按钮', async () => {
    render(<App />)

    await waitFor(() => expect(screen.getByRole('combobox')).toBeInTheDocument())
    expect(screen.getByRole('button', { name: '新建会话' })).toBeInTheDocument()
    expect(screen.getByTestId('copilot-kit')).toBeInTheDocument()
    expect(latestCopilotKitProps.threadId).toMatch(/^thread-/)
    expect(Object.keys((latestCopilotKitProps.agents__unsafe_dev_only as Record<string, unknown>) ?? {})).toEqual(
      expect.arrayContaining(['default', 'coding', 'code_reviewer']),
    )
  })

  it('切换 Agent 时更新 agentId 和 agentUrl', async () => {
    const user = userEvent.setup()
    render(<App />)

    await waitFor(() => expect(screen.getByRole('combobox')).toBeInTheDocument())
    await user.selectOptions(screen.getByRole('combobox'), 'code_reviewer')

    await waitFor(() => expect(latestCopilotChatProps.agentId).toBe('code_reviewer'))
  })

  it('点击新建会话重置 threadId', async () => {
    const user = userEvent.setup()
    render(<App />)

    await waitFor(() => expect(screen.getByRole('button', { name: '新建会话' })).toBeInTheDocument())

    const firstThreadId = latestCopilotKitProps.threadId as string
    await user.click(screen.getByRole('button', { name: '新建会话' }))

    await waitFor(() => expect(latestCopilotKitProps.threadId).not.toBe(firstThreadId))
  })
})
