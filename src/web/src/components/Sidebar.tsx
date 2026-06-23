import { useEffect, useState } from 'react'
import { listAgents } from '../api'

export default function Sidebar({
  assistantId,
  setAssistantId,
}: {
  assistantId: string
  setAssistantId: (id: string) => void
}) {
  const [agents, setAgents] = useState<Array<{ name: string; type: string }>>([])

  useEffect(() => {
    listAgents().then((data) => setAgents(data.agents)).catch(() => {})
    const interval = setInterval(() => {
      listAgents().then((data) => setAgents(data.agents)).catch(() => {})
    }, 5000)
    return () => clearInterval(interval)
  }, [])

  return (
    <aside className="w-64 bg-white border-r flex flex-col">
      <div className="p-4 border-b">
        <h2 className="font-semibold text-gray-800">Agents</h2>
      </div>
      <div className="flex-1 overflow-y-auto p-2 space-y-1">
        {agents.length === 0 && (
          <div className="text-sm text-gray-400 p-2">No agents registered yet</div>
        )}
        {agents.map((agent) => (
          <button
            key={agent.name}
            onClick={() => setAssistantId(agent.name)}
            className={`w-full text-left rounded-md px-3 py-2 text-sm transition ${
              assistantId === agent.name
                ? 'bg-blue-100 text-blue-800 font-medium'
                : 'hover:bg-gray-100 text-gray-700'
            }`}
          >
            {agent.name}
          </button>
        ))}
      </div>
    </aside>
  )
}
