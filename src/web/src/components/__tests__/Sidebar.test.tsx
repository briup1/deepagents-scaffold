import { render, screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { describe, expect, it, vi } from 'vitest'
import type { ThreadSummary } from '../../api/threads'
import { Sidebar } from '../Sidebar'

describe('Sidebar', () => {
  const agents = [
    { name: 'default', type: 'agent' },
    { name: 'code_reviewer', type: 'agent' },
  ]

  const threads: ThreadSummary[] = [
    {
      thread_id: 't1',
      agent_id: 'default',
      title: '测试会话',
      last_message_preview: '最后一条消息',
      created_at: '2026-08-18T10:00:00Z',
      updated_at: '2026-08-18T10:05:00Z',
    },
  ]

  function renderSidebar(overrides: Partial<Parameters<typeof Sidebar>[0]> = {}) {
    const props: Parameters<typeof Sidebar>[0] = {
      agents,
      currentAgentId: 'default',
      threadId: 'thread-test-123',
      threads,
      threadsLoading: false,
      threadsError: null,
      onAgentChange: vi.fn(),
      onNewChat: vi.fn(),
      onSelectThread: vi.fn(),
      ...overrides,
    }
    render(<Sidebar {...props} />)
    return props
  }

  it('renders brand, new chat button, and agent selector', () => {
    renderSidebar()

    expect(screen.getByText('DeepAgents')).toBeInTheDocument()
    expect(screen.getByRole('button', { name: '新建会话' })).toBeInTheDocument()
    expect(screen.getByRole('button', { name: '选择 Agent' })).toBeInTheDocument()
    expect(screen.getByText('当前会话')).toBeInTheDocument()
  })

  it('calls onNewChat when new chat button is clicked', async () => {
    const { onNewChat } = renderSidebar()

    await userEvent.click(screen.getByRole('button', { name: '新建会话' }))
    expect(onNewChat).toHaveBeenCalledTimes(1)
  })

  it('calls onAgentChange when a different agent is selected', async () => {
    const { onAgentChange } = renderSidebar()

    await userEvent.click(screen.getByRole('button', { name: '选择 Agent' }))
    await userEvent.click(screen.getByRole('option', { name: 'code_reviewer' }))

    expect(onAgentChange).toHaveBeenCalledWith('code_reviewer')
  })

  it('渲染传入的历史会话列表', () => {
    renderSidebar()
    expect(screen.getByText('测试会话')).toBeInTheDocument()
  })

  it('加载中显示提示，不渲染列表', () => {
    renderSidebar({ threadsLoading: true })
    expect(screen.getByText('加载中...')).toBeInTheDocument()
    expect(screen.queryByText('测试会话')).not.toBeInTheDocument()
  })

  it('加载失败显示错误信息', () => {
    renderSidebar({ threadsError: 'HTTP 500' })
    expect(screen.getByText('HTTP 500')).toBeInTheDocument()
  })

  it('当前 threadId 对应条目高亮（aria-selected），其余不高亮', () => {
    renderSidebar({ threadId: 't1' })

    const options = screen.getAllByRole('option')
    const active = options.find((el) => el.getAttribute('aria-selected') === 'true')
    expect(active).toBeDefined()
    expect(active?.textContent).toContain('测试会话')
  })

  it('为 runningThreadId 对应条目渲染运行中指示', () => {
    renderSidebar({ runningThreadId: 't1' })
    expect(screen.getByTestId('thread-running-indicator')).toBeInTheDocument()
  })

  it('calls onSelectThread when a history thread is clicked', async () => {
    const { onSelectThread } = renderSidebar()

    await userEvent.click(screen.getByRole('button', { name: /测试会话/ }))
    expect(onSelectThread).toHaveBeenCalledWith('t1', 'default')
  })
})
