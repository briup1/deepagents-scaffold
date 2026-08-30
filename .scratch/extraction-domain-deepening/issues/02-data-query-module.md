# 02: data_query module + query 工具接入

**What to build:** "对 Extracted CSV 执行查询"获得一个唯一归属的深 module。新 module 提供单一入口：接收 Extraction Workspace、一组 Artifact 引用（artifact_id + 表名）和一个"拿到数据库连接后做什么"的回调；工件存在性与 Session-scoped 归属校验、临时文件创建与清理、表加载、SELECT-only 校验、结果 JSON 安全化全部藏在这条 seam 之后。query 工具改为薄编排：校验参数后调用该入口，用户无感知。

**Blocked by:** None (can start immediately)

**Status:** done

- [x] query 工具不再自己创建/清理临时文件，也不再自己做工件校验与 SELECT-only 校验
- [x] 临时文件在异常路径下仍被清理（有针对性测试）
- [x] 新 module 的专属测试覆盖：正常查询、多表加载、非 SELECT 拒绝、跨 thread_id 的 Artifact 拒绝、CSV 读取失败、SQL 执行失败
- [x] query 工具对外行为（名称、参数、返回结构、错误响应形状）不变，现有工具级测试不改断言仍通过
- [x] `pytest` 全量通过；`ruff check src tests` 通过
