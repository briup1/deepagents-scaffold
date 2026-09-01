# 08: extraction-coder 技能文件

**What to build:** 新建子 Agent 专属技能文件 extraction-coder，定义解析方案选型规则和迭代工作流指令，allowed-tools 声明与子 Agent 白名单一致。

**Blocked by:** 5 (run_extraction_script 迭代), 6 (run_extraction_script 收口)

**Status:** ready-for-agent

- [ ] 创建 extraction-coder/SKILL.md
- [ ] frontmatter: allowed-tools = "run_extraction_script normalize_upload_file"
- [ ] 解析方案选型章节（pandas/openpyxl/预处理）
- [ ] 迭代工作流指令（写→跑→看→改，最多 8 轮）
- [ ] 返回协议（脚本路径+摘要+自评，不返回完整内容）
- [ ] 测试：validate_skill_tools 通过
