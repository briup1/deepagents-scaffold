import { useEffect, useMemo, useState } from 'react'
import Chat from './components/Chat'
import MessageInput from './components/MessageInput'
import Sidebar from './components/Sidebar'
import ConfigPanel from './components/ConfigPanel'
import { createAgent, sendAgentMessage, listAgents, type DisplayItem } from './api'

export default function App() {
  const [threadId] = useState(() => `thread-${Date.now()}`)
  const [assistantId, setAssistantId] = useState('default')
  const [agents, setAgents] = useState<Array<{ name: string; type: string }>>([])
  const [items, setItems] = useState<DisplayItem[]>([])
  const [isLoading, setIsLoading] = useState(false)

  useEffect(() => {
    listAgents()
      .then((data) => setAgents(data.agents))
      .catch(() => setAgents([]))
  }, [])

  const agent = useMemo(() => {
    const url = agents.length <= 1 ? '/agent' : `/agent/${assistantId}`
    return createAgent(threadId, url)
  }, [threadId, agents.length, assistantId])

  const handleSend = async (text: string) => {
    const userItem: DisplayItem = {
      id: `msg-${Date.now()}`,
      type: 'text',
      role: 'user',
      content: text,
    }
    setItems((prev) => [...prev, userItem])
    setIsLoading(true)

    let currentAssistantId: string | null = null
    let currentReasoningId: string | null = null
    let currentToolId: string | null = null

    try {
      await sendAgentMessage(agent, text, {
        onTextMessageStartEvent: ({ event }) => {
          currentAssistantId = event.messageId
          setItems((prev) => [
            ...prev,
            { id: event.messageId, type: 'text', role: 'assistant', content: '' },
          ])
        },
        onTextMessageContentEvent: ({ event }) => {
          if (!currentAssistantId) return
          setItems((prev) =>
            prev.map((item) =>
              item.id === currentAssistantId && item.type === 'text'
                ? { ...item, content: item.content + event.delta }
                : item,
            ),
          )
        },
        onTextMessageEndEvent: () => {
          currentAssistantId = null
        },
        onReasoningStartEvent: ({ event }) => {
          currentReasoningId = event.messageId
          setItems((prev) => [
            ...prev,
            { id: event.messageId, type: 'reasoning', content: '' },
          ])
        },
        onReasoningMessageContentEvent: ({ event }) => {
          if (!currentReasoningId) return
          setItems((prev) =>
            prev.map((item) =>
              item.id === currentReasoningId && item.type === 'reasoning'
                ? { ...item, content: item.content + event.delta }
                : item,
            ),
          )
        },
        onReasoningEndEvent: () => {
          currentReasoningId = null
        },
        onToolCallStartEvent: ({ event }) => {
          currentToolId = event.toolCallId
          setItems((prev) => [
            ...prev,
            {
              id: event.toolCallId,
              type: 'tool',
              toolName: event.toolCallName,
              args: '',
            },
          ])
        },
        onToolCallArgsEvent: ({ toolCallBuffer }) => {
          if (!currentToolId) return
          setItems((prev) =>
            prev.map((item) =>
              item.id === currentToolId && item.type === 'tool'
                ? { ...item, args: toolCallBuffer }
                : item,
            ),
          )
        },
        onToolCallResultEvent: ({ event }) => {
          if (!currentToolId) return
          setItems((prev) =>
            prev.map((item) =>
              item.id === currentToolId && item.type === 'tool'
                ? { ...item, result: String(event.result) }
                : item,
            ),
          )
          currentToolId = null
        },
        onRunErrorEvent: ({ event }) => {
          setItems((prev) => [
            ...prev,
            { id: `err-${Date.now()}`, type: 'error', content: event.message },
          ])
        },
      })
    } catch (err) {
      setItems((prev) => [
        ...prev,
        { id: `err-${Date.now()}`, type: 'error', content: (err as Error).message },
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
            <Chat items={items} isLoading={isLoading} />
            <MessageInput onSend={handleSend} disabled={isLoading} />
          </div>
          <ConfigPanel />
        </div>
      </div>
    </div>
  )
}
