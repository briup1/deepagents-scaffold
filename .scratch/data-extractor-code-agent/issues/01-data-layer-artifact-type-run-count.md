# 01: 数据层基础 - ArtifactType 扩展 + run_count 字段

**What to build:** 扩展 ArtifactType 支持 "normalized" 类型，extraction_tasks 表新增 run_count 字段（含迁移），为后续工具和子 Agent 提供数据基础。

**Blocked by:** None (can start immediately)

**Status:** ready-for-agent

- [ ] ArtifactType Literal 增加 "normalized"
- [ ] extraction_tasks 表 ALTER TABLE 添加 run_count INTEGER NOT NULL DEFAULT 0
- [ ] 迁移逻辑：PRAGMA table_info 检查缺列后 ADD COLUMN
- [ ] 存量库升级测试：旧库可启动、计数可读写
