import type { ThreadSummary } from '../api/threads'

interface ThreadListProps {
  threads: ThreadSummary[]
  currentThreadId: string
  /** 正在运行 Agent 的会话 id，对应条目显示运行中指示 */
  runningThreadId?: string | null
  onSelectThread: (threadId: string, agentId: string) => void
}

export function ThreadList({ threads, currentThreadId, runningThreadId, onSelectThread }: ThreadListProps) {
  if (threads.length === 0) {
    return (
      <div className="px-3 py-4 text-xs text-ink-subtle">
        暂无历史会话，开始一段新对话吧。
      </div>
    )
  }

  return (
    <ul className="flex flex-col gap-1 px-2" role="listbox" aria-label="历史会话">
      {threads.map((thread) => {
        const isActive = thread.thread_id === currentThreadId
        const displayTitle = thread.title || thread.last_message_preview || '新会话'
        const showPreview = thread.last_message_preview && displayTitle !== thread.last_message_preview
        return (
          <li key={thread.thread_id} role="option" aria-selected={isActive}>
            <button
              type="button"
              aria-label={displayTitle}
              onClick={() => onSelectThread(thread.thread_id, thread.agent_id)}
              className={`
                w-full rounded-lg px-3 py-2 text-left text-sm transition-colors
                ${isActive ? 'bg-cream-200 text-ink' : 'text-ink-muted hover:bg-cream-100'}
              `}
            >
              <div className="flex items-center gap-2 font-medium">
                <span className="truncate">{displayTitle}</span>
                {thread.thread_id === runningThreadId && (
                  <span
                    data-testid="thread-running-indicator"
                    aria-label="运行中"
                    className="h-2 w-2 shrink-0 animate-pulse rounded-full bg-emerald-500"
                  />
                )}
              </div>
              {showPreview && (
                <div className="mt-0.5 truncate text-xs opacity-70">
                  {thread.last_message_preview}
                </div>
              )}
            </button>
          </li>
        )
      })}
    </ul>
  )
}
