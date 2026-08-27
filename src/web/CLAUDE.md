# 前端项目指南

本文件聚焦 `src/web/` 内的前端实现。AI 协作原则、安全红线、跨前后端验证闭环、环境变量配置见根目录 `CLAUDE.md`。

## 项目简介

基于 React 18 + TypeScript + Tailwind CSS 的多 Agent 前端界面。使用 CopilotKit v2（`@copilotkit/react-core/v2`）提供聊天组件、工具渲染与流式响应能力；通过 `HttpAgent` 直连后端 AG-UI `/agent/{agentId}` SSE 端点，不引入 CopilotKit Runtime 服务。支持 Agent 选择、新建会话、以及可扩展的 Generative UI Catalog。

## 项目结构

```
src/web/
├── index.html                    # 主入口 HTML 页面
├── package.json                  # npm 包定义
├── vite.config.ts                # Vite 开发服务器配置（含 CopilotKit v2 CSS raw 注入插件）
├── tsconfig.json                 # TypeScript 编译选项
├── tailwind.config.js            # Tailwind CSS 配置
├── postcss.config.js             # PostCSS 配置
├── vitest.config.ts              # Vitest 测试配置
└── src/                          # React 应用源码
    ├── main.tsx                  # React 应用挂载入口
    ├── App.tsx                   # 根组件：Agent 选择、新建会话、CopilotKit Provider
    ├── index.css                 # Tailwind CSS 入口
    ├── api/
    │   └── copilotkit.ts         # Agent 列表等辅助接口
    ├── catalog/                  # Generative UI 组件目录
    │   ├── types.ts              # Catalog 类型定义
    │   ├── createCatalog.ts      # Catalog 工厂与 schema 提取
    │   ├── index.tsx             # 注册所有组件与导出
    │   ├── GenerativeUIContext.tsx # dispatch 上下文
    │   └── __tests__/            # Catalog 单元测试
    ├── components/
    │   ├── AgentSelector.tsx     # Agent 下拉选择器
    │   ├── NewChatButton.tsx     # 新建会话按钮
    │   ├── ErrorBoundary.tsx     # 全局错误边界
    │   ├── GenerativeUIRenderer.tsx # 从 Catalog 查找 renderer
    │   └── ui/                   # 可复用 Generative UI 组件
    │       ├── MarkdownCard.tsx
    │       ├── DataTable.tsx
    │       ├── Form.tsx
    │       ├── ButtonGroup.tsx
    │       ├── MetricCard.tsx
    │       └── Chart.tsx
    ├── hooks/
    │   ├── useGenerativeUITool.ts   # useRenderTool("render_ui")
    │   └── useGenerativeUIAction.ts # 将用户动作发回 Agent
    └── test-setup.ts             # 测试初始化
```

## 常用命令

```bash
# 安装依赖
npm install

# 启动开发服务器（端口 3002）
npm run dev

# 构建生产版本（含类型检查）
npm run build

# 预览生产版本
npm run preview

# 运行测试
npm test
```

## 技术栈

- **React**: 18.3
- **TypeScript**: 5.6
- **构建工具**: Vite 5.4
- **样式**: Tailwind CSS 3.4
- **聊天框架**: CopilotKit v2（`@copilotkit/react-core/v2`、`@copilotkit/react-ui`）
- **Agent 协议**: AG-UI（`@ag-ui/client` 的 `HttpAgent`）
- **测试**: Vitest + React Testing Library + jsdom

## 架构说明

### 入口与布局

- `src/main.tsx` 挂载应用，外层包裹 `ErrorBoundary`。
- `src/App.tsx` 管理全局状态：
  - `threadId`：当前会话 ID，点击“新建会话”后重新生成。
  - `agentId`：当前选中的 Agent。
  - `agents`：从 `/api/agents/` 加载的 Agent 列表。
  - `ChatShell`：被 `key={threadId}` 包裹，切换会话时重置聊天上下文。

### CopilotKit 连接

使用 `selfManagedAgents` 直接连接后端 AG-UI SSE 端点，不引入 CopilotKit Runtime：

