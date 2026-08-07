from starlette.types import ASGIApp, Message, Receive, Scope, Send

from app.core.logging import get_logger

logger = get_logger("http")

_MAX_BODY = 2000


class AccessLogMiddleware:
    """Ghi log request API ở mức DEBUG: method, path, status, body, response."""

    def __init__(self, app: ASGIApp) -> None:
        self.app = app

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return

        method = scope.get("method", "")
        path = scope.get("path", "")
        request_content_type = next(
            (
                v.decode(errors="replace")
                for k, v in scope.get("headers", [])
                if k == b"content-type"
            ),
            "",
        )

        is_request_json = request_content_type.startswith(("application/json",))

        req_parts: list[bytes] = []
        resp_parts: list[bytes] = []
        status: int | None = None
        is_response_json = False

        async def wrapped_receive() -> Message:
            message = await receive()
            if (
                message["type"] == "http.request"
                and is_request_json
                and message.get("body")
            ):
                req_parts.append(bytes(message["body"]))
            return message

        async def wrapped_send(message: Message) -> None:
            nonlocal status, is_response_json
            if message["type"] == "http.response.start":
                status = message.get("status")
                is_response_json = any(
                    k == b"content-type"
                    and v.decode(errors="replace").startswith(
                        ("application/json", "text/")
                    )
                    for k, v in message.get("headers", [])
                )
            elif message["type"] == "http.response.body" and is_response_json:
                if message.get("body"):
                    resp_parts.append(bytes(message["body"]))
            await send(message)

        try:
            await self.app(scope, wrapped_receive, wrapped_send)
        finally:
            logger.debug(
                "api {} {} status={} req_body={} resp_body={}",
                method,
                path,
                status,
                b"".join(req_parts)[:_MAX_BODY].decode("utf-8", errors="replace"),
                b"".join(resp_parts)[:_MAX_BODY].decode("utf-8", errors="replace"),
            )
