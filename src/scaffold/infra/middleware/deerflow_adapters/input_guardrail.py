"""输入护栏中间件。

在模型调用前拦截最近一条用户消息，通过正则模式与关键词检测危险或违反策略的请求，
并执行可配置动作：block（阻断）、warn（警告）或 log（仅审计）。

默认审核器为纯正则/关键词实现（无外部 API）。``Moderator`` 协议允许后续在不改变中间件
接口的前提下，接入外部内容审核服务。
"""

from __future__ import annotations

import logging
import re
from dataclasses import dataclass
from typing import Any, Callable, Literal, Protocol

from langchain.agents.middleware.types import AgentMiddleware, ModelRequest, ModelResponse
from langchain_core.messages import AIMessage, HumanMessage, SystemMessage

logger = logging.getLogger(__name__)

GuardrailAction = Literal["block", "warn", "log"]


@dataclass(frozen=True)
class GuardrailMatch:
    """审核命中结果。"""

    name: str
    value: str
    source: Literal["pattern", "keyword", "external"]


class Moderator(Protocol):
    """可插拔内容审核后端协议。"""

    def check(self, text: str) -> GuardrailMatch | None:
        """同步检查 ``text``；命中返回 GuardrailMatch，否则返回 ``None``。"""
        ...

    async def acheck(self, text: str) -> GuardrailMatch | None:
        """异步检查 ``text``；命中返回 GuardrailMatch，否则返回 ``None``。"""
        ...


class RegexModerator:
    """基于正则模式与关键词的轻量默认审核器。"""

    def __init__(
        self,
        patterns: list[dict[str, str]] | list[str] | None = None,
        keywords: list[str] | None = None,
        *,
        case_sensitive: bool = False,
        strip_claimed_intent: bool = True,
    ) -> None:
        self._case_sensitive = case_sensitive
        self._strip_claimed_intent = strip_claimed_intent
        self._patterns = self._compile_patterns(patterns or [])
        self._keywords = self._compile_keywords(keywords or [])
        # 匹配常见的「声称意图」免责声明，例如 "for educational purposes"、"just curious" 等。
        # 这些话术不应成为危险请求的豁免理由。
        self._intent_disclaimer_re = re.compile(
            r"\b(for\s+(educational|practice|training|learning|research|academic|personal)\s+"
            r"(purposes?|only|use)|this\s+is\s+(a\s+)?(hypothetical|theoretical|thought\s+experiment|"
            r"test|practice)|just\s+(curious|wondering|asking))\b",
            re.IGNORECASE,
        )

    def _compile_patterns(
        self, patterns: list[dict[str, str]] | list[str]
    ) -> list[tuple[str, re.Pattern[str]]]:
        """编译正则模式列表；支持字典（含 name/pattern）或纯字符串形式。"""
        flags = 0 if self._case_sensitive else re.IGNORECASE
        compiled: list[tuple[str, re.Pattern[str]]] = []
        for item in patterns:
            if isinstance(item, dict):
                name = item.get("name") or f"pattern_{len(compiled)}"
                pattern = item.get("pattern", "")
            else:
                name = f"pattern_{len(compiled)}"
                pattern = item
            if not pattern:
                continue
            compiled.append((name, re.compile(pattern, flags)))
        return compiled

    def _compile_keywords(self, keywords: list[str]) -> list[tuple[str, re.Pattern[str]]]:
        """编译关键词列表，使用单词边界减少误报。"""
        flags = 0 if self._case_sensitive else re.IGNORECASE
        compiled: list[tuple[str, re.Pattern[str]]] = []
        for kw in keywords:
            escaped = re.escape(kw)
            compiled.append((kw, re.compile(r"\b" + escaped + r"\b", flags)))
        return compiled

    def check(self, text: str) -> GuardrailMatch | None:
        """同步审核文本，先剥离声称意图，再按 patterns、keywords 顺序匹配。"""
        normalized = text
        if self._strip_claimed_intent:
            normalized = self._intent_disclaimer_re.sub("", text)

        for name, pattern in self._patterns:
            match = pattern.search(normalized)
            if match:
                return GuardrailMatch(name=name, value=match.group(0), source="pattern")

        for name, pattern in self._keywords:
            match = pattern.search(normalized)
            if match:
                return GuardrailMatch(name=name, value=match.group(0), source="keyword")

        return None

    async def acheck(self, text: str) -> GuardrailMatch | None:
        """异步审核入口；默认委托给同步 check。"""
        return self.check(text)


@dataclass(frozen=True)
class _GuardrailDecision:
    """护栏内部决策结果。"""

    request: ModelRequest[Any] | None = None
    response: AIMessage | None = None
    metadata: dict[str, Any] | None = None


