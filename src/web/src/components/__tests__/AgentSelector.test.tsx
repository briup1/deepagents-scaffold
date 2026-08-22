import { render, screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { afterEach, describe, expect, it, vi } from 'vitest'
import { AgentSelector } from '../AgentSelector'

const mockFetch = vi.fn()
vi.stubGlobal('fetch', mockFetch)

describe('AgentSelector', () => {
  afterEach(() => {
    vi.unstubAllGlobals()
    vi.clearAllMocks()
  })

  it('loads and selects agents via custom dropdown', async () => {
    mockFetch.mockResolvedValueOnce({
      ok: true,
      json: async () => ({ agents: [{ name: 'default' }, { name: 'code_reviewer' }] }),
    })

    const onChange = vi.fn()
    render(<AgentSelector value="default" onChange={onChange} />)

    // 等待下拉按钮渲染完成
    const trigger = await screen.findByRole('button', { name: '选择 Agent' })
    expect(trigger).toHaveTextContent('default')

    // 打开下拉面板
    await userEvent.click(trigger)
    const option = await screen.findByRole('option', { name: 'code_reviewer' })
    expect(option).toBeInTheDocument()

    // 选择另一个 Agent
    await userEvent.click(option)
    expect(onChange).toHaveBeenCalledWith('code_reviewer')
  })
})
