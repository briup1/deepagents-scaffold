import { useEffect, useMemo, useState } from 'react'
import { CopilotKit } from '@copilotkit/react-core'
import { CopilotSidebar, CopilotChat } from '@copilotkit/react-ui'
import { AgentSelector } from './components/AgentSelector'
import { listAgents, type AgentInfo } from './api/copilotkit'
import { SAMPLE_MARKDOWN_CARD, useGenerativeUI } from './hooks/useGenerativeUI'
import '@copilotkit/react-ui/styles.css'

export default function App() {
  const [threadId] = useState(() => `thread-${crypto.randomUUID()}`)
  const [agents, setAgents] = useState<AgentInfo[]>([])
  const [loadingAgents, setLoadingAgents] = useState(true)
  const [agentError, setAgentError] = useState<string | null>(null)
  const [agentId, setAgentId] = useState<string | null>(null)
  const { renderMessage } = useGenerativeUI({
    enableMock: import.meta.env.DEV,
    mockMetadata: SAMPLE_MARKDOWN_CARD,
  })

  useEffect(() => {
    listAgents()
      .then((data) => {
        setAgents(data.agents)
        if (data.agents.length > 0) {
          setAgentId(data.agents[0].name)
        }
      })
      .catch((err) => {
        setAgentError(err instanceof Error ? err.message : String(err))
      })
      .finally(() => {
        setLoadingAgents(false)
      })
  }, [])

  const runtimeUrl = useMemo(() => {
    if (agents.length === 1) return '/agent'
    if (agentId) return `/agent/${agentId}`
    return '/agent'
  }, [agents.length, agentId])

  if (loadingAgents) {
    return <div className="p-4 text-sm text-gray-500">加载 Agent 列表...</div>
  }
  if (agentError) {
    return <div className="p-4 text-sm text-red-500">加载失败：{agentError}</div>
  }

  const currentAgentId = agentId ?? agents[0]?.name ?? 'default'

  return (
    <div className="h-screen w-screen">
      <CopilotKit runtimeUrl={runtimeUrl} threadId={threadId}>
        <CopilotSidebar
          defaultOpen={true}
          clickOutsideToClose={false}
          className="h-full"
        >
          <div className="flex h-full flex-col">
            <AgentSelector
              value={currentAgentId}
              onChange={setAgentId}
              agents={agents}
            />
            <div className="flex-1 overflow-hidden">
              <CopilotChat
                className="h-full"
                labels={{
                  title: 'DeepAgents Chat',
                  initial: '有什么可以帮你的？',
                  placeholder: '输入消息...',
                }}
                RenderMessage={renderMessage}
              />
            </div>
          </div>
        </CopilotSidebar>
      </CopilotKit>
    </div>
  )
}
