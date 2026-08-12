## Task 4: GenerativeUIRenderer

- **模块路径**: `src/web/src/components/GenerativeUIRenderer.tsx`
- **Mock 字段/方法**: `metadata` 参数当前由调用方传入；后端尚未真实 emit `metadata.generative_ui`。
- **当前假数据逻辑**: 单元测试中使用硬编码的 `{ type: 'markdown_card' | 'data_table', ... }` 验证渲染。
- **未来需替换的真实业务逻辑**: 当后端 Agent 在 AG-UI 文本事件中携带 `metadata.generative_ui` 时，本组件应直接消费真实 metadata，不再依赖硬编码测试数据。
