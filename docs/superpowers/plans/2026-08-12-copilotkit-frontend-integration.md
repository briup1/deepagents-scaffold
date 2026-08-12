# CopilotKit 前端集成实施计划

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 将现有 `src/web` 前端从 `@ag-ui/client` 手写 UI 迁移到 CopilotKit React 组件，通过 AG-UI 协议直连后端 `/agent/{agentId}`，并实现 Markdown 卡片与数据表格两种 Generative UI 渲染。

**Architecture:** 前端使用 `@copilotkit/react-core` 的 `CopilotKit` Provider 和 `@copilotkit/react-ui` 的 `CopilotSidebar`/`CopilotChat`；`runtimeUrl` 根据 `AgentSelector` 的选择动态切换。`GenerativeUIRenderer` 拦截带 `metadata.generative_ui` 的 AG-UI 文本事件并渲染对应组件。后端保持不变，Generative UI 的 Agent 提示词调优作为后续填肉任务。

**Tech Stack:** React 18.3, TypeScript 5.6, Vite 5.4, Tailwind CSS 3.4, CopilotKit (@copilotkit/react-core, @copilotkit/react-ui), @ag-ui/client 移除。

## Global Constraints

- 所有新增 Python 依赖必须通过 `uv add <package>` 安装；前端依赖通过 `npm install <package>` 安装。
- 后端接口契约（`RunAgentInput`、`/agent/{agentId}` SSE）禁止修改。
- 前端 TypeScript 使用严格模式。
- 组件命名使用 PascalCase；工具函数/类型使用 camelCase/snake-case 文件路径。
- 每次产生 Mock 数据必须在 `MOCK_REGISTRY.md` 中登记。
- 改完必须给出可独立执行的验证命令，禁止只写“已验证”。

---

## File Structure

| 文件 | 责任 |
|---|---|
| `src/web/src/types/generative-ui.ts` | Generative UI 的 TypeScript 类型定义 |
| `src/web/src/components/ui/MarkdownCard.tsx` | 渲染 Markdown 富文本卡片 |
| `src/web/src/components/ui/DataTable.tsx` | 渲染结构化数据表格 |
| `src/web/src/components/GenerativeUIRenderer.tsx` | 根据 metadata 路由到具体 UI 组件 |
| `src/web/src/components/AgentSelector.tsx` | Agent 下拉选择器 |
| `src/web/src/api/copilotkit.ts` | 封装 `/api/agents/` 等 HTTP 调用 |
| `src/web/src/components/ErrorBoundary.tsx` | 全局错误边界 |
| `src/web/src/App.tsx` | 根组件：CopilotKit Provider + 布局 |
| `src/web/src/index.css` | 引入 CopilotKit 默认样式 |
| `src/web/package.json` | 新增/移除依赖 |
| `MOCK_REGISTRY.md` | Mock 数据注册表 |

**删除文件：** `src/web/src/components/Chat.tsx`、`MessageInput.tsx`、`Sidebar.tsx`、`ConfigPanel.tsx`、`src/web/src/api.ts`。

---

## Task 1: 安装 CopilotKit 依赖并清理旧依赖

**Files:**
- Modify: `src/web/package.json`

**Interfaces:**
- Produces: 安装后的 `node_modules` 包含 `@copilotkit/react-core`、`@copilotkit/react-ui`；不再依赖 `@ag-ui/client`。

- [ ] **Step 1: 修改 package.json**

在 `src/web/package.json` 的 `dependencies` 中：

```json
"dependencies": {
  "@copilotkit/react-core": "^1.0.0",
  "@copilotkit/react-ui": "^1.0.0",
  "react": "^18.3.0",
  "react-dom": "^18.3.0"
}
```

移除 `@ag-ui/client`。

同时在 `devDependencies` 中新增测试框架（如果尚不存在）：

```json
"devDependencies": {
  "@testing-library/react": "^16.0.0",
  "@testing-library/jest-dom": "^6.4.0",
  "@testing-library/user-event": "^14.5.0",
  "jsdom": "^25.0.0",
  "vitest": "^2.1.0"
}
```

并在 `scripts` 中新增：

```json
"scripts": {
  "test": "vitest run"
}
```

