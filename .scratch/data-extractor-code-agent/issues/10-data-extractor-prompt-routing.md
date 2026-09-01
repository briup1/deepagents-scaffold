# 10: data_extractor prompt 路由增强

**What to build:** data_extractor profile 的 system_prompt_suffix 增加路由规则：异常信号→预处理→委派；模板命中→快路径；复杂→委派。

**Blocked by:** 3 (preview_excel 增强), 4 (normalize_upload_file), 9 (子 Agent 定义)

**Status:** ready-for-agent

- [ ] system_prompt_suffix 增加路由规则
- [ ] 预处理决策：preview 异常信号 → 先 normalize_upload_file
- [ ] 委派协议：需求契约+验收标准+结构摘要+工作区约定
- [ ] 集成测试：完整链路可走通
