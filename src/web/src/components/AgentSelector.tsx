import { useEffect, useState } from 'react'
import { listAgents, type AgentInfo } from '../api/copilotkit'

interface AgentSelectorProps {
  value: string
  onChange: (agentId: string) => void
}

export function AgentSelector({ value, onChange }: AgentSelectorProps) {
  const [agents, setAgents] = useState<AgentInfo[]>([])
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)

  useEffect(() => {
    listAgents()
      .then((data) => {
        setAgents(data.agents)
        setLoading(false)
      })
      .catch((err) => {
        setError(err instanceof Error ? err.message : String(err))
        setLoading(false)
      })
  }, [])

  if (loading) return <div className="p-2 text-sm text-gray-500">加载中...</div>
  if (error) return <div className="p-2 text-sm text-red-500">{error}</div>

  return (
    <div className="p-3 border-b border-gray-200">
      <label className="block text-xs font-medium text-gray-500 mb-1">Agent</label>
      <select
        className="w-full rounded border border-gray-300 bg-white px-2 py-1 text-sm"
        value={value}
        onChange={(e) => onChange(e.target.value)}
      >
        {agents.map((agent) => (
          <option key={agent.name} value={agent.name}>
            {agent.name}
          </option>
        ))}
      </select>
    </div>
  )
}
