import { act, renderHook, waitFor } from '@testing-library/react'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import type { ThreadSummary } from '../../api/threads'
import { mergePendingThread, useThreads } from '../useThreads'

function makeThread(threadId: string, agentId = 'default'): ThreadSummary {
  return {
    thread_id: threadId,
    agent_id: agentId,
    title: `会话-${threadId}`,
    last_message_preview: null,
    created_at: '2026-08-18T10:00:00Z',
    updated_at: '2026-08-18T10:05:00Z',
  }
}

const mockFetch = vi.fn()

function mockThreadsResponse(threads: ThreadSummary[]) {
  mockFetch.mockResolvedValue({
    ok: true,
    json: async () => ({ threads, total: threads.length }),
  })
}

describe('useThreads', () => {
  beforeEach(() => {
    vi.stubGlobal('fetch', mockFetch)
    mockFetch.mockReset()
  })

  afterEach(() => {
    vi.unstubAllGlobals()
  })

  it('挂载后按 Agent 拉取会话列表', async () => {
    mockThreadsResponse([makeThread('t1')])
    const { result } = renderHook(() => useThreads('default', null))

    await waitFor(() => expect(result.current.loading).toBe(false))
    expect(mockFetch).toHaveBeenCalledWith('/api/threads/?agent_id=default')
    expect(result.current.threads.map((t) => t.thread_id)).toEqual(['t1'])
    expect(result.current.error).toBeNull()
  })

  it('agentId 为空时不发请求', async () => {
    const { result } = renderHook(() => useThreads('', null))

    await waitFor(() => expect(result.current.loading).toBe(false))
    expect(mockFetch).not.toHaveBeenCalled()
    expect(result.current.threads).toEqual([])
  })

  it('refetch 重新拉取并返回最新列表', async () => {
    mockThreadsResponse([makeThread('t1')])
    const { result } = renderHook(() => useThreads('default', null))
    await waitFor(() => expect(result.current.threads).toHaveLength(1))

    mockThreadsResponse([makeThread('t-new'), makeThread('t1')])
    let latest: ThreadSummary[] = []
    await act(async () => {
      latest = await result.current.refetch()
    })

    expect(latest.map((t) => t.thread_id)).toEqual(['t-new', 't1'])
    expect(result.current.threads.map((t) => t.thread_id)).toEqual(['t-new', 't1'])
  })

  it('refetch 期间保留旧数据，不闪回加载态', async () => {
    mockThreadsResponse([makeThread('t1')])
    const { result } = renderHook(() => useThreads('default', null))
    await waitFor(() => expect(result.current.loading).toBe(false))

    let resolveSecond: (value: unknown) => void = () => {}
    mockFetch.mockImplementation(
      () =>
        new Promise((resolve) => {
          resolveSecond = resolve
        }),
    )
    let refetchPromise: Promise<ThreadSummary[]> = Promise.resolve([])
    act(() => {
      refetchPromise = result.current.refetch()
    })

    // refetch 未完成时仍展示旧列表，且不进入 loading
    expect(result.current.loading).toBe(false)
    expect(result.current.threads.map((t) => t.thread_id)).toEqual(['t1'])

    resolveSecond({
      ok: true,
      json: async () => ({ threads: [makeThread('t1'), makeThread('t2')], total: 2 }),
    })
    await act(async () => {
      await refetchPromise
    })
    expect(result.current.threads).toHaveLength(2)
  })

  it('切换 Agent 后重新拉取，过期响应被丢弃', async () => {
    let resolveFirst: (value: unknown) => void = () => {}
    mockFetch.mockImplementation(
      () =>
        new Promise((resolve) => {
          resolveFirst = resolve
        }),
    )
    const { result, rerender } = renderHook(({ agentId }) => useThreads(agentId, null), {
      initialProps: { agentId: 'default' },
    })

    // 切到 coding，第二个请求先完成
    mockThreadsResponse([makeThread('t-coding', 'coding')])
    rerender({ agentId: 'coding' })
    await waitFor(() => expect(result.current.threads.map((t) => t.thread_id)).toEqual(['t-coding']))

    // 旧的 default 响应后到，应被丢弃
    resolveFirst({
      ok: true,
      json: async () => ({ threads: [makeThread('t-stale')], total: 1 }),
    })
    await waitFor(() => expect(result.current.loading).toBe(false))
    expect(result.current.threads.map((t) => t.thread_id)).toEqual(['t-coding'])
  })

  it('拉取失败时暴露错误信息', async () => {
    mockFetch.mockResolvedValue({ ok: false, status: 500 })
    const { result } = renderHook(() => useThreads('default', null))

    await waitFor(() => expect(result.current.loading).toBe(false))
    expect(result.current.error).toBe('HTTP 500')
  })
})

describe('mergePendingThread', () => {
  it('占位条目置顶于服务器列表之前', () => {
    const merged = mergePendingThread([makeThread('t1')], makeThread('t-pending'), 'default')
    expect(merged.map((t) => t.thread_id)).toEqual(['t-pending', 't1'])
  })

  it('服务器已返回同 threadId 条目时收敛去重，不重复出现', () => {
    const server = makeThread('t-pending')
    const merged = mergePendingThread([server, makeThread('t1')], makeThread('t-pending'), 'default')
    expect(merged.map((t) => t.thread_id)).toEqual(['t-pending', 't1'])
    // 收敛后使用服务器条目（标题来自后端）
    expect(merged[0].title).toBe('会话-t-pending')
  })

  it('其他 Agent 的占位条目不泄漏到当前列表', () => {
    const merged = mergePendingThread([makeThread('t1')], makeThread('t-pending', 'coding'), 'default')
    expect(merged.map((t) => t.thread_id)).toEqual(['t1'])
  })

  it('无占位条目时原样返回服务器列表', () => {
    const threads = [makeThread('t1')]
    expect(mergePendingThread(threads, null, 'default')).toBe(threads)
  })
})
