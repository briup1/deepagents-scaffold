import { render, screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { describe, expect, it, vi } from 'vitest'
import { ThreadList } from '../ThreadList'

const threads = [
  {
    thread_id: 't1',
    agent_id: 'default',
    title: '测试会话',
    last_message_preview: '最后一条消息',
    created_at: '2026-08-18T10:00:00Z',
    updated_at: '2026-08-18T10:05:00Z',
  },
  {
    thread_id: 't2',
    agent_id: 'default',
    title: null,
    last_message_preview: '无标题会话预览',
    created_at: '2026-08-18T11:00:00Z',
    updated_at: '2026-08-18T11:05:00Z',
  },
]

describe('ThreadList', () => {
  it('renders empty state', () => {
    render(<ThreadList threads={[]} currentThreadId="" onSelectThread={(_id, _agent) => {}} />)
    expect(screen.getByText('暂无历史会话，开始一段新对话吧。')).toBeInTheDocument()
  })

  it('renders threads and handles selection', async () => {
    const onSelect = vi.fn()
    render(<ThreadList threads={threads} currentThreadId="t1" onSelectThread={onSelect} />)

    expect(screen.getByText('测试会话')).toBeInTheDocument()
    expect(screen.getByText('无标题会话预览')).toBeInTheDocument()
    await userEvent.click(screen.getByRole('button', { name: '无标题会话预览' }))
    expect(onSelect).toHaveBeenCalledWith('t2', 'default')
  })
})
