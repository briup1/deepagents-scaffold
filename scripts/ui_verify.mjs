#!/usr/bin/env node
// Phase 3 全栈 UI 端到端验证（L3）：用真实浏览器驱动聊天界面
// 1. 打开前端 → 选择 data_extractor Agent
// 2. 上传 simple_quote.xlsx
// 3. 发送「抽取 + 分析 + data_table 展示」请求
// 4. 等待生成式 UI（data_table）渲染，截图保存
//
// 前置：bash scripts/dev.sh 已启动（config.yaml 真实模型）
// 运行：node scripts/ui_verify.mjs
import { chromium } from 'playwright-core'
import { fileURLToPath } from 'node:url'
import path from 'node:path'

const FRONTEND = 'http://localhost:3002'
const XLSX = path.join(path.dirname(fileURLToPath(import.meta.url)), '..', 'simple_quote.xlsx')
const SHOT_DIR = path.join(path.dirname(fileURLToPath(import.meta.url)), '..', 'docs', 'superpowers', 'evidence')

const fail = (msg) => {
  console.error('[FAIL] ' + msg)
  process.exitCode = 1
}

const browser = await chromium.launch()
const page = await browser.newPage({ viewport: { width: 1440, height: 900 } })

try {
  console.log('[1/6] 打开前端', FRONTEND)
  await page.goto(FRONTEND, { waitUntil: 'networkidle', timeout: 60000 })
  await page.waitForTimeout(3000)

  console.log('[2/6] 选择 data_extractor Agent')
  const selector = page.getByRole('button', { name: '选择 Agent' })
  await selector.waitFor({ timeout: 20000 })
  await selector.click()
  await page.getByRole('option', { name: /data_extractor/i }).first().click()
  await page.waitForTimeout(1500)

  console.log('[3/6] 上传 simple_quote.xlsx')
  const fileInput = page.locator('input[type=file]')
  await fileInput.setInputFiles(XLSX)
  await page.waitForTimeout(2000)
  // 上传完成后截图文件卡片
  await page.screenshot({ path: path.join(SHOT_DIR, 'phase3-l3-upload.png'), fullPage: false })

  console.log('[4/6] 发送分析请求')
  const textarea = page.locator('textarea').first()
  await textarea.waitFor({ timeout: 15000 })
  await textarea.fill(
    '请抽取这份 Excel 报价单中的 carrier、pol、pod、container_type、amount 字段（amount 为数字），' +
      '验证通过后用 analyze_extracted_data 或 query_extracted_data 找出到 Los Angeles 最便宜的航线，' +
      '最后用 render_ui 的 data_table 展示结果并给出结论。'
  )
  await textarea.press('Enter')

  console.log('[5/6] 等待 Agent 抽取并分析（真实模型，预计 1-3 分钟）…')
  // 等待最终分析结果表：表格含真实数据（港口/船公司），而非抽取阶段的字段映射表
  let rendered = false
  for (let i = 0; i < 72; i++) {
    await page.waitForTimeout(5000)
    const tables = page.locator('table')
    const count = await tables.count()
    if (count > 0) {
      const lastTxt = (await tables.last().innerText()).toLowerCase()
      const hasData = /los angeles|洛杉矶|shanghai|上海|msc|cosco|1200|最便宜|最低/.test(lastTxt)
      if (hasData && !lastTxt.includes('目标字段')) {
        rendered = true
        console.log('  检测到最终结果表渲染（第', (i + 1) * 5, '秒）')
        break
      }
    }
  }

  await page.waitForTimeout(2000)
  await page.screenshot({ path: path.join(SHOT_DIR, 'phase3-l3-chat-result.png'), fullPage: true })

  if (rendered) {
    console.log('[6/6] ✅ data_table 已渲染，截图已保存')
    // 打印表格内容作为文本证据
    const txt = await page.locator('table').last().innerText()
    console.log('--- 渲染的表格内容 ---')
    console.log(txt.slice(0, 800))
    console.log('---')
  } else {
    fail('超时未检测到 data_table 渲染')
  }
} catch (err) {
  fail(err.message)
  await page.screenshot({ path: path.join(SHOT_DIR, 'phase3-l3-error.png'), fullPage: true })
} finally {
  await browser.close()
}
console.log(process.exitCode ? '结论: L3 前端验证失败' : '结论: L3 前端验证通过 ✅')
