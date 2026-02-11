# extensions/cors_fallback_middleware.py
"""ASGI middleware that adds CORS headers when missing and handles OPTIONS preflight."""

LOCAL_CORS_ORIGINS = frozenset([
    "http://localhost:7001",
    "http://127.0.0.1:7001",
    "http://localhost:5173",
])


def cors_headers(origin: str) -> list[tuple[bytes, bytes]]:
    return [
        (b"access-control-allow-origin", origin.encode()),
        (b"access-control-allow-credentials", b"true"),
        (b"access-control-allow-methods", b"GET, POST, PUT, PATCH, DELETE, OPTIONS"),
        (b"access-control-allow-headers", b"Content-Type, Authorization"),
        (b"access-control-max-age", b"3600"),
    ]


class CORSFallbackMiddleware:
    """ASGI middleware that adds CORS headers when missing and handles OPTIONS preflight."""

    def __init__(self, app, origins=None, **kwargs):
        self.app = app
        self.origins = origins or frozenset()

    async def __call__(self, scope, receive, send):
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return

        origin = None
        for h in scope.get("headers", []):
            if h[0].lower() == b"origin":
                origin = h[1].decode("latin-1")
                break

        # Handle preflight: respond immediately with 200 + CORS headers.
        if scope.get("method") == "OPTIONS" and origin and origin in self.origins:
            await send({
                "type": "http.response.start",
                "status": 200,
                "headers": cors_headers(origin),
            })
            await send({"type": "http.response.body", "body": b"", "more_body": False})
            return

        async def send_with_cors(message):
            if message["type"] == "http.response.start":
                headers = list(message.get("headers", []))
                has_allow_origin = any(k.lower() == b"access-control-allow-origin" for k, _ in headers)
                if not has_allow_origin and origin and origin in self.origins:
                    headers.extend(cors_headers(origin))
                    message = {**message, "headers": headers}
            await send(message)

        try:
            await self.app(scope, receive, send_with_cors)
        except Exception:
            raise
