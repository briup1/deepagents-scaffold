# 07: subagent_definitions permissions 接线

**What to build:** SubAgentDefinitionConfig 的 permissions 字段从 list[str] 改为 list[dict]（含 paths/operations/mode），builder 映射为 FilesystemPermission 并校验必填字段。

**Blocked by:** None (can start immediately)

**Status:** ready-for-agent

- [ ] SubAgentDefinitionConfig.permissions 类型改为 list[dict]
- [ ] builder 映射为 FilesystemPermission
- [ ] 校验必填字段（paths、operations）
- [ ] 测试：配置解析、映射正确、缺失字段报错
