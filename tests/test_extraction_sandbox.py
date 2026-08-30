"""子进程沙箱测试。"""

from __future__ import annotations

import tempfile
from pathlib import Path

import pytest

from scaffold.infra.sandbox import SubprocessSandbox


@pytest.fixture
def sandbox():
    return SubprocessSandbox()


class TestSubprocessSandbox:
    async def test_run_valid_script(self, sandbox: SubprocessSandbox) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            tmp = Path(tmpdir)
            input_dir = tmp / "input"
            output_dir = tmp / "output"
            input_dir.mkdir()
            output_dir.mkdir()

            script = tmp / "hello.py"
            script.write_text(
                """
import json
with open('/mnt/output/result.json', 'w') as f:
    json.dump({'ok': True}, f)
print('done')
""",
                encoding="utf-8",
            )

            # 沙箱通过环境变量映射路径；脚本使用默认值需确保 /mnt/output 可写，
            # 但 MVP 子进程无法创建 /mnt，因此脚本中使用相对路径更稳妥。
            # 此处测试 AST 白名单和输出收集。
            script.write_text(
                """
import json
import os
out_dir = os.environ.get('OUTPUT_DIR', '.')
out_file = os.path.join(out_dir, 'result.json')
with open(out_file, 'w') as f:
    json.dump({'ok': True}, f)
print('done')
""",
                encoding="utf-8",
            )

            result = await sandbox.run(script, input_dir, output_dir, timeout=10)

            assert result.exit_code == 0
            assert "done" in result.stdout
            assert "result.json" in result.output_files

    async def test_numpy_import_with_default_memory_limit(self, sandbox: SubprocessSandbox) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            tmp = Path(tmpdir)
            script = tmp / "numpy_import.py"
            script.write_text("import numpy as np\nprint(np.__version__)\n", encoding="utf-8")

            result = await sandbox.run(script, tmp / "in", tmp / "out")

            assert result.exit_code == 0, result.stderr

    async def test_forbidden_import(self, sandbox: SubprocessSandbox) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            tmp = Path(tmpdir)
            script = tmp / "bad.py"
            script.write_text("import requests\nrequests.get('https://example.com')\n", encoding="utf-8")
            with pytest.raises(ValueError, match="禁止导入模块"):
                await sandbox.run(script, tmp / "in", tmp / "out", timeout=10)

    async def test_forbidden_call(self, sandbox: SubprocessSandbox) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            tmp = Path(tmpdir)
            script = tmp / "bad.py"
            script.write_text("import subprocess\nsubprocess.run(['ls'])\n", encoding="utf-8")
            with pytest.raises(ValueError, match="禁止导入模块"):
                await sandbox.run(script, tmp / "in", tmp / "out", timeout=10)

    async def test_eval_blocked(self, sandbox: SubprocessSandbox) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            tmp = Path(tmpdir)
            script = tmp / "bad.py"
            script.write_text("eval('1+1')\n", encoding="utf-8")
            with pytest.raises(ValueError, match="禁止调用函数"):
                await sandbox.run(script, tmp / "in", tmp / "out", timeout=10)

    async def test_timeout(self, sandbox: SubprocessSandbox) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            tmp = Path(tmpdir)
            script = tmp / "sleep.py"
            script.write_text("import time\ntime.sleep(10)\n", encoding="utf-8")
            result = await sandbox.run(script, tmp / "in", tmp / "out", timeout=1)
            assert result.exit_code == -1
            assert "超时" in result.stderr
