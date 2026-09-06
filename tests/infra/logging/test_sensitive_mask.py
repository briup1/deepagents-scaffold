"""日志敏感信息脱敏（红线 9 相关）：消息中的密钥模式必须被掩码。

覆盖 sk- 前缀密钥、X-API-Key 头值、api_key/token/secret/password 赋值形态；
脱敏不得改变日志字段结构（仅替换消息内容）。
"""

from __future__ import annotations

import logging

from scaffold.infra.logging.config import configure_logging
from scaffold.infra.logging.structured import SensitiveDataFilter, mask_sensitive


def _record(msg: object, args: object = ()) -> logging.LogRecord:
    return logging.LogRecord(
        name="scaffold.test",
        level=logging.INFO,
        pathname=__file__,
        lineno=1,
        msg=msg,
        args=args,  # type: ignore[arg-type]
        exc_info=None,
    )


class TestMaskSensitive:
    def test_sk_prefix_key_masked(self) -> None:
        assert mask_sensitive("call failed with sk-abcdefghij1234567890XYZ") == "call failed with sk-***"

    def test_short_sk_token_not_masked(self) -> None:
        # 长度不足的 sk- 片段按普通文本对待，避免误伤
        assert mask_sensitive("value: sk-abc") == "value: sk-abc"

    def test_api_key_header_masked(self) -> None:
        assert mask_sensitive("request headers: X-API-Key: super-secret-token-123") == (
            "request headers: X-API-Key: ***"
        )

    def test_assignment_forms_masked(self) -> None:
        assert mask_sensitive('body={"api_key": "abcdef123456"}') == 'body={"api_key": "***"}'
        assert mask_sensitive("token=abc.def.ghi") == "token=***"
        assert mask_sensitive("secret : 'shhh'") == "secret : '***'"

    def test_normal_message_untouched(self) -> None:
        assert mask_sensitive("agent 'default' created with 15 tools") == "agent 'default' created with 15 tools"

    def test_password_assignment_masked(self) -> None:
        assert mask_sensitive("login password=hunter2") == "login password=***"


class TestSensitiveDataFilter:
    def test_filter_masks_msg_and_args(self) -> None:
        record = _record("model call failed, key=%s", ("sk-abcdef1234567890",))
        assert SensitiveDataFilter().filter(record)
        assert record.getMessage() == "model call failed, key=sk-***"

    def test_filter_masks_plain_msg(self) -> None:
        record = _record("Authorization: X-API-Key: hunter2xyz")
        SensitiveDataFilter().filter(record)
        assert record.getMessage() == "Authorization: X-API-Key: ***"

    def test_dict_args_masked(self) -> None:
        record = _record("payload %(api_key)s", ({"api_key": "sk-abcdef1234567890"},))
        SensitiveDataFilter().filter(record)
        assert record.getMessage() == "payload sk-***"


class TestConfigureLoggingWiring:
    def test_configure_logging_attaches_mask_filter(self) -> None:
        handler = logging.StreamHandler()
        configure_logging(level="info", handlers=[handler])
        mask_filters = [f for f in handler.filters if isinstance(f, SensitiveDataFilter)]
        assert len(mask_filters) == 1
        # 原有 RequestIdFilter 仍在，字段结构不变
        assert any(f.__class__.__name__ == "RequestIdFilter" for f in handler.filters)
