import { useState } from 'react'
import Chat from './components/Chat'
import MessageInput from './components/MessageInput'
import Sidebar from './components/Sidebar'
import ConfigPanel from './components/ConfigPanel'
import { sendMessageStream } from './api'

interface Message {
  role: 'user' | 'assistant' | 'tool'
  content: string
}

export default function App() {
  const [messages, setMessages] = useState<Message[]>([])
  const [assistantId, setAssistantId] = useState('default')
  const [isLoading, setIsLoading] = useState(false)

  const handleSend = async (text: string) => {
    const userMsg: Message = { role: 'user', content: text }
    const assistantPlaceholder: Message = { role: 'assistant', content: '' }
    setMessages((prev) => [...prev, userMsg, assistantPlaceholder])
    setIsLoading(true)

    let assistantContent = ''
    try {
      await sendMessageStream(
        [...messages, userMsg],
        (event) => {
          const ev = event as Record<string, unknown>

          // Backend uses stream_mode="values": each event is a state snapshot
          // with a "messages" array. Extract the latest assistant/ai message.
          let content = ''
          if (typeof ev.content === 'string') {
            content = ev.content
          } else if (Array.isArray(ev.messages)) {
            for (let i = ev.messages.length - 1; i >= 0; i--) {
              const m = ev.messages[i] as Record<string, unknown>
              const t = (m.type as string) || (m.role as string)
              if (t === 'ai' || t === 'assistant') {
                content = typeof m.content === 'string' ? m.content : ''
                break
              }
            }
          }

          if (!content) return

          assistantContent = content
          setMessages((prev) => {
            const updated = [...prev]
            const lastIndex = updated.length - 1
            if (updated[lastIndex]?.role === 'assistant') {
              updated[lastIndex] = { role: 'assistant', content: assistantContent }
            }
            return updated
          })
        },
        assistantId,
      )
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