```tsx
const agent = new HttpAgent({ url: `/agent/${agentId}`, threadId })

<CopilotKit threadId={threadId} selfManagedAgents={{ [agentId]: agent }}>
  <CopilotChat agentId={agentId} labels={...} />
</CopilotKit>
```

Vite 开发服务器将 `/api` 与 `/agent` 代理到 `http://localhost:8000`。

### Generative UI Catalog

Catalog 是“全能力 Generative UI”的核心：

- 每个组件注册一个 `description`、Zod `schema` 和 React `renderer`。
- `createCatalog()` 生成类型安全的 `render(envelope, dispatch)` 方法。
- `componentSchema` 可导出给后端系统提示词，让 Agent 知道可用组件与字段。
- 新增组件只需在 `src/web/src/catalog/index.tsx` 注册，无需修改 `GenerativeUIRenderer`。

已注册组件：

| type | 用途 |
|------|------|
| `markdown_card` | 展示 Markdown 文本 |
| `data_table` | 展示结构化表格 |
| `form` | 输入表单，提交后发送 `form_submit` 动作 |
| `button_group` | 多个按钮，点击发送 `button_click` 动作 |
| `metric_card` | 展示指标数值与变化率 |
| `chart` | SVG 柱状图/折线图 |

### Generative UI 数据流

```
用户输入 (CopilotChat)
    |
    v
HttpAgent -> POST /agent/{agentId} (SSE)
    |
    v
后端 Agent 调用 render_ui(type, props, surface_id)
    |
    v
AG-UI TOOL_CALL_RESULT -> result.generative_ui
    |
    v
useRenderTool("render_ui") -> GenerativeUIRenderer -> Catalog.render(envelope, dispatch)
    |
    v
渲染 MarkdownCard / DataTable / Form / ButtonGroup / MetricCard / Chart
    |
    v (可交互组件)
form_submit / button_click -> useGenerativeUIAction -> agent.addMessage + agent.runAgent()
    |
    v
后端 Agent 再次调用 render_ui 更新界面
```

### 交互回环

- `Form` 提交时 `dispatch({ type: 'form_submit', surfaceId, values })`。
- `ButtonGroup` 点击时 `dispatch({ type: 'button_click', surfaceId, id })`。
- `useGenerativeUIAction(agentId)` 使用 `useAgent()` 获取当前 Agent 实例，将动作 JSON 作为用户消息发送并触发 `runAgent()`。
- 后端收到动作后，可再次调用 `render_ui` 并复用 `surface_id` 更新同一组件。

## 开发指南

### 添加新的 Generative UI 组件

1. 在 `src/web/src/components/ui/` 创建新的 `.tsx` 组件（PascalCase）。
2. 在 `src/web/src/catalog/index.tsx` 定义 Zod schema 并注册到 `catalog`。
3. 如需交互，组件通过 props 接收 `dispatch` 与 `surfaceId`。
4. 在 `src/web/src/catalog/__tests__/` 或组件目录补充测试。
5. 更新 `config.yaml` 中 `profiles.harness.default.system_prompt_suffix`，追加新组件的字段说明与使用示例。

### 修改样式

- 组件样式使用 Tailwind CSS utility classes。
- 全局样式在 `src/index.css`。
- CopilotKit v2 样式通过 `vite.config.ts` 中的 `rawCopilotKitCssPlugin` 注入；请勿直接 import `@copilotkit/react-core/v2/styles.css`，否则 Tailwind CSS v3 PostCSS 会报错。

### 测试约定

- 测试文件与源文件同目录，或放在 `__tests__/` 子目录。
- 测试文件命名：`*.test.tsx`。
- 使用 React Testing Library + Vitest。
- 组件测试覆盖渲染、用户交互与 dispatch 回调。

## 验证命令

```bash
# 类型检查与构建
cd src/web && npm run build

# 运行前端测试
cd src/web && npm test
```

## 调试与日志

- 开发时需要同时启动后端服务（端口 8000）：`bash scripts/dev.sh`。
- Vite 开发服务器自动代理 `/api` 与 `/agent` 到后端。
- 后端已配置 `allow_origins=["*"]` 的 CORS，开发环境无需额外处理。
- 浏览器开发者工具 Console 中可查看 Catalog 渲染警告与 props 校验错误。
