#!/usr/bin/env node
// 将 Phase 3 完成证据 HTML 页截图保存（无浏览器交互）
import { chromium } from 'playwright-core'
import { fileURLToPath } from 'node:url'
import path from 'node:path'

const dir = path.dirname(fileURLToPath(import.meta.url))
const htmlPath = path.join(dir, '..', 'docs', 'superpowers', 'evidence', 'phase3-evidence.html')
const outPng = path.join(dir, '..', 'docs', 'superpowers', 'evidence', 'phase3-evidence-summary.png')

const browser = await chromium.launch()
const page = await browser.newPage({ viewport: { width: 1200, height: 1000 } })
await page.goto('file://' + htmlPath, { waitUntil: 'networkidle' })
await page.waitForTimeout(1000)
await page.screenshot({ path: outPng, fullPage: true })
console.log('saved', outPng)
await browser.close()
