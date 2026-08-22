import { useEffect, useRef, useState } from 'react'
import { listAgents, type AgentInfo } from '../api/copilotkit'

interface AgentSelectorProps {
  value: string
  onChange: (agentId: string) => void
  agents?: AgentInfo[]
}

function ChevronIcon({ open }: { open: boolean }) {
  return (
    <svg
      xmlns="http://www.w3.org/2000/svg"
      width="16"
      height="16"
      viewBox="0 0 24 24"
      fill="none"
      stroke="currentColor"
      strokeWidth="2"
      strokeLinecap="round"
      strokeLinejoin="round"
      className={`transition-transform duration-200 ${open ? 'rotate-180' : ''}`}
      aria-hidden="true"
    >
      <polyline points="6 9 12 15 18 9" />
    </svg>
  )
}

export function AgentSelector({ value, onChange, agents: agentsProp }: AgentSelectorProps) {
  const [agents, setAgents] = useState<AgentInfo[]>(agentsProp ?? [])
  const [loading, setLoading] = useState(!agentsProp)
  const [error, setError] = useState<string | null>(null)
  const [open, setOpen] = useState(false)
  const containerRef = useRef<HTMLDivElement>(null)

  useEffect(() => {
    if (agentsProp) {
      setAgents(agentsProp)
      setLoading(false)
      setError(null)
      return
    }

    setLoading(true)
    listAgents()
      .then((data) => {
        setAgents(data.agents)
        setLoading(false)
      })
      .catch((err) => {
        setError(err instanceof Error ? err.message : String(err))
        setLoading(false)
      })
  }, [agentsProp])

  useEffect(() => {
    function handleClickOutside(event: MouseEvent) {
      if (containerRef.current && !containerRef.current.contains(event.target as Node)) {
        setOpen(false)
      }
    }
    document.addEventListener('mousedown', handleClickOutside)
    return () => document.removeEventListener('mousedown', handleClickOutside)
  }, [])

  const currentAgent = agents.find((a) => a.name === value) ?? agents[0]

  if (loading) {
    return (
      <div className="h-10 w-full animate-pulse rounded-xl bg-cream-200" aria-label="加载 Agent 列表" />
    )
  }
  if (error) {
    return <div className="rounded-lg bg-red-50 px-3 py-2 text-sm text-red-600">{error}</div>
  }

  return (
    <div ref={containerRef} className="relative w-full">
      <button
        type="button"
        onClick={() => setOpen((prev) => !prev)}
        className="flex w-full items-center justify-between gap-2 rounded-xl border border-cream-300 bg-white px-3 py-2 text-sm font-medium text-ink shadow-soft transition hover:border-cream-300 hover:shadow-input focus:outline-none focus:ring-2 focus:ring-blue-500/20"
        aria-label="选择 Agent"
        aria-haspopup="listbox"
        aria-expanded={open}
      >
        <span className="truncate">{currentAgent?.name ?? value}</span>
        <ChevronIcon open={open} />
      </button>

      {open && (
        <div
          className="absolute left-0 right-0 top-full z-50 mt-1 rounded-xl border border-cream-300 bg-white py-1 shadow-card"
          role="listbox"
        >
          {agents.map((agent) => (
            <button
              key={agent.name}
              type="button"
              role="option"
              aria-selected={agent.name === value}
              onClick={() => {
                onChange(agent.name)
                setOpen(false)
              }}
              className={`w-full px-3 py-2 text-left text-sm transition hover:bg-cream-100 ${
                agent.name === value ? 'bg-cream-100 font-medium text-ink' : 'text-ink-muted'
              }`}
            >
              {agent.name}
            </button>
          ))}
        </div>
      )}
    </div>
  )
}
