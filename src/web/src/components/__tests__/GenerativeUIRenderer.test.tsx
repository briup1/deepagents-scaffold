import { render, screen } from '@testing-library/react'
import { describe, expect, it, vi } from 'vitest'
import { GenerativeUIRenderer } from '../GenerativeUIRenderer'
import { GenerativeUIContext } from '../../catalog/GenerativeUIContext'

function Wrapper({ children }: { children: React.ReactNode }) {
  return (
    <GenerativeUIContext.Provider value={{ dispatch: vi.fn() }}>
      {children}
    </GenerativeUIContext.Provider>
  )
}

describe('GenerativeUIRenderer', () => {
  it('渲染 MarkdownCard', () => {
    render(
      <GenerativeUIRenderer
        envelope={{ type: 'markdown_card', props: { title: 'T', content: 'C' } }}
      />,
      { wrapper: Wrapper },
    )
    expect(screen.getByText('T')).toBeInTheDocument()
    expect(screen.getByText('C')).toBeInTheDocument()
  })

  it('渲染 DataTable', () => {
    render(
      <GenerativeUIRenderer
        envelope={{
          type: 'data_table',
          props: {
            title: 'Table',
            columns: [{ key: 'k', label: 'K' }],
            rows: [{ k: 'v' }],
          },
        }}
      />,
      { wrapper: Wrapper },
    )
    expect(screen.getByText('Table')).toBeInTheDocument()
    expect(screen.getByText('v')).toBeInTheDocument()
  })

  it('渲染 Form 并传入 dispatch', () => {
    render(
      <GenerativeUIRenderer
        envelope={{
          type: 'form',
          props: {
            title: 'My Form',
            fields: [{ name: 'name', label: 'Name' }],
          },
        }}
      />,
      { wrapper: Wrapper },
    )
    expect(screen.getByText('My Form')).toBeInTheDocument()
    expect(screen.getByLabelText('Name')).toBeInTheDocument()
    expect(screen.getByRole('button', { name: '提交' })).toBeInTheDocument()
  })

  it('未知类型降级', () => {
    const warnSpy = vi.spyOn(console, 'warn').mockImplementation(() => {})
    render(
      <GenerativeUIRenderer envelope={{ type: 'unknown' }} />,
      { wrapper: Wrapper },
    )
    expect(screen.getByText('无法渲染 Generative UI')).toBeInTheDocument()
    warnSpy.mockRestore()
  })
})
