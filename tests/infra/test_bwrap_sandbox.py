"""BwrapSandbox 端到端隔离探针测试。

bwrap 不存在（如 CI / 未安装机器）时整体 skip；存在时验证隔离底线。
"""

from __future__ import annotations

import shutil
import sys
from pathlib import Path

import pytest

from scaffold.infra.sandbox.bwrap_sandbox import BwrapSandbox

pytestmark = pytest.mark.skipif(shutil.which("bwrap") is None, reason="bwrap 未安装")

VENV_ROOT = Path(sys.executable).parent.parent


def _bindings_ok() -> bool:
    """当前机器 bwrap userns 是否可用（AppArmor 可能未放行）。"""
    import subprocess

    try:
        subprocess.run(
            ["bwrap", "--unshare-all", "--ro-bind", "/usr", "/usr", "--ro-bind", "/bin", "/bin",
             "--ro-bind", "/lib", "/lib", "--ro-bind", "/lib64", "/lib64", "/bin/true"],
            check=True,
            capture_output=True,
            timeout=10,
        )
        return True
    except Exception:
        return False


requires_userns = pytest.mark.skipif(not _bindings_ok(), reason="bwrap userns 被 AppArmor 限制（先执行 scripts/setup_bwrap_apparmor.sh）")


@pytest.fixture
def workspace(tmp_path: Path):
    input_dir = tmp_path / "input"
    output_dir = tmp_path / "output"
    input_dir.mkdir()
    output_dir.mkdir()
    (input_dir / "data.txt").write_text("hello", encoding="utf-8")
    return input_dir, output_dir


@requires_userns
async def test_normal_script_produces_output(workspace):
    """正常脚本：读输入、写输出，行为与 subprocess 沙箱一致。"""
    input_dir, output_dir = workspace
    script = output_dir.parent / "extract.py"
    script.write_text(
        "import os\n"
        "data = open(os.path.join(os.environ['INPUT_DIR'], 'data.txt')).read()\n"
        "open(os.path.join(os.environ['OUTPUT_DIR'], 'result.txt'), 'w').write(data.upper())\n"
        "print('done')\n",
        encoding="utf-8",
    )
    result = await BwrapSandbox().run(script, input_dir, output_dir)
    assert result.exit_code == 0
    assert "done" in result.stdout
    assert result.output_files["result.txt"] == b"HELLO"


@requires_userns
async def test_isolation_probe(workspace):
    """恶意探针：读 /etc/passwd、写输入目录、读宿主机项目目录全部被拒。"""
    input_dir, output_dir = workspace
    script = output_dir.parent / "probe.py"
    script.write_text(
        "import os\n"
        "r = {}\n"
        "try: open('/etc/passwd'); r['etc'] = 'LEAKED'\n"
        "except Exception: r['etc'] = 'BLOCKED'\n"
        "try: open(os.path.join(os.environ['INPUT_DIR'], 'x'), 'w'); r['in'] = 'LEAKED'\n"
        "except Exception: r['in'] = 'BLOCKED'\n"
        f"try: open('{Path.cwd()}/config.yaml'); r['host'] = 'LEAKED'\n"
        "except Exception: r['host'] = 'BLOCKED'\n"
        "print(r)\n",
        encoding="utf-8",
    )
    result = await BwrapSandbox().run(script, input_dir, output_dir)
    assert result.exit_code == 0
    assert "'etc': 'BLOCKED'" in result.stdout
    assert "'in': 'BLOCKED'" in result.stdout
    assert "'host': 'BLOCKED'" in result.stdout


@requires_userns
async def test_network_import_rejected_by_ast_scan(workspace):
    """网络第一道闸：AST 静态扫描拒绝 urllib/socket 导入（bwrap --unshare-net 为第二道）。"""
    input_dir, output_dir = workspace
    script = output_dir.parent / "net.py"
    script.write_text("import urllib.request\n", encoding="utf-8")
    with pytest.raises(ValueError, match="禁止导入模块"):
        await BwrapSandbox().run(script, input_dir, output_dir)


@requires_userns
async def test_memory_limit_kills_allocation(workspace):
    """超出内存限制：分配失败（MemoryError）而非拖垮宿主机。"""
    input_dir, output_dir = workspace
    script = output_dir.parent / "mem.py"
    script.write_text(
        "try:\n"
        "    x = bytearray(1024 * 1024 * 1024)\n"
        "    print('LEAKED')\n"
        "except MemoryError:\n"
        "    print('BLOCKED: MemoryError')\n",
        encoding="utf-8",
    )
    result = await BwrapSandbox().run(script, input_dir, output_dir, memory_limit_mb=256)
    assert "BLOCKED" in result.stdout
    assert "LEAKED" not in result.stdout


@requires_userns
async def test_timeout_kills_process(workspace):
    """超时：进程被杀死，返回结构化超时标记。"""
    input_dir, output_dir = workspace
    script = output_dir.parent / "sleeper.py"
    script.write_text("import time\ntime.sleep(100)\n", encoding="utf-8")
    result = await BwrapSandbox().run(script, input_dir, output_dir, timeout=2)
    assert result.exit_code == -1
    assert "执行超时" in result.stderr


async def test_extra_env_host_paths_mapped(workspace, monkeypatch):
    """extra_env 中的宿主机 input/output 路径前缀被替换为沙箱内路径。"""
    input_dir, output_dir = workspace
    captured = {}

    class FakeProc:
        returncode = 0

        async def communicate(self):
            return b"", b""

    import asyncio

    async def fake_exec(*args, **kwargs):
        captured["args"] = args
        return FakeProc()

    monkeypatch.setattr(asyncio, "create_subprocess_exec", fake_exec)
    script = output_dir.parent / "extract.py"
    script.write_text("print('ok')\n", encoding="utf-8")
    sandbox = BwrapSandbox()
    # 跳过 AST 校验之外的执行，直接观察参数构造
    await sandbox.run(script, input_dir, output_dir, extra_env={"OUTPUT_FILE": str(output_dir / "x.csv")})
    args = list(captured["args"])
    i = args.index("OUTPUT_FILE")
    assert args[i + 1] == "/work/out/x.csv"


def test_bwrap_missing_raises_readable_error(workspace, monkeypatch):
    """bwrap 二进制不存在时抛出可读错误（非裸 FileNotFoundError）。"""
    import asyncio

    input_dir, output_dir = workspace
    script = output_dir.parent / "extract.py"
    script.write_text("print('ok')\n", encoding="utf-8")

    sandbox = BwrapSandbox(bwrap_executable="/nonexistent/bwrap")
    with pytest.raises(RuntimeError, match="bwrap 不可用"):
        asyncio.run(sandbox.run(script, input_dir, output_dir))
