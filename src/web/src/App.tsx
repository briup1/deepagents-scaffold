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
    setMessages((prev) => [...prev, userMsg])
    setIsLoading(true)

    let assistantContent = ''
    try {
      await sendMessageStream(
        [...messages, userMsg],
        (event) => {
          const ev = event as Record<string, unknown>
          if (typeof ev.content === 'string') {
            assistantContent += ev.content
            setMessages((prev) => {
              const filtered = prev.filter((m) => m.role !== 'assistant' || m.content !== assistantContent.slice(0, -ev.content.length))
              return [...filtered, { role: 'assistant', content: assistantContent }]
            })
          }
        },
        assistantId,
      )
    } catch (err) {
      setMessages((prev) => [
        ...prev,
        { role: 'assistant', content: `Error: ${(err as Error).message}` },
      ])
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
              setMessages={setMessages}
              assistantId={assistantId}
              isLoading={isLoading}
              setIsLoading={setIsLoading}
            />
            <MessageInput onSend={handleSend} disabled={isLoading} />
          </div>
          <ConfigPanel />
        </div>
      </div>
    </div>
  )
}
