# Mock / 占位注册表

本文件记录项目中用于开发、测试或降级场景的 Mock 与占位实现。

## Generative UI

### 前端 Catalog Mock

位置：`src/web/src/catalog/index.tsx`

当前 Catalog 注册了 6 种示例组件：`markdown_card`、`data_table`、`form`、`button_group`、`metric_card`、`chart`。这些组件本身是真实 React 组件，但后端 Agent 是否调用 `render_ui` 取决于模型行为与提示词引导。在以下场景中会用到“占位数据”：

- 单元测试使用固定 envelope 验证 `GenerativeUIRenderer` 与各个 UI 组件。
- 本地开发时若后端未触发 `render_ui`，可在浏览器控制台手动构造 envelope 验证渲染：

  ```ts
  window.__catalogMock = {
    type: 'form',
    props: {
      title: 'Mock Form',
      fields: [{ name: 'q', label: '问题' }],
    },
  }
  ```

### 后端 render_ui 工具

位置：`src/scaffold/plugins/tools/generative_ui.py`

`render_ui` 本身是一个透传工具：Agent 调用时直接返回 `{"generative_ui": {...}}`，不执行真实业务逻辑。真正的“渲染”由前端 Catalog 完成。该工具是占位/桥梁：

- 不依赖外部图表库或 UI 框架。
- 不持久化状态。
- 组件 props 的实际语义由前端 schema 决定。

### CopilotKit v2 样式注入

位置：`src/web/vite.config.ts`

由于 `@copilotkit/react-core/v2/styles.css` 是 Tailwind CSS v4 产物，而项目仍使用 Tailwind CSS v3，Vite 的 PostCSS/Tailwind 插件无法直接处理其中的 `@layer` 指令。`rawCopilotKitCssPlugin` 将该 CSS 以原始字符串方式注入 `<head>`，避免 PostCSS 解析错误。这是一种兼容性占位，未来若升级到 Tailwind CSS v4，可移除该插件并改为正常 import。

## 维护提示

- 新增 Catalog 组件时，请同步更新 `config.yaml` 中 `profiles.harness.default.system_prompt_suffix` 里的组件列表与字段说明。
- 更新 Mock envelope 示例后，应在 `src/web/src/catalog/__tests__` 与 `src/web/src/components/__tests__` 补充对应渲染/交互测试。
