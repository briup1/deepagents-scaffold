import { render, screen } from '@testing-library/react'
import { describe, expect, it } from 'vitest'
import { DataTable } from '../DataTable'

describe('DataTable', () => {
  it('renders columns and rows', () => {
    render(
      <DataTable
        title="Results"
        columns={[
          { key: 'name', label: 'Name' },
          { key: 'value', label: 'Value' },
        ]}
        rows={[{ name: 'A', value: 1 }]}
      />,
    )
    expect(screen.getByText('Results')).toBeInTheDocument()
    expect(screen.getByText('Name')).toBeInTheDocument()
    expect(screen.getByText('A')).toBeInTheDocument()
    expect(screen.getByText('1')).toBeInTheDocument()
  })
})