- [ ] **Step 2: 安装依赖**

```bash
cd src/web
npm install
```

- [ ] **Step 3: 创建 vitest 配置**

创建 `src/web/vitest.config.ts`：

```typescript
import { defineConfig } from 'vitest/config'
import react from '@vitejs/plugin-react'

export default defineConfig({
  plugins: [react()],
  test: {
    environment: 'jsdom',
    globals: true,
    setupFiles: ['./src/test-setup.ts'],
  },
})
```

创建 `src/web/src/test-setup.ts`：

```typescript
import '@testing-library/jest-dom/vitest'
```

- [ ] **Step 4: 验证安装**

```bash
cd src/web
npm ls @copilotkit/react-core @copilotkit/react-ui
```

Expected: 两个包均显示版本号，无 `ERR!`。

- [ ] **Step 5: 提交**

```bash
git add src/web/package.json src/web/package-lock.json src/web/vitest.config.ts src/web/src/test-setup.ts
git commit -m "deps(web): add copilotkit packages, remove ag-ui client, setup vitest"
```

---

## Task 2: 定义 Generative UI 类型

**Files:**
- Create: `src/web/src/types/generative-ui.ts`

**Interfaces:**
- Produces: `GenerativeUIMetadata`、`MarkdownCardMetadata`、`DataTableMetadata` 类型，供后续组件使用。

- [ ] **Step 1: 创建类型文件**

```typescript
export interface GenerativeUIMetadata {
  type: 'markdown_card' | 'data_table'
  title?: string
}

export interface MarkdownCardMetadata extends GenerativeUIMetadata {
  type: 'markdown_card'
  content: string
}

export interface DataTableMetadata extends GenerativeUIMetadata {
  type: 'data_table'
  columns: Array<{ key: string; label: string }>
  rows: Array<Record<string, string | number | boolean>>
}

export function isMarkdownCard(
  metadata: GenerativeUIMetadata,
): metadata is MarkdownCardMetadata {
  return metadata.type === 'markdown_card'
}

export function isDataTable(
  metadata: GenerativeUIMetadata,
): metadata is DataTableMetadata {
  return metadata.type === 'data_table'
}
```

- [ ] **Step 2: 验证 TypeScript 编译**

```bash
cd src/web
npm run build
```

Expected: `tsc` 通过，无类型错误。

- [ ] **Step 3: 提交**

```bash
git add src/web/src/types/generative-ui.ts
git commit -m "feat(web): add generative ui type definitions"
```

---

## Task 3: 实现 MarkdownCard 与 DataTable UI 组件

**Files:**
- Create: `src/web/src/components/ui/MarkdownCard.tsx`
- Create: `src/web/src/components/ui/DataTable.tsx`
- Create: `src/web/src/components/ui/__tests__/MarkdownCard.test.tsx`
- Create: `src/web/src/components/ui/__tests__/DataTable.test.tsx`

**Interfaces:**
- Consumes: `MarkdownCardMetadata`、`DataTableMetadata`（Task 2）。
- Produces: `MarkdownCard` 和 `DataTable` React 组件。

- [ ] **Step 1: 创建 MarkdownCard 组件**

```tsx
import type { MarkdownCardMetadata } from '../../types/generative-ui'

interface MarkdownCardProps {
  metadata: MarkdownCardMetadata
}

export function MarkdownCard({ metadata }: MarkdownCardProps) {
  return (
    <div className="rounded-lg border border-gray-200 bg-white p-4 shadow-sm my-2">
      {metadata.title && (
        <h3 className="mb-2 text-sm font-semibold text-gray-700">{metadata.title}</h3>
      )}
      <div className="prose prose-sm max-w-none">
        <pre className="whitespace-pre-wrap text-sm text-gray-800">{metadata.content}</pre>
      </div>
    </div>
  )
}
```

- [ ] **Step 2: 创建 DataTable 组件**

