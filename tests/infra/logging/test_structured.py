"""Tests for JSONFormatter structured field merging."""

from __future__ import annotations

import json
import logging

from scaffold.infra.logging.structured import JSONFormatter


def _make_record(extra: dict) -> logging.LogRecord:
    record = logging.LogRecord(
        name="scaffold.test",
        level=logging.WARNING,
        pathname=__file__,
        lineno=1,
        msg="something happened",
        args=(),
        exc_info=None,
    )
    for key, value in extra.items():
        setattr(record, key, value)
    return record


class TestJSONFormatterExtras:
    def test_extra_fields_merged_into_payload(self):
        """extra={...} 注入的结构化字段必须出现在 JSON 输出中。"""
        record = _make_record(
            {
                "event": "model_retry",
                "model": "primary-model",
                "attempt": 2,
                "latency_ms": 123.4,
                "outcome": "failed",
            }
        )
        payload = json.loads(JSONFormatter().format(record))

        assert payload["event"] == "model_retry"
        assert payload["model"] == "primary-model"
        assert payload["attempt"] == 2
        assert payload["latency_ms"] == 123.4
        assert payload["outcome"] == "failed"
        assert payload["message"] == "something happened"
        assert payload["level"] == "WARNING"

    def test_reserved_attrs_not_duplicated(self):
        """标准 LogRecord 属性不应被重复混入 payload。"""
        record = _make_record({"event": "x"})
        payload = json.loads(JSONFormatter().format(record))

        assert "pathname" not in payload
        assert "args" not in payload
        assert "lineno" not in payload
