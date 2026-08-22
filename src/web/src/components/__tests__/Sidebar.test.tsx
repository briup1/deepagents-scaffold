import { render, screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { Sidebar } from '../Sidebar'

describe('Sidebar', () => {
  const agents = [
    { name: 'default', type: 'agent' },
    { name: 'code_reviewer', type: 'agent' },
  ]

  const mockFetch = vi.fn()

  beforeEach(() => {
    vi.stubGlobal('fetch', mockFetch)
    mockFetch.mockImplementation((url: string) => {
      if (url.startsWith('/api/threads')) {
        return Promise.resolve({
          ok: true,
          json: async () => ({
            threads: [
              {
                thread_id: 't1',
                agent_id: 'default',
                title: '测试会话',
                last_message_preview: '最后一条消息',
                created_at: '2026-08-18T10:00:00Z',
                updated_at: '2026-08-18T10:05:00Z',
              },
            ],
            total: 1,
          }),
        })
      }
      return Promise.resolve({ ok: true, json: async () => ({}) })
    })
  })

  afterEach(() => {
    vi.unstubAllGlobals()
    vi.clearAllMocks()
  })

  it('renders brand, new chat button, and agent selector', () => {
    render(
      <Sidebar
        agents={agents}
        currentAgentId="default"
        threadId="thread-test-123"
        onAgentChange={vi.fn()}
        onNewChat={vi.fn()}
        onSelectThread={(_id, _agent) => {}}
      />
    )

    expect(screen.getByText('DeepAgents')).toBeInTheDocument()
    expect(screen.getByRole('button', { name: '新建会话' })).toBeInTheDocument()
    expect(screen.getByRole('button', { name: '选择 Agent' })).toBeInTheDocument()
    expect(screen.getByText('当前会话')).toBeInTheDocument()
  })

  it('calls onNewChat when new chat button is clicked', async () => {
    const onNewChat = vi.fn()
    render(
      <Sidebar
        agents={agents}
        currentAgentId="default"
        threadId="thread-test-123"
        onAgentChange={vi.fn()}
        onNewChat={onNewChat}
        onSelectThread={(_id, _agent) => {}}
      />
    )

    await userEvent.click(screen.getByRole('button', { name: '新建会话' }))
    expect(onNewChat).toHaveBeenCalledTimes(1)
  })

  it('calls onAgentChange when a different agent is selected', async () => {
    const onAgentChange = vi.fn()
    render(
      <Sidebar
        agents={agents}
        currentAgentId="default"
        threadId="thread-test-123"
        onAgentChange={onAgentChange}
        onNewChat={vi.fn()}
        onSelectThread={(_id, _agent) => {}}
      />
    )

    await userEvent.click(screen.getByRole('button', { name: '选择 Agent' }))
    await userEvent.click(screen.getByRole('option', { name: 'code_reviewer' }))

    expect(onAgentChange).toHaveBeenCalledWith('code_reviewer')
  })

  it('loads and renders history threads for current agent', async () => {
    render(
      <Sidebar
        agents={agents}
        currentAgentId="default"
        threadId="thread-test-123"
        onAgentChange={vi.fn()}
        onNewChat={vi.fn()}
        onSelectThread={vi.fn()}
      />
    )

    await waitFor(() => expect(screen.getByText('测试会话')).toBeInTheDocument())
    expect(mockFetch).toHaveBeenCalledWith('/api/threads/?agent_id=default')
  })

  it('calls onSelectThread when a history thread is clicked', async () => {
    const onSelectThread = vi.fn()
    render(
      <Sidebar
        agents={agents}
        currentAgentId="default"
        threadId="thread-test-123"
        onAgentChange={vi.fn()}
        onNewChat={vi.fn()}
        onSelectThread={onSelectThread}
      />
    )

    await waitFor(() => expect(screen.getByText('测试会话')).toBeInTheDocument())
    await userEvent.click(screen.getByRole('button', { name: '测试会话' }))
    expect(onSelectThread).toHaveBeenCalledWith('t1', 'default')
  })
})