_DEFAULT_BLOCK_TEMPLATE = (
    "I can't help with requests that involve {matched_pattern}. "
    "If you're working on legitimate security research or defense, "
    "please rephrase your request to focus on protective or defensive measures."
)

_DEFAULT_WARNING_TEMPLATE = (
    "The user's last message was flagged for {matched_pattern}. "
    "Decline the request politely and offer to help with a defensive or educational alternative."
)

# 默认危险请求模式：强调「动作 + 对象」组合，降低误报。
_DEFAULT_PATTERNS: list[dict[str, str]] = [
    {
        "name": "malware_creation",
        "pattern": r"\b(create|write|make|build|develop|generate|code)\b[\s\S]{0,50}\b(malware|virus|trojan|worm|ransomware|spyware|keylogger|rootkit)\b",
    },
    {
        "name": "credential_theft",
        "pattern": r"\b(steal|phish|harvest|extract|dump|skim|grab)\b[\s\S]{0,50}\b(password|credential|login|token|api key|secret|cookie|session)\b",
    },
    {
        "name": "social_engineering",
        "pattern": r"\b(write|craft|create|draft|compose)\b[\s\S]{0,50}\b(phishing|spear.phishing|social.engineering|scam|pretexting|bait|hook)\b",
    },
    {
        "name": "exploit_development",
        "pattern": r"\b(write|create|build|develop|generate|code)\b[\s\S]{0,50}\b(exploit|payload|shellcode|reverse.shell|0day|zero.day|buffer.overflow|sql.injection)\b",
    },
    {
        "name": "harmful_instructions",
        "pattern": r"\b(how.to|steps.to|guide.for|tutorial.on)\b[\s\S]{0,30}\b(make|build|create)\b[\s\S]{0,30}\b(bomb|weapon|poison|drug|meth|explosive)\b",
    },
]

# 默认放行模式：用于识别防御性/安全研究语境，避免误伤正常请求。
_DEFAULT_ALLOW_LIST: list[str] = [
    r"\bdefend\b[\s\S]{0,30}\b(against|from)\b",
    r"\bhow\b[\s\S]{0,10}\bdetect\b",
    r"\bsecurity\s+awareness\b",
    r"\bincident\s+response\b",
    r"\bmitigate\b",
]

_DEFAULT_KEYWORDS: list[str] = []


