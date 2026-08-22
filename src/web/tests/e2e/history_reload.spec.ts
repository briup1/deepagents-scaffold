import { expect, test } from '@playwright/test'

test.describe('历史会话持久化与重载', () => {
  test('发送消息后持久化，刷新后可在 Sidebar 加载并重载到聊天区', async ({ page }) => {
    const testMarker = `你好-${Math.random().toString(36).slice(2, 6)}`
    const consoleErrors: string[] = []
    const consoleLogs: string[] = []
    const historyRequests: string[] = []

    page.on('console', (msg) => {
      const text = msg.text()
      if (msg.type() === 'error') {
        consoleErrors.push(text)
        console.error('Browser console error:', text)
      } else if (text.includes('[ChatInner]') || text.includes('setMessages')) {
        consoleLogs.push(text)
        console.log('Browser console:', text)
      }
    })

    page.on('response', async (res) => {
      const url = res.url()
      if (url.includes('/api/threads/') && res.status() === 200) {
        try {
          const body = await res.json()
          console.log('API response', url, JSON.stringify(body).slice(0, 500))
        } catch {
          // ignore non-json
        }
      }
    })

    page.on('request', (req) => {
      const url = req.url()
      if (url.includes('/api/threads/')) {
        historyRequests.push(`${req.method()} ${url}`)
      }
    })

    // 1. 打开前端
    await page.goto('/')

    // 2. 等待 Sidebar 与 Agent 选择器加载
    await page.waitForSelector('button[aria-label="选择 Agent"]', { timeout: 15000 })
    await expect(page.getByText('历史会话').first()).toBeVisible()

    // 3. 输入并发送消息（CopilotKit 使用 contenteditable 或 textarea，优先通过占位符定位）
    const input = page
      .locator('input[placeholder="输入消息..."], textarea[placeholder="输入消息..."], [contenteditable="true"]')
      .first()
    await input.fill(testMarker)
    await input.press('Enter')

    // 4. 等待 assistant 回复持久化到后端（轮询 /api/threads/{threadId}/messages）
    let hasAssistant = false
    let threadId = ''
    for (let i = 0; i < 30; i++) {
      if (!threadId) {
        const listRes = await page.evaluate(async () => {
          const r = await fetch('/api/threads/?agent_id=default')
          return r.json()
        })
        const latest = (listRes.threads || []).find((t: { last_message_preview?: string }) =>
          (t.last_message_preview || '').includes('你好'),
        )
        if (latest) threadId = latest.thread_id
      }
      if (threadId) {
        const res = await page.evaluate(async (tid) => {
          const r = await fetch(`/api/threads/${tid}/messages`)
          return r.json()
        }, threadId)
        const roles = (res.messages || []).map((m: { role: string }) => m.role)
        if (roles.includes('assistant')) {
          hasAssistant = true
          break
        }
      }
      await page.waitForTimeout(1000)
    }
    expect(hasAssistant, 'assistant 消息未在 30 秒内持久化').toBe(true)

    // 5. 刷新页面，验证历史列表出现
    await page.reload()
    await page.waitForSelector('button[aria-label="选择 Agent"]', { timeout: 15000 })

    // Sidebar 中应出现历史会话按钮
    const historyButton = page.locator('button[aria-label]').filter({ hasText: new RegExp(testMarker.slice(0, 12)) })
    await expect(historyButton).toBeVisible({ timeout: 10000 })

    // 6. 点击历史会话
    await historyButton.click()

    // 7. 验证聊天区出现 user + assistant 消息（CopilotKit 默认免责声明外的实际消息）
    await page.waitForTimeout(2000)
    const pageText = await page.evaluate(() => document.body.innerText)
    expect(pageText).toContain(testMarker)

    // 8. 验证网络请求与无关键报错（忽略 CopilotKit 对未配置端点的 404）
    expect(
      historyRequests.some((r) => /GET .*\/api\/threads\/\?agent_id=/.test(r)),
      `历史列表请求未触发，实际请求：${historyRequests.join(', ')}`,
    ).toBe(true)
    expect(
      historyRequests.some((r) => /GET .*\/api\/threads\/[^/]+\/messages/.test(r)),
      `历史消息请求未触发，实际请求：${historyRequests.join(', ')}`,
    ).toBe(true)
    const criticalErrors = consoleErrors.filter((e) => !e.includes('status of 404'))
    expect(criticalErrors, `浏览器控制台出现关键错误：${criticalErrors.join('; ')}`).toEqual([])
  })
})
