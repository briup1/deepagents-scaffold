export async function fetchJson<T>(
  input: RequestInfo | URL,
  init?: RequestInit,
  errorPrefix = 'HTTP',
): Promise<T> {
  let response: Response
  try {
    response = init === undefined ? await fetch(input) : await fetch(input, init)
  } catch {
    throw new Error('网络请求失败')
  }

  if (!response.ok) {
    const detail = typeof response.text === 'function' ? await response.text().catch(() => '') : ''
    const message = errorPrefix === 'HTTP'
      ? `HTTP ${response.status}`
      : `${errorPrefix} (${response.status})${detail ? `: ${detail}` : ''}`
    throw new Error(message)
  }

  try {
    return await response.json() as T
  } catch {
    throw new Error('服务器返回了无效 JSON')
  }
}
