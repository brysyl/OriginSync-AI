from collections.abc import Awaitable, Callable
from typing import Any

from starlette.responses import JSONResponse

ASGIReceive = Callable[[], Awaitable[dict[str, Any]]]
ASGISend = Callable[[dict[str, Any]], Awaitable[None]]


class PayloadSizeLimitMiddleware:
    def __init__(
        self,
        app: Callable[..., Awaitable[None]],
        max_document_bytes: int,
    ) -> None:
        self.app = app
        self.max_trade_body_bytes = (max_document_bytes * 4 // 3) + 1_000_000
        self.max_webhook_body_bytes = 1_000_000

    async def __call__(
        self,
        scope: dict[str, Any],
        receive: ASGIReceive,
        send: ASGISend,
    ) -> None:
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return

        path = scope.get("path", "")
        if path == "/api/v1/trades":
            limit = self.max_trade_body_bytes
        elif path.startswith("/api/v1/webhooks/"):
            limit = self.max_webhook_body_bytes
        else:
            await self.app(scope, receive, send)
            return

        headers = dict(scope.get("headers", []))
        content_length = headers.get(b"content-length")
        if content_length is not None:
            try:
                if int(content_length) > limit:
                    await self._reject(scope, receive, send)
                    return
            except ValueError:
                pass

        messages: list[dict[str, Any]] = []
        total_bytes = 0
        while True:
            message = await receive()
            messages.append(message)
            if message["type"] == "http.disconnect":
                return
            if message["type"] == "http.request":
                total_bytes += len(message.get("body", b""))
                if total_bytes > limit:
                    await self._reject(scope, receive, send)
                    return
                if not message.get("more_body", False):
                    break

        index = 0

        async def replay_receive() -> dict[str, Any]:
            nonlocal index
            if index < len(messages):
                message = messages[index]
                index += 1
                return message
            return await receive()

        await self.app(scope, replay_receive, send)

    @staticmethod
    async def _reject(
        scope: dict[str, Any],
        receive: ASGIReceive,
        send: ASGISend,
    ) -> None:
        response = JSONResponse(
            status_code=413,
            content={
                "error": {
                    "code": "payload_too_large",
                    "message": "Request body exceeds the configured endpoint size limit.",
                    "details": {},
                }
            },
        )
        await response(scope, receive, send)
