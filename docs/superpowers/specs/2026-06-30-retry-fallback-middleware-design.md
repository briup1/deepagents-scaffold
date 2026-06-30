# 模型重试、工具重试与模型回退中间件设计

## 背景

项目当前中间件体系已覆盖工具错误处理、循环检测、上下文注入、Token 统计、安全终止、摘要压缩等能力，但缺少**模型调用重试**、**工具调用重试**和**模型故障回退**三类韧性（resilience）能力。生产环境中网络抖动、Provider 限流、模型服务短暂不可用是常见问题，需要一套配置驱动的中间件来应对。

## 目标

在现有 Deer-Flow 适配器架构下，新增三个中间件：

1. `ModelRetryMiddleware`：模型调用失败时按指数退避重试。
2. `ToolRetryMiddleware`：工具调用失败时重试。
3. `ModelFallbackMiddleware`：主模型失败时自动切换到备选模型。

设计遵循项目既有约定：

- 配置是 `config.yaml` 的唯一事实来源；
- 中间件通过 `MiddlewareRegistry` 注册别名；
- 尽量复用 LangChain/DeepAgents 原生实现，只在外围做薄适配；
- 异步优先；
- 仅补充单元测试。

## 非目标

- 不实现熔断器（Circuit Breaker）；
- 不实现自定义退避策略（只支持指数退避 + jitter）；
- 不增加结构化日志字段或 StreamBridge 事件；
- 不引入端到端/集成测试。

## 方案选型

采用**薄适配器层（方案 B）**：

在 `src/scaffold/infra/middleware/deerflow_adapters/` 下新增三个适配器类，接收 scaffold 风格的配置，内部实例化并委托给 LangChain 原生中间件。

相比原生直通（方案 A），适配器层能统一配置语义、封装“状态码→异常判断”和“模型引用→BaseChatModel”的转换逻辑，避免工厂出现大量特例代码。相比统一 `ResilienceMiddleware`（方案 C），薄适配器更贴合原生能力，升级和单独开关都更灵活。

## 组件设计

### 新增文件

```
src/scaffold/infra/middleware/deerflow_adapters/
├── model_retry.py          # ModelRetryAdapter
├── tool_retry.py           # ToolRetryAdapter
└── model_fallback.py       # ModelFallbackAdapter
```

### 修改文件

- `src/scaffold/infra/middleware/registry.py`：注册三个新别名。
- `src/scaffold/infra/middleware/factory.py`：无需修改，配置通过现有 kwargs 机制传入；`ModelFallbackAdapter` 通过 `$config.models` 注入模型配置列表。

### 依赖方向

适配器位于 `infra` 层，允许依赖 `core` 的 `create_chat_model()` 和 `AppConfig`，符合项目分层规范。

## 配置 Schema

### config.yaml 示例

```yaml
middleware:
  items:
    - name: ModelFallbackMiddleware
      enabled: true
      kwargs:
        models: $config.models
        fallback_models:
          - gpt-4o-mini
          - claude-3-5-sonnet

    - name: ModelRetryMiddleware
      enabled: true
      kwargs:
        max_retries: 2
        backoff_factor: 2.0
        initial_delay: 1.0
        max_delay: 60.0
        jitter: true
        retry_on_status_codes: [429, 502, 503, 504]

    - name: ToolRetryMiddleware
      enabled: true
      kwargs:
        max_retries: 1
        backoff_factor: 2.0
        initial_delay: 1.0
        max_delay: 60.0
        jitter: true
        retry_on_status_codes: [429, 502, 503, 504]
```

### 字段说明

| 字段 | 类型 | 默认值 | 说明 |
|---|---|---|---|
| `max_retries` | int | Model=2, Tool=1 | 初始调用之外的最大重试次数 |
| `backoff_factor` | float | 2.0 | 退避倍数 |
| `initial_delay` | float | 1.0 | 首次重试前等待秒数 |
| `max_delay` | float | 60.0 | 退避增长上限 |
| `jitter` | bool | true | 是否加入 ±25% 随机抖动 |
| `retry_on_status_codes` | list[int] | [429, 502, 503, 504] | 触发重试的 HTTP 状态码 |
| `models` | list[ModelConfig] | 必填 | 通过 `$config.models` 注入的全部模型配置 |
| `fallback_models` | list[str] | 必填 | 按 `ModelConfig.name` 引用备选模型 |

## 适配器实现细节

### 通用重试判断函数

```python
def _build_retry_predicate(status_codes: list[int]):
    status_set = set(status_codes)

    def should_retry(exc: Exception) -> bool:
        code = getattr(exc, "status_code", None)
        if code is not None and code in status_set:
            return True
        return isinstance(exc, _RETRIABLE_PROVIDER_EXCEPTIONS)

    return should_retry
```

