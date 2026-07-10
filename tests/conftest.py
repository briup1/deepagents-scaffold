import logging
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from scaffold.api.app import create_app
from scaffold.infra.config.app_config import reload_app_config


@pytest.fixture(scope="session")
def project_root() -> Path:
    """返回项目根目录。"""
    return Path(__file__).parent.parent


@pytest.fixture(scope="session")
def test_config_path(project_root: Path) -> Path:
    """返回测试专用配置文件路径。"""
    return project_root / "config.test.yaml"


@pytest.fixture
def _reset_app_config(test_config_path: Path, monkeypatch: pytest.MonkeyPatch):
    """重置配置缓存并强制使用 config.test.yaml，测试后恢复日志状态。"""
    monkeypatch.setenv("SCAFFOLD_CONFIG_PATH", str(test_config_path))

    scaffold_logger = logging.getLogger("scaffold")
    old_level = scaffold_logger.level
    old_handlers = list(scaffold_logger.handlers)
    old_propagate = scaffold_logger.propagate

    reload_app_config()
    yield
    reload_app_config()

    scaffold_logger.setLevel(old_level)
    scaffold_logger.handlers.clear()
    scaffold_logger.handlers.extend(old_handlers)
    scaffold_logger.propagate = old_propagate


@pytest.fixture
def client(_reset_app_config) -> TestClient:
    """创建使用测试配置的 TestClient。"""
    app = create_app()
    with TestClient(app) as test_client:
        yield test_client
