interface DataTableColumn {
  key: string
  label: string
}

interface DataTableProps {
  title?: string
  columns: DataTableColumn[]
  rows: Array<Record<string, string | number | boolean>>
}

export function DataTable({ title, columns, rows }: DataTableProps) {
  return (
    <div className="my-2 overflow-hidden rounded-lg border border-gray-200 bg-white shadow-sm">
      {title && (
        <div className="border-b border-gray-200 bg-gray-50 px-4 py-2">
          <h3 className="text-sm font-semibold text-gray-700">{title}</h3>
        </div>
      )}
      <div className="overflow-x-auto">
        <table className="min-w-full text-sm">
          <thead className="bg-gray-50">
            <tr>
              {columns.map((col) => (
                <th
                  key={col.key}
                  className="px-4 py-2 text-left font-medium text-gray-600"
                >
                  {col.label}
                </th>
              ))}
            </tr>
          </thead>
          <tbody className="divide-y divide-gray-100">
            {rows.map((row, idx) => (
              <tr key={idx}>
                {columns.map((col) => (
                  <td key={col.key} className="px-4 py-2 text-gray-800">
                    {String(row[col.key] ?? '')}
                  </td>
                ))}
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </div>
  )
}
