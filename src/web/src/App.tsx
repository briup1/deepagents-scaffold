import { useCallback, useEffect, useMemo, useRef, useState } from 'react'
import { CopilotKit, CopilotChat, useAgent } from '@copilotkit/react-core/v2'
import { listAgents, type AgentInfo } from './api/copilotkit'
import { type ThreadSummary } from './api/threads'
import { HistoryHttpAgent } from './api/historyAgent'
import { type UploadedFile } from './api/files'
import { mergePendingThread, useThreads } from './hooks/useThreads'
import { Sidebar } from './components/Sidebar'
import { FileUploadDropzone, FileAttachmentList } from './components/FileUploadDropzone'
import { GenerativeUIContext } from './catalog/GenerativeUIContext'
import { useGenerativeUITool } from './hooks/useGenerativeUITool'
import { useGenerativeUIAction } from './hooks/useGenerativeUIAction'
import { randomUUID } from './lib/uuid'

interface ChatShellProps {
  agents: AgentInfo[]
  currentAgentId: string
  threadId: string
  onFirstUserMessage: (threadId: string, content: string) => void
  onRunStateChange: (threadId: string, running: boolean) => void
}

interface ChatInnerProps {
  agentId: string
  threadId: string
  onFirstUserMessage: (threadId: string, content: string) => void
  onRunStateChange: (threadId: string, running: boolean) => void
}

