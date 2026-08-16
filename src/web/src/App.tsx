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
  agents: AgentInfo[]
  currentAgentId: string
  threadId: string
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

function ChatShell({ agents, currentAgentId, threadId }: ChatShellProps) {
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
      <ChatInner agentId={currentAgentId} />
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
        agents={agents}
        currentAgentId={currentAgentId}
        threadId={threadId}
      />
    </div>
  )
}