```tsx
import type { DataTableMetadata } from '../../types/generative-ui'

interface DataTableProps {
  metadata: DataTableMetadata
}

export function DataTable({ metadata }: DataTableProps) {
  const { columns, rows, title } = metadata

  return (
    <div className="overflow-hidden rounded-lg border border-gray-200 bg-white shadow-sm my-2">
      {title && (
        <div className="border-b border-gray-200 bg-gray-50 px-4 py-2">
          <h3 className="text-sm font-semibold text-gray-700">{title}</h3>
        </div>
      )}
      <div className="overflow-x-auto">
        <table className="min-w-full text-sm">
          <thead className="bg-gray-50">
            <tr>
              {columns.map((col) => (
                <th
                  key={col.key}
                  className="px-4 py-2 text-left font-medium text-gray-600"
                >
                  {col.label}
                </th>
              ))}
            </tr>
          </thead>
          <tbody className="divide-y divide-gray-100">
            {rows.map((row, idx) => (
              <tr key={idx}>
                {columns.map((col) => (
                  <td key={col.key} className="px-4 py-2 text-gray-800">
                    {String(row[col.key] ?? '')}
                  </td>
                ))}
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </div>
  )
}
```

- [ ] **Step 3: 编写单元测试**

`MarkdownCard.test.tsx`：

```tsx
import { render, screen } from '@testing-library/react'
import { describe, expect, it } from 'vitest'
import { MarkdownCard } from '../MarkdownCard'

describe('MarkdownCard', () => {
  it('renders title and content', () => {
    render(
      <MarkdownCard
        metadata={{
          type: 'markdown_card',
          title: 'Summary',
          content: '# Hello',
        }}
      />,
    )
    expect(screen.getByText('Summary')).toBeInTheDocument()
    expect(screen.getByText('# Hello')).toBeInTheDocument()
  })
})
```

`DataTable.test.tsx`：

```tsx
import { render, screen } from '@testing-library/react'
import { describe, expect, it } from 'vitest'
import { DataTable } from '../DataTable'

describe('DataTable', () => {
  it('renders columns and rows', () => {
    render(
      <DataTable
        metadata={{
          type: 'data_table',
          title: 'Results',
          columns: [
            { key: 'name', label: 'Name' },
            { key: 'value', label: 'Value' },
          ],
          rows: [
            { name: 'A', value: 1 },
            { name: 'B', value: 2 },
          ],
        }}
      />,
    )
    expect(screen.getByText('Results')).toBeInTheDocument()
    expect(screen.getByText('Name')).toBeInTheDocument()
    expect(screen.getByText('A')).toBeInTheDocument()
    expect(screen.getByText('2')).toBeInTheDocument()
  })
})
```

- [ ] **Step 4: 运行测试**

```bash
cd src/web
npm test
```

Expected: `MarkdownCard` 和 `DataTable` 测试通过。

- [ ] **Step 5: 提交**

```bash
git add src/web/src/components/ui
git commit -m "feat(web): add markdown card and data table components with tests"
```

---

## Task 4: 实现 GenerativeUIRenderer（含 Mock 占位）

**Files:**
- Create: `src/web/src/components/GenerativeUIRenderer.tsx`
- Create: `src/web/src/components/__tests__/GenerativeUIRenderer.test.tsx`

**Interfaces:**
- Consumes: `MarkdownCard`、`DataTable`、`isMarkdownCard`、`isDataTable`（Task 2、Task 3）。
- Produces: `GenerativeUIRenderer` 组件，接收任意 `unknown` metadata 并安全渲染或降级。

- [ ] **Step 1: 创建组件**

```tsx
import { DataTable } from './ui/DataTable'
import { MarkdownCard } from './ui/MarkdownCard'
import {
  isDataTable,
  isMarkdownCard,
  type GenerativeUIMetadata,
} from '../types/generative-ui'

interface GenerativeUIRendererProps {
  metadata: unknown
}

export function GenerativeUIRenderer({ metadata }: GenerativeUIRendererProps) {
  if (!metadata || typeof metadata !== 'object') {
    return null
  }

  const meta = metadata as GenerativeUIMetadata

  if (isMarkdownCard(meta)) {
    return <MarkdownCard metadata={meta} />
  }

  if (isDataTable(meta)) {
    return <DataTable metadata={meta} />
  }

  console.warn('[GenerativeUIRenderer] unsupported generative_ui type:', meta.type)
  return null
}
```

- [ ] **Step 2: 编写测试**

