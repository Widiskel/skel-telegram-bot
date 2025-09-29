import asyncio
import json
from dataclasses import dataclass
from typing import AsyncIterator, Dict, Optional, Tuple

import httpx
from loguru import logger
from ulid import ULID


class AgentClientError(RuntimeError):
    """Raised when the agent cannot produce a response."""


@dataclass(slots=True)
class SessionState:
    activity_id: str


def _new_ulid() -> str:
    return str(ULID())


class AgentClient:
    """HTTP client that talks to the Skel Crypto Agent service via SSE."""

    def __init__(
        self,
        base_url: str,
        *,
        processor_id: str,
        timeout: float = 60.0,
    ) -> None:
        self._base_url = base_url.rstrip("/")
        self._processor_id = processor_id
        self._client = httpx.AsyncClient(timeout=timeout)
        self._sessions: Dict[str, SessionState] = {}
        self._lock = asyncio.Lock()

    async def close(self) -> None:
        await self._client.aclose()

    async def send(self, chat_id: str, prompt: str) -> str:
        session = await self._ensure_session(chat_id)
        payload = {
            "query": {
                "id": _new_ulid(),
                "prompt": prompt,
            },
            "session": {
                "processor_id": self._processor_id,
                "activity_id": session.activity_id,
                "request_id": _new_ulid(),
                "interactions": [],
            },
        }

        url = f"{self._base_url}/assist"
        final_chunks: list[str] = []
        error_message: Optional[str] = None

        logger.debug("Posting prompt to {}", url)

        try:
            async with self._client.stream("POST", url, json=payload) as response:
                response.raise_for_status()
                async for event_name, data in self._iter_events(response):
                    normalized_name = event_name.split(".", 1)[-1].upper()
                    if normalized_name == "FINAL_RESPONSE" and data.get("content_type") == "atomic.textblock":
                        final_chunks.append(data.get("content", ""))
                    elif normalized_name == "ERROR":
                        content = data.get("content")
                        if isinstance(content, dict):
                            error_message = content.get("error_message") or json.dumps(content)
                        else:
                            error_message = str(content)
        except httpx.HTTPError as exc:
            logger.exception("Agent HTTP error: {}", exc)
            raise AgentClientError("Failed to contact the agent.") from exc

        if error_message:
            raise AgentClientError(error_message)

        message = "".join(final_chunks).strip()
        if not message:
            raise AgentClientError("The agent did not send a reply.")
        return message

    async def reset(self, chat_id: str) -> None:
        async with self._lock:
            self._sessions.pop(chat_id, None)

    async def _ensure_session(self, chat_id: str) -> SessionState:
        async with self._lock:
            if chat_id not in self._sessions:
                self._sessions[chat_id] = SessionState(activity_id=_new_ulid())
            return self._sessions[chat_id]

    async def _iter_events(self, response: httpx.Response) -> AsyncIterator[Tuple[str, dict]]:
        event_name: Optional[str] = None
        data_buffer: list[str] = []

        async for raw_line in response.aiter_lines():
            if raw_line == "":
                if event_name and data_buffer:
                    payload = "\n".join(data_buffer)
                    try:
                        data = json.loads(payload)
                    except json.JSONDecodeError as exc:
                        logger.warning("Invalid SSE JSON chunk from agent: {}", exc)
                    else:
                        yield event_name, data
                event_name = None
                data_buffer = []
                continue

            if raw_line.startswith("event:"):
                event_name = raw_line[len("event:"):].strip()
            elif raw_line.startswith("data:"):
                data_buffer.append(raw_line[len("data:"):].strip())

        if event_name and data_buffer:
            payload = "\n".join(data_buffer)
            try:
                data = json.loads(payload)
            except json.JSONDecodeError as exc:
                logger.warning("Invalid SSE JSON chunk from agent: {}", exc)
            else:
                yield event_name, data

