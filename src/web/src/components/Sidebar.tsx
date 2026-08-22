import { useEffect, useState } from 'react'
import type { AgentInfo } from '../api/copilotkit'
import { listThreads, type ThreadSummary } from '../api/threads'
import { AgentSelector } from './AgentSelector'
import { NewChatButton } from './NewChatButton'
import { ThreadList } from './ThreadList'

interface SidebarProps {
  agents: AgentInfo[]
  currentAgentId: string
  threadId: string
  onAgentChange: (agentId: string) => void
  onNewChat: () => void
  onSelectThread: (threadId: string, agentId: string) => void
}

function SparkleIcon() {
  return (
    <svg
      xmlns="http://www.w3.org/2000/svg"
      width="20"
      height="20"
      viewBox="0 0 24 24"
      fill="none"
      stroke="currentColor"
      strokeWidth="2"
      strokeLinecap="round"
      strokeLinejoin="round"
      aria-hidden="true"
    >
      <path d="M9.937 15.5A2 2 0 0 0 8.5 14.063l-6.135-1.582a.5.5 0 0 1 0-.962L8.5 9.936A2 2 0 0 0 9.937 8.5l1.582-6.135a.5.5 0 0 1 .962 0L14.063 8.5A2 2 0 0 0 15.5 9.937l6.135 1.582a.5.5 0 0 1 0 .962L15.5 14.063a2 2 0 0 0-1.437 1.437l-1.582 6.135a.5.5 0 0 1-.962 0z" />
    </svg>
  )
}

export function Sidebar({
  agents,
  currentAgentId,
  threadId,
  onAgentChange,
  onNewChat,
  onSelectThread,
}: SidebarProps) {
  const [threads, setThreads] = useState<ThreadSummary[]>([])
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)

  useEffect(() => {
    let cancelled = false
    setLoading(true)
    setError(null)
    listThreads(currentAgentId)
      .then((data) => {
        if (!cancelled) setThreads(data.threads)
      })
      .catch((err) => {
        if (!cancelled) setError(err instanceof Error ? err.message : String(err))
      })
      .finally(() => {
        if (!cancelled) setLoading(false)
      })
    return () => {
      cancelled = true
    }
  }, [currentAgentId])

  const threadDisplay = threadId.replace(/^thread-/, '').slice(0, 8)

  return (
    <aside
      className="flex h-screen w-64 flex-col border-r border-cream-300 bg-white"
      aria-label="导航侧边栏"
    >
      <div className="flex items-center gap-2 px-4 py-4">
        <div className="flex h-8 w-8 items-center justify-center rounded-lg bg-ink text-white">
          <SparkleIcon />
        </div>
        <span className="text-lg font-semibold tracking-tight text-ink">DeepAgents</span>
      </div>

      <div className="px-3 py-2">
        <NewChatButton onClick={onNewChat} />
      </div>

      <nav className="flex-1 overflow-y-auto px-3 py-4">
        <div className="space-y-1.5">
          <label className="px-1 text-xs font-medium text-ink-subtle">当前 Agent</label>
          <AgentSelector
            value={currentAgentId}
            onChange={onAgentChange}
            agents={agents}
          />
        </div>

        <div className="mt-6 px-1">
          <div className="mb-2 text-xs font-medium text-ink-subtle">历史会话</div>
          {loading ? (
            <div className="px-2 py-2 text-xs text-ink-muted">加载中...</div>
          ) : error ? (
            <div className="px-2 py-2 text-xs text-red-500">{error}</div>
          ) : (
            <ThreadList
              threads={threads}
              currentThreadId={threadId}
              onSelectThread={onSelectThread}
            />
          )}
        </div>

        <div className="mt-6 px-1">
          <p className="text-xs leading-relaxed text-ink-muted">
            选择一个 Agent 开始对话。切换 Agent 会自动新建会话。
          </p>
        </div>
      </nav>

      <div className="border-t border-cream-300 px-4 py-3">
        <div className="flex items-center justify-between text-xs text-ink-muted">
          <span>当前会话</span>
          <span className="font-mono">{threadDisplay}</span>
        </div>
      </div>
    </aside>
  )
}
