import { useEffect, useMemo, useState } from 'react'
import { CopilotKit, CopilotChat, useAgent } from '@copilotkit/react-core/v2'
import { HttpAgent } from '@ag-ui/client'
import { listAgents, type AgentInfo } from './api/copilotkit'
import { getThreadMessages, type ThreadMessage } from './api/threads'
import { Sidebar } from './components/Sidebar'
import { GenerativeUIContext } from './catalog/GenerativeUIContext'
import { useGenerativeUITool } from './hooks/useGenerativeUITool'
import { useGenerativeUIAction } from './hooks/useGenerativeUIAction'

interface ChatShellProps {
  agents: AgentInfo[]
  currentAgentId: string
  threadId: string
  initialMessages: ThreadMessage[]
}

interface ChatInnerProps {
  agentId: string
  initialMessages: ThreadMessage[]
}

function ChatInner({ agentId, initialMessages }: ChatInnerProps) {
  useGenerativeUITool()
  const { agent } = useAgent({ agentId })
  const dispatch = useGenerativeUIAction(agentId)

  useEffect(() => {
    if (agent && initialMessages.length > 0) {
      const agUiMessages = initialMessages
        .filter((m) => m.role === 'user' || m.role === 'assistant')
        .map((m) => ({
          id: m.message_id,
          role: m.role as 'user' | 'assistant',
          content: m.content ?? '',
        }))
      agent.setMessages(agUiMessages as { id: string; role: 'user' | 'assistant'; content: string }[])
    }
  }, [agent, initialMessages])

  return (
    <GenerativeUIContext.Provider value={{ dispatch }}>
      <main className="flex h-full flex-1 flex-col overflow-hidden">
        <CopilotChat
          agentId={agentId}
          className="h-full"
          labels={{
            chatInputPlaceholder: '输入消息...',
            welcomeMessageText: '有什么可以帮你的？',
            modalHeaderTitle: 'DeepAgents Chat',
          }}
        />
      </main>
    </GenerativeUIContext.Provider>
  )
}

function ChatShell({ agents, currentAgentId, threadId, initialMessages }: ChatShellProps) {
  // 把所有已注册 Agent 都交给 CopilotKit，否则切换 Agent 时 useAgent
  // 内部 known agents 只有当前一个，导致报错。
  const agentMap = useMemo(() => {
    const map: Record<string, HttpAgent> = {}
    for (const agent of agents) {
      const url = agents.length === 1 ? '/agent' : `/agent/${agent.name}`
      map[agent.name] = new HttpAgent({ url, threadId })
    }
    return map
  }, [agents, threadId])

  return (
    <CopilotKit threadId={threadId} agents__unsafe_dev_only={agentMap}>
      <ChatInner agentId={currentAgentId} initialMessages={initialMessages} />
    </CopilotKit>
  )
}

export default function App() {
  const [threadId, setThreadId] = useState(() => `thread-${crypto.randomUUID()}`)
  const [initialMessages, setInitialMessages] = useState<ThreadMessage[]>([])
  const [agents, setAgents] = useState<AgentInfo[]>([])
  const [loadingAgents, setLoadingAgents] = useState(true)
  const [agentError, setAgentError] = useState<string | null>(null)
  const [agentId, setAgentId] = useState<string | null>(null)

  useEffect(() => {
    listAgents()
      .then((data) => {
        setAgents(data.agents)
        if (data.agents.length > 0 && agentId == null) {
          setAgentId(data.agents[0].name)
        }
      })
      .catch((err) => {
        setAgentError(err instanceof Error ? err.message : String(err))
      })
      .finally(() => {
        setLoadingAgents(false)
      })
  }, [agentId])

  if (loadingAgents) {
    return (
      <div className="flex h-screen w-screen items-center justify-center bg-cream-50">
        <div className="text-center">
          <div className="mx-auto mb-4 h-8 w-8 animate-spin rounded-full border-2 border-cream-300 border-t-ink" />
          <p className="text-sm text-ink-muted">加载 Agent 列表...</p>
        </div>
      </div>
    )
  }

  if (agentError) {
    return (
      <div className="flex h-screen w-screen items-center justify-center bg-cream-50 p-4">
        <div className="max-w-md rounded-2xl border border-red-200 bg-white p-6 shadow-card">
          <h1 className="text-lg font-semibold text-red-600">加载失败</h1>
          <p className="mt-2 text-sm text-ink-muted">{agentError}</p>
        </div>
      </div>
    )
  }

  const currentAgentId = agentId ?? agents[0]?.name ?? 'default'

  const handleNewChat = () => {
    setThreadId(`thread-${crypto.randomUUID()}`)
    setInitialMessages([])
  }

  const handleAgentChange = (nextAgentId: string) => {
    if (nextAgentId === currentAgentId) return
    setAgentId(nextAgentId)
    setThreadId(`thread-${crypto.randomUUID()}`)
    setInitialMessages([])
  }

  const handleSelectThread = async (selectedThreadId: string, selectedAgentId: string) => {
    if (selectedThreadId === threadId) return
    try {
      const data = await getThreadMessages(selectedThreadId)
      if (selectedAgentId !== currentAgentId && agents.some((a) => a.name === selectedAgentId)) {
        setAgentId(selectedAgentId)
      }
      setThreadId(selectedThreadId)
      setInitialMessages(data.messages ?? [])
    } catch (err) {
      setAgentError(err instanceof Error ? err.message : String(err))
    }
  }

  return (
    <div className="flex h-screen w-screen overflow-hidden bg-cream-50">
      <Sidebar
        agents={agents}
        currentAgentId={currentAgentId}
        threadId={threadId}
        onAgentChange={handleAgentChange}
        onNewChat={handleNewChat}
        onSelectThread={handleSelectThread}
      />
      <ChatShell
        key={threadId}
        agents={agents}
        currentAgentId={currentAgentId}
        threadId={threadId}
        initialMessages={initialMessages}
      />
    </div>
  )
}
