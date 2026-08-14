import { render, screen } from '@testing-library/react'
import { describe, expect, it } from 'vitest'
import { MetricCard } from '../MetricCard'

describe('MetricCard', () => {
  it('renders value and positive change', () => {
    render(<MetricCard title="Revenue" value={1200} unit="USD" change={5.4} />)
    expect(screen.getByText('1200')).toBeInTheDocument()
    expect(screen.getByText('USD')).toBeInTheDocument()
    expect(screen.getByText('+5.4%')).toBeInTheDocument()
  })

  it('renders negative change', () => {
    render(<MetricCard value={80} change={-2} />)
    expect(screen.getByText('-2%')).toHaveClass('text-red-600')
  })
})
