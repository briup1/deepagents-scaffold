import { render, screen } from '@testing-library/react'
import { describe, expect, it } from 'vitest'
import { Chart } from '../Chart'

describe('Chart', () => {
  it('renders bar chart title and labels', () => {
    render(
      <Chart
        title="Sales"
        kind="bar"
        data={[
          { label: 'Q1', value: 100 },
          { label: 'Q2', value: 200 },
        ]}
      />,
    )
    expect(screen.getByText('Sales')).toBeInTheDocument()
    expect(screen.getByText('Q1')).toBeInTheDocument()
    expect(screen.getByText('Q2')).toBeInTheDocument()
  })

  it('renders line chart', () => {
    const { container } = render(
      <Chart
        title="Trend"
        kind="line"
        data={[{ label: 'A', value: 10 }]}
      />,
    )
    expect(container.querySelector('polyline')).toBeInTheDocument()
  })
})
