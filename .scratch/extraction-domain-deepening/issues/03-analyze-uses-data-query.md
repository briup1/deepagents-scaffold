# 03: analyze 工具接入 data_query，删除私有 import

**What to build:** analyze 工具不再 import query 工具的任何私有函数。它只保留"自然语言/比较意图 → SQL"的纯函数构造器，执行阶段调用与 query 工具相同的 data_query 入口。两个工具共享的全部机制只有一份实现。

**Blocked by:** 02: data_query module + query 工具接入

**Status:** done

- [x] analyze 工具中对 query 工具下划线函数的 import（含延迟 import）全部消失，`grep` 静态验证为零
- [x] analyze 工具内重复的临时文件 ceremony 删除
- [x] NL→SQL 构造器保持纯函数，拥有独立测试（不依赖 workspace/数据库）
- [x] analyze 工具对外行为不变，现有工具级测试不改断言仍通过
- [x] `pytest` 全量通过；`ruff check src tests` 通过