```tsx
import { render, screen } from '@testing-library/react'
import { describe, expect, it, vi } from 'vitest'
import { GenerativeUIRenderer } from '../GenerativeUIRenderer'

describe('GenerativeUIRenderer', () => {
  it('renders markdown card', () => {
    render(
      <GenerativeUIRenderer
        metadata={{ type: 'markdown_card', title: 'T', content: 'C' }}
      />,
    )
    expect(screen.getByText('T')).toBeInTheDocument()
    expect(screen.getByText('C')).toBeInTheDocument()
  })

  it('renders data table', () => {
    render(
      <GenerativeUIRenderer
        metadata={{
          type: 'data_table',
          title: 'T',
          columns: [{ key: 'k', label: 'K' }],
          rows: [{ k: 'v' }],
        }}
      />,
    )
    expect(screen.getByText('T')).toBeInTheDocument()
    expect(screen.getByText('v')).toBeInTheDocument()
  })

  it('returns null for unsupported type and logs warning', () => {
    const warnSpy = vi.spyOn(console, 'warn').mockImplementation(() => {})
    const { container } = render(<GenerativeUIRenderer metadata={{ type: 'unknown' }} />)
    expect(container.firstChild).toBeNull()
    warnSpy.mockRestore()
  })
})
```

- [ ] **Step 3: 登记 Mock 占位**

在 `MOCK_REGISTRY.md`（若不存在则创建）中追加：

```markdown
## Task 4: GenerativeUIRenderer

- **模块路径**: `src/web/src/components/GenerativeUIRenderer.tsx`
- **Mock 字段/方法**: `metadata` 参数当前由调用方传入；后端尚未真实 emit `metadata.generative_ui`。
- **当前假数据逻辑**: 单元测试中使用硬编码的 `{ type: 'markdown_card' | 'data_table', ... }` 验证渲染。
- **未来需替换的真实业务逻辑**: 当后端 Agent 在 AG-UI 文本事件中携带 `metadata.generative_ui` 时，本组件应直接消费真实 metadata，不再依赖硬编码测试数据。
```

- [ ] **Step 4: 运行测试**

```bash
cd src/web
npm test
```

Expected: 全部通过。

- [ ] **Step 5: 提交**

```bash
git add src/web/src/components/GenerativeUIRenderer.tsx src/web/src/components/__tests__/GenerativeUIRenderer.test.tsx MOCK_REGISTRY.md
git commit -m "feat(web): add generative ui renderer with mock registry"
```

---

## Task 5: 实现 AgentSelector 与 API 封装

**Files:**
- Create: `src/web/src/components/AgentSelector.tsx`
- Create: `src/web/src/api/copilotkit.ts`
- Create: `src/web/src/components/__tests__/AgentSelector.test.tsx`

**Interfaces:**
- Consumes: `/api/agents/` HTTP endpoint（后端已存在）。
- Produces: `AgentSelector` 组件，`listAgents()` API 函数。

- [ ] **Step 1: 创建 API 封装**

```typescript
export interface AgentInfo {
  name: string
  type: string
}

export async function listAgents(): Promise<{ agents: AgentInfo[] }> {
  const res = await fetch('/api/agents/')
  if (!res.ok) throw new Error(`HTTP ${res.status}`)
  return res.json()
}
```

- [ ] **Step 2: 创建 AgentSelector 组件**

```tsx
import { useEffect, useState } from 'react'
import { listAgents, type AgentInfo } from '../api/copilotkit'

interface AgentSelectorProps {
  value: string
  onChange: (agentId: string) => void
}

export function AgentSelector({ value, onChange }: AgentSelectorProps) {
  const [agents, setAgents] = useState<AgentInfo[]>([])
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)

  useEffect(() => {
    listAgents()
      .then((data) => {
        setAgents(data.agents)
        setLoading(false)
      })
      .catch((err) => {
        setError(err instanceof Error ? err.message : String(err))
        setLoading(false)
      })
  }, [])

  if (loading) return <div className="p-2 text-sm text-gray-500">加载中...</div>
  if (error) return <div className="p-2 text-sm text-red-500">{error}</div>

  return (
    <div className="p-3 border-b border-gray-200">
      <label className="block text-xs font-medium text-gray-500 mb-1">Agent</label>
      <select
        className="w-full rounded border border-gray-300 bg-white px-2 py-1 text-sm"
        value={value}
        onChange={(e) => onChange(e.target.value)}
      >
        {agents.map((agent) => (
          <option key={agent.name} value={agent.name}>
            {agent.name}
          </option>
        ))}
      </select>
    </div>
  )
}
```

