import { renderHook } from '@testing-library/react'
import { describe, expect, it, vi } from 'vitest'
import { parseEnvelope, useGenerativeUITool } from '../useGenerativeUITool'

vi.mock('@copilotkit/react-core/v2', () => ({
  useRenderTool: vi.fn(),
}))

describe('parseEnvelope', () => {
  it('returns undefined for non-object result', () => {
    expect(parseEnvelope(null)).toBeUndefined()
    expect(parseEnvelope('string')).toBeUndefined()
  })

  it('extracts envelope from result.generative_ui', () => {
    expect(
      parseEnvelope({
        generative_ui: { type: 'metric_card', props: { value: 42 }, surfaceId: 's1' },
      }),
    ).toEqual({ type: 'metric_card', props: { value: 42 }, surfaceId: 's1' })
  })

  it('accepts envelope directly', () => {
    expect(parseEnvelope({ type: 'markdown_card', props: { content: 'hi' } })).toEqual({
      type: 'markdown_card',
      props: { content: 'hi' },
    })
  })

  it('returns undefined when type is missing', () => {
    expect(parseEnvelope({ props: {} })).toBeUndefined()
  })
})

describe('useGenerativeUITool', () => {
  it('registers render_ui tool', async () => {
    const { useRenderTool } = await import('@copilotkit/react-core/v2')
    renderHook(() => useGenerativeUITool())
    expect(useRenderTool).toHaveBeenCalledWith(
      expect.objectContaining({ name: 'render_ui' }),
      [],
    )
  })
})
