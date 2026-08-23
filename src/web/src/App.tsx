import { useCallback, useEffect, useMemo, useRef, useState } from 'react'
import { CopilotKit, CopilotChat, useAgent } from '@copilotkit/react-core/v2'
import { HttpAgent } from '@ag-ui/client'
import { listAgents, type AgentInfo } from './api/copilotkit'
import { getThreadMessages, type ThreadMessage } from './api/threads'
import { type UploadedFile } from './api/files'
import { Sidebar } from './components/Sidebar'
import { FileUploadDropzone, FileAttachmentList } from './components/FileUploadDropzone'
import { GenerativeUIContext } from './catalog/GenerativeUIContext'
import { useGenerativeUITool } from './hooks/useGenerativeUITool'
import { useGenerativeUIAction } from './hooks/useGenerativeUIAction'

interface ChatShellProps {
  agents: AgentInfo[]
  currentAgentId: string
  threadId: string
  initialMessages: ThreadMessage[]
}

interface AgentToolCall {
  id: string
  type: 'function'
  function: {
    name: string
    arguments: string
  }
}

interface AgentMessage {
  id: string
  role: 'user' | 'assistant' | 'tool' | 'system'
  content?: string
  name?: string
  toolCallId?: string
  toolCalls?: AgentToolCall[]
}

interface ThreadToolCall {
  id?: string
  function?: {
    name?: string
    arguments?: string | Record<string, unknown>
  }
}

function toAgentMessage(m: ThreadMessage): AgentMessage | null {
  // 前端聊天界面只需要展示 user/assistant/tool 三类消息
  if (m.role !== 'user' && m.role !== 'assistant' && m.role !== 'tool') {
    return null
  }

  const base: AgentMessage = {
    id: m.message_id,
    role: m.role,
    content: m.content ?? undefined,
    name: m.name ?? undefined,
  }

  if (m.role === 'assistant' && m.tool_calls && m.tool_calls.length > 0) {
    base.toolCalls = (m.tool_calls as ThreadToolCall[]).map((tc) => {
      const fn = tc.function ?? {}
      const args = fn.arguments ?? {}
      return {
        id: String(tc.id ?? crypto.randomUUID()),
        type: 'function' as const,
        function: {
          name: String(fn.name ?? ''),
          arguments: typeof args === 'string' ? args : JSON.stringify(args),
        },
      }
    })
  }

  if (m.role === 'tool') {
    base.toolCallId = m.tool_call_id ?? m.message_id
  }

  return base
}

interface ChatInnerProps {
  agentId: string
  threadId: string
  initialMessages: ThreadMessage[]
}

function ChatInner({ agentId, threadId, initialMessages }: ChatInnerProps) {
  useGenerativeUITool()
  const { agent, isReady } = useAgent({ agentId })
  const dispatch = useGenerativeUIAction(agentId)
  const hasInjectedRef = useRef(false)
  const [uploadedFiles, setUploadedFiles] = useState<UploadedFile[]>([])
  const pendingFilesRef = useRef<UploadedFile[]>([])

  const injectMessages = useCallback(() => {
    if (!isReady) return
    const historyMessages = initialMessages
      .map(toAgentMessage)
      .filter((m): m is AgentMessage => m !== null)
    const fileMessages: AgentMessage[] =
      uploadedFiles.length === 0
        ? []
        : [
            {
              id: `files-${uploadedFiles.map((f) => f.artifact_id).join('-')}`,
              role: 'user',
              content: `已上传以下文件，可用于后续抽取分析：\n${uploadedFiles.map((file, index) => `${index + 1}. ${file.original_name}（artifact_id: ${file.artifact_id}）`).join('\n')}`,
            },
          ]
    agent.setMessages(
      [...historyMessages, ...fileMessages] as Parameters<typeof agent.setMessages>[0],
    )
    hasInjectedRef.current = true
  }, [isReady, initialMessages, uploadedFiles, agent])

  useEffect(() => {
    if (!isReady) return
    if (pendingFilesRef.current.length > 0) {
      setUploadedFiles((prev) => [...prev, ...pendingFilesRef.current])
      pendingFilesRef.current = []
    }
  }, [isReady])

  useEffect(() => {
    if (!isReady || (initialMessages.length === 0 && uploadedFiles.length === 0)) return
    injectMessages()
  }, [isReady, initialMessages, uploadedFiles, injectMessages])

  useEffect(() => {
    if (!isReady || initialMessages.length === 0) return
    if (hasInjectedRef.current && agent.messages.length === 0) {
      injectMessages()
    }
  }, [agent.messages.length, isReady, initialMessages, uploadedFiles, injectMessages])

  // 在 agent ready 时注入历史消息
  useEffect(() => {
    if (!isReady || initialMessages.length === 0) return
    injectMessages()
  }, [isReady, initialMessages, injectMessages])

  // 防御性重注：若外部（如 CopilotChat connectAgent）将消息清空到 0，则重新注入
  useEffect(() => {
    if (!isReady || initialMessages.length === 0) return
    if (hasInjectedRef.current && agent.messages.length === 0) {
      injectMessages()
    }
  }, [agent.messages.length, isReady, initialMessages, injectMessages])

  const handleFileUploaded = useCallback((file: UploadedFile) => {
    if (isReady && agent) {
      setUploadedFiles((prev) => [...prev, file])
    } else {
      pendingFilesRef.current.push(file)
    }
  }, [isReady, agent])

  const handleRemoveFile = useCallback((artifactId: string) => {
    setUploadedFiles((prev) => prev.filter((f) => f.artifact_id !== artifactId))
  }, [])

  const [uploadError, setUploadError] = useState<string | null>(null)

  const handleDropzoneError = useCallback((message: string) => {
    setUploadError(message)
  }, [])

  const clearUploadError = useCallback(() => {
    setUploadError(null)
  }, [])

  return (
    <GenerativeUIContext.Provider value={{ dispatch }}>
      <FileUploadDropzone
        threadId={threadId}
        onFileUploaded={handleFileUploaded}
        onError={handleDropzoneError}
      >
        <main className="flex h-full flex-1 flex-col overflow-hidden">
          {uploadError && (
            <div className="absolute right-4 top-4 z-50 rounded-lg bg-red-100 px-4 py-2 text-sm text-red-700 shadow">
              <button
                type="button"
                onClick={clearUploadError}
                className="mr-2 font-bold"
                aria-label="关闭错误提示"
              >
                ×
              </button>
              {uploadError}
            </div>
          )}
          {uploadedFiles.length > 0 && (
            <div className="border-b border-cream-200 bg-white px-4 py-3">
              <FileAttachmentList files={uploadedFiles} onRemove={handleRemoveFile} />
            </div>
          )}
          <CopilotChat
            agentId={agentId}
            threadId={threadId}
            className="h-full"
            labels={{
              chatInputPlaceholder: uploadedFiles.length > 0 ? '输入消息...' : '拖拽 Excel 到此处或输入消息...',
              welcomeMessageText: '有什么可以帮你的？',
              modalHeaderTitle: 'DeepAgents Chat',
            }}
          />
        </main>
      </FileUploadDropzone>
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
    <CopilotKit agents__unsafe_dev_only={agentMap}>
      <ChatInner agentId={currentAgentId} threadId={threadId} initialMessages={initialMessages} />
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
