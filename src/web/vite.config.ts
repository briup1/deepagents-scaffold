import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'
import fs from 'node:fs'
import path from 'node:path'

const COPILOTKIT_V2_CSS = '@copilotkit/react-core/dist/v2/index.css'
const VIRTUAL_CSS = '\0copilotkit-v2-styles.js'

/**
 * 将 CopilotKit v2 的 Tailwind CSS v4 产物以原始字符串形式注入，
 * 避免当前项目 Tailwind CSS v3 PostCSS 插件解析 `@layer` 指令时出错。
 */
function rawCopilotKitCssPlugin() {
  const cssFileByVirtual = new Map<string, string>()
  return {
    name: 'raw-copilotkit-css',
    enforce: 'pre' as const,
    resolveId(id: string, importer: string | undefined) {
      const isCopilotKitCss =
        id.endsWith('/dist/v2/index.css') ||
        id.endsWith('/v2/styles.css') ||
        (id === './index.css' && importer && importer.includes('/dist/v2/'))
      if (isCopilotKitCss) {
        cssFileByVirtual.set(VIRTUAL_CSS, importer ? path.resolve(path.dirname(importer), id) : path.resolve('node_modules/@copilotkit/react-core/dist/v2/index.css'))
        return VIRTUAL_CSS
      }
      return null
    },
    load(id: string) {
      if (id === VIRTUAL_CSS) {
        const file = cssFileByVirtual.get(id) ?? path.resolve('node_modules/@copilotkit/react-core/dist/v2/index.css')
        const css = fs.readFileSync(file, 'utf-8')
        const escaped = JSON.stringify(css)
        return `
          const css = ${escaped};
          if (typeof document !== 'undefined') {
            const style = document.createElement('style');
            style.textContent = css;
            document.head.appendChild(style);
          }
          export default css;
        `
      }
      return null
    },
  }
}

export default defineConfig({
  plugins: [rawCopilotKitCssPlugin(), react()],
  server: {
    port: 3000,
    proxy: {
      '/api': {
        target: 'http://localhost:8000',
        changeOrigin: true,
      },
      '/agent': {
        target: 'http://localhost:8000',
        changeOrigin: true,
      },
    },
  },
})
