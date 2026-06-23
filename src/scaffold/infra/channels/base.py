"""Channel abstract base class.

Defines the interface that all IM platform adapters must implement.
"""

from __future__ import annotations

import logging
from abc import ABC, abstractmethod
from typing import Any, Callable

logger = logging.getLogger(__name__)


class Channel(ABC):
    """Abstract base for IM platform channel adapters.

    Each adapter connects an external messaging platform to the
    scaffold's agent runtime.
    """

    def __init__(self, name: str, config: dict[str, Any]) -> None:
        self.name = name
        self.config = config
        self._message_handler: Callable[[str, str, str], Any] | None = None

    @abstractmethod
    async def start(self) -> None:
        """Start the channel (connect, begin polling/webhook)."""

    @abstractmethod
    async def stop(self) -> None:
        """Stop the channel (disconnect, cleanup)."""

    @abstractmethod
    async def send_message(self, user_id: str, text: str, **kwargs: Any) -> None:
        """Send a text message to a user."""

    def on_message(self, handler: Callable[[str, str, str], Any]) -> None:
        """Register a handler for incoming messages.

        Args:
            handler: Callback receiving (user_id, text, thread_id).
        """
        self._message_handler = handler

    async def handle_incoming(
        self,
        user_id: str,
        text: str,
        thread_id: str | None = None,
    ) -> None:
        """Process an incoming message from the platform."""
        if self._message_handler is None:
            logger.warning("No message handler registered for channel '%s'", self.name)
            return
        await self._message_handler(user_id, text, thread_id or "default")
