import { describe, expect, it, vi } from 'vitest'
import { randomUUID } from '../uuid'

describe('randomUUID', () => {
  it('返回标准 UUID v4 格式', () => {
    const id = randomUUID()
    expect(id).toMatch(/^[0-9a-f]{8}-[0-9a-f]{4}-4[0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}$/)
  })

  it('当 crypto.randomUUID 不可用时仍能生成 UUID', () => {
    const originalRandomUUID = crypto.randomUUID
    vi.stubGlobal('crypto', {
      ...crypto,
      randomUUID: undefined,
      getRandomValues: (arr: Uint8Array) => {
        for (let i = 0; i < arr.length; i++) arr[i] = i
        return arr
      },
    })

    const id = randomUUID()
    expect(id).toMatch(/^[0-9a-f]{8}-[0-9a-f]{4}-4[0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}$/)

    vi.stubGlobal('crypto', { ...crypto, randomUUID: originalRandomUUID })
  })
})
