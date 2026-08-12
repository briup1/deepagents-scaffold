import { useMemo, useState } from 'react'
import { CopilotKit } from '@copilotkit/react-core'
import { CopilotSidebar, CopilotChat } from '@copilotkit/react-ui'
import { AgentSelector } from './components/AgentSelector'
import { SAMPLE_MARKDOWN_CARD, useGenerativeUI } from './hooks/useGenerativeUI'
import '@copilotkit/react-ui/styles.css'

export default function App() {
  const [threadId] = useState(() => `thread-${crypto.randomUUID()}`)
  const [agentId, setAgentId] = useState('default')
  const { renderMessage } = useGenerativeUI({
    enableMock: import.meta.env.DEV,
    mockMetadata: SAMPLE_MARKDOWN_CARD,
  })

  const runtimeUrl = useMemo(() => {
    return agentId === 'default' ? '/agent' : `/agent/${agentId}`
  }, [agentId])

  return (
    <div className="h-screen w-screen">
      <CopilotKit runtimeUrl={runtimeUrl} threadId={threadId}>
        <CopilotSidebar
          defaultOpen={true}
          clickOutsideToClose={false}
          className="h-full"
        >
          <div className="flex h-full flex-col">
            <AgentSelector value={agentId} onChange={setAgentId} />
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
