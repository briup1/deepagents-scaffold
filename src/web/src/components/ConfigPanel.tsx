import { useEffect, useState } from 'react'
import { listTools } from '../api'

export default function ConfigPanel() {
  const [tools, setTools] = useState<Array<{ name: string; description?: string }>>([])
  const [expanded, setExpanded] = useState(false)

  useEffect(() => {
    listTools().then((data) => setTools(data.tools)).catch(() => {})
  }, [])

  return (
    <aside className={`${expanded ? 'w-72' : 'w-10'} bg-white border-l transition-all duration-200 flex flex-col`}>
      <button
        onClick={() => setExpanded(!expanded)}
        className="p-2 text-gray-500 hover:text-gray-800 border-b"
        title="Toggle config panel"
      >
        {expanded ? '>>' : '<<'}
      </button>
      {expanded && (
        <div className="flex-1 overflow-y-auto p-4">
          <h3 className="font-semibold text-sm text-gray-800 mb-3">Available Tools</h3>
          {tools.length === 0 ? (
            <p className="text-xs text-gray-400">No tools loaded</p>
          ) : (
            <ul className="space-y-2">
              {tools.map((tool) => (
                <li key={tool.name} className="text-sm">
                  <div className="font-medium text-gray-700">{tool.name}</div>
                  {tool.description && (
                    <div className="text-xs text-gray-500">{tool.description}</div>
                  )}
                </li>
              ))}
            </ul>
          )}
        </div>
      )}
    </aside>
  )
}
