# 前端项目指南

本文件聚焦 `src/web/` 内的前端实现。AI 协作原则、安全红线、跨前后端验证闭环、环境变量配置见根目录 `CLAUDE.md`。

## 项目简介

基于 React 18 + TypeScript + Tailwind CSS 的多 Agent 前端界面。使用 CopilotKit 提供聊天组件与流式响应能力，支持 Agent 选择、Generative UI 渲染（Markdown 卡片 / 数据表）。

## 项目结构

```
src/web/
├── index.html                    # 主入口 HTML 页面
├── package.json                  # npm 包定义
├── vite.config.ts                # Vite 开发服务器配置
├── tsconfig.json                 # TypeScript 编译选项
├── tailwind.config.js            # Tailwind CSS 配置
├── postcss.config.js             # PostCSS 配置
└── src/                          # React 应用源码
    ├── main.tsx                  # React 应用挂载入口
    ├── App.tsx                   # 根组件
    ├── index.css                 # Tailwind CSS 入口
    ├── api/                      # API 客户端
    │   └── copilotkit.ts         # Agent 列表等辅助接口
    ├── hooks/                    # 自定义 Hooks
    │   └── useGenerativeUI.tsx   # CopilotKit 消息自定义渲染
    ├── types/                    # TypeScript 类型
    │   └── generative-ui.ts      # Generative UI 元数据类型与守卫
    └── components/               # React 组件
        ├── AgentSelector.tsx     # Agent 选择下拉框
        ├── GenerativeUIRenderer.tsx  # Generative UI 分发渲染器
        ├── ErrorBoundary.tsx     # 全局错误边界
        └── ui/                   # 可复用 UI 组件
            ├── MarkdownCard.tsx  # Markdown 卡片渲染
            └── DataTable.tsx     # 数据表渲染
```

## 常用命令

```bash
# 安装依赖
npm install

# 启动开发服务器（端口 3000）
npm run dev

# 构建生产版本
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
- **聊天框架**: CopilotKit `@copilotkit/react-core` / `@copilotkit/react-ui`
- **开发服务器**: 端口 3000，`/api` 与 `/agent` 代理到 `http://localhost:8000`

## 架构说明

构建工具：Vite
入口：`src/main.tsx` → `App.tsx`
组件层次：`App` → `CopilotKit` Provider → `CopilotSidebar` → `AgentSelector` + `CopilotChat`
API 通信：基于 `@copilotkit/react-core` 的 `CopilotKit` Provider 与 `/agent/{agentId}` SSE 端点通信；`src/api/copilotkit.ts` 提供 Agent 列表等辅助 `fetch` 接口
样式：Tailwind CSS utility-first

## 核心模块说明

### src/main.tsx — React 应用入口

挂载 React 应用到 DOM，外层包裹 `ErrorBoundary` 捕获渲染错误。

### src/App.tsx — 根组件

管理全局状态并组装 CopilotKit 聊天界面：
- 生成并固定当前会话 `threadId`
- 维护当前选中的 `agentId`，并据此计算 `runtimeUrl`
- 通过 `CopilotKit` Provider 向子树提供 CopilotKit 运行时上下文
- `CopilotSidebar` 提供可折叠的侧边栏容器
- `AgentSelector`：选择当前要对话的 Agent
- `CopilotChat`：聊天消息列表、输入框与流式响应
- `useGenerativeUI`：注入自定义 `RenderMessage`，根据消息元数据渲染 Generative UI

### src/api/copilotkit.ts — API 客户端

核心函数：
- `listAgents()`: 从 `/api/agents/` 获取已注册 Agent 列表

### src/hooks/useGenerativeUI.tsx — Generative UI 渲染 Hook

- `extractGenerativeUIMetadata()`: 从 CopilotKit 消息中提取 `metadata.generative_ui`
- `useGenerativeUI()`: 返回 `renderMessage`，用于 `CopilotChat` 的 `RenderMessage` 属性
- 开发环境（`import.meta.env.DEV`）下可对当前 assistant 消息注入 Mock 元数据，便于本地验证
- 支持两种 Generative UI 类型：`markdown_card`、`data_table`

