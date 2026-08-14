import { render, screen } from '@testing-library/react'
import { describe, expect, it, vi } from 'vitest'
import { catalog, componentSchema } from '../index'

describe('catalog components', () => {
  describe('button_group', () => {
    it('使用 buttons 字段渲染按钮组', () => {
      render(
        <>
          {catalog.render(
            {
              type: 'button_group',
              props: {
                title: '操作',
                buttons: [
                  { id: 'view_details', label: '查看详细报告' },
                  { id: 'generate_patch', label: '生成修改补丁' },
                  { id: 'skip', label: '跳过修改' },
                ],
              },
            },
            vi.fn(),
          )}
        </>,
      )

      expect(screen.getByText('操作')).toBeInTheDocument()
      expect(screen.getByRole('button', { name: '查看详细报告' })).toBeInTheDocument()
      expect(screen.getByRole('button', { name: '生成修改补丁' })).toBeInTheDocument()
      expect(screen.getByRole('button', { name: '跳过修改' })).toBeInTheDocument()
    })

    it('兼容 LLM 返回的 options 字段', () => {
      render(
        <>
          {catalog.render(
            {
              type: 'button_group',
              props: {
                title: '操作',
                options: [
                  { id: 'view_details', label: '查看详细报告' },
                  { id: 'generate_patch', label: '生成修改补丁' },
                  { id: 'skip', label: '跳过修改' },
                ],
              },
            },
            vi.fn(),
          )}
        </>,
      )

      expect(screen.getByText('操作')).toBeInTheDocument()
      expect(screen.getByRole('button', { name: '查看详细报告' })).toBeInTheDocument()
      expect(screen.getByRole('button', { name: '生成修改补丁' })).toBeInTheDocument()
      expect(screen.getByRole('button', { name: '跳过修改' })).toBeInTheDocument()
    })

    it('点击按钮触发 button_click 动作', () => {
      const dispatch = vi.fn()
      render(
        <>
          {catalog.render(
            {
              type: 'button_group',
              props: {
                buttons: [{ id: 'skip', label: '跳过修改' }],
              },
              surfaceId: 'surface-1',
            },
            dispatch,
          )}
        </>,
      )

      screen.getByRole('button', { name: '跳过修改' }).click()
      expect(dispatch).toHaveBeenCalledWith({
        type: 'button_click',
        surfaceId: 'surface-1',
        id: 'skip',
      })
    })
  })

  it('导出的 componentSchema 仍描述 buttons 为必填字段', () => {
    expect(componentSchema.button_group).toMatchObject({
      description: expect.any(String),
      type: 'object',
      properties: {
        title: { type: 'string' },
        buttons: {
          type: 'array',
          items: {
            type: 'object',
            properties: {
              id: { type: 'string' },
              label: { type: 'string' },
            },
          },
        },
      },
      required: ['buttons'],
    })
  })
})
