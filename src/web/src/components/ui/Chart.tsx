interface ChartDataPoint {
  label: string
  value: number
}

interface ChartProps {
  title?: string
  kind: 'bar' | 'line'
  data: ChartDataPoint[]
  width?: number
  height?: number
}

export function Chart({ title, kind, data, width = 320, height = 200 }: ChartProps) {
  const padding = { top: 16, right: 16, bottom: 40, left: 40 }
  const plotWidth = Math.max(width - padding.left - padding.right, 1)
  const plotHeight = Math.max(height - padding.top - padding.bottom, 1)

  const maxValue = Math.max(...data.map((d) => d.value), 1)
  const yTicks = 4

  const xForIndex = (idx: number) => padding.left + (idx * plotWidth) / Math.max(data.length - 1, 1)
  const yForValue = (value: number) => padding.top + plotHeight - (value / maxValue) * plotHeight

  const barGap = 2
  const barWidth = data.length > 0 ? plotWidth / data.length - barGap : 0

  return (
    <div className="my-2 rounded-lg border border-gray-200 bg-white p-4 shadow-sm">
      {title && <h3 className="mb-2 text-sm font-semibold text-gray-700">{title}</h3>}
      <svg width={width} height={height} role="img" aria-label={title || 'chart'}>
        {/* Y-axis grid lines */}
        {Array.from({ length: yTicks + 1 }, (_, i) => {
          const value = (maxValue * i) / yTicks
          const y = yForValue(value)
          return (
            <g key={i}>
              <line
                x1={padding.left}
                y1={y}
                x2={width - padding.right}
                y2={y}
                stroke="#e5e7eb"
                strokeWidth={1}
              />
              <text x={padding.left - 6} y={y + 4} textAnchor="end" className="fill-gray-500 text-[10px]">
                {Math.round(value)}
              </text>
            </g>
          )
        })}

        {kind === 'bar' &&
          data.map((point, idx) => {
            const x = padding.left + idx * (barWidth + barGap) + barGap / 2
            const y = yForValue(point.value)
            const h = padding.top + plotHeight - y
            return (
              <rect
                key={idx}
                x={x}
                y={y}
                width={Math.max(barWidth, 1)}
                height={h}
                fill="#3b82f6"
                rx={2}
              />
            )
          })}

        {kind === 'line' && data.length > 0 && (
          <>
            <polyline
              fill="none"
              stroke="#3b82f6"
              strokeWidth={2}
              points={data
                .map((point, idx) => `${xForIndex(idx)},${yForValue(point.value)}`)
                .join(' ')}
            />
            {data.map((point, idx) => (
              <circle
                key={idx}
                cx={xForIndex(idx)}
                cy={yForValue(point.value)}
                r={4}
                fill="#3b82f6"
              />
            ))}
          </>
        )}

        {/* X-axis labels */}
        {data.map((point, idx) => (
          <text
            key={idx}
            x={kind === 'bar' ? padding.left + idx * (barWidth + barGap) + barGap / 2 + barWidth / 2 : xForIndex(idx)}
            y={height - padding.bottom + 16}
            textAnchor="middle"
            className="fill-gray-600 text-[10px]"
          >
            {point.label}
          </text>
        ))}
      </svg>
    </div>
  )
}
