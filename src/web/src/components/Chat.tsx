import { useEffect, useRef } from 'react'
import { type DisplayItem } from '../api'

interface ChatProps {
  items: DisplayItem[]
  isLoading: boolean
}

export default function Chat({ items, isLoading }: ChatProps) {
  const bottomRef = useRef<HTMLDivElement>(null)

  useEffect(() => {
    bottomRef.current?.scrollIntoView({ behavior: 'smooth' })
  }, [items])

  return (
    <div className="flex-1 flex flex-col bg-white rounded-lg shadow overflow-hidden">
      <div className="flex-1 overflow-y-auto p-4 space-y-4">
        {items.map((item) => (
          <div
            key={item.id}
            className={`flex ${item.role === 'user' ? 'justify-end' : 'justify-start'}`}
          >
            {item.type === 'tool' ? (
              <div className="max-w-[80%] w-full rounded-lg border border-yellow-200 bg-yellow-50 px-4 py-2">
                <div className="text-xs font-medium text-yellow-800 mb-1">
                  Tool: {item.toolName}
                </div>
                <pre className="text-xs text-yellow-900 whitespace-pre-wrap">{item.args}</pre>
                {item.result && (
                  <div className="mt-2 text-xs text-green-700 border-t border-yellow-200 pt-2">
                    Result: {item.result}
                  </div>
                )}
              </div>
            ) : (
              <div
                className={`max-w-[70%] rounded-lg px-4 py-2 whitespace-pre-wrap ${
                  item.role === 'user'
                    ? 'bg-blue-600 text-white'
                    : item.type === 'error'
                    ? 'bg-red-100 text-red-900'
                    : item.type === 'reasoning'
                    ? 'bg-purple-50 text-purple-900 border border-purple-200'
                    : 'bg-gray-100 text-gray-900'
                }`}
              >
                <div className="text-xs opacity-70 mb-1 font-medium">
                  {item.role === 'user'
                    ? 'You'
                    : item.type === 'reasoning'
                    ? 'Reasoning'
                    : item.type === 'error'
                    ? 'Error'
                    : 'Agent'}
                </div>
                {item.content}
              </div>
            )}
          </div>
        ))}
        {isLoading && (
          <div className="flex justify-start">
            <div className="bg-gray-100 rounded-lg px-4 py-2 text-sm text-gray-500">Thinking...</div>
          </div>
        )}
        <div ref={bottomRef} />
      </div>
    </div>
  )
}
