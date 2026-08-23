# ADR-0001：Demo 阶段保留 SubprocessSandbox

- **状态**：已接受（Accepted）
- **日期**：2026-08-22
- **决策者**：产品与开发团队

## 上下文

本项目的 Excel 抽取与分析功能需要执行 Agent 生成的 Python 脚本。设计文档 Phase 4 规划了"生产沙箱替换"，候选方案包括 E2B、Docker、Firecracker 等更专业的隔离技术。

经过架构审查（候选 2），我们已经把沙箱选择抽象为配置驱动的工厂层：`infra/sandbox/factory.py` + `execution_sandbox.provider`，但当前仍只有 `SubprocessSandbox` 一个适配器。

## 决策

**Demo 阶段继续保留 `SubprocessSandbox` 作为默认沙箱，不引入 Docker / E2B / Firecracker。**

理由：

1. **需求匹配**：当前产品目标是验证端到端抽取、分析、生成式 UI 的可行性，而非面向不可信代码的多租户生产环境。
2. **复杂度控制**：Docker / E2B 需要额外基础设施（Docker daemon、API key、镜像维护），Demo 阶段引入会拖慢迭代。
3. **迁移成本低**：候选 2 已完成工厂层抽象；后续切换到 Docker 或 E2B 只需：
   - 新增 `DockerSandbox` / `E2BSandbox` 实现 `Sandbox` 接口
   - 在 `get_sandbox()` 中注册
   - 修改 `config.yaml` 的 `execution_sandbox.provider`

## 已知风险

`SubprocessSandbox` 的安全边界有限：

- 已通过 AST 白名单限制 import、禁止危险调用、禁止网络与 shell。
- 但仍依赖进程级隔离，无法完全防御内存爆破、环境变量读取、决心绕过白名单的恶意脚本。

因此本方案**仅适用于 Demo / 内部使用 / 受信用户场景**。

## 触发条件

当以下任一条件成立时，应重新评估本决策：

- 产品对外开放给不可信用户
- 需要执行来自公共渠道的 Agent 生成代码
- 出现实际的安全事件或审计要求
- 需要满足 SOC2 / 等保等合规要求

## 结论

保留当前实现，把沙箱升级工作显式推迟到产品从 Demo 迈向生产多租户阶段。工厂层已就位，切换不会比现在更困难。
