# Mock Registry

本文件记录 CopilotKit 前端集成（Phase 2）中所有 Mock 占位，便于 Phase 4 按项替换为真实业务逻辑。

## Task 4: GenerativeUIRenderer

- **模块路径**: `src/web/src/components/GenerativeUIRenderer.tsx`
- **Mock 字段/方法**: `metadata` 参数当前由调用方传入；后端尚未真实 emit `metadata.generative_ui`。
- **当前假数据逻辑**: 单元测试 `src/web/src/components/__tests__/GenerativeUIRenderer.test.tsx` 中使用硬编码的 `{ type: 'markdown_card', title: 'T', content: 'C' }` 与 `{ type: 'data_table', title: 'T', columns: [...], rows: [...] }` 验证渲染。
- **未来需替换的真实业务逻辑**: 后端 Agent 在 AG-UI 文本事件中真实携带 `metadata.generative_ui`，本组件直接消费真实 metadata，不再依赖测试中的硬编码对象。

## Task 5: AgentSelector

- **模块路径**: `src/web/src/components/AgentSelector.tsx`
- **Mock 字段/方法**: 单元测试中 mock 的 `global.fetch` 返回 `{ agents: [{ name: 'default' }, { name: 'code_reviewer' }] }`。
- **当前假数据逻辑**: 测试使用硬编码 Agent 列表验证下拉框加载与选择事件。
- **未来需替换的真实业务逻辑**: 组件通过 `listAgents()` 调用真实的 `/api/agents/` 端点；测试数据替换为后端实际返回的 `{ name, type }` 对象。

## Task 6: App.tsx

- **模块路径**: `src/web/src/App.test.tsx`
- **Mock 字段/方法**:
  - 复用 Task 5 的 mock 数据，测试中 mock 的 `global.fetch` 返回 `{ agents: [{ name: 'default' }, { name: 'code_reviewer' }] }`。
  - 使用 `vi.mock('@copilotkit/react-core')` 与 `vi.mock('@copilotkit/react-ui')` 提供 mock 的 `CopilotKit`、`CopilotSidebar`、`CopilotChat` 运行时组件。
- **当前假数据逻辑**: 单元测试使用该硬编码 Agent 列表验证 `AgentSelector` 与 `CopilotKit` 的集成，以及 `runtimeUrl` 随 agent 切换的逻辑；CopilotKit 相关组件仅记录调用参数并渲染占位 DOM。
- **未来需替换的真实业务逻辑**: 当 `App.tsx` 通过 `AgentSelector` 调用真实 `/api/agents/` 端点时，mock 数据替换为后端实际返回的 `{ name, type }` 对象；测试可保留对真实 CopilotKit 组件的 mock，但 Agent 列表应来自真实 API 响应。

## Task 7: CopilotKit 消息流中的 Generative UI

- **模块路径**: `src/web/src/App.tsx` / `src/web/src/hooks/useGenerativeUI.tsx`
- **Mock 字段/方法**: `useGenerativeUI` 提供 `enableMock` 与 `mockMetadata` 选项；导出 `SAMPLE_MARKDOWN_CARD` 与 `SAMPLE_DATA_TABLE` 作为示例元数据；`App.tsx` 在 `import.meta.env.DEV` 下启用 `SAMPLE_MARKDOWN_CARD`。
- **当前假数据逻辑**:
  - `useGenerativeUI` 的 `renderMessage` 优先从消息对象提取 `metadata.generative_ui`。
  - 当真实 metadata 不存在、且 `enableMock` 为 true、且当前消息为 assistant 消息、且为当前（正在生成）消息时，回退到 `mockMetadata`（默认 `SAMPLE_MARKDOWN_CARD`）。
  - 用户消息与历史 assistant 消息不受 mock 影响，仍走默认气泡渲染。
  - `SAMPLE_MARKDOWN_CARD` 渲染 Markdown 卡片；`SAMPLE_DATA_TABLE` 渲染示例数据表，二者仅用于开发环境本地验证。
- **未来需替换的真实业务逻辑**: 后端 Agent 在 AG-UI 文本事件中真实携带 `metadata.generative_ui`；前端直接从事件 metadata 读取并渲染。届时移除 `enableMock`/`mockMetadata` 选项及 `SAMPLE_MARKDOWN_CARD`/`SAMPLE_DATA_TABLE` 示例数据，`CopilotChat` 仅在真实 metadata 存在时渲染 Generative UI。
