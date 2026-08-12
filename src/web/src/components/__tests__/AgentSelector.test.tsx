import { render, screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { describe, expect, it, vi } from 'vitest'
import { AgentSelector } from '../AgentSelector'

const mockFetch = vi.fn()
vi.stubGlobal('fetch', mockFetch)

describe('AgentSelector', () => {
  it('loads and selects agents', async () => {
    mockFetch.mockResolvedValueOnce({
      ok: true,
      json: async () => ({ agents: [{ name: 'default' }, { name: 'code_reviewer' }] }),
    })

    const onChange = vi.fn()
    render(<AgentSelector value="default" onChange={onChange} />)

    await waitFor(() => expect(screen.getByText('code_reviewer')).toBeInTheDocument())

    await userEvent.selectOptions(screen.getByRole('combobox'), 'code_reviewer')
    expect(onChange).toHaveBeenCalledWith('code_reviewer')
  })
})
