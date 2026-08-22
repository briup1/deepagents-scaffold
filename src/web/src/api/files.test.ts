import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest'
import { uploadFile, listFiles } from './files'

describe('files API', () => {
  let mockFetch: ReturnType<typeof vi.fn>

  beforeEach(() => {
    mockFetch = vi.fn()
    vi.stubGlobal('fetch', mockFetch)
  })

  afterEach(() => {
    vi.unstubAllGlobals()
  })

  it('uploadFile sends multipart form data and parses response', async () => {
    const uploaded = {
      artifact_id: 'art-123',
      thread_id: 't-123',
      artifact_type: 'upload',
      original_name: 'quote.xlsx',
      stored_path: 't-123/uploads/art-123-quote.xlsx',
      mime_type: 'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet',
      size_bytes: 1024,
      created_at: '2026-08-22T10:00:00Z',
    }

    mockFetch.mockResolvedValueOnce({
      ok: true,
      json: async () => uploaded,
    })

    const file = new File(['fake'], 'quote.xlsx', {
      type: 'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet',
    })

    const result = await uploadFile('t-123', file)

    expect(result).toEqual(uploaded)
    expect(mockFetch).toHaveBeenCalledWith(
      '/api/files/upload',
      expect.objectContaining({
        method: 'POST',
        body: expect.any(FormData),
      }),
    )
  })

  it('uploadFile throws on non-ok response', async () => {
    mockFetch.mockResolvedValueOnce({
      ok: false,
      status: 415,
      text: async () => '仅支持 Excel 文件',
    })

    const file = new File(['fake'], 'malicious.py', { type: 'text/x-python' })

    await expect(uploadFile('t-123', file)).rejects.toThrow('上传失败 (415)')
  })

  it('listFiles builds URL with thread_id and optional artifact_type', async () => {
    mockFetch.mockResolvedValueOnce({
      ok: true,
      json: async () => ({
        thread_id: 't-123',
        artifacts: [],
        total: 0,
      }),
    })

    await listFiles('t-123', 'upload')

    expect(mockFetch).toHaveBeenCalledWith(
      '/api/files/?thread_id=t-123&artifact_type=upload',
    )
  })
})