- 优先按异常对象的 `status_code` 属性匹配；
- 其次匹配常见 Provider 限流/超时异常（如 `openai.RateLimitError`、`anthropic.RateLimitError`、`httpx.TimeoutException`），通过延迟 import 避免硬依赖；
- 业务异常（如 `ValueError`）不重试。

### ModelRetryAdapter

```python
class ModelRetryAdapter(AgentMiddleware):
    def __init__(self, *, max_retries: int = 2, backoff_factor: float = 2.0,
                 initial_delay: float = 1.0, max_delay: float = 60.0,
                 jitter: bool = True,
                 retry_on_status_codes: list[int] | None = None) -> None:
        self._middleware = ModelRetryMiddleware(
            max_retries=max_retries,
            retry_on=_build_retry_predicate(retry_on_status_codes or [429, 502, 503, 504]),
            on_failure="continue",
            backoff_factor=backoff_factor,
            initial_delay=initial_delay,
            max_delay=max_delay,
            jitter=jitter,
        )

    def wrap_model_call(self, state, runtime, handler):
        return self._middleware.wrap_model_call(state, runtime, handler)

    async def awrap_model_call(self, state, runtime, handler):
        return await self._middleware.awrap_model_call(state, runtime, handler)
```

### ToolRetryAdapter

与 `ModelRetryAdapter` 同构，内部使用 `ToolRetryMiddleware`，默认 `max_retries=1`，`tools` 省略表示全部工具生效。

### ModelFallbackAdapter

```python
class ModelFallbackAdapter(AgentMiddleware):
    def __init__(self, *, models: list[ModelConfig],
                 fallback_models: list[str]) -> None:
        fallback_chat_models = [
            create_chat_model(_resolve_model_by_name(name, models))
            for name in fallback_models
        ]
        self._middleware = ModelFallbackMiddleware(*fallback_chat_models)

    def wrap_model_call(self, state, runtime, handler):
        return self._middleware.wrap_model_call(state, runtime, handler)

    async def awrap_model_call(self, state, runtime, handler):
        return await self._middleware.awrap_model_call(state, runtime, handler)
```

- `models` 通过 `$config.models` 注入全部模型配置；
- `fallback_models` 按 `ModelConfig.name` 在 `models` 中查找；
- 匹配到 `ModelConfig` 后通过 `create_chat_model()` 实例化为 `BaseChatModel`；
- 匹配失败抛 `ValueError`；
- `_resolve_model_by_name` 为未展示的模块级辅助函数，负责按名称匹配模型配置。

## 中间件链顺序

建议 `config.yaml` 中按以下顺序声明：

```text
ModelFallbackMiddleware
  → ModelRetryMiddleware
    → SafetyTerminationMiddleware
      → LoopDetectionMiddleware
      → DynamicContextMiddleware
      → ...
        → 模型调用

ToolRetryMiddleware
  → ToolErrorHandlingMiddleware
    → 工具执行
```

原因：

- `ModelFallback` 在最外层，主模型重试耗尽后再切换备选；
- `ModelRetry` 在 `SafetyTermination` 之前，避免对安全拒绝信号做无意义重试；
- `ToolRetry` 在 `ToolErrorHandling` 之前，重试耗尽后再把异常转成 error ToolMessage。

## 错误处理语义

| 中间件 | 默认重试 | 耗尽后行为 |
|---|---|---|
| `ModelRetryMiddleware` | `max_retries=2` | `on_failure="continue"`，返回错误 AIMessage，让 Agent 继续运行 |
| `ToolRetryMiddleware` | `max_retries=1` | `on_failure="continue"`，返回错误 ToolMessage，Agent 自行决定下一步 |
| `ModelFallbackMiddleware` | 按 `fallback_models` 顺序 | 全部备选失败时抛异常，快速失败 |

## 日志

按项目现有风格使用普通 logger：

- 重试时记录 `warning`，包含 `thread_id`、`attempt`、`status_code`；
- 回退时记录 `warning`，包含 `thread_id`、`fallback_model`；
- 不引入结构化字段，不写入 StreamBridge。

## 测试

仅补充适配器单元测试：

```
tests/infra/middleware/deerflow_adapters/
├── test_model_retry.py
├── test_tool_retry.py
└── test_model_fallback.py
```

覆盖：

1. 配置解析：状态码列表、fallback_models 名称查找；
2. `retry_on` callable：状态码匹配、Provider 异常匹配、业务异常不匹配；
3. 委托调用：验证内部原生中间件被正确实例化和调用。

## 风险与后续扩展

1. **Provider 异常类硬编码**：`_RETRIABLE_PROVIDER_EXCEPTIONS` 需要随依赖升级维护，后续可考虑通过配置扩展。
2. **状态码不适用于所有异常**：部分工具抛出的异常没有 `status_code`，依赖 Provider 异常类兜底。
3. **Fallback 模型配置**：当前只支持引用现有模型配置，未来可考虑支持内联模型字符串作为补充。
