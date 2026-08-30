import { useState } from 'react'

interface TokenGateProps {
  onSave: (token: string) => void
}

/**
 * API Token 输入页：后端启用认证时显示，token 存入 localStorage。
 * 只要求输入非空字符串，不校验格式（校验由后端在首个请求时完成，
 * 失败会触发 401 → 全局登出回到本页）。
 */
export function TokenGate({ onSave }: TokenGateProps) {
  const [value, setValue] = useState('')
  const [error, setError] = useState<string | null>(null)

  const handleSubmit = (e: React.FormEvent) => {
    e.preventDefault()
    if (!value.trim()) {
      setError('请输入访问令牌')
      return
    }
    setError(null)
    onSave(value)
  }

  return (
    <div className="flex h-screen w-screen items-center justify-center bg-cream-50">
      <form
        onSubmit={handleSubmit}
        className="w-full max-w-sm rounded-2xl border border-cream-300 bg-white p-8 shadow-card"
      >
        <h1 className="text-xl font-semibold text-ink">访问令牌</h1>
        <p className="mt-2 text-sm text-ink-muted">
          请输入部署时分配的 API Token（管理员在部署配置中生成）。
        </p>
        <input
          type="password"
          value={value}
          onChange={(e) => setValue(e.target.value)}
          placeholder="粘贴 Token"
          autoFocus
          className="mt-5 w-full rounded-lg border border-cream-300 bg-white px-3 py-2 text-sm text-ink outline-none focus:border-ink focus:ring-2 focus:ring-cream-300"
        />
        {error && <p className="mt-2 text-sm text-red-600">{error}</p>}
        <button
          type="submit"
          className="mt-5 w-full rounded-lg bg-ink px-4 py-2 text-sm font-medium text-white transition hover:bg-ink-soft"
        >
          进入
        </button>
      </form>
    </div>
  )
}
