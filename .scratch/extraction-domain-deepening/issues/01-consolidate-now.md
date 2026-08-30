# 01: 收敛六处重复的 `_now()`

**What to build:** 时间戳格式化在整个仓库只有一份实现。目前六处各自为政的 `_now()`（extraction workspace、history repository 两处、artifacts repository、抽取工具公共模块、validate 工具）统一为一处定义、五处引用。对外行为完全不变——这是一次让后续改动更容易的 prefactor。

**Blocked by:** None (can start immediately)

**Status:** done

- [x] 仓库中 `_now` 的定义只剩一处，其余位置全部改为 import 引用
- [x] 时间戳输出格式与重构前完全一致（ISO 格式、时区行为不变）
- [x] `pytest` 全量通过
- [x] `ruff check src tests` 通过
