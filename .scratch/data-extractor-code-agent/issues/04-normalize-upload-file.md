# 04: normalize_upload_file 工具

**What to build:** 新增预处理工具，接收上传文件，按封装语义（拆分合并单元格填充同值、处理删除线）产出规范化新文件，返回 normalized_artifact_id。

**Blocked by:** 1 (数据层基础)

**Status:** ready-for-agent

- [ ] normalize_upload_file 工具实现
- [ ] 合并单元格拆分：区域内所有单元格填充同值
- [ ] 删除线处理：默认过滤该行（config 可覆盖）
- [ ] 产出 normalized 类型工件，记录 source_upload_artifact_id
- [ ] 测试：合并单元格样本、删除线样本、正常文件