- [ ] **Step 3: 编写测试**

```tsx
import { render, screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { describe, expect, it, vi } from 'vitest'
import { AgentSelector } from '../AgentSelector'

const mockFetch = vi.fn()
global.fetch = mockFetch

describe('AgentSelector', () => {
  it('loads and selects agents', async () => {
    mockFetch.mockResolvedValueOnce({
      ok: true,
      json: async () => ({ agents: [{ name: 'default' }, { name: 'code_reviewer' }] }),
    })

    const onChange = vi.fn()
    render(<AgentSelector value="default" onChange={onChange} />)

    await waitFor(() => expect(screen.getByText('code_reviewer')).toBeInTheDocument())

    await userEvent.selectOptions(screen.getByRole('combobox'), 'code_reviewer')
    expect(onChange).toHaveBeenCalledWith('code_reviewer')
  })
})
```

- [ ] **Step 4: 运行测试**

```bash
cd src/web
npm test
```

Expected: `AgentSelector` 测试通过。

- [ ] **Step 5: 提交**

```bash
git add src/web/src/components/AgentSelector.tsx src/web/src/api/copilotkit.ts src/web/src/components/__tests__/AgentSelector.test.tsx
git commit -m "feat(web): add agent selector and copilotkit api wrapper"
```

---

## Task 6: 替换 App.tsx 为 CopilotKit 主界面

**Files:**
- Modify: `src/web/src/App.tsx`
- Modify: `src/web/src/index.css`
- Delete: `src/web/src/components/Chat.tsx`
- Delete: `src/web/src/components/MessageInput.tsx`
- Delete: `src/web/src/components/Sidebar.tsx`
- Delete: `src/web/src/components/ConfigPanel.tsx`
- Delete: `src/web/src/api.ts`

**Interfaces:**
- Consumes: `AgentSelector`（Task 5）、`GenerativeUIRenderer`（Task 4）、`CopilotKit` Provider、`CopilotSidebar`、`CopilotChat`。
- Produces: 新的 `App.tsx` 根组件。

- [ ] **Step 1: 重写 App.tsx**

```tsx
import { useMemo, useState } from 'react'
import { CopilotKit } from '@copilotkit/react-core'
import { CopilotSidebar, CopilotChat } from '@copilotkit/react-ui'
import { AgentSelector } from './components/AgentSelector'
import { GenerativeUIRenderer } from './components/GenerativeUIRenderer'
import '@copilotkit/react-ui/styles.css'

export default function App() {
  const [threadId] = useState(() => `thread-${crypto.randomUUID()}`)
  const [agentId, setAgentId] = useState('default')

  const runtimeUrl = useMemo(() => {
    return agentId === 'default' ? '/agent' : `/agent/${agentId}`
  }, [agentId])

  return (
    <div className="h-screen w-screen">
      <CopilotKit runtimeUrl={runtimeUrl} threadId={threadId}>
        <CopilotSidebar
          defaultOpen={true}
          clickOutsideToClose={false}
          className="h-full"
        >
          <div className="flex h-full flex-col">
            <AgentSelector value={agentId} onChange={setAgentId} />
            <div className="flex-1 overflow-hidden">
              <CopilotChat
                className="h-full"
                labels={{
                  title: 'DeepAgents Chat',
                  initial: '有什么可以帮你的？',
                  placeholder: '输入消息...',
                }}
              />
            </div>
          </div>
        </CopilotSidebar>
      </CopilotKit>
    </div>
  )
}
```

> 注意：`CopilotChat` 的 Generative UI 渲染需要在 CopilotKit 中通过 `useCopilotAction` 或自定义 message renderer 接入。如果 `CopilotChat` 默认不暴露 message 渲染钩子，可先让 `GenerativeUIRenderer` 作为独立组件待命，在 Task 7 中通过 CopilotKit 的 API 接入真实事件。

