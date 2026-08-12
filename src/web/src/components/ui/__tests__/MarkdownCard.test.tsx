import { render, screen } from '@testing-library/react'
import { describe, expect, it } from 'vitest'
import { MarkdownCard } from '../MarkdownCard'

describe('MarkdownCard', () => {
  it('renders title and content', () => {
    render(
      <MarkdownCard
        metadata={{
          type: 'markdown_card',
          title: 'Summary',
          content: '# Hello',
        }}
      />,
    )
    expect(screen.getByText('Summary')).toBeInTheDocument()
    expect(screen.getByText('# Hello')).toBeInTheDocument()
  })
})
