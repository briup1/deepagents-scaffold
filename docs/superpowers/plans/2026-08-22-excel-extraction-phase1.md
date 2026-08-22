# Phase 1 实施计划：文件上传与会话工件

## 目标

实现用户在聊天框拖拽上传 Excel 文件，后端保存为**会话隔离的工件**，并提供 `preview_excel` 工具让 Agent 预览文件结构。

## 预计涉及文件

后端（约 7 个新文件 + 2 处改动）：
- 新建 `src/scaffold/infra/artifacts/models.py`
- 新建 `src/scaffold/infra/artifacts/repository.py`
- 新建 `src/scaffold/infra/artifacts/storage.py`
- 新建 `src/scaffold/api/routers/files.py`
- 新建 `src/scaffold/plugins/tools/preview_excel.py`
- 新建 `tests/test_artifacts.py`
- 新建 `tests/test_files_api.py`
- 修改 `src/scaffold/api/app.py`（注册 files 路由）
- 修改 `src/scaffold/infra/history/repository.py`（添加 artifacts 表迁移）
- 修改 `config.yaml`（注册 preview_excel 工具）
- 修改 `pyproject.toml`（添加 `openpyxl` 依赖）

前端（约 3 个新文件 + 2 处改动）：
- 新建 `src/web/src/api/files.ts`
- 新建 `src/web/src/components/FileUploadDropzone.tsx`
- 修改 `src/web/src/App.tsx`（在聊天区加入拖拽上传）
- 修改 `src/web/src/index.css`（拖拽区域样式）

## 任务拆分与依赖

### 任务 1：工件元数据模型与存储（无依赖）

实现 `Artifact` Pydantic 模型和 `ArtifactRepository`。

```python
class Artifact(BaseModel):
    artifact_id: str
    thread_id: str
    artifact_type: Literal["upload", "script", "extraction", "report"]
    original_name: str | None
    stored_path: str
    mime_type: str | None
    size_bytes: int
    created_at: str
    metadata: dict[str, Any]
```

### 任务 2：文件系统存储（依赖任务 1）

实现 `ArtifactStorage`，负责：
- 创建目录：`data/artifacts/{thread_id}/{uploads,scripts,extractions,reports}/`
- 保存上传文件，生成 `artifact_id`
- 读取文件内容
- 删除工件文件

### 任务 3：数据库迁移（无依赖）

在 `HistoryRepository.migrate()` 或新增 `ArtifactRepository.migrate()` 中创建 `artifacts` 表。

### 任务 4：API 路由（依赖任务 1-3）

实现 `POST /api/files/upload` 和 `GET /api/files/?thread_id=xxx`。

### 任务 5：preview_excel 工具（依赖任务 2）

实现 `src/scaffold/plugins/tools/preview_excel.py`：

```python
async def preview_excel(artifact_id: str, sheet_index: int = 0, limit: int = 20) -> dict:
    # 使用 openpyxl 读取 Excel
    # 返回：sheet_names, columns, sample_rows, total_rows
```

并在 `config.yaml` 中注册。

### 任务 6：前端拖拽上传（依赖任务 4）

- 实现 `POST /api/files/upload` 的 TypeScript 客户端；
- 在聊天输入区添加拖拽区域；
- 上传成功后把 `artifact_id` 放入消息 state/attachments。

### 任务 7：测试

- 后端单元测试：`ArtifactRepository`、文件存储、`/api/files/upload`、`preview_excel`；
- 前端测试：上传组件渲染测试。

### 任务 8：文档更新

更新 `CLAUDE.md` 中的快速命令和验证方式（如果需要）。

## 验证方式

启动开发环境后：

```bash
# 后端测试
pytest tests/test_files_api.py tests/test_artifacts.py -v

# 手动验证
bash scripts/dev.sh
curl -X POST http://localhost:8000/api/files/upload \
  -F "thread_id=test-thread-001" \
  -F "file=@/path/to/quote.xlsx"
```

## 建议下一步

完成 Phase 1 后再进入 Phase 2（三段式抽取 Skill + 代码执行沙箱）。
