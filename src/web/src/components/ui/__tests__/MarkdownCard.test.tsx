import { render, screen } from '@testing-library/react'
import { describe, expect, it } from 'vitest'
import { MarkdownCard } from '../MarkdownCard'

describe('MarkdownCard', () => {
  it('renders title and content', () => {
    render(<MarkdownCard title="Summary" content="# Hello" />)
    expect(screen.getByText('Summary')).toBeInTheDocument()
    expect(screen.getByText('# Hello')).toBeInTheDocument()
  })

  it('renders without title', () => {
    render(<MarkdownCard content="no title" />)
    expect(screen.getByText('no title')).toBeInTheDocument()
  })
})
