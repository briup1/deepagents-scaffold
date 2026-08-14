import { render, screen } from '@testing-library/react'
import { describe, expect, it, vi } from 'vitest'
import { z } from 'zod'
import { createCatalog } from '../createCatalog'

describe('createCatalog', () => {
  const catalog = createCatalog(
    {
      test: {
        description: '测试组件',
        schema: z.object({ text: z.string() }),
      },
    },
    {
      test: ({ props, dispatch }) => (
        <button type="button" onClick={() => dispatch({ type: 'test_action' })}>
          {props.text}
        </button>
      ),
    },
  )

  it('渲染已注册组件', () => {
    render(<>{catalog.render({ type: 'test', props: { text: 'hello' } }, vi.fn())}</>)
    expect(screen.getByRole('button', { name: 'hello' })).toBeInTheDocument()
  })

  it('dispatch 回调可触发', async () => {
    const dispatch = vi.fn()
    render(<>{catalog.render({ type: 'test', props: { text: 'click me' } }, dispatch)}</>)
    screen.getByRole('button', { name: 'click me' }).click()
    expect(dispatch).toHaveBeenCalledWith({ type: 'test_action' })
  })

  it('未知类型渲染降级组件', () => {
    const warnSpy = vi.spyOn(console, 'warn').mockImplementation(() => {})
    render(<>{catalog.render({ type: 'unknown' }, vi.fn())}</>)
    expect(screen.getByText('无法渲染 Generative UI')).toBeInTheDocument()
    warnSpy.mockRestore()
  })

  it('props 校验失败渲染降级组件', () => {
    const errorSpy = vi.spyOn(console, 'error').mockImplementation(() => {})
    render(<>{catalog.render({ type: 'test', props: { text: 123 } }, vi.fn())}</>)
    expect(screen.getByText('无法渲染 Generative UI')).toBeInTheDocument()
    errorSpy.mockRestore()
  })

  it('extractSchemas 返回 JSON Schema 描述', () => {
    expect(catalog.schema.test).toMatchObject({
      description: '测试组件',
      type: 'object',
      properties: { text: { type: 'string' } },
      required: ['text'],
    })
  })
})
