import { useAgent } from '@copilotkit/react-core/v2'
import { useCallback } from 'react'
import { randomUUID } from '../lib/uuid'

export function useGenerativeUIAction(agentId: string) {
  const { agent } = useAgent({ agentId })

  return useCallback(
    async (action: unknown) => {
      if (!agent) {
        console.warn('[useGenerativeUIAction] agent 尚未初始化')
        return
      }
      agent.addMessage({
        id: randomUUID(),
        role: 'user',
        content: JSON.stringify(action),
      })
      try {
        await agent.runAgent()
      } catch (error) {
        console.error('[useGenerativeUIAction] agent 执行失败', error)
      }
    },
    [agent],
  )
}
