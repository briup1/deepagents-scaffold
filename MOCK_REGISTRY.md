## Task 4: GenerativeUIRenderer

- **模块路径**: `src/web/src/components/GenerativeUIRenderer.tsx`
- **Mock 字段/方法**: `metadata` 参数当前由调用方传入；后端尚未真实 emit `metadata.generative_ui`。
- **当前假数据逻辑**: 单元测试中使用硬编码的 `{ type: 'markdown_card' | 'data_table', ... }` 验证渲染。
- **未来需替换的真实业务逻辑**: 当后端 Agent 在 AG-UI 文本事件中携带 `metadata.generative_ui` 时，本组件应直接消费真实 metadata，不再依赖硬编码测试数据。

## Task 5: AgentSelector

- **模块路径**: `src/web/src/components/AgentSelector.tsx`
- **Mock 字段/方法**: 单元测试中 mock 的 `global.fetch` 返回 `{ agents: [{ name: 'default' }, { name: 'code_reviewer' }] }`。
- **当前假数据逻辑**: 测试使用硬编码 Agent 列表验证下拉框加载与选择事件。
- **未来需替换的真实业务逻辑**: 组件通过 `listAgents()` 调用真实的 `/api/agents/` 端点；测试数据替换为后端实际返回的 `{ name, type }` 对象。

## Task 6: App.tsx

- **模块路径**: `src/web/src/App.test.tsx`
- **Mock 字段/方法**: 复用 Task 5 的 mock 数据，测试中 mock 的 `global.fetch` 返回 `{ agents: [{ name: 'default' }, { name: 'code_reviewer' }] }`。
- **当前假数据逻辑**: 单元测试使用该硬编码 Agent 列表验证 `AgentSelector` 与 `CopilotKit` 的集成，以及 `runtimeUrl` 随 agent 切换的逻辑。
- **未来需替换的真实业务逻辑**: 当 `App.tsx` 通过 `AgentSelector` 调用真实 `/api/agents/` 端点时，mock 数据替换为后端实际返回的 `{ name, type }` 对象。

## Task 7: CopilotKit 消息流中的 Generative UI

- **模块路径**: `src/web/src/App.tsx` / `src/web/src/hooks/useGenerativeUI.ts`
- **Mock 字段/方法**: `useGenerativeUI` 提供 `mockMetadata` 选项；默认传入 `SAMPLE_MARKDOWN_CARD`。
- **当前假数据逻辑**: 若后端 Agent 尚未输出 `metadata.generative_ui`，`renderMessage` 回退到 `mockMetadata`，在 `CopilotChat` 中渲染 `MarkdownCard`/`DataTable`，以验证 UI 组件工作正常。
- **未来需替换的真实业务逻辑**: 后端 Agent 在 AG-UI 文本事件中真实携带 `metadata.generative_ui`，前端直接从事件 metadata 读取；移除 `mockMetadata` 后 `CopilotChat` 仅在真实 metadata 存在时渲染 Generative UI。
