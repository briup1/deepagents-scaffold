import { useState } from 'react'

export default function MessageInput({
  onSend,
  disabled,
}: {
  onSend: (text: string) => void
  disabled: boolean
}) {
  const [text, setText] = useState('')

  const handleSubmit = (e: React.FormEvent) => {
    e.preventDefault()
    if (!text.trim() || disabled) return
    onSend(text.trim())
    setText('')
  }

  return (
    <form onSubmit={handleSubmit} className="flex gap-2 p-4 bg-white border-t">
      <input
        type="text"
        value={text}
        onChange={(e) => setText(e.target.value)}
        placeholder="Type a message..."
        disabled={disabled}
        className="flex-1 rounded-lg border border-gray-300 px-4 py-2 focus:outline-none focus:ring-2 focus:ring-blue-500 disabled:bg-gray-100"
      />
      <button
        type="submit"
        disabled={disabled || !text.trim()}
        className="rounded-lg bg-blue-600 px-6 py-2 text-white font-medium hover:bg-blue-700 disabled:opacity-50"
      >
        Send
      </button>
    </form>
  )
}
