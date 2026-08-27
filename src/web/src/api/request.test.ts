import { afterEach, describe, expect, it, vi } from 'vitest'
import { fetchJson } from './request'

describe('fetchJson', () => {
  afterEach(() => vi.unstubAllGlobals())

  it('normalizes network failures', async () => {
    vi.stubGlobal('fetch', vi.fn().mockRejectedValue(new TypeError('network down')))
    await expect(fetchJson('/api/test')).rejects.toThrow('网络请求失败')
  })

  it('normalizes invalid JSON responses', async () => {
    vi.stubGlobal('fetch', vi.fn().mockResolvedValue({
      ok: true,
      json: vi.fn().mockRejectedValue(new SyntaxError('invalid json')),
    }))
    await expect(fetchJson('/api/test')).rejects.toThrow('服务器返回了无效 JSON')
  })

  it('includes an error response body when a prefix is supplied', async () => {
    vi.stubGlobal('fetch', vi.fn().mockResolvedValue({
      ok: false,
      status: 415,
      text: vi.fn().mockResolvedValue('仅支持 Excel 文件'),
    }))
    await expect(fetchJson('/api/test', undefined, '上传失败')).rejects.toThrow(
      '上传失败 (415): 仅支持 Excel 文件',
    )
  })
})
