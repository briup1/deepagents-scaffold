"""Input guardrail middleware.

Intercepts the latest user message before the model call, detects dangerous or
policy-violating requests using regex patterns and keywords, and applies a
configurable action: block, warn, or log.

The default moderator is pure regex/keyword (no external API). The ``Moderator``
protocol allows swapping in an external moderation service later without changing
the middleware interface.
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
    """Result of a moderation check."""

    name: str
    value: str
    source: Literal["pattern", "keyword", "external"]


class Moderator(Protocol):
    """Pluggable content moderation backend."""

    def check(self, text: str) -> GuardrailMatch | None:
        """Synchronously check ``text``; return a match or ``None``."""
        ...

    async def acheck(self, text: str) -> GuardrailMatch | None:
        """Asynchronously check ``text``; return a match or ``None``."""
        ...


class RegexModerator:
    """Default lightweight moderator using regex patterns and keywords."""

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
        self._intent_disclaimer_re = re.compile(
            r"\b(for\s+(educational|practice|training|learning|research|academic|personal)\s+"
            r"(purposes?|only|use)|this\s+is\s+(a\s+)?(hypothetical|theoretical|thought\s+experiment|"
            r"test|practice)|just\s+(curious|wondering|asking))\b",
            re.IGNORECASE,
        )

    def _compile_patterns(self, patterns: list[dict[str, str]] | list[str]) -> list[tuple[str, re.Pattern[str]]]:
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
        flags = 0 if self._case_sensitive else re.IGNORECASE
        compiled: list[tuple[str, re.Pattern[str]]] = []
        for kw in keywords:
            escaped = re.escape(kw)
            compiled.append((kw, re.compile(r"\b" + escaped + r"\b", flags)))
        return compiled

    def check(self, text: str) -> GuardrailMatch | None:
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
        return self.check(text)


@dataclass(frozen=True)
class _GuardrailDecision:
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

_DEFAULT_ALLOW_LIST: list[str] = [
    r"\bdefend\b[\s\S]{0,30}\b(against|from)\b",
    r"\bhow\b[\s\S]{0,10}\bdetect\b",
    r"\bsecurity\s+awareness\b",
    r"\bincident\s+response\b",
    r"\bmitigate\b",
]

_DEFAULT_KEYWORDS: list[str] = []


class InputGuardrailMiddleware(AgentMiddleware):
    """Intercept and moderate user input before the model call.

    Args:
        patterns: Regex patterns. Each entry may be a dict with ``name`` and
            ``pattern`` keys, or a plain regex string.
        keywords: Keyword strings matched with word boundaries.
        allow_list: Regex patterns that exempt the input from guardrail checks.
        action: ``block`` (return refusal), ``warn`` (add system warning),
            or ``log`` (audit only).
        message_template: Template for block refusal. May use ``matched_pattern``
            and ``matched_value``.
        warning_template: Template appended to the system message for warn action.
            May use ``matched_pattern`` and ``matched_value``.
        case_sensitive: Whether pattern/keyword matching is case sensitive.
        strip_claimed_intent: Whether to strip "for educational purposes" style
            disclaimers before matching. When ``True``, claimed intent is not
            treated as an exemption.
        log_level: Log level for audit events (``debug``, ``info``, ``warning``,
            ``error``).
        moderator: Optional ``Moderator`` instance. If provided, it replaces the
            default regex/keyword implementation.
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
        return getattr(logging, level.upper(), logging.WARNING)

    def _compile_allow_list(self, patterns: list[str], case_sensitive: bool) -> list[re.Pattern[str]]:
        flags = 0 if case_sensitive else re.IGNORECASE
        return [re.compile(p, flags) for p in patterns if p]

    def _extract_last_user_text(self, messages: list[Any]) -> str | None:
        for msg in reversed(messages):
            if isinstance(msg, HumanMessage):
                return self._extract_text(msg)
        return None

    @staticmethod
    def _extract_text(message: HumanMessage) -> str:
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
        return any(pattern.search(text) for pattern in self._allow_list)

    def _make_decision(self, match: GuardrailMatch, request: ModelRequest[Any]) -> _GuardrailDecision:
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

        # warn
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
        existing = ""
        if system_message is not None:
            existing = str(system_message.content or "")
        new_text = f"{existing}\n\n[SECURITY NOTICE]\n{warning}".strip()
        return SystemMessage(content=new_text)

    def _evaluate_sync(self, request: ModelRequest[Any]) -> _GuardrailDecision | None:
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
        decision = await self._evaluate_async(request)
        if decision is None:
            return await handler(request)
        if decision.response is not None:
            return decision.response
        if decision.request is not None:
            return await handler(decision.request)
        return await handler(request)
