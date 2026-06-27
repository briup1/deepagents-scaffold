"""自定义工具目录。

将自定义工具模块放在此处。每个模块应暴露异步函数，
这些函数可以被注册为 agent 工具。

示例:
    # plugins/tools/my_tool.py
    async def search_database(query: str) -> str:
        return f"Results for: {query}"

然后在 config.yaml 中添加:
    tools:
      - name: search_database
        use: scaffold.plugins.tools.my_tool:search_database
"""