- [ ] **Step 2: 清理旧文件**

```bash
cd src/web/src
rm -f components/Chat.tsx components/MessageInput.tsx components/Sidebar.tsx components/ConfigPanel.tsx api.ts
```

- [ ] **Step 3: 更新 index.css**

确保 Tailwind  directives 在最上面，并加入 CopilotKit 样式覆盖预留：

```css
@tailwind base;
@tailwind components;
@tailwind utilities;

/* CopilotKit 样式微调 */
.copilotkit-chat {
  --copilot-kit-primary-color: #3b82f6;
}
```

- [ ] **Step 4: 验证构建**

```bash
cd src/web
npm run build
```

Expected: `tsc` 和 `vite build` 均通过。

- [ ] **Step 5: 提交**

```bash
git add src/web/src/App.tsx src/web/src/index.css
git rm src/web/src/components/Chat.tsx src/web/src/components/MessageInput.tsx src/web/src/components/Sidebar.tsx src/web/src/components/ConfigPanel.tsx src/web/src/api.ts
git commit -m "feat(web): replace custom ui with copilotkit sidebar and chat"
```

---

## Task 7: 接入 GenerativeUIRenderer 到 CopilotKit 消息流

**Files:**
- Modify: `src/web/src/App.tsx`
- Create: `src/web/src/hooks/useGenerativeUI.ts`

**Interfaces:**
- Consumes: `GenerativeUIRenderer`（Task 4）、CopilotKit message events。
- Produces: 能在 CopilotChat 中渲染 Markdown 卡片和数据表格的 hook/组件。

- [ ] **Step 1: 调研 CopilotKit 消息渲染 API**

根据实际安装的 `@copilotkit/react-ui` 版本，确定以下之一：

- `CopilotChat` 是否支持 `MessageRenderer` 或 `renderMessage` prop？
- 是否需要用 `useCopilotChat` + 自定义组件替换 `CopilotChat`？
- 是否通过 `useCopilotAction` 的 `render` 函数实现 Generative UI？

> 这一步先读 `node_modules/@copilotkit/react-ui/dist` 中的类型定义或官方文档，再写代码。如果 API 不确定，先用 **Mock 占位**：在 `App.tsx` 中临时渲染一个 `GenerativeUIRenderer` 示例，并登记到 `MOCK_REGISTRY.md`。

- [ ] **Step 2a: 若 CopilotChat 支持 render prop**

```tsx
<CopilotChat
  renderMessage={(message) => {
    const metadata = message.metadata?.generative_ui
    if (metadata) {
      return <GenerativeUIRenderer metadata={metadata} />
    }
    return undefined // 走默认渲染
  }}
/>
```

- [ ] **Step 2b: 若不支持 render prop**

改用 `useCopilotChat` 自定义聊天组件，将 `GenerativeUIRenderer` 嵌入消息列表。

- [ ] **Step 3: 添加 Mock 占位（如后端未 emit metadata）**

在 `MOCK_REGISTRY.md` 中追加：

```markdown
## Task 7: CopilotKit 消息流中的 Generative UI

- **模块路径**: `src/web/src/App.tsx` / `src/web/src/hooks/useGenerativeUI.ts`
- **Mock 字段/方法**: 当前 Generative UI metadata 来源。
- **当前假数据逻辑**: 若后端 Agent 尚未输出 `metadata.generative_ui`，前端使用一个本地 Mock 状态或示例事件渲染 `MarkdownCard`/`DataTable`，以验证 UI 组件工作正常。
- **未来需替换的真实业务逻辑**: 后端 Agent 在 AG-UI 文本事件中真实携带 `metadata.generative_ui`，前端直接从事件 metadata 读取。
```

- [ ] **Step 4: 验证构建与测试**

```bash
cd src/web
npm run build
npm test
```

- [ ] **Step 5: 提交**

```bash
git add src/web/src/App.tsx src/web/src/hooks/useGenerativeUI.ts MOCK_REGISTRY.md
git commit -m "feat(web): wire generative ui renderer into copilotkit chat"
```

---

## Task 8: 添加全局 ErrorBoundary

**Files:**
- Create: `src/web/src/components/ErrorBoundary.tsx`
- Modify: `src/web/src/main.tsx`

