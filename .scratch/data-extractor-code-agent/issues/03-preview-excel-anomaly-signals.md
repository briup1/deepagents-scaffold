# 03: preview_excel 增强 - 异常信号 + normalized 放行

**What to build:** preview_excel 在现有结构预览基础上返回异常信号（合并单元格数量、删除线单元格数量），同时放行 normalized 类型工件预览。

**Blocked by:** 1 (数据层基础)

**Status:** ready-for-agent

- [ ] preview_excel 返回异常信号：merged_cells_count、strikethrough_count
- [ ] 放行 normalized 类型工件（当前拒绝非 upload 类型）
- [ ] 测试：upload 和 normalized 工件均可预览，异常信号正确返回
