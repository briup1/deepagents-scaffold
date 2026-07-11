# 前端项目指南

本文件聚焦 `src/web/` 内的前端实现。AI 协作原则、安全红线、跨前后端验证闭环、环境变量配置见根目录 `CLAUDE.md`。

## 项目简介

基于 React 18 + TypeScript + Tailwind CSS 的多 Agent 前端界面。支持 SSE 流式响应、Agent 选择、工具列表展示。

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
    ├── api.ts                    # API 客户端
    ├── index.css                 # Tailwind CSS 入口
    └── components/               # React 组件
        ├── Chat.tsx              # 聊天消息列表
        ├── MessageInput.tsx      # 消息输入框
        ├── Sidebar.tsx           # 左侧边栏（Agent 列表）
        └── ConfigPanel.tsx       # 右侧配置面板
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
```

## 技术栈

- **React**: 18.3
- **TypeScript**: 5.6
- **构建工具**: Vite 5.4
- **样式**: Tailwind CSS 3.4
- **开发服务器**: 端口 3000，`/api` 代理到 `http://localhost:8000`

## 架构说明

构建工具：Vite
入口：`src/main.tsx` → `App.tsx`
组件层次：`App` → `Sidebar` + `Chat` + `MessageInput` + `ConfigPanel`
API 通信：`src/api.ts` 基于 `@ag-ui/client` 的 `HttpAgent` 与 `/agent` SSE 端点通信
样式：Tailwind CSS utility-first

## 核心模块说明

### src/main.tsx — React 应用入口

挂载 React 应用到 DOM。

### src/App.tsx — 根组件

管理全局状态和布局：
- Sidebar：Agent 列表和选择
- Chat：聊天消息列表
- MessageInput：消息输入框
- ConfigPanel：工具列表配置

### src/api.ts — API 客户端

核心函数：
- `createAgent()`: 创建 ag-ui Agent 实例（基于 `HttpAgent`）
- `sendAgentMessage()`: 通过 SSE 向 `/agent` 发送消息并接收流式事件
- `listAgents()`: 获取已注册 Agent 列表
- `listTools()`: 获取可用工具列表

### src/components/ — React 组件

**Chat.tsx**:
- 渲染用户/助手/工具消息
- 支持自动滚动
- 支持工具调用结果展示

**MessageInput.tsx**:
- 单行文本输入
- 发送按钮
- 支持 Enter 键发送

**Sidebar.tsx**:
- Agent 列表展示
- 每 5 秒轮询刷新
- 支持 Agent 选择

**ConfigPanel.tsx**:
- 可折叠配置面板
- 展示可用工具列表

## 数据流

```
用户输入 (MessageInput)
    |
    v
App.tsx (sendAgentMessage)
    |
    v
api.ts -> HttpAgent -> POST /agent (SSE)
    |
    v
Backend /agent endpoint
    |
    v
SSE events <- @ag-ui/client callbacks <- ag-ui graph stream
    |
    v
App.tsx (逐块更新 messages state)
    |
    v
Chat.tsx (渲染消息列表)
```

## 开发指南

### 添加新组件

1. 在 `src/components/` 中创建新的 `.tsx` 文件
2. 使用 PascalCase 命名
3. 导出为默认导出或具名导出
4. 在 `App.tsx` 中导入并使用

### 修改样式

- 使用 Tailwind CSS 类名
- 全局样式在 `src/index.css`
- 组件样式使用 Tailwind utility classes

### 添加 API 调用

1. 在 `src/api.ts` 中添加新函数
2. 使用 `fetch` 或 SSE Reader
3. 在组件中调用 API 函数

## 测试约定

- 测试文件与源文件同目录
- 测试文件命名：`*.test.tsx` 或 `*.spec.tsx`
- 使用 React Testing Library
- 测试用户交互和组件渲染

## 调试与日志

- 开发时需要同时启动后端服务（端口 8000）
- Vite 开发服务器会自动代理 `/api` 请求到后端
- 生产构建会生成静态文件，由后端服务提供
- 支持热模块替换（HMR）
- 使用 TypeScript 严格模式
- 使用浏览器开发者工具查看网络请求与 Console 日志