**Interfaces:**
- Produces: `ErrorBoundary` 组件，包裹 `App`。

- [ ] **Step 1: 创建 ErrorBoundary**

```tsx
import { Component, type ErrorInfo, type ReactNode } from 'react'

interface Props {
  children: ReactNode
}

interface State {
  hasError: boolean
  error: Error | null
}

export class ErrorBoundary extends Component<Props, State> {
  state: State = { hasError: false, error: null }

  static getDerivedStateFromError(error: Error): State {
    return { hasError: true, error }
  }

  componentDidCatch(error: Error, errorInfo: ErrorInfo) {
    console.error('[ErrorBoundary]', error, errorInfo)
  }

  render() {
    if (this.state.hasError) {
      return (
        <div className="flex h-screen flex-col items-center justify-center p-4 text-center">
          <h1 className="text-xl font-semibold text-red-600">出错了</h1>
          <p className="mt-2 text-sm text-gray-600">
            {this.state.error?.message || '未知错误'}
          </p>
          <button
            className="mt-4 rounded bg-blue-600 px-4 py-2 text-sm text-white"
            onClick={() => window.location.reload()}
          >
            刷新页面
          </button>
        </div>
      )
    }

    return this.props.children
  }
}
```

- [ ] **Step 2: 在 main.tsx 中包裹 App**

```tsx
import { StrictMode } from 'react'
import { createRoot } from 'react-dom/client'
import App from './App'
import './index.css'
import { ErrorBoundary } from './components/ErrorBoundary'

createRoot(document.getElementById('root')!).render(
  <StrictMode>
    <ErrorBoundary>
      <App />
    </ErrorBoundary>
  </StrictMode>,
)
```

- [ ] **Step 3: 验证构建**

```bash
cd src/web
npm run build
```

- [ ] **Step 4: 提交**

```bash
git add src/web/src/components/ErrorBoundary.tsx src/web/src/main.tsx
git commit -m "feat(web): add global error boundary"
```

---

## Task 9: 更新前端文档

**Files:**
- Modify: `src/web/CLAUDE.md`

**Interfaces:**
- Produces: 更新后的前端开发指南。

- [ ] **Step 1: 更新 CLAUDE.md**

- 将“API 通信：`src/api.ts` 基于 `@ag-ui/client`”改为“基于 CopilotKit `@copilotkit/react-core`”。
- 更新项目结构，列出新增组件，删除旧组件。
- 更新数据流说明：用户输入 → `CopilotChat` → `CopilotKit` Provider → `/agent/{agentId}` SSE → 后端。
- 增加 CopilotKit 相关环境/代理说明（如需 CORS 调整）。

- [ ] **Step 2: 提交**

```bash
git add src/web/CLAUDE.md
git commit -m "docs(web): update frontend guide for copilotkit integration"
```

---

## Task 10: 端到端验证

**Files:**
- 无新文件。

**Interfaces:**
- 验证前后端集成是否跑通。

- [ ] **Step 1: 启动后端**

```bash
bash scripts/dev.sh
```

等待后端 8000、前端 3000 启动。

- [ ] **Step 2: 后端健康检查**

```bash
curl -s http://localhost:8000/health
curl -s http://localhost:8000/agent/health
```

Expected: 均返回 JSON 且 `status` 为 `ok`。

- [ ] **Step 3: 前端页面验证**

打开 http://localhost:3000，确认：

- 页面加载无白屏。
- Sidebar 中显示 AgentSelector 并能切换 Agent。
- 发送消息后能看到流式回复。

- [ ] **Step 4: AG-UI 直连验证**

```bash
curl -N -X POST http://localhost:8000/agent \
  -H "Content-Type: application/json" \
  -H "Accept: text/event-stream" \
  -d '{"threadId":"thread-verify-001","runId":"run-verify-001","messages":[{"id":"msg-001","role":"user","content":"hello"}],"state":{},"tools":[],"context":[],"forwardedProps":{}}'
```

Expected: 返回 SSE 事件流，包含文本消息事件。

- [ ] **Step 5: 生产构建验证**

```bash
cd src/web
npm run build
```

Expected: 构建产物生成到 `src/web/dist`，无错误。

