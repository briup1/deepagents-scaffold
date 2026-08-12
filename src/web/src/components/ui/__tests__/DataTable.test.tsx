import { render, screen } from '@testing-library/react'
import { describe, expect, it } from 'vitest'
import { DataTable } from '../DataTable'

describe('DataTable', () => {
  it('renders columns and rows', () => {
    render(
      <DataTable
        metadata={{
          type: 'data_table',
          title: 'Results',
          columns: [
            { key: 'name', label: 'Name' },
            { key: 'value', label: 'Value' },
          ],
          rows: [
            { name: 'A', value: 1 },
            { name: 'B', value: 2 },
          ],
        }}
      />,
    )
    expect(screen.getByText('Results')).toBeInTheDocument()
    expect(screen.getByText('Name')).toBeInTheDocument()
    expect(screen.getByText('A')).toBeInTheDocument()
    expect(screen.getByText('2')).toBeInTheDocument()
  })
})
