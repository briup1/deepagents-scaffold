import { useCallback, useEffect, useRef, useState } from 'react'
import { listThreads, type ThreadSummary } from '../api/threads'

/**
 * 会话列表 hook：按 Agent 过滤拉取，暴露 refetch 供外部在 run 完成后失效刷新。
 * refetch 期间保留旧数据，避免列表闪回加载态。
 */
export function useThreads(agentId: string) {
  const [threads, setThreads] = useState<ThreadSummary[]>([])
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)
  // 序号 + agentId 双重校验，丢弃切换 Agent 后姗姗来迟的过期响应
  const seqRef = useRef(0)
  const agentIdRef = useRef(agentId)
  agentIdRef.current = agentId

  const refetch = useCallback(async (): Promise<ThreadSummary[]> => {
    if (!agentId) {
      setThreads([])
      setLoading(false)
      return []
    }
    const seq = ++seqRef.current
    try {
      const data = await listThreads(agentId)
      if (seq !== seqRef.current || agentIdRef.current !== agentId) return []
      setThreads(data.threads)
      setError(null)
      return data.threads
    } catch (err) {
      if (seq === seqRef.current && agentIdRef.current === agentId) {
        setError(err instanceof Error ? err.message : String(err))
      }
      return []
    } finally {
      if (seq === seqRef.current && agentIdRef.current === agentId) {
        setLoading(false)
      }
    }
  }, [agentId])

  useEffect(() => {
    setLoading(true)
    void refetch()
  }, [refetch])

  return { threads, loading, error, refetch }
}

/**
 * 将本地乐观占位条目合并进服务器列表：按 threadId 去重（服务器条目优先），
 * 占位条目置顶；其他 Agent 的占位条目不混入当前列表。
 */
export function mergePendingThread(
  threads: ThreadSummary[],
  pending: ThreadSummary | null,
  currentAgentId: string,
): ThreadSummary[] {
  if (!pending || pending.agent_id !== currentAgentId) return threads
  if (threads.some((t) => t.thread_id === pending.thread_id)) return threads
  return [pending, ...threads]
}
