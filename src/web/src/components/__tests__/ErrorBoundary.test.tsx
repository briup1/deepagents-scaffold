import { render, screen } from '@testing-library/react'
import { describe, expect, it, vi } from 'vitest'
import { ErrorBoundary } from '../ErrorBoundary'

function Throwing({ shouldThrow }: { shouldThrow: boolean }) {
  if (shouldThrow) {
    throw new Error('测试错误')
  }
  return <div>正常内容</div>
}

describe('ErrorBoundary', () => {
  it('正常渲染子组件', () => {
    render(
      <ErrorBoundary>
        <Throwing shouldThrow={false} />
      </ErrorBoundary>,
    )

    expect(screen.getByText('正常内容')).toBeInTheDocument()
  })

  it('捕获子组件错误并显示 fallback UI', () => {
    const consoleError = vi.spyOn(console, 'error').mockImplementation(() => {})

    render(
      <ErrorBoundary>
        <Throwing shouldThrow={true} />
      </ErrorBoundary>,
    )

    expect(screen.getByText('出错了')).toBeInTheDocument()
    expect(screen.getByText('测试错误')).toBeInTheDocument()
    expect(screen.getByRole('button', { name: '刷新页面' })).toBeInTheDocument()

    consoleError.mockRestore()
  })
})