class InputGuardrailMiddleware(AgentMiddleware):
    """在模型调用前拦截并审核用户输入。

    Args:
        patterns: 正则模式列表。每项可以是含 ``name`` 与 ``pattern`` 的字典，
            也可以是纯正则字符串。
        keywords: 关键词列表，按单词边界匹配。
        allow_list: 放行规则列表（正则字符串），命中则跳过审核。
        action: 命中后动作：``block``（返回拒绝）、``warn``（追加系统警告）
            或 ``log``（仅审计）。
        message_template: 阻断时使用的拒绝消息模板，可用 ``matched_pattern``、
            ``matched_value`` 占位符。
        warning_template: warn 动作追加到 system_message 的警告模板，可用
            ``matched_pattern``、``matched_value`` 占位符。
        case_sensitive: 是否区分大小写。
        strip_claimed_intent: 是否在匹配前剥离 "for educational purposes" 等
            声称意图免责声明；为 ``True`` 时，声称意图不被视为豁免理由。
        log_level: 审计日志级别（``debug``、``info``、``warning``、``error``）。
        moderator: 可选自定义 ``Moderator`` 实例；提供时替代默认 RegexModerator。
    """

    def __init__(
        self,
        *,
        patterns: list[dict[str, str]] | list[str] | None = None,
        keywords: list[str] | None = None,
        allow_list: list[str] | None = None,
        action: GuardrailAction = "block",
        message_template: str = _DEFAULT_BLOCK_TEMPLATE,
        warning_template: str = _DEFAULT_WARNING_TEMPLATE,
        case_sensitive: bool = False,
        strip_claimed_intent: bool = True,
        log_level: str = "warning",
        moderator: Moderator | None = None,
    ) -> None:
        self.action = action
        self.message_template = message_template
        self.warning_template = warning_template
        self._log_level = self._resolve_log_level(log_level)
        self._allow_list = self._compile_allow_list(allow_list or _DEFAULT_ALLOW_LIST, case_sensitive)
        self._moderator = moderator or RegexModerator(
            patterns=patterns if patterns is not None else _DEFAULT_PATTERNS,
            keywords=keywords if keywords is not None else _DEFAULT_KEYWORDS,
            case_sensitive=case_sensitive,
            strip_claimed_intent=strip_claimed_intent,
        )

    @staticmethod
    def _resolve_log_level(level: str) -> int:
        """将字符串日志级别解析为 logging 常量。"""
        return getattr(logging, level.upper(), logging.WARNING)

    def _compile_allow_list(self, patterns: list[str], case_sensitive: bool) -> list[re.Pattern[str]]:
        """编译放行规则。"""
        flags = 0 if case_sensitive else re.IGNORECASE
        return [re.compile(p, flags) for p in patterns if p]

    def _extract_last_user_text(self, messages: list[Any]) -> str | None:
        """从消息列表中提取最后一条 HumanMessage 的文本内容。"""
        for msg in reversed(messages):
            if isinstance(msg, HumanMessage):
                return self._extract_text(msg)
        return None

    @staticmethod
    def _extract_text(message: HumanMessage) -> str:
        """提取 HumanMessage 的文本内容；支持字符串与列表（多模态）形式。"""
        content = getattr(message, "content", None)
        if content is None:
            return ""
        if isinstance(content, str):
            return content
        if isinstance(content, list):
            texts = []
            for item in content:
                if isinstance(item, dict) and item.get("type") == "text":
                    texts.append(item.get("text", ""))
                elif isinstance(item, str):
                    texts.append(item)
            return " ".join(texts)
        return str(content)

    def _is_allowed(self, text: str) -> bool:
        """判断文本是否命中任意放行规则。"""
        return any(pattern.search(text) for pattern in self._allow_list)

    def _make_decision(self, match: GuardrailMatch, request: ModelRequest[Any]) -> _GuardrailDecision:
        """根据命中结果与配置动作生成决策。"""
        metadata: dict[str, Any] = {
            "input_guardrail": {
                "action": self.action,
                "matched_pattern": match.name,
                "matched_value": match.value,
                "source": match.source,
            }
        }

        logger.log(
            self._log_level,
            "Input guardrail matched — action=%s pattern=%s source=%s",
            self.action,
            match.name,
            match.source,
            extra={"input_guardrail": metadata["input_guardrail"]},
        )

        if self.action == "log":
            return _GuardrailDecision(metadata=metadata)

        if self.action == "block":
            refusal = self.message_template.format(
                matched_pattern=match.name,
                matched_value=match.value,
            )
            return _GuardrailDecision(
                response=AIMessage(content=refusal, additional_kwargs=metadata),
                metadata=metadata,
            )

        # warn：将警告追加到 system_message，不改变用户可见消息。
        warning = self.warning_template.format(
            matched_pattern=match.name,
            matched_value=match.value,
        )
        new_system = self._append_warning(request.system_message, warning)
        return _GuardrailDecision(
            request=request.override(system_message=new_system),
            metadata=metadata,
        )

    @staticmethod
    def _append_warning(system_message: SystemMessage | None, warning: str) -> SystemMessage:
        """将警告追加到现有 system_message；没有时创建新的。"""
        existing = ""
        if system_message is not None:
            existing = str(system_message.content or "")
        new_text = f"{existing}\n\n[SECURITY NOTICE]\n{warning}".strip()
        return SystemMessage(content=new_text)

    def _evaluate_sync(self, request: ModelRequest[Any]) -> _GuardrailDecision | None:
        """同步评估请求：提取文本 → 放行检查 → 审核 → 生成决策。"""
        text = self._extract_last_user_text(request.messages)
        if not text:
            return None
        if self._is_allowed(text):
            return None
        match = self._moderator.check(text)
        if match is None:
            return None
        return self._make_decision(match, request)

    async def _evaluate_async(self, request: ModelRequest[Any]) -> _GuardrailDecision | None:
        """异步评估请求；当 moderator 提供 acheck 时优先使用。"""
        text = self._extract_last_user_text(request.messages)
        if not text:
            return None
        if self._is_allowed(text):
            return None
        if hasattr(self._moderator, "acheck"):
            match = await self._moderator.acheck(text)
        else:
            match = self._moderator.check(text)
        if match is None:
            return None
        return self._make_decision(match, request)

    def wrap_model_call(
        self,
        request: ModelRequest[Any],
        handler: Callable[[ModelRequest[Any]], ModelResponse[Any]],
    ) -> ModelResponse[Any] | AIMessage:
        """同步拦截模型调用：命中 block 直接返回拒绝；warn 修改请求后调用 handler；
        log 与未命中均透传。
        """
        decision = self._evaluate_sync(request)
        if decision is None:
            return handler(request)
        if decision.response is not None:
            return decision.response
        if decision.request is not None:
            return handler(decision.request)
        return handler(request)

    async def awrap_model_call(
        self,
        request: ModelRequest[Any],
        handler: Callable[[ModelRequest[Any]], Any],
    ) -> ModelResponse[Any] | AIMessage:
        """异步拦截模型调用；逻辑与同步 wrap_model_call 一致。"""
        decision = await self._evaluate_async(request)
        if decision is None:
            return await handler(request)
        if decision.response is not None:
            return decision.response
        if decision.request is not None:
            return await handler(decision.request)
        return await handler(request)
