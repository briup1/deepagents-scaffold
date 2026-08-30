/**
 * API Token 管理：localStorage 持久化 + 统一请求头注入 + 401 全局登出。
 *
 * 后端启用认证时（config.yaml auth.enabled），所有 /api 与 /agent 请求
 * 都要求 X-API-Key 头；未配置 token 或 token 失效时，界面回到 Token 输入页。
 */

const STORAGE_KEY = 'scaffold_token'

type UnauthorizedListener = () => void
const listeners = new Set<UnauthorizedListener>()

export function getToken(): string | null {
  return localStorage.getItem(STORAGE_KEY)
}

export function setToken(token: string): void {
  localStorage.setItem(STORAGE_KEY, token.trim())
}

export function clearToken(): void {
  localStorage.removeItem(STORAGE_KEY)
}

/** 订阅 401 事件（token 失效时界面需回到输入页）。返回退订函数。 */
export function onUnauthorized(listener: UnauthorizedListener): () => void {
  listeners.add(listener)
  return () => listeners.delete(listener)
}

/**
 * 带认证的 fetch 封装：注入 X-API-Key；收到 401 时清空 token 并通知订阅者。
 * 未配置 token 时行为与原生 fetch 完全一致（init 无额外字段），
 * 方便未启用认证的环境零成本接入。
 */
export async function apiFetch(input: string | URL | Request, init?: RequestInit): Promise<Response> {
  const token = getToken()
  let res: Response
  if (token) {
    const headers = new Headers(init?.headers)
    headers.set('X-API-Key', token)
    res = await fetch(input, init ? { ...init, headers } : { headers })
  } else {
    // 未配置 token 时按原始签名转发，保持与原生 fetch 一致（调用方测试不受影响）
    res = init ? await fetch(input, init) : await fetch(input)
  }
  // 401 无论是否携带 token 都要处理：auth 开启时首个未授权请求即触发登录页
  if (res.status === 401) {
    clearToken()
    for (const listener of listeners) listener()
  }
  return res
}
