"""Custom tools directory.

Place your custom tool modules here. Each module should expose async functions
that can be registered as agent tools.

Example:
    # plugins/tools/my_tool.py
    async def search_database(query: str) -> str:
        return f"Results for: {query}"

Then add to config.yaml:
    tools:
      - name: search_database
        use: scaffold.plugins.tools.my_tool:search_database
"""
