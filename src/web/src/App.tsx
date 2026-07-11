import { useRef, useState } from 'react'
import Chat from './components/Chat'
import MessageInput from './components/MessageInput'
import Sidebar from './components/Sidebar'
import ConfigPanel from './components/ConfigPanel'
import { createAgent, sendAgentMessage } from './api'

interface Message {
  role: 'user' | 'assistant' | 'tool'
  content: string
}

export default function App() {
  const [messages, setMessages] = useState<Message[]>([])
  const [assistantId, setAssistantId] = useState('default')
  const [threadId] = useState(() => `thread-${Date.now()}`)
  const [isLoading, setIsLoading] = useState(false)
  const agentRef = useRef(createAgent(threadId))
  const assistantContentRef = useRef('')

  const handleSend = async (text: string) => {
    const userMsg: Message = { role: 'user', content: text }
    const assistantPlaceholder: Message = { role: 'assistant', content: '' }
    setMessages((prev) => [...prev, userMsg, assistantPlaceholder])
    setIsLoading(true)
    assistantContentRef.current = ''

    try {
      await sendAgentMessage(agentRef.current, text, {
        onTextMessageContentEvent: ({ event }) => {
          assistantContentRef.current += event.delta
          setMessages((prev) => {
            const updated = [...prev]
            const lastIndex = updated.length - 1
            if (updated[lastIndex]?.role === 'assistant') {
              updated[lastIndex] = { role: 'assistant', content: assistantContentRef.current }
            }
            return updated
          })
        },
        onRunErrorEvent: ({ event }) => {
          assistantContentRef.current = `Error: ${event.message}`
          setMessages((prev) => {
            const updated = [...prev]
            const lastIndex = updated.length - 1
            if (updated[lastIndex]?.role === 'assistant') {
              updated[lastIndex] = { role: 'assistant', content: assistantContentRef.current }
            }
            return updated
          })
        },
      })
    } catch (err) {
      setMessages((prev) => {
        const updated = [...prev]
        const lastIndex = updated.length - 1
        if (updated[lastIndex]?.role === 'assistant') {
          updated[lastIndex] = { role: 'assistant', content: `Error: ${(err as Error).message}` }
          return updated
        }
        return [...prev, { role: 'assistant', content: `Error: ${(err as Error).message}` }]
      })
    } finally {
      setIsLoading(false)
    }
  }

  return (
    <div className="flex h-screen bg-gray-50">
      <Sidebar assistantId={assistantId} setAssistantId={setAssistantId} />
      <div className="flex-1 flex flex-col">
        <header className="bg-white border-b px-6 py-3 flex items-center justify-between">
          <h1 className="font-semibold text-gray-800">DeepAgents Scaffold</h1>
          <span className="text-sm text-gray-500">Agent: {assistantId}</span>
        </header>
        <div className="flex-1 flex overflow-hidden">
          <div className="flex-1 flex flex-col p-4">
            <Chat
              messages={messages}
              isLoading={isLoading}
            />
            <MessageInput onSend={handleSend} disabled={isLoading} />
          </div>
          <ConfigPanel />
        </div>
      </div>
    </div>
  )
}
