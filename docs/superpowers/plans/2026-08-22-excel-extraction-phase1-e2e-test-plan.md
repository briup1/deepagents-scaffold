# Phase 1 端到端测试方案

## 1. 测试目标

验证 Phase 1 核心能力：

1. 用户能在聊天框上传 Excel 文件；
2. 上传文件按 **会话（thread_id）隔离** 保存；
3. Agent 可通过 `preview_excel` 工具读取上传文件的结构；
4. 非 Excel 文件被正确拒绝；
5. 前端上传组件与后端 API 链路连通。

## 2. 测试策略

- **后端端到端**：使用 `httpx.AsyncClient` / `TestClient` 走完整链路：上传 → 落盘 → 查表 → 调工具预览；
- **隔离性测试**：两个不同 thread 分别上传文件，验证彼此不可见；
- **前端单元/集成**：用 Vitest + React Testing Library 验证拖拽组件触发上传并反馈结果；
- **全栈冒烟**（可选）：启动 `scripts/dev.sh` 后，用 Playwright 或手动 curl 走一遍拖拽上传 → 页面显示文件卡片。

## 3. 测试环境

- 后端启动或直接使用 FastAPI `TestClient`；
- 数据库使用测试 SQLite（`config.test.yaml` 已配置）；
- 文件存储目录指向临时目录（测试 fixture 中覆盖 `data/artifacts` 根目录）。

## 4. 测试用例

### 4.1 后端端到端用例

| 编号 | 场景 | 前置条件 | 操作步骤 | 预期结果 |
|------|------|----------|----------|----------|
| BE-01 | 正常上传 Excel | 服务运行；临时目录已清空 | 1. POST `/api/files/upload` 上传 `quote.xlsx`<br>2. 参数携带 `thread_id=t1` | 返回 `200`，包含 `artifact_id`、`stored_path`、`mime_type`；文件真实保存到 `{tmp}/artifacts/t1/uploads/`；`artifacts` 表存在一条 `thread_id=t1` 的记录 |
| BE-02 | 预览上传文件 | BE-01 已完成 | 1. 调用 `preview_excel(artifact_id, limit=3)` | 返回 `sheet_names`、非空 `columns`、3 行 sample_rows，`total_rows >= 3` |
| BE-03 | 跨线程隔离 | 服务运行 | 1. 用 `thread_id=t1` 上传 `a.xlsx`<br>2. 用 `thread_id=t2` 上传 `b.xlsx`<br>3. GET `/api/files/?thread_id=t1` | `t1` 列表中只有 `a.xlsx`，没有 `b.xlsx`；文件目录中 `t1` 和 `t2` 目录独立 |
| BE-04 | 拒绝非 Excel 文件 | 服务运行 | 1. POST `/api/files/upload` 上传 `malicious.py` | 返回 `400` / `415`，`artifacts` 表无记录，磁盘无残留 |
| BE-05 | 缺少 thread_id | 服务运行 | 1. POST `/api/files/upload` 不携带 `thread_id` | 返回 `422` |
| BE-06 | 空文件上传 | 服务运行 | 1. 上传 0 字节 `.xlsx` | 返回 `400`，提示文件为空 |
| BE-07 | 大文件限制 | 服务运行 | 1. 上传超过 20MB 的 `.xlsx` | 返回 `413`（或配置的大小限制错误） |

### 4.2 前端测试用例

| 编号 | 场景 | 操作步骤 | 预期结果 |
|------|------|----------|----------|
| FE-01 | 拖拽上传 Excel | 1. 渲染 `FileUploadDropzone`<br>2. 模拟 drop 一个 `.xlsx` 文件 | 组件调用上传 API，显示文件卡片，无错误提示 |
| FE-02 | 错误反馈 | 1. 拖拽上传 `.py` 文件 | 组件显示“仅支持 Excel 文件”提示，不调用 API |
| FE-03 | 文件卡片展示 | 1. 上传成功后 | 聊天输入区显示文件名 + 大小；`artifact_id` 被正确附加到待发消息中 |

## 5. 关键断言示例

### 后端上传断言

```python
async def test_upload_excel(client, tmp_artifact_root):
    resp = await client.post(
        "/api/files/upload",
        data={"thread_id": "t-001"},
        files={"file": ("quote.xlsx", excel_bytes, "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")},
    )
    assert resp.status_code == 200
    data = resp.json()
    assert data["thread_id"] == "t-001"
    assert data["artifact_type"] == "upload"
    assert data["original_name"] == "quote.xlsx"
    assert Path(data["stored_path"]).exists()
```

### 隔离性断言

```python
async def test_thread_isolation(client, tmp_artifact_root):
    await client.post("/api/files/upload", data={"thread_id": "t1"}, files={"file": excel_a})
    await client.post("/api/files/upload", data={"thread_id": "t2"}, files={"file": excel_b})

    resp = await client.get("/api/files/?thread_id=t1")
    data = resp.json()
    assert len(data["artifacts"]) == 1
    assert data["artifacts"][0]["thread_id"] == "t1"
```

### preview_excel 断言

```python
async def test_preview_excel(client, artifact_id):
    result = await preview_excel(artifact_id=artifact_id, sheet_index=0, limit=5)
    assert "sheet_names" in result
    assert len(result["columns"]) > 0
    assert len(result["sample_rows"]) == 5
```

## 6. 验收标准

- BE-01 ~ BE-07 全部通过；
- FE-01 ~ FE-03 全部通过；
- 代码覆盖率：新增后端模块不低于 80%；
- 手动验证命令可复现：

```bash
bash scripts/dev.sh
curl -X POST http://localhost:8000/api/files/upload \
  -F "thread_id=test-thread-001" \
  -F "file=@/path/to/quote.xlsx"
```

## 7. 自动化脚本

```bash
# 后端 E2E 测试
pytest tests/test_files_api.py tests/test_artifacts.py tests/test_preview_excel.py -v

# 前端测试
cd src/web && npm test -- FileUploadDropzone
```
