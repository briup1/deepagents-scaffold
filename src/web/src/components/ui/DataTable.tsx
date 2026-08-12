import type { DataTableMetadata } from '../../types/generative-ui'

interface DataTableProps {
  metadata: DataTableMetadata
}

export function DataTable({ metadata }: DataTableProps) {
  const { title } = metadata
  const columns = Array.isArray(metadata.columns) ? metadata.columns : []
  const rows = Array.isArray(metadata.rows) ? metadata.rows : []

  if (!Array.isArray(metadata.columns) || !Array.isArray(metadata.rows)) {
    console.warn('[DataTable] data_table metadata 缺少 columns 或 rows 字段，将使用空数组')
  }

  return (
    <div className="overflow-hidden rounded-lg border border-gray-200 bg-white shadow-sm my-2">
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
