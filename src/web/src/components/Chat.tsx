import { useEffect, useRef } from 'react'

interface Message {
  role: 'user' | 'assistant' | 'tool'
  content: string
}

export default function Chat({
  messages,
  isLoading,
}: {
  messages: Message[]
  isLoading: boolean
}) {
  const bottomRef = useRef<HTMLDivElement>(null)

  useEffect(() => {
    bottomRef.current?.scrollIntoView({ behavior: 'smooth' })
  }, [messages])

  return (
    <div className="flex-1 flex flex-col bg-white rounded-lg shadow overflow-hidden">
      <div className="flex-1 overflow-y-auto p-4 space-y-4">
        {messages.map((msg, i) => (
          <div
            key={i}
            className={`flex ${msg.role === 'user' ? 'justify-end' : 'justify-start'}`}
          >
            <div
              className={`max-w-[70%] rounded-lg px-4 py-2 whitespace-pre-wrap ${
                msg.role === 'user'
                  ? 'bg-blue-600 text-white'
                  : msg.role === 'tool'
                  ? 'bg-yellow-100 text-yellow-900'
                  : 'bg-gray-100 text-gray-900'
              }`}
            >
              <div className="text-xs opacity-70 mb-1 font-medium">
                {msg.role === 'user' ? 'You' : msg.role === 'tool' ? 'Tool' : 'Agent'}
              </div>
              {msg.content}
            </div>
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
