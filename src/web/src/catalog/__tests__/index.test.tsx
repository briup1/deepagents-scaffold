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

  describe('chart', () => {
    it('缺少 kind 时默认渲染为柱状图，避免历史消息校验失败', () => {
      render(
        <>
          {catalog.render(
            {
              type: 'chart',
              props: {
                title: '各起运港报价条数',
                data: [
                  { label: '上海 SHANGHAI', value: 1 },
                  { label: '盐田 YANTIAN', value: 1 },
                  { label: '宁波 NINGBO', value: 1 },
                ],
              },
            },
            vi.fn(),
          )}
        </>,
      )

      expect(screen.getByText('各起运港报价条数')).toBeInTheDocument()
      expect(screen.getByRole('img', { name: '各起运港报价条数' })).toBeInTheDocument()
      expect(screen.queryByText('无法渲染 Generative UI')).not.toBeInTheDocument()
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
