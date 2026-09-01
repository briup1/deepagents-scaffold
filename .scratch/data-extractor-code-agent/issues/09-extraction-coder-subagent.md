# 09: extraction_coder 子 Agent 定义 + 配置

**What to build:** config.yaml 新增 extraction_coder 子 Agent 定义，配置 tools 白名单、skills 路径、permissions（allow+deny 最小闭包），确保装配成功而非静默跳过。

**Blocked by:** 7 (permissions 接线), 8 (技能文件)

**Status:** ready-for-agent

- [ ] config.yaml 新增 extraction_coder 子 Agent 定义
- [ ] tools: ["run_extraction_script", "normalize_upload_file"]
- [ ] skills: 指向 extraction-coder 技能目录
- [ ] permissions: allow 工作区 + deny 兜底
- [ ] 装配测试：extraction_coder 出现在构建结果中
- [ ] 非抽取 profile excluded_tools 排除两个新工具
