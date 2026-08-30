import { act, renderHook } from '@testing-library/react'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import { useGenerativeUIAction } from '../useGenerativeUIAction'

const addMessage = vi.fn()
const runAgent = vi.fn()

vi.mock('@copilotkit/react-core/v2', () => ({
  useAgent: () => ({ agent: { addMessage, runAgent } }),
}))

describe('useGenerativeUIAction', () => {
  beforeEach(() => {
    addMessage.mockReset()
    runAgent.mockReset()
  })

  it('handles runAgent rejection without an unhandled promise', async () => {
    const error = new Error('run failed')
    const consoleError = vi.spyOn(console, 'error').mockImplementation(() => undefined)
    runAgent.mockRejectedValue(error)
    const { result } = renderHook(() => useGenerativeUIAction('default'))

    await act(async () => {
      await result.current({ type: 'button_click' })
    })

    expect(consoleError).toHaveBeenCalledWith('[useGenerativeUIAction] agent 执行失败', error)
    consoleError.mockRestore()
  })
})