function ChatInner({ agentId, threadId, onFirstUserMessage, onRunStateChange }: ChatInnerProps) {
  useGenerativeUITool()
  const { agent, isReady } = useAgent({ agentId })
  const dispatch = useGenerativeUIAction(agentId)
  const [uploadedFiles, setUploadedFiles] = useState<UploadedFile[]>([])
  const pendingFilesRef = useRef<UploadedFile[]>([])

  // agent 未 ready 时上传的文件先入暂存队列，ready 后落盘到状态
  useEffect(() => {
    if (!isReady) return
    if (pendingFilesRef.current.length > 0) {
      setUploadedFiles((prev) => [...prev, ...pendingFilesRef.current])
      pendingFilesRef.current = []
    }
  }, [isReady])

  // 文件上传后向 agent 追加一条合成用户消息（携带 artifact_id 供工具抽取）。
  // 若 connectAgent 的历史回放清空了本地消息（消息未随 run 落库），这里靠
  // “消息列表中不存在同 id 条目”的判断重新追加，无需额外防御机制。
  // 注意：deps 用 agent.messages.length 而非 agent.messages——
  // ag-ui 的 addMessage 是原地 push，数组引用不变，length 才能触发 effect
  useEffect(() => {
    if (!isReady || uploadedFiles.length === 0) return
    const key = uploadedFiles.map((f) => f.artifact_id).join('-')
    const messageId = `files-${key}`
    if (agent.messages.some((m) => m.id === messageId)) return
    agent.addMessage({
      id: messageId,
      role: 'user',
      content: `已上传以下文件，可用于后续抽取分析：\n${uploadedFiles.map((file, index) => `${index + 1}. ${file.original_name}（artifact_id: ${file.artifact_id}）`).join('\n')}`,
    })
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [isReady, uploadedFiles, agent, agent.messages.length])

  // 首条用户消息出现时通知外层（用于更新侧栏占位条目标题）。
  // 历史回放产生的用户消息不会误触发：App 层会校验 threadId 与占位状态。
  const firstMessageNotifiedRef = useRef(false)
  useEffect(() => {
    if (!isReady || firstMessageNotifiedRef.current) return
    const firstUser = agent.messages.find(
      (m) => m.role === 'user' && typeof m.content === 'string' && !m.id.startsWith('files-'),
    )
    if (firstUser && typeof firstUser.content === 'string' && firstUser.content.length > 0) {
      firstMessageNotifiedRef.current = true
      onFirstUserMessage(threadId, firstUser.content)
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [agent.messages.length, isReady, threadId, onFirstUserMessage])

  // 订阅 isRunning 边沿，run 开始/结束时通知外层（驱动运行中指示与列表 refetch）
  const prevRunningRef = useRef(false)
  useEffect(() => {
    if (!isReady) return
    const running = Boolean(agent.isRunning)
    if (running !== prevRunningRef.current) {
      prevRunningRef.current = running
      onRunStateChange(threadId, running)
    }
  }, [agent.isRunning, isReady, threadId, onRunStateChange])

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

function ChatShell({ agents, currentAgentId, threadId, onFirstUserMessage, onRunStateChange }: ChatShellProps) {
  // 把所有已注册 Agent 都交给 CopilotKit，否则切换 Agent 时 useAgent
  // 内部 known agents 只有当前一个，导致报错。
  // HistoryHttpAgent 在 threadId 切换时从后端回放历史消息；
  // 显式传入 agentId 让 CopilotKitCore 的 restore 跟踪键稳定。
  const agentMap = useMemo(() => {
    const map: Record<string, HistoryHttpAgent> = {}
    for (const agent of agents) {
      const url = agents.length === 1 ? '/agent' : `/agent/${agent.name}`
      map[agent.name] = new HistoryHttpAgent({ url, threadId, agentId: agent.name })
    }
    return map
  }, [agents, threadId])

  return (
    <CopilotKit agents__unsafe_dev_only={agentMap}>
      <ChatInner
        agentId={currentAgentId}
        threadId={threadId}
        onFirstUserMessage={onFirstUserMessage}
        onRunStateChange={onRunStateChange}
      />
    </CopilotKit>
  )
}

export default function App() {
  const [threadId, setThreadId] = useState(() => `thread-${randomUUID()}`)
  const [agents, setAgents] = useState<AgentInfo[]>([])
  const [loadingAgents, setLoadingAgents] = useState(true)
  const [agentError, setAgentError] = useState<string | null>(null)
  const [agentId, setAgentId] = useState<string | null>(null)
  // 本地乐观占位条目：新建会话时设置，服务器条目落库后清除
  const [pendingThread, setPendingThread] = useState<ThreadSummary | null>(null)
  const [runningThreadId, setRunningThreadId] = useState<string | null>(null)

  const currentAgentId = agentId ?? agents[0]?.name ?? ''
  const { threads, loading: threadsLoading, error: threadsError, refetch } = useThreads(currentAgentId)

  // 渲染列表 = 服务器列表 + 本地占位（按 threadId 去重，占位置顶）
  const mergedThreads = useMemo(
    () => mergePendingThread(threads, pendingThread, currentAgentId),
    [threads, pendingThread, currentAgentId],
  )

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

  // 首条用户消息：占位条目标题本地截取前 20 字，立即生效。
  // 历史回放的旧消息不会命中：占位条目只可能属于当前全新会话的 threadId。
  const handleFirstUserMessage = useCallback((msgThreadId: string, content: string) => {
    setPendingThread((p) =>
      p && p.thread_id === msgThreadId && p.title === '新会话'
        ? { ...p, title: content.slice(0, 20) || '新会话' }
        : p,
    )
  }, [])

  // run 开始显示运行中指示；run 结束触发 refetch，服务器条目落库后清除占位完成收敛
  const handleRunStateChange = useCallback(
    async (runThreadId: string, running: boolean) => {
      setRunningThreadId(running ? runThreadId : null)
      if (running) return
      const latest = await refetch()
      setPendingThread((p) => (p && latest.some((t) => t.thread_id === p.thread_id) ? null : p))
    },
    [refetch],
  )

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
      <div className="flex h-screen w-screen overflow-hidden bg-cream-50 p-4">
        <div className="max-w-md rounded-2xl border border-red-200 bg-white p-6 shadow-card">
          <h1 className="text-lg font-semibold text-red-600">加载失败</h1>
          <p className="mt-2 text-sm text-ink-muted">{agentError}</p>
        </div>
      </div>
    )
  }

  const effectiveAgentId = currentAgentId || 'default'

  const handleNewChat = () => {
    // 当前会话仍是未发消息的空占位时复用，不产生第二个占位条目
    if (pendingThread && pendingThread.thread_id === threadId && pendingThread.title === '新会话') {
      return
    }
    // 旧占位已发消息但尚未收敛时，先刷新一次列表避免其从侧栏丢失
    if (pendingThread) void refetch()
    const id = `thread-${randomUUID()}`
    const now = new Date().toISOString()
    setThreadId(id)
    setPendingThread({
      thread_id: id,
      agent_id: effectiveAgentId,
      title: '新会话',
      last_message_preview: null,
      created_at: now,
      updated_at: now,
    })
  }

  const handleAgentChange = (nextAgentId: string) => {
    if (nextAgentId === currentAgentId) return
    setAgentId(nextAgentId)
    setThreadId(`thread-${randomUUID()}`)
    // 切换 Agent 后清除占位条目，避免跨 Agent 泄漏
    setPendingThread(null)
  }

  const handleSelectThread = (selectedThreadId: string, selectedAgentId: string) => {
    if (selectedThreadId === threadId) return
    // 空会话占位（从未发消息）切走后不留痕
    if (pendingThread && pendingThread.title === '新会话') setPendingThread(null)
    if (selectedAgentId !== currentAgentId && agents.some((a) => a.name === selectedAgentId)) {
      setAgentId(selectedAgentId)
    }
    // 历史消息由 HistoryHttpAgent.connectAgent 在新 threadId 挂载时回放，无需在此拉取
    setThreadId(selectedThreadId)
  }

  return (
    <div className="flex h-screen w-screen overflow-hidden bg-cream-50">
      <Sidebar
        agents={agents}
        currentAgentId={effectiveAgentId}
        threadId={threadId}
        threads={mergedThreads}
        threadsLoading={threadsLoading}
        threadsError={threadsError}
        runningThreadId={runningThreadId}
        onAgentChange={handleAgentChange}
        onNewChat={handleNewChat}
        onSelectThread={handleSelectThread}
      />
      <ChatShell
        key={threadId}
        agents={agents}
        currentAgentId={effectiveAgentId}
        threadId={threadId}
        onFirstUserMessage={handleFirstUserMessage}
        onRunStateChange={handleRunStateChange}
      />
    </div>
  )
}
