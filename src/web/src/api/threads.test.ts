import { describe, expect, it, vi } from 'vitest'
import { createThread, getThreadMessages, listThreads } from './threads'

const mockFetch = vi.fn()
vi.stubGlobal('fetch', mockFetch)

describe('threads api', () => {
  it('listThreads fetches with agent_id', async () => {
    mockFetch.mockResolvedValueOnce({
      ok: true,
      json: async () => ({ threads: [], total: 0 }),
    })
    await listThreads('default')
    expect(mockFetch).toHaveBeenCalledWith('/api/threads/?agent_id=default')
  })

  it('getThreadMessages encodes thread id', async () => {
    mockFetch.mockResolvedValueOnce({
      ok: true,
      json: async () => ({ thread_id: 't1', messages: [] }),
    })
    await getThreadMessages('t1')
    expect(mockFetch).toHaveBeenCalledWith('/api/threads/t1/messages')
  })

  it('createThread posts agent_id', async () => {
    mockFetch.mockResolvedValueOnce({
      ok: true,
      json: async () => ({ thread_id: 't2' }),
    })
    await createThread('default')
    expect(mockFetch).toHaveBeenCalledWith('/api/threads/', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ agent_id: 'default' }),
    })
  })

  it('throws on non-ok response', async () => {
    mockFetch.mockResolvedValueOnce({ ok: false, status: 500 })
    await expect(listThreads()).rejects.toThrow('HTTP 500')
  })
})
