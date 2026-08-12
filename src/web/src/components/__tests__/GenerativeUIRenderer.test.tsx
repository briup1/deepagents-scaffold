import { render, screen } from '@testing-library/react'
import { describe, expect, it, vi } from 'vitest'
import { GenerativeUIRenderer } from '../GenerativeUIRenderer'

describe('GenerativeUIRenderer', () => {
  it('renders markdown card', () => {
    render(
      <GenerativeUIRenderer
        metadata={{ type: 'markdown_card', title: 'T', content: 'C' }}
      />,
    )
    expect(screen.getByText('T')).toBeInTheDocument()
    expect(screen.getByText('C')).toBeInTheDocument()
  })

  it('renders data table', () => {
    render(
      <GenerativeUIRenderer
        metadata={{
          type: 'data_table',
          title: 'T',
          columns: [{ key: 'k', label: 'K' }],
          rows: [{ k: 'v' }],
        }}
      />,
    )
    expect(screen.getByText('T')).toBeInTheDocument()
    expect(screen.getByText('v')).toBeInTheDocument()
  })

  it('returns null for unsupported type and logs warning', () => {
    const warnSpy = vi.spyOn(console, 'warn').mockImplementation(() => {})
    const { container } = render(<GenerativeUIRenderer metadata={{ type: 'unknown' }} />)
    expect(container.firstChild).toBeNull()
    expect(warnSpy).toHaveBeenCalled()
    warnSpy.mockRestore()
  })
})
