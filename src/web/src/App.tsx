import { useEffect, useMemo, useState } from 'react'
import { CopilotKit, CopilotChat } from '@copilotkit/react-core/v2'
import { HttpAgent } from '@ag-ui/client'
import { listAgents, type AgentInfo } from './api/copilotkit'
import { AgentSelector } from './components/AgentSelector'
import { NewChatButton } from './components/NewChatButton'
import { GenerativeUIContext } from './catalog/GenerativeUIContext'
import { useGenerativeUITool } from './hooks/useGenerativeUITool'
import { useGenerativeUIAction } from './hooks/useGenerativeUIAction'

interface ChatShellProps {
  agentId: string
  threadId: string
  agentUrl: string
}

interface ChatInnerProps {
  agentId: string
}

function ChatInner({ agentId }: ChatInnerProps) {
  useGenerativeUITool()
  const dispatch = useGenerativeUIAction(agentId)

  return (
    <GenerativeUIContext.Provider value={{ dispatch }}>
      <main className="flex-1 overflow-hidden">
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

function ChatShell({ agentId, threadId, agentUrl }: ChatShellProps) {
  const agent = useMemo(
    () => new HttpAgent({ url: agentUrl, threadId }),
    [agentUrl, threadId],
  )

  return (
    <CopilotKit threadId={threadId} selfManagedAgents={{ [agentId]: agent }}>
      <ChatInner agentId={agentId} />
    </CopilotKit>
  )
}

export default function App() {
  const [threadId, setThreadId] = useState(() => `thread-${crypto.randomUUID()}`)
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
    return <div className="p-4 text-sm text-gray-500">加载 Agent 列表...</div>
  }
  if (agentError) {
    return <div className="p-4 text-sm text-red-500">加载失败：{agentError}</div>
  }

  const currentAgentId = agentId ?? agents[0]?.name ?? 'default'
  const agentUrl = agents.length === 1 ? '/agent' : `/agent/${currentAgentId}`

  const handleNewChat = () => {
    setThreadId(`thread-${crypto.randomUUID()}`)
  }

  return (
    <div className="flex h-screen w-screen flex-col">
      <header className="flex items-center justify-between gap-4 border-b border-gray-200 px-4 py-3">
        <div className="flex items-center gap-4">
          <h1 className="text-lg font-semibold text-gray-800">DeepAgents</h1>
          <AgentSelector
            value={currentAgentId}
            onChange={setAgentId}
            agents={agents}
          />
        </div>
        <NewChatButton onClick={handleNewChat} />
      </header>
      <ChatShell
        key={threadId}
        agentId={currentAgentId}
        threadId={threadId}
        agentUrl={agentUrl}
      />
    </div>
  )
}
