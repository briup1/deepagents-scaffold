import { afterEach, describe, expect, it, vi } from 'vitest'
import { apiFetch, apiFetchJson, clearToken, getToken, onUnauthorized, setToken } from './auth'

const mockFetch = vi.fn()
vi.stubGlobal('fetch', mockFetch)

afterEach(() => {
  clearToken()
  vi.clearAllMocks()
})

describe('token storage', () => {
  it('setToken stores trimmed value, getToken reads back', () => {
    setToken('  abc-123  ')
    expect(getToken()).toBe('abc-123')
  })

  it('clearToken removes the stored token', () => {
    setToken('abc')
    clearToken()
    expect(getToken()).toBeNull()
  })
})

describe('apiFetch header injection', () => {
  it('passes through without token (exact original call signature)', async () => {
    mockFetch.mockResolvedValueOnce({ status: 200, ok: true })
    await apiFetch('/api/threads/')
    expect(mockFetch).toHaveBeenCalledWith('/api/threads/')
  })

  it('injects X-API-Key when token present', async () => {
    setToken('tok-1')
    mockFetch.mockResolvedValueOnce({ status: 200, ok: true })
    await apiFetch('/api/threads/')
    const [url, init] = mockFetch.mock.calls[0]
    expect(url).toBe('/api/threads/')
    expect(new Headers(init?.headers).get('X-API-Key')).toBe('tok-1')
  })

  it('merges with existing init headers without overwriting them', async () => {
    setToken('tok-1')
    mockFetch.mockResolvedValueOnce({ status: 200, ok: true })
    await apiFetch('/api/threads/', { method: 'POST', headers: { 'Content-Type': 'application/json' } })
    const [, init] = mockFetch.mock.calls[0]
    const headers = new Headers(init?.headers)
    expect(headers.get('Content-Type')).toBe('application/json')
    expect(headers.get('X-API-Key')).toBe('tok-1')
  })
})

describe('401 handling', () => {
  it('clears token and notifies subscribers on 401', async () => {
    setToken('tok-1')
    const listener = vi.fn()
    const unsubscribe = onUnauthorized(listener)

    mockFetch.mockResolvedValueOnce({ status: 401, ok: false })
    const res = await apiFetch('/api/threads/')
    expect(res.status).toBe(401)
    expect(getToken()).toBeNull()
    expect(listener).toHaveBeenCalledTimes(1)

    unsubscribe()
    mockFetch.mockResolvedValueOnce({ status: 401, ok: false })
    await apiFetch('/api/threads/')
    expect(listener).toHaveBeenCalledTimes(1)
  })

  it('does not clear token on non-401 errors', async () => {
    setToken('tok-1')
    mockFetch.mockResolvedValueOnce({ status: 500, ok: false })
    await apiFetch('/api/threads/')
    expect(getToken()).toBe('tok-1')
  })
})

describe('apiFetchJson error handling (merged from fetchJson)', () => {
  it('throws 网络请求失败 on network error', async () => {
    mockFetch.mockRejectedValueOnce(new TypeError('fetch failed'))
    await expect(apiFetchJson('/api/threads/')).rejects.toThrow('网络请求失败')
  })

  it('throws HTTP status error with detail', async () => {
    mockFetch.mockResolvedValueOnce({ status: 403, ok: false, text: async () => 'forbidden' })
    await expect(apiFetchJson('/api/threads/', undefined, '获取失败')).rejects.toThrow('获取失败 (403): forbidden')
  })

  it('throws HTTP status without prefix', async () => {
    mockFetch.mockResolvedValueOnce({ status: 500, ok: false, text: async () => '' })
    await expect(apiFetchJson('/api/threads/')).rejects.toThrow('HTTP 500')
  })

  it('throws 服务器返回了无效 JSON', async () => {
    mockFetch.mockResolvedValueOnce({ status: 200, ok: true, json: async () => { throw new SyntaxError('bad') } })
    await expect(apiFetchJson('/api/threads/')).rejects.toThrow('服务器返回了无效 JSON')
  })

  it('returns parsed JSON on success', async () => {
    mockFetch.mockResolvedValueOnce({ status: 200, ok: true, json: async () => ({ threads: [] }) })
    await expect(apiFetchJson<{ threads: unknown[] }>('/api/threads/')).resolves.toEqual({ threads: [] })
  })

  it('still notifies unauthorized listeners on 401 via apiFetch', async () => {
    setToken('tok-1')
    const listener = vi.fn()
    onUnauthorized(listener)
    mockFetch.mockResolvedValueOnce({ status: 401, ok: false, text: async () => '' })
    await expect(apiFetchJson('/api/threads/')).rejects.toThrow('HTTP 401')
    expect(getToken()).toBeNull()
    expect(listener).toHaveBeenCalledTimes(1)
  })
})
