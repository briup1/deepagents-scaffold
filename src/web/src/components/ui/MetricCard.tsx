interface MetricCardProps {
  title?: string
  value: number
  unit?: string
  change?: number
}

export function MetricCard({ title, value, unit, change }: MetricCardProps) {
  const changePositive = change !== undefined && change >= 0
  return (
    <div className="my-2 rounded-lg border border-gray-200 bg-white p-4 shadow-sm">
      {title && <p className="text-xs font-medium text-gray-500">{title}</p>}
      <div className="mt-1 flex items-baseline gap-2">
        <span className="text-2xl font-semibold text-gray-900">{value}</span>
        {unit && <span className="text-sm text-gray-500">{unit}</span>}
        {change !== undefined && (
          <span
            className={`text-sm font-medium ${
              changePositive ? 'text-green-600' : 'text-red-600'
            }`}
          >
            {changePositive ? '+' : ''}
            {change}%
          </span>
        )}
      </div>
    </div>
  )
}
