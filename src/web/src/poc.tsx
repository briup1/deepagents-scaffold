import { useState } from 'react'
import ReactDOM from 'react-dom/client'
import { HttpAgent } from '@ag-ui/client'

function PocApp() {
  const [logs, setLogs] = useState<string[]>([])
  const [input, setInput] = useState('hello')
  const [threadId] = useState(() => `poc-thread-${Date.now()}`)

  const send = async () => {
    setLogs((prev) => [...prev, `==> threadId=${threadId} send: ${input}`])
    const agent = new HttpAgent({
      url: '/agent',
      threadId,
    })
    agent.addMessage({ id: `msg-${Date.now()}`, role: 'user', content: input })
    await agent.runAgent(
      { runId: `poc-run-${Date.now()}` },
      {
        onRunStartedEvent: ({ event }: any) => {
          setLogs((prev) => [...prev, `EVENT: ${event.type}`])
        },
        onTextMessageContentEvent: ({ event }: any) => {
          setLogs((prev) => [...prev, `TEXT: ${event.delta}`])
        },
        onToolCallStartEvent: ({ event }: any) => {
          setLogs((prev) => [...prev, `TOOL: ${event.toolCallName}`])
        },
        onRunFinishedEvent: () => {
          setLogs((prev) => [...prev, 'COMPLETE'])
        },
        onRunErrorEvent: ({ event }: any) => {
          setLogs((prev) => [...prev, `ERROR: ${JSON.stringify(event)}`])
        },
      },
    )
  }

  return (
    <div style={{ padding: 20, fontFamily: 'sans-serif' }}>
      <h1>AG-UI PoC</h1>
      <div>
        <input value={input} onChange={(e) => setInput(e.target.value)} style={{ width: 300 }} />
        <button onClick={send} style={{ marginLeft: 8 }}>Send</button>
      </div>
      <pre style={{ marginTop: 20, background: '#f5f5f5', padding: 12 }}>{logs.join('\n')}</pre>
    </div>
  )
}

ReactDOM.createRoot(document.getElementById('root')!).render(<PocApp />)