- [ ] **Step 6: 提交验证脚本/截图（可选）**

如有必要，将端到端验证命令追加到 `scripts/verify_dev.sh` 或文档中。

- [ ] **Step 7: 提交**

```bash
git add scripts/verify_dev.sh  # 如有修改
git commit -m "chore(web): verify copilotkit integration end-to-end"
```

---

## Task 11: 创建/更新 MOCK_REGISTRY.md

**Files:**
- Create/Modify: `MOCK_REGISTRY.md`

**Interfaces:**
- Produces: 完整的 Mock 注册表，记录 Phase 2 中所有 Mock 占位。

- [ ] **Step 1: 确保 MOCK_REGISTRY.md 包含以下条目**

```markdown
# Mock Registry

## Task 4: GenerativeUIRenderer

- **模块路径**: `src/web/src/components/GenerativeUIRenderer.tsx`
- **Mock 字段/方法**: `metadata` 参数当前由调用方传入；后端尚未真实 emit `metadata.generative_ui`。
- **当前假数据逻辑**: 单元测试中使用硬编码的 `{ type: 'markdown_card' | 'data_table', ... }` 验证渲染。
- **未来需替换的真实业务逻辑**: 后端 Agent 在 AG-UI 文本事件中真实携带 `metadata.generative_ui`，本组件直接消费真实 metadata。

## Task 7: CopilotKit 消息流中的 Generative UI

- **模块路径**: `src/web/src/App.tsx` / `src/web/src/hooks/useGenerativeUI.ts`
- **Mock 字段/方法**: Generative UI metadata 来源。
- **当前假数据逻辑**: 若后端 Agent 尚未输出 `metadata.generative_ui`，前端使用本地 Mock 状态或示例事件渲染 `MarkdownCard`/`DataTable`。
- **未来需替换的真实业务逻辑**: 后端 Agent 在 AG-UI 文本事件中真实携带 `metadata.generative_ui`。
```

- [ ] **Step 2: 提交**

```bash
git add MOCK_REGISTRY.md
git commit -m "docs: update mock registry for copilotkit generative ui"
```

---

## Self-Review

### Spec Coverage

| 设计文档章节 | 覆盖任务 |
|---|---|
| 架构总览（直连模式、Agent 切换、Generative UI 触发） | Task 6、Task 7 |
| 组件与模块划分 | Task 2、Task 3、Task 4、Task 5、Task 8 |
| 数据流 | Task 6、Task 7 |
| 接口契约（AG-UI 端点、metadata schema） | Task 2、Task 6 |
| 错误处理 | Task 8 |
| 测试策略 | Task 3、Task 4、Task 5、Task 10 |
| 验证命令 | Task 10 |

### Placeholder Scan

- 无 "TBD"、"TODO"。
- 无 "add appropriate error handling" 等模糊描述。
- Task 7 中对 CopilotKit 消息渲染 API 的探索有明确 fallback（Mock 占位 + `MOCK_REGISTRY.md`）。

### Type Consistency

- `GenerativeUIMetadata`、`MarkdownCardMetadata`、`DataTableMetadata` 在 Task 2 定义，Task 3、Task 4、Task 7 消费，字段一致。
- `AgentInfo` 在 `src/web/src/api/copilotkit.ts` 定义，`AgentSelector` 消费，名称一致。

---

## 后续迭代（Phase 4 填肉）

当本计划全部任务完成且端到端跑通后，按 `MOCK_REGISTRY.md` 逐项替换：

1. 在 `config.yaml` 中新增或调整一个 Agent 的 system prompt，引导其输出 `metadata.generative_ui`。
2. 后端 Agent 在合适场景下 emit 带 metadata 的 AG-UI 文本事件。
3. 前端移除 Mock 数据，直接从事件流消费 metadata。
4. 每完成一项，在 `MOCK_REGISTRY.md` 中标记 `[COMPLETED]`。

---

## 参考

- 设计文档：`docs/superpowers/specs/2026-08-12-copilotkit-frontend-integration-design.md`
- 后端 AG-UI 端点：`src/scaffold/api/ag_ui.py`
- 项目顶层指南：`CLAUDE.md`
- 前端指南：`src/web/CLAUDE.md`