### src/components/ — React 组件

**AgentSelector.tsx**:
- 从 `/api/agents/` 加载 Agent 列表
- 下拉框展示并支持切换当前 Agent
- 加载与错误状态提示

**GenerativeUIRenderer.tsx**:
- 根据 `metadata` 的 `type` 字段分发到 `MarkdownCard` 或 `DataTable`
- 对不支持的类型输出警告并回退到默认渲染

**ErrorBoundary.tsx**:
- 类组件实现的错误边界
- 捕获渲染异常并展示友好的错误页面与刷新按钮

**ui/MarkdownCard.tsx**:
- 渲染 `markdown_card` 类型的 Generative UI
- 显示标题与 Markdown 内容

**ui/DataTable.tsx**:
- 渲染 `data_table` 类型的 Generative UI
- 根据 `columns` 与 `rows` 渲染表格

### src/types/generative-ui.ts — 类型定义

- `MarkdownCardMetadata` / `DataTableMetadata`：Generative UI 元数据结构
- `isMarkdownCard()` / `isDataTable()`：类型守卫函数

## 数据流

```
用户输入 (CopilotChat 内置输入框)
    |
    v
CopilotKit Provider (runtimeUrl=/agent/{agentId})
    |
    v
POST /agent/{agentId} (SSE)
    |
    v
Backend ag-ui-langgraph /agent endpoint
    |
    v
SSE events -> CopilotKit react-core -> CopilotChat
    |
    v
RenderMessage (useGenerativeUI) -> GenerativeUIRenderer -> MarkdownCard / DataTable
```

## 开发指南

### 添加新组件

1. 在 `src/components/`（或 `src/components/ui/`）中创建新的 `.tsx` 文件
2. 使用 PascalCase 命名
3. 导出为默认导出或具名导出
4. 在 `App.tsx` 或其他父组件中导入并使用

### 添加新的 Generative UI 类型

1. 在 `src/types/generative-ui.ts` 中定义新的元数据类型与类型守卫
2. 在 `src/components/ui/` 中创建对应的渲染组件
3. 在 `src/components/GenerativeUIRenderer.tsx` 中添加分发逻辑
4. 在 `src/hooks/useGenerativeUI.tsx` 的 `VALID_GENERATIVE_UI_TYPES` 中注册新类型

### 修改样式

- 使用 Tailwind CSS 类名
- 全局样式在 `src/index.css`
- 组件样式使用 Tailwind utility classes

### 添加 API 调用

1. 在 `src/api/copilotkit.ts` 中添加新函数
2. 使用 `fetch` 调用 `/api/*` 端点
3. 在组件中通过 `useEffect` 或事件处理器调用

## 测试约定

- 测试文件与源文件同目录，或放在 `__tests__/` 子目录
- 测试文件命名：`*.test.tsx` 或 `*.spec.tsx`
- 使用 React Testing Library + Vitest
- 测试用户交互、组件渲染与错误边界行为

## 调试与日志

- 开发时需要同时启动后端服务（端口 8000）
- Vite 开发服务器会自动代理 `/api` 与 `/agent` 请求到后端
- 后端已配置 `allow_origins=["*"]` 的 CORS，开发环境无需额外处理
- 生产部署应通过 Nginx、CDN 或 `npm run preview` 等方式提供 `dist/` 产物；FastAPI 不再挂载 `/static` 或服务 `/`
- 支持热模块替换（HMR）
- 使用 TypeScript 严格模式
- 使用浏览器开发者工具查看网络请求与 Console 日志

## 验证命令

```bash
# 类型检查（无需启动服务）
cd src/web && npx tsc --noEmit

# 等价于 npm run build 中的类型检查与生产构建
cd src/web && npm run build
```
